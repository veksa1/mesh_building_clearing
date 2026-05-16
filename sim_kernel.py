"""Discrete-time decentralized swarm kernel — truth env + RF plane + independent actors."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

import numpy as np

from .agent import DroneAgent
from .building import BuildingMap
from .environment import Environment
from .layout_bfs_agent import LayoutBFSDrone
from .navigation import grid_shortest_path
from .radio import CommEvent, Packet, RadioConfig, RadioMedium
from .viz_comms import DEFAULT_OVERLAY_TTL, CommsOverlay, FadedLink


@dataclass
class DecentralizedFrame:
    """One animation frame for decentralized mode."""

    drones_rc: list[tuple[float, float]]
    caption: str
    layout_name: str
    belief_panel: str
    phase_line: str
    discovered_line: str
    rf_log_tail: list[str] = field(default_factory=list)
    comm_links: list[FadedLink] = field(default_factory=list)
    #: BFS spanning tree on fused grid graph (drone 0, spawn-rooted) for map overlay.
    tree_segments_rc: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)
    #: Rooms merged as discovered (layout-oracle mode) — drives side-panel graph coloring.
    rooms_discovered_sorted: tuple[int, ...] = ()
    #: Entrance-rooted spanning-tree edges (same as centralized ``bfs_plan`` order).
    room_spanning_edges: tuple[tuple[int, int], ...] = ()
    #: Rolling gossip adoption / originate lines for Telemetry HUD tail.
    mesh_activity_tail: list[str] = field(default_factory=list)


def _room_spanning_tree_segments(
    building: BuildingMap, edges: list[tuple[int, int]]
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Grid polylines for each room-tree edge (anchors[u]→anchors[v]), as segment pairs."""
    wall = building.wall
    anchors = building.anchors
    out: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for u, v in edges:
        path = grid_shortest_path(wall, anchors[u], anchors[v])
        for i in range(len(path) - 1):
            out.append((path[i], path[i + 1]))
    return out


