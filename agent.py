"""Independent drone actors — no oracle floorplan graph imports."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import zlib

import numpy as np

from .environment import CellReading, Environment
from .perception import VisualDetection
from .radio import MsgKind, Packet


def _node_key(r: int, c: int) -> str:
    return f"{r},{c}"


@dataclass(frozen=True)
class StepIntent:
    """Movement target for one tick (kernel resolves collisions)."""

    target_rc: tuple[int, int]


class DroneAgent:
    """
    Explores via frontier BFS on the known-free grid (toward vision/belief waypoint), greedy fog steps at the edge,
    then a light scoring fallback — plus belief-region cues and optional TOKEN gossip.

    Topology uses anonymous grid/region keys — not oracle room IDs.
    """

    def __init__(
        self,
        uid: int,
        start_rc: tuple[int, int],
        *,
        perception_radius: int = 5,
        beacon_interval: int = 4,
        merge_interval: int = 10,
        token_interval: int = 17,
        vision_radius: int | None = None,
        visit_history_len: int = 48,
        fleet_n: int = 1,
    ) -> None:
        self.uid = uid
        self.start_r = int(start_rc[0])
        self.start_c = int(start_rc[1])
        self.r, self.c = self.start_r, self.start_c
        self.perception_radius = perception_radius
        self.vision_radius = vision_radius if vision_radius is not None else max(perception_radius + 6, 12)
        self.beacon_interval = beacon_interval
        self.merge_interval = merge_interval
        self.token_interval = token_interval
        self.fleet_n = max(1, int(fleet_n))

        self.known_wall: set[tuple[int, int]] = set()
        self.known_free: set[tuple[int, int]] = set()

        self.inbox: list[tuple[Packet, float]] = []

        self.neighbors_last: dict[int, tuple[int, int, int]] = {}

        self.topo_nodes: set[str] = set()
        self.topo_edges: set[frozenset[str]] = set()

        self.recent_detections: list[VisualDetection] = []
        self.portal_anchor_cells: set[tuple[int, int]] = set()
        self.portal_sig_at: dict[tuple[int, int], str] = {}

        self.belief_edges: set[tuple[str, str, str]] = set()

        self.claims: dict[str, tuple[int, int]] = {}
        self._visit_hist: deque[tuple[int, int]] = deque(maxlen=visit_history_len)

        self.cell_to_region: dict[tuple[int, int], str] = {}
        self.region_bfs_dist: dict[str, int] = {}
        self._visited_regions: set[str] = set()

        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def absorb_readings(self, readings: list[CellReading]) -> None:
        """Integrate sensed cells into local fog + inferred corridor graph."""
        for cd in readings:
            if cd.is_wall:
                self.known_wall.add((cd.r, cd.c))
            else:
                self.known_free.add((cd.r, cd.c))
                self.topo_nodes.add(_node_key(cd.r, cd.c))

        for (r, c) in list(self.known_free):
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if (nr, nc) in self.known_free:
                    self.topo_edges.add(frozenset({_node_key(r, c), _node_key(nr, nc)}))

    def observe_visual(self, detections: list[VisualDetection]) -> None:
        """Fuse camera-like doorway hypotheses (already sensor-bounded by kernel)."""
        self.recent_detections = list(detections)
        for d in detections:
            if d.confidence < 0.35:
                continue
            p = (d.anchor_r, d.anchor_c)
            self.portal_anchor_cells.add(p)
            self.portal_sig_at[p] = d.signature

    def _is_fog(self, r: int, c: int) -> bool:
        return (r, c) not in self.known_free and (r, c) not in self.known_wall

    def _neighbors4(self, r: int, c: int) -> list[tuple[int, int]]:
        return [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]

    def _refresh_belief_graph(self, tick: int) -> None:
        """Recompute region labels (portal-cut CC), portal edges, and BFS depths from spawn region."""
        self.claims = {s: t for s, t in self.claims.items() if t[1] > tick}

        effective_portals = {p for p in self.portal_anchor_cells if p in self.known_free}
        active = self.known_free - effective_portals

        cell_to_region: dict[tuple[int, int], str] = {}
        visited: set[tuple[int, int]] = set()

        for cell in active:
            if cell in visited:
                continue
            stack = [cell]
            comp: set[tuple[int, int]] = set()
            while stack:
                u = stack.pop()
                if u in visited or u not in active:
                    continue
                visited.add(u)
                comp.add(u)
                ur, uc = u
                for v in self._neighbors4(ur, uc):
                    if v in active and v not in visited:
                        stack.append(v)
            rid = _node_key(*min(comp))
            for u in comp:
                cell_to_region[u] = rid

        self.cell_to_region = cell_to_region

        inferred_edges: set[tuple[str, str, str]] = set()
        for p in effective_portals:
            pr, pc = p
            sig = self.portal_sig_at.get(p, "?")
            regs = {cell_to_region[n] for n in self._neighbors4(pr, pc) if n in cell_to_region}
            regs_list = sorted(regs)
            for i in range(len(regs_list)):
                for j in range(i + 1, len(regs_list)):
                    a, b = regs_list[i], regs_list[j]
                    if a > b:
                        a, b = b, a
                    inferred_edges.add((sig, a, b))

        self.belief_edges.update(inferred_edges)

        adj: dict[str, set[str]] = defaultdict(set)
        for sig, a, b in self.belief_edges:
            adj[a].add(b)
            adj[b].add(a)

        root = cell_to_region.get((self.start_r, self.start_c))
        if root is None:
            root = cell_to_region.get((self.r, self.c))
        if root is None:
            self.region_bfs_dist = {}
            return

        q: deque[str] = deque([root])
        dist: dict[str, int] = {root: 0}
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        self.region_bfs_dist = dist

    def _anchor_for_signature(self, sig: str) -> tuple[int, int] | None:
        for p, s in self.portal_sig_at.items():
            if s == sig:
                return p
        return None

    def _detection_for_signature(self, sig: str) -> VisualDetection | None:
        for d in self.recent_detections:
            if d.signature == sig:
                return d
        return None

    def _waypoint_detection(self, *, min_conf: float = 0.35) -> VisualDetection | None:
        """Pick a doorway hypothesis to steer toward — prefer nearest anchor, not loudest YOLO hit."""
        cands = [d for d in self.recent_detections if d.confidence >= min_conf]
        if not cands:
            return None
        return min(
            cands,
            key=lambda d: (
                abs(d.anchor_r - self.r) + abs(d.anchor_c - self.c),
                -float(d.confidence),
                d.anchor_r,
                d.anchor_c,
                str(d.signature),
            ),
        )

    def _focus_expansion_portal(self, cur_reg: str | None) -> tuple[str | None, tuple[int, int] | None, tuple[int, int]]:
        """Choose next portal using belief BFS when edges split regions; else nearest vision waypoint."""
        rd = self.region_bfs_dist
        if not rd:
            d = self._waypoint_detection()
            if d is not None:
                return d.signature, (d.anchor_r, d.anchor_c), (d.corridor_dr, d.corridor_dc)
            return None, None, (0, 0)

        reg = cur_reg if cur_reg is not None else self.cell_to_region.get((self.r, self.c))
        if reg is None:
            d = self._waypoint_detection()
            if d is not None:
                return d.signature, (d.anchor_r, d.anchor_c), (d.corridor_dr, d.corridor_dc)
            return None, None, (0, 0)

        myd = rd.get(reg)
        if myd is None:
            d = self._waypoint_detection()
            if d is not None:
                return d.signature, (d.anchor_r, d.anchor_c), (d.corridor_dr, d.corridor_dc)
            return None, None, (0, 0)

        best: tuple[int, str] | None = None
        for sig, a, b in self.belief_edges:
            if reg not in (a, b):
                continue
            other = b if a == reg else a
            od = rd.get(other, 999)
            if od > myd:
                cand = (od, sig)
                if best is None or cand < best:
                    best = cand

        if best is None:
            d = self._waypoint_detection()
            if d is not None:
                return d.signature, (d.anchor_r, d.anchor_c), (d.corridor_dr, d.corridor_dc)
            return None, None, (0, 0)

        sig = best[1]
        anchor = self._anchor_for_signature(sig)
        det = self._detection_for_signature(sig)
        if det is not None:
            cr = (det.corridor_dr, det.corridor_dc)
        else:
            cr = (0, 1)
        return sig, anchor, cr

    def _frontier_cell_set(self) -> set[tuple[int, int]]:
        """Known floor cells with at least one unexplored (fog) 4-neighbor."""
        out: set[tuple[int, int]] = set()
        for (r, c) in self.known_free:
            for vr, vc in self._neighbors4(r, c):
                if self._is_fog(vr, vc):
                    out.add((r, c))
                    break
        return out

    def _bfs_first_step_toward_goals(
        self,
        goal_cells: set[tuple[int, int]],
        waypoint: tuple[int, int] | None,
    ) -> tuple[int, int] | None:
        """Shortest path on ``known_free`` to any goal; tie-break toward ``waypoint`` Manhattan."""
        start = (self.r, self.c)
        if not goal_cells or start not in self.known_free:
            return None

        layer = [start]
        parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        seen: set[tuple[int, int]] = {start}

        def tie_key(u: tuple[int, int]) -> tuple[int, int, int]:
            if waypoint is None:
                return (0, u[0], u[1])
            wr, wc = waypoint
            return (abs(u[0] - wr) + abs(u[1] - wc), u[0], u[1])

        while layer:
            hits = [u for u in layer if u in goal_cells and u != start]
            if hits:
                pick = min(hits, key=tie_key)
                cur = pick
                while parent[cur] is not None and parent[cur] != start:
                    cur = parent[cur]
                return cur
            next_layer: list[tuple[int, int]] = []
            for u in layer:
                ur, uc = u
                for v in self._neighbors4(ur, uc):
                    if v not in self.known_free or v in seen:
                        continue
                    seen.add(v)
                    parent[v] = u
                    next_layer.append(v)
            layer = next_layer
        return None

    def _greedy_fog_step_toward(
        self, env: Environment, waypoint: tuple[int, int] | None
    ) -> tuple[int, int] | None:
        """When already beside fog, step into unknown roughly toward ``waypoint``."""
        if waypoint is None:
            return None
        wr, wc = waypoint
        d0 = abs(self.r - wr) + abs(self.c - wc)
        legal = env.legal_steps(self.r, self.c)
        fog_steps = [p for p in legal if p not in self.known_free]
        if not fog_steps:
            return None
        improving = [p for p in fog_steps if abs(p[0] - wr) + abs(p[1] - wc) < d0]
        pool = improving if improving else fog_steps
        return min(pool, key=lambda p: (abs(p[0] - wr) + abs(p[1] - wc), p[0], p[1]))

    def _portal_scout_uid(self, sig: str, anchor: tuple[int, int]) -> int:
        """Deterministic single scout per portal — same inputs ⇒ same uid cluster-wide (fleet roster size only)."""
        h = zlib.adler32(f"{sig}:{anchor[0]}:{anchor[1]}".encode())
        return int(h % self.fleet_n)

    def drain_inbox(self, tick: int) -> None:
        """Apply gossip merges from received packets."""
        for pkt, _rssi in self.inbox:
            if pkt.kind == MsgKind.BEACON:
                rr = pkt.payload.get("r")
                cc = pkt.payload.get("c")
                if rr is not None and cc is not None:
                    self.neighbors_last[pkt.sender_uid] = (int(rr), int(cc), tick)
                self._on_beacon_received(pkt.sender_uid, pkt.payload, tick)

            elif pkt.kind == MsgKind.TOPOLOGY_MERGE:
                nodes = pkt.payload.get("nodes") or []
                edges = pkt.payload.get("edges") or []
                for n in nodes:
                    if isinstance(n, str):
                        self.topo_nodes.add(n)
                for e in edges:
                    if isinstance(e, (list, tuple)) and len(e) == 2:
                        a, b = str(e[0]), str(e[1])
                        self.topo_edges.add(frozenset({a, b}))
                for triple in pkt.payload.get("belief_edges") or []:
                    if isinstance(triple, (list, tuple)) and len(triple) == 3:
                        sig, a, b = str(triple[0]), str(triple[1]), str(triple[2])
                        if a > b:
                            a, b = b, a
                        self.belief_edges.add((sig, a, b))

            elif pkt.kind == MsgKind.TOKEN:
                sig = pkt.payload.get("signature")
                ttl = int(pkt.payload.get("ttl_ticks", 28))
                if isinstance(sig, str) and sig:
                    self.claims[sig] = (pkt.sender_uid, tick + ttl)

        self.inbox.clear()

    def _beacon_payload_extras(self, _tick: int) -> dict[str, object]:
        return {}

    def _on_beacon_received(self, _sender_uid: int, _payload: dict[str, object], _tick: int) -> None:
        pass

    def _reserved_corridor_toward_anchor(
        self,
        nr: int,
        nc: int,
        *,
        focus_anchor: tuple[int, int] | None,
        cdr: int,
        cdc: int,
    ) -> bool:
        """Corridor-axis step that strictly closes distance to the vision portal anchor (choke queue)."""
        if focus_anchor is None:
            return False
        if (nr, nc) == (self.r, self.c):
            return False
        ar, ac = focus_anchor
        if cdr == 0 and cdc == 0:
            return False
        mdr, mdc = nr - self.r, nc - self.c
        if (mdr, mdc) not in ((cdr, cdc), (-cdr, -cdc)):
            return False
        old_d = abs(self.r - ar) + abs(self.c - ac)
        new_d = abs(nr - ar) + abs(nc - ac)
        return new_d < old_d

    def on_receive(self, packet: Packet, rssi_dbm: float) -> None:
        self.inbox.append((packet, rssi_dbm))

    def decide_move(
        self,
        env: Environment,
        rng: np.random.Generator,
        *,
        tick: int = 0,
        portal_cross_allowed: bool = True,
    ) -> StepIntent:
        _ = rng
        self._refresh_belief_graph(tick)
        cur_reg = self.cell_to_region.get((self.r, self.c))
        if cur_reg is not None:
            self._visited_regions.add(cur_reg)

        _, focus_anchor, (cdr, cdc) = self._focus_expansion_portal(cur_reg)
        waypoint = focus_anchor
        if waypoint is None:
            wd = self._waypoint_detection()
            if wd is not None:
                waypoint = (wd.anchor_r, wd.anchor_c)

        legal = env.legal_steps(self.r, self.c)
        if focus_anchor is not None and not portal_cross_allowed:
            legal = [
                p
                for p in legal
                if not self._reserved_corridor_toward_anchor(
                    p[0], p[1], focus_anchor=focus_anchor, cdr=cdr, cdc=cdc
                )
            ]

        frontier = self._frontier_cell_set()
        here = (self.r, self.c)
        if waypoint is not None:
            wr, wc = waypoint
            d_here = abs(self.r - wr) + abs(self.c - wc)
            toward_frontier = {
                g
                for g in frontier
                if g != here and abs(g[0] - wr) + abs(g[1] - wc) < d_here
            }
            if toward_frontier:
                bfs_goals = toward_frontier
            elif here in frontier:
                bfs_goals = set()
            else:
                bfs_goals = frontier - {here}
        else:
            bfs_goals = frontier - {here}

        bfs_step = self._bfs_first_step_toward_goals(bfs_goals, waypoint)
        if bfs_step is not None and bfs_step in legal:
            return StepIntent(bfs_step)

        fog_step = self._greedy_fog_step_toward(env, waypoint)
        if fog_step is not None and fog_step in legal:
            return StepIntent(fog_step)

        choices = list(legal)
        choices.append((self.r, self.c))
        choices = list(dict.fromkeys(choices))

        def score_fallback(nr: int, nc: int) -> float:
            s = 0.0
            if (nr, nc) == (self.r, self.c):
                s -= 4.0
            elif (nr, nc) not in self.known_free:
                s += 36.0
            if waypoint is not None:
                wr, wc = waypoint
                old_d = abs(self.r - wr) + abs(self.c - wc)
                new_d = abs(nr - wr) + abs(nc - wc)
                if new_d < old_d:
                    s += 22.0
                elif new_d > old_d:
                    s -= 18.0
            if (nr, nc) in frontier:
                s += 12.0
            if (nr, nc) in self._visit_hist:
                s -= 3.5
            if self._visit_hist and (nr, nc) == self._visit_hist[-1]:
                s -= 44.0
            return s

        ranked = sorted(
            ((score_fallback(nr, nc), nr, nc) for nr, nc in choices),
            key=lambda t: (-t[0], t[1], t[2]),
        )
        return StepIntent((ranked[0][1], ranked[0][2]))

    def apply_pose(self, r: int, c: int) -> None:
        self._visit_hist.append((self.r, self.c))
        self.r, self.c = int(r), int(c)

    def maybe_transmit(self, tick: int) -> Packet | None:
        """Periodic beacon + TOKEN claims + topology/belief gossip."""
        if tick % self.beacon_interval == 0:
            return Packet(
                kind=MsgKind.BEACON,
                sender_uid=self.uid,
                seq=self._next_seq(),
                payload={
                    "r": self.r,
                    "c": self.c,
                    "tick": tick,
                    **self._beacon_payload_extras(tick),
                },
            )

        if tick % self.token_interval == 0 and tick % self.beacon_interval != 0:
            self._refresh_belief_graph(tick)
            cur = self.cell_to_region.get((self.r, self.c))
            fsig, _, _ = self._focus_expansion_portal(cur)
            if fsig:
                return Packet(
                    kind=MsgKind.TOKEN,
                    sender_uid=self.uid,
                    seq=self._next_seq(),
                    payload={
                        "signature": fsig,
                        "ttl_ticks": 48,
                        "tick": tick,
                    },
                )

        if tick % self.merge_interval == 0 and tick % self.beacon_interval != 0:
            edges_serial = [sorted(list(e)) for e in self.topo_edges]
            belief_serial = [list(t) for t in sorted(self.belief_edges)]
            return Packet(
                kind=MsgKind.TOPOLOGY_MERGE,
                sender_uid=self.uid,
                seq=self._next_seq(),
                payload={
                    "nodes": sorted(self.topo_nodes),
                    "edges": edges_serial,
                    "belief_edges": belief_serial,
                    "tick": tick,
                },
            )

        return None
