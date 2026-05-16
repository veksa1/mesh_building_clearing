"""Layout-oracle drones: each agent keeps an identical room BFS tree copy and plans locally."""

from __future__ import annotations

import math

from swarm_sim.agent import DroneAgent, StepIntent
from swarm_sim.building import BuildingMap
from swarm_sim.environment import Environment
from swarm_sim.navigation import concat_paths, grid_shortest_path, sample_polyline
from swarm_sim.room_bfs_plan import bfs_plan, rooms_root_to_u

MAX_SEEN_ROOMS_BEACON = 48


class LayoutBFSDrone(DroneAgent):
    """
    Omniscient floorplan (walls + room graph) while remaining an independent actor.

    Mirrors the *centralized* BFS takeover logic:

    - **Relays** (UID ``0 … fleet_n-2``) hold stations sampled along the backbone polyline
      from the entrance toward the **parent** room of the next spanning-tree edge.
    - **Scout** (UID ``fleet_n-1``) alone advances along the grid shortest path toward the
      next unseen child's anchor (same corridor crossing as the scripted demo).

    Visited rooms are merged over beacons so everyone agrees which tree edge is “active.”
    """

    def __init__(
        self,
        uid: int,
        start_rc: tuple[int, int],
        *,
        building: BuildingMap,
        perception_radius: int = 5,
        beacon_interval: int = 4,
        merge_interval: int = 10,
        token_interval: int = 17,
        vision_radius: int | None = None,
        visit_history_len: int = 48,
        fleet_n: int = 1,
    ) -> None:
        super().__init__(
            uid=uid,
            start_rc=start_rc,
            perception_radius=perception_radius,
            beacon_interval=beacon_interval,
            merge_interval=merge_interval,
            token_interval=token_interval,
            vision_radius=vision_radius,
            visit_history_len=visit_history_len,
            fleet_n=fleet_n,
        )
        self._bm = building
        wall = building.wall
        anchors = building.anchors
        self._root = int(building.entrance_room)
        self._room_parent, self._room_edges, _ = bfs_plan(building.adjacency, self._root)
        self._edge_paths: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for u, v in self._room_edges:
            self._edge_paths[(u, v)] = grid_shortest_path(wall, anchors[u], anchors[v])
        self._stage_path = grid_shortest_path(wall, anchors[self._root], building.door_lobby_rc)
        self._rooms_seen: set[int] = {self._root}

    @property
    def room_tree_edges(self) -> tuple[tuple[int, int], ...]:
        return tuple(self._room_edges)

    def _backbone_cells_upto(self, room_id: int) -> list[tuple[int, int]]:
        """Same polyline construction as ``build_timeline.backbone_cells_upto``."""
        chain = rooms_root_to_u(self._room_parent, self._root, room_id)
        if len(chain) == 1:
            return list(self._stage_path)
        parts = [self._edge_paths[(chain[i], chain[i + 1])] for i in range(len(chain) - 1)]
        return concat_paths(parts)

    def _room_at(self, r: int, c: int) -> int | None:
        if bool(self._bm.wall[r, c]):
            return None
        rid = int(self._bm.room_id[r, c])
        return rid if rid >= 0 else None

    def _sync_room_seen(self) -> None:
        rr = self._room_at(self.r, self.c)
        if rr is not None:
            self._rooms_seen.add(rr)

    def _next_expand_room(self) -> int | None:
        for u, w in self._room_edges:
            if u in self._rooms_seen and w not in self._rooms_seen:
                return int(w)
        return None

    def _step_toward(self, env: Environment, goal_rc: tuple[int, int]) -> StepIntent:
        wall = self._bm.wall
        gr, gc = goal_rc
        path = grid_shortest_path(wall, (self.r, self.c), (gr, gc))
        if len(path) < 2:
            return StepIntent((self.r, self.c))
        nxt = path[1]
        legal = env.legal_steps(self.r, self.c)
        if nxt in legal:
            return StepIntent(nxt)
        best = (self.r, self.c)
        best_len = 10**9
        for pr, pc in legal:
            detour = grid_shortest_path(wall, (pr, pc), (gr, gc))
            ln = len(detour)
            if ln < best_len or (ln == best_len and (pr, pc) < best):
                best_len = ln
                best = (pr, pc)
        return StepIntent(best)

    def _relay_slot_goal_cell(self, backbone: list[tuple[int, int]], relay_index: int, n_relays: int) -> tuple[int, int]:
        """Arc-length slot along backbone (matches ``sample_polyline`` usage in centralized demo)."""
        if not backbone:
            ar, ac = self._bm.anchors[self._root]
            return (ar, ac)
        h, wdim = self._bm.wall.shape
        pts_f = sample_polyline(backbone, max(1, n_relays))
        fr, fc = pts_f[min(relay_index, len(pts_f) - 1)]
        gr = max(0, min(h - 1, int(math.floor(fr))))
        gc = max(0, min(wdim - 1, int(math.floor(fc))))
        if not self._bm.wall[gr, gc]:
            return (gr, gc)
        return min(backbone, key=lambda cell: abs(cell[0] - gr) + abs(cell[1] - gc))

    def decide_move(
        self,
        env: Environment,
        rng,
        *,
        tick: int = 0,
        portal_cross_allowed: bool = True,
    ) -> StepIntent:
        _ = rng
        _ = tick
        _ = portal_cross_allowed
        self._sync_room_seen()

        scout_uid = self.fleet_n - 1
        n_relays = max(0, self.fleet_n - 1)

        tgt_room = self._next_expand_room()

        if tgt_room is None:
            final_room = self._room_edges[-1][1] if self._room_edges else self._root
            backbone = self._backbone_cells_upto(final_room)
            ar, ac = self._bm.anchors[final_room]
            if self.uid == scout_uid or n_relays <= 0:
                return self._step_toward(env, (ar, ac))
            return self._step_toward(env, self._relay_slot_goal_cell(backbone, self.uid, n_relays))

        pu = self._room_parent.get(tgt_room)
        parent_room = int(pu) if pu is not None else self._root
        backbone = self._backbone_cells_upto(parent_room)
        gr, gc = self._bm.anchors[tgt_room]

        if self.uid == scout_uid:
            return self._step_toward(env, (gr, gc))
        if n_relays <= 0:
            return self._step_toward(env, (gr, gc))
        return self._step_toward(env, self._relay_slot_goal_cell(backbone, self.uid, n_relays))

    def _beacon_payload_extras(self, _tick: int) -> dict[str, object]:
        rs = sorted(self._rooms_seen)
        if len(rs) > MAX_SEEN_ROOMS_BEACON:
            rs = rs[:MAX_SEEN_ROOMS_BEACON]
        return {"seen_rooms": rs}

    def _on_beacon_received(self, sender_uid: int, payload: dict[str, object], tick: int) -> None:
        _ = sender_uid
        _ = tick
        raw = payload.get("seen_rooms")
        if not isinstance(raw, list):
            return
        for x in raw:
            if isinstance(x, int):
                self._rooms_seen.add(int(x))