def _exploration_bfs_tree_segments(agent: DroneAgent) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Shortest-hop spanning tree over locally fused floor cells (deterministic child order)."""
    root_k = f"{agent.start_r},{agent.start_c}"
    if root_k not in agent.topo_nodes:
        return []
    adj: dict[str, list[str]] = defaultdict(list)
    for e in agent.topo_edges:
        if len(e) != 2:
            continue
        a, b = sorted(e)
        adj[a].append(b)
        adj[b].append(a)
    for k in adj:
        adj[k].sort()

    parent: dict[str, str | None] = {root_k: None}
    depth: dict[str, int] = {root_k: 0}
    q: deque[str] = deque([root_k])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in parent:
                parent[v] = u
                depth[v] = depth[u] + 1
                q.append(v)

    out: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for v, pu in parent.items():
        if pu is None:
            continue
        r1, c1 = map(int, pu.split(",", 1))
        r2, c2 = map(int, v.split(",", 1))
        out.append(((r1, c1), (r2, c2)))

    seen_seg: set[frozenset[tuple[int, int]]] = {frozenset(p) for p in out}
    for pr, pc in sorted(agent.portal_anchor_cells):
        if (pr, pc) not in agent.known_free:
            continue
        pk = f"{pr},{pc}"
        if pk not in agent.topo_nodes:
            continue
        best_k: str | None = None
        best_d = 10**9
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nk = f"{pr + dr},{pc + dc}"
            if nk in depth and depth[nk] < best_d:
                best_d = depth[nk]
                best_k = nk
        if best_k is None:
            continue
        br, bc = map(int, best_k.split(",", 1))
        edge = frozenset({(br, bc), (pr, pc)})
        if edge in seen_seg:
            continue
        seen_seg.add(edge)
        out.append(((br, bc), (pr, pc)))

    return out


def _unique_staging_cells(building: BuildingMap, stage_path: list[tuple[int, int]], need: int) -> list[tuple[int, int]]:
    """Enough distinct lobby cells for ``need`` drones — short anchor→door paths cannot hold many floats."""
    wall = building.wall
    rid = building.room_id
    root = int(building.entrance_room)
    h, wdim = wall.shape
    ar, ac = building.anchors[root]

    def walk_floor(r: int, c: int) -> bool:
        return 0 <= r < h and 0 <= c < wdim and not wall[r, c]

    cells: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    for r, c in stage_path:
        if not walk_floor(r, c):
            continue
        if int(rid[r, c]) != root:
            continue
        if (r, c) in seen:
            continue
        seen.add((r, c))
        cells.append((r, c))

    q: deque[tuple[int, int]] = deque(cells)
    while len(cells) < need and q:
        r, c = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if not walk_floor(nr, nc):
                continue
            if int(rid[nr, nc]) != root:
                continue
            if (nr, nc) in seen:
                continue
            seen.add((nr, nc))
            cells.append((nr, nc))
            q.append((nr, nc))

    q = deque(cells)
    while len(cells) < need and q:
        r, c = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if not walk_floor(nr, nc):
                continue
            if (nr, nc) in seen:
                continue
            seen.add((nr, nc))
            cells.append((nr, nc))
            q.append((nr, nc))

    while len(cells) < need:
        cells.append((ar, ac))

    return cells


def _spawn_positions(building: BuildingMap, n: int) -> list[tuple[int, int]]:
    """Kernel-only staging: distinct grid cells near entrance→door corridor (no co-spawns)."""
    if n <= 0:
        return []
    root = building.entrance_room
    wall = building.wall
    stage_path = grid_shortest_path(wall, building.anchors[root], building.door_lobby_rc)
    ar, ac = building.anchors[root]
    if not stage_path:
        return [(ar, ac)] * n

    cells = _unique_staging_cells(building, stage_path, n)
    lc = len(cells)
    if lc == 0:
        return [(ar, ac)] * n

    if n == 1:
        picks = [cells[min(lc - 1, max(lc // 2, 0))]]
    else:
        picks = [cells[(i * (lc - 1)) // (n - 1)] for i in range(n)]

    # UID 0 toward doorway end (matches legacy ``sample_polyline`` + reverse convention).
    if len(picks) >= 2:
        picks.reverse()
    return picks


def _follower_mesh_intent(
    follower: DroneAgent,
    explorer: DroneAgent,
    env: Environment,
    rng: np.random.Generator,
    *,
    d_lo: int = 2,
    d_hi: int = 8,
) -> tuple[int, int]:
    """Hold station behind the explorer; inch only to keep a crude RF-friendly spacing band."""
    er, ec = explorer.r, explorer.c

    def md(r: int, c: int) -> int:
        return abs(r - er) + abs(c - ec)

    dist = md(follower.r, follower.c)
    legal = env.legal_steps(follower.r, follower.c)
    if not legal:
        return (follower.r, follower.c)

    if dist > d_hi:
        return min(legal, key=lambda p: md(p[0], p[1]))
    if dist < d_lo:
        farther = [p for p in legal if md(p[0], p[1]) > dist]
        if farther:
            return max(farther, key=lambda p: md(p[0], p[1]))
        return (follower.r, follower.c)
    if rng.random() < 0.93:
        return (follower.r, follower.c)
    return legal[int(rng.integers(0, len(legal)))]


def follower_mesh_intent_from_explorer_rc(
    follower: DroneAgent,
    explorer_rc: tuple[int, int],
    env: Environment,
    rng: np.random.Generator,
    *,
    d_lo: int = 2,
    d_hi: int = 8,
) -> tuple[int, int]:
    """Same as :func:`_follower_mesh_intent` but explorer position supplied explicitly (distributed workers)."""
    er, ec = explorer_rc

    def md(r: int, c: int) -> int:
        return abs(r - er) + abs(c - ec)

    dist = md(follower.r, follower.c)
    legal = env.legal_steps(follower.r, follower.c)
    if not legal:
        return (follower.r, follower.c)

    if dist > d_hi:
        return min(legal, key=lambda p: md(p[0], p[1]))
    if dist < d_lo:
        farther = [p for p in legal if md(p[0], p[1]) > dist]
        if farther:
            return max(farther, key=lambda p: md(p[0], p[1]))
        return (follower.r, follower.c)
    if rng.random() < 0.93:
        return (follower.r, follower.c)
    return legal[int(rng.integers(0, len(legal)))]


class PoseResolveShell:
    """Duck-compatible with :class:`DroneAgent` for move resolution (``.uid``, ``.r``, ``.c``, ``apply_pose``)."""

    __slots__ = ("uid", "r", "c")

    def __init__(self, uid: int, r: int, c: int) -> None:
        self.uid = int(uid)
        self.r = int(r)
        self.c = int(c)

    def apply_pose(self, r: int, c: int) -> None:
        self.r, self.c = int(r), int(c)


def _layout_relieve_scout_head(
    agents: list[DroneAgent],
    intents: dict[int, tuple[int, int]],
    env: Environment,
    scout_uid: int,
) -> None:
    """If another drone occupies the scout's intended tile, retarget it to step sideways first.

    Centralized playback avoids discrete collisions via floating placements along polylines; on the grid,
    relays often park where the scout's shortest-path advance would land unless someone yields first.
    """
    for _ in range(max(len(agents), 4)):
        scout = next((a for a in agents if a.uid == scout_uid), None)
        if scout is None:
            return
        ts = intents.get(scout_uid)
        if ts is None or ts == (scout.r, scout.c):
            return
        blocker = next((a for a in agents if (a.r, a.c) == ts and a.uid != scout_uid), None)
        if blocker is None:
            return
        legal = env.legal_steps(blocker.r, blocker.c)
        occupied_other = {(a.r, a.c) for a in agents if a.uid != blocker.uid}
        candidates = [p for p in legal if p != ts and p not in occupied_other]
        if not candidates:
            candidates = [p for p in legal if p != ts]
        if not candidates:
            return
        intents[blocker.uid] = max(
            candidates,
            key=lambda p: abs(p[0] - scout.r) + abs(p[1] - scout.c),
        )


def resolve_moves_sequential(
    agents: list[DroneAgent],
    intents: dict[int, tuple[int, int]],
    *,
    rng: np.random.Generator | None = None,
    priority_uid: int | None = None,
    defer_uid: int | None = None,
) -> None:
    """Resolve movement intents with pairwise swaps first, then greedy occupancy checks.

    When ``A`` intends ``B``'s cell and ``B`` intends ``A``'s, we swap immediately.
    Remaining drones apply one-at-a-time. Optional ``rng`` shuffles non-priority agents.
    ``priority_uid`` (when set) moves first in the sequential pass so the explorer is not boxed out.
    ``defer_uid`` (when set and ``priority_uid`` is None) resolves that agent **last** so others can
    yield corridor tiles first — used by layout-oracle scouts blocked by stationary relays.
    """
    before_pos = {a.uid: (a.r, a.c) for a in agents}
    uid_agent = {a.uid: a for a in agents}
    owner_before = {before_pos[u]: u for u in before_pos}

    swapped_uids: set[int] = set()
    pair_order = sorted(uid_agent.keys())
    if rng is not None:
        rng.shuffle(pair_order)

    for ua in pair_order:
        if ua in swapped_uids:
            continue
        ta = intents[ua]
        ba = before_pos[ua]
        if ta == ba:
            continue
        vb = owner_before.get(ta)
        if vb is None or vb == ua or vb in swapped_uids:
            continue
        tb = intents[vb]
        bb = before_pos[vb]
        if tb == bb:
            continue
        if ta == bb and tb == ba:
            a = uid_agent[ua]
            b = uid_agent[vb]
            ar, ac = ta
            br, bc = tb
            a.apply_pose(ar, ac)
            b.apply_pose(br, bc)
            swapped_uids.add(ua)
            swapped_uids.add(vb)

    occupied: Counter[tuple[int, int]] = Counter((a.r, a.c) for a in agents)
    order = list(agents)
    if priority_uid is not None:
        pri = next((x for x in order if x.uid == priority_uid), None)
        if pri is not None:
            order.remove(pri)
            rest = order
            order = [pri]
            if rng is not None:
                rng.shuffle(rest)
                order.extend(rest)
            else:
                rest.sort(key=lambda x: x.uid)
                order.extend(rest)
    elif defer_uid is not None:
        defer_ag = next((x for x in order if x.uid == defer_uid), None)
        if defer_ag is not None:
            order.remove(defer_ag)
            rest = order
            if rng is not None:
                rng.shuffle(rest)
            else:
                rest.sort(key=lambda x: x.uid)
            order = rest + [defer_ag]
    elif rng is not None:
        rng.shuffle(order)
    else:
        order.sort(key=lambda x: x.uid)
    for a in order:
        tr, tc = intents[a.uid]
        cur = (a.r, a.c)
        target = (tr, tc)
        if target == cur:
            continue
        if occupied[target] > 0:
            continue
        occupied[cur] -= 1
        if occupied[cur] <= 0:
            del occupied[cur]
        occupied[target] += 1
        a.apply_pose(tr, tc)


def run_decentralized(
    building: BuildingMap,
    *,
    layout_name: str,
    n_drones: int,
    n_ticks: int,
    radio_cfg: RadioConfig | None,
    rng: np.random.Generator | None,
    rf_log_cap: int,
    seed: int,
    perception_radius: int = 5,
    beacon_interval: int = 4,
    merge_interval: int = 10,
    explorer_phase_ticks: int | None = None,
    decentralized_policy: str = "layout_bfs",
    mesh_activity_tail_cap: int = 36,
) -> tuple[list[DecentralizedFrame], list[CommEvent]]:
    if decentralized_policy not in ("layout_bfs", "local_sense"):
        raise ValueError(f"unknown decentralized_policy: {decentralized_policy!r}")
    use_layout = decentralized_policy == "layout_bfs"

    rng = rng if rng is not None else np.random.default_rng(seed)
    env = Environment(building)
    radio = RadioMedium(building.wall, radio_cfg)
    spawns = _spawn_positions(building, n_drones)

    hud_mesh_cap = max(0, int(mesh_activity_tail_cap))
    mesh_buf: deque[str] = deque(maxlen=max(512, hud_mesh_cap * 16))

    def mesh_sink(line: str) -> None:
        mesh_buf.append(line)

    if use_layout:
        agents: list[DroneAgent] = [
            LayoutBFSDrone(
                uid=i,
                start_rc=spawns[i],
                building=building,
                perception_radius=perception_radius,
                beacon_interval=beacon_interval,
                merge_interval=merge_interval,
                fleet_n=max(1, len(spawns)),
                mesh_activity_sink=mesh_sink,
            )
            for i in range(len(spawns))
        ]
        room_tree_segments = _room_spanning_tree_segments(building, list(agents[0].room_tree_edges)) if agents else []
        phase_len = 1
    else:
        agents = [
            DroneAgent(
                uid=i,
                start_rc=spawns[i],
                perception_radius=perception_radius,
                beacon_interval=beacon_interval,
                merge_interval=merge_interval,
                fleet_n=max(1, len(spawns)),
                mesh_activity_sink=mesh_sink,
            )
            for i in range(len(spawns))
        ]
        room_tree_segments = []
        if explorer_phase_ticks is None:
            phase_len = max(55, min(n_ticks // max(len(agents) * 3, 1), 180))
        else:
            phase_len = max(1, int(explorer_phase_ticks))

    n_agents = len(agents)
    overlay = CommsOverlay(ttl_ticks=DEFAULT_OVERLAY_TTL)
    log_buf: deque[str] = deque(maxlen=max(8, rf_log_cap))
    all_events: list[CommEvent] = []

    frames: list[DecentralizedFrame] = []
    pending_rx: list[tuple[int, Packet, float]] = []

    for tick in range(n_ticks):
        for a in agents:
            a.drain_inbox(tick)

        explorer_uid = int((tick // phase_len) % max(n_agents, 1))
        explorer = next((a for a in agents if a.uid == explorer_uid), None)
        lead = explorer if explorer is not None else (min(agents, key=lambda a: a.uid) if agents else None)

        intents: dict[int, tuple[int, int]] = {}
        priority_uid: int | None = None
        defer_uid: int | None = None
        tree_segments: list[tuple[tuple[int, int], tuple[int, int]]] = []

        if use_layout:
            scout_uid = max(0, n_agents - 1)
            defer_uid = scout_uid if n_agents else None
            tree_segments = room_tree_segments
            for a in agents:
                readings = env.sense_disc(a.r, a.c, a.perception_radius)
                a.absorb_readings(readings)
                intents[a.uid] = a.decide_move(env, rng, tick=tick).target_rc
            _layout_relieve_scout_head(agents, intents, env, scout_uid)
        else:
            for a in agents:
                readings = env.sense_disc(a.r, a.c, a.perception_radius)
                a.absorb_readings(readings)
                detections = env.detect_openings(a.r, a.c, radius=a.vision_radius, rng=None)
                a.observe_visual(detections)
                if explorer is not None and a.uid == explorer_uid:
                    intents[a.uid] = a.decide_move(
                        env, rng, tick=tick, portal_cross_allowed=True
                    ).target_rc
                elif explorer is not None:
                    intents[a.uid] = _follower_mesh_intent(a, explorer, env, rng)
                else:
                    intents[a.uid] = a.decide_move(
                        env, rng, tick=tick, portal_cross_allowed=True
                    ).target_rc
            priority_uid = explorer_uid if explorer is not None else None
            tree_segments = _exploration_bfs_tree_segments(lead) if lead is not None else []

        resolve_moves_sequential(
            agents,
            intents,
            rng=rng,
            priority_uid=priority_uid,
            defer_uid=defer_uid,
        )

        tick_events: list[CommEvent] = []
        poses_f = {a.uid: (float(a.r), float(a.c)) for a in agents}

        for a in sorted(agents, key=lambda x: x.uid):
            pkt = a.maybe_transmit(tick)
            if pkt is None:
                continue
            a.emit_mesh_tx_activity(pkt, tick)
            deliveries, evs = radio.broadcast_tick(
                tick,
                a.uid,
                (float(a.r), float(a.c)),
                pkt,
                receiver_poses=poses_f,
            )
            tick_events.extend(evs)
            for rid, p, rssi in deliveries:
                pending_rx.append((rid, p, rssi))

        for rid, p, rssi in pending_rx:
            next(a for a in agents if a.uid == rid).on_receive(p, rssi)
        pending_rx.clear()

        all_events.extend(tick_events)
        for ev in tick_events:
            log_buf.append(ev.format_rf_hud_line())
        overlay.ingest_tick(tick_events)

        total_nodes = max(len(a.topo_nodes) for a in agents) if agents else 0
        total_edges = max(len(a.topo_edges) for a in agents) if agents else 0
        belief_edges_n = max(len(a.belief_edges) for a in agents) if agents else 0
        vision_hits = sum(len(a.recent_detections) for a in agents)
        tree_n = len(tree_segments)

        span_edges_t: tuple[tuple[int, int], ...] = ()
        rooms_disc_t: tuple[int, ...] = ()
        if use_layout:
            union_seen: set[int] = set()
            for la in agents:
                if isinstance(la, LayoutBFSDrone):
                    union_seen |= la._rooms_seen
            rooms_disc_t = tuple(sorted(union_seen))
            if agents and isinstance(agents[0], LayoutBFSDrone):
                span_edges_t = tuple(agents[0].room_tree_edges)
            discovered_line = (
                "Rooms ∪ "
                + ",".join(map(str, sorted(union_seen)))
                + " — spanning-tree expansion order matches centralized planner."
            )
            belief_panel = (
                f"Layout-oracle decentralized (identical room BFS tree per drone)\n"
                f"{'─' * 26}\n\n"
                f"Movement: relays yield lane tiles first; scout UID {scout_uid} resolves last each tick.\n"
                f"(Discrete grid needs this ordering — centralized playback used floats without collision.)\n"
                f"Room-tree grid segments (reference overlay): {tree_n}\n"
                f"Sensed topo nodes (local): {total_nodes}\n"
                f"Vision doorway hits (sum): {vision_hits}\n\n"
                f"Neighbors (last beacon):\n"
                + "\n".join(
                    f"  drone {a.uid}: {sorted(a.neighbors_last.keys())}"
                    for a in sorted(agents, key=lambda x: x.uid)
                )
            )
            caption = (
                "Omniscient layout — same room BFS tree per drone as centralized mode.\n"
                f"Relays hold arc-length slots along the backbone to the parent room; scout (UID {scout_uid}) opens the next edge.\n"
                f"tick={tick}/{max(n_ticks - 1, 1)}. Gray lines: room spanning tree on anchor shortest paths.\n"
            )
        else:
            discovered_line = "Inbox deliveries applied at tick start; TX at tick end."
            belief_panel = (
                f"Decentralized belief (max over swarm)\n"
                f"{'─' * 26}\n\n"
                f"Movement: explorer rotates every {phase_len} ticks (current drone {explorer_uid}); mesh-follow others\n"
                f"Local topo nodes: {total_nodes}\n"
                f"Local topo edges: {total_edges}\n"
                f"BFS tree edges (drone {lead.uid if lead else '-'} overlay): {tree_n}\n"
                f"Belief portal-edges (gossip ∪ local): {belief_edges_n}\n"
                f"Vision detections (this tick, sum): {vision_hits}\n\n"
                f"Neighbors (last beacon):\n"
                + "\n".join(
                    f"  drone {a.uid}: {sorted(a.neighbors_last.keys())}"
                    for a in sorted(agents, key=lambda x: x.uid)
                )
            )
            caption = (
                "Decentralized exploration — agents sense locally and gossip topology.\n"
                f"Explorer rotates every {phase_len} ticks (now drone {explorer_uid}); path on-map uses frontier BFS.\n"
                f"tick={tick}/{max(n_ticks - 1, 1)}. Gray lines: BFS tree on explorer map.\n"
            )

        frames.append(
            DecentralizedFrame(
                drones_rc=[(float(a.r), float(a.c)) for a in sorted(agents, key=lambda x: x.uid)],
                caption=caption,
                layout_name=layout_name,
                belief_panel=belief_panel,
                phase_line=f"Tick {tick} — moves resolved (UID order); mesh TX/RX logged.",
                discovered_line=discovered_line,
                rf_log_tail=list(log_buf),
                comm_links=list(overlay.links),
                tree_segments_rc=tree_segments,
                rooms_discovered_sorted=rooms_disc_t,
                room_spanning_edges=span_edges_t,
                mesh_activity_tail=(
                    list(mesh_buf)[-hud_mesh_cap:] if hud_mesh_cap else []
                ),
            )
        )

    return frames, all_events
