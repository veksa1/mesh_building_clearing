"""Decentralized kernel with multiprocess drones and UDP propagation (same physics as :class:`RadioMedium`)."""

from __future__ import annotations

import multiprocessing as mp
import pickle
import queue as queue_std
from collections import deque
from typing import Any

import numpy as np

from swarm_sim.building import BuildingMap
from swarm_sim.environment import Environment
from swarm_sim.layout_bfs_agent import LayoutBFSDrone
from swarm_sim.packet_codec import packet_from_json_bytes
from swarm_sim.radio import CommEvent, RadioConfig, RadioMedium
from swarm_sim.sim_drone_worker import sim_drone_worker_main
from swarm_sim.sim_kernel import (
    DecentralizedFrame,
    PoseResolveShell,
    _layout_relieve_scout_head,
    _room_spanning_tree_segments,
    _spawn_positions,
    resolve_moves_sequential,
)
from swarm_sim.viz_comms import DEFAULT_OVERLAY_TTL, CommsOverlay


def run_decentralized_udp_mesh(
    building: BuildingMap,
    *,
    layout_name: str,
    n_drones: int,
    n_ticks: int,
    radio_cfg: RadioConfig | None,
    rng: np.random.Generator | None,
    rf_log_cap: int,
    seed: int,
    udp_base_port: int = 8700,
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
    radio_snap = RadioMedium(building.wall, radio_cfg)
    cfg = radio_cfg or RadioConfig()
    spawns = _spawn_positions(building, n_drones)
    n_agents = len(spawns)
    scout_uid = max(0, n_agents - 1)

    if use_layout:
        oracle = LayoutBFSDrone(
            uid=0,
            start_rc=spawns[0],
            building=building,
            perception_radius=perception_radius,
            beacon_interval=beacon_interval,
            merge_interval=merge_interval,
            fleet_n=max(1, n_agents),
        )
        room_tree_segments = _room_spanning_tree_segments(building, list(oracle.room_tree_edges))
        phase_len = 1
    else:
        room_tree_segments = []
        if explorer_phase_ticks is None:
            phase_len = max(55, min(n_ticks // max(n_agents * 3, 1), 180))
        else:
            phase_len = max(1, int(explorer_phase_ticks))

    hud_mesh_cap = max(0, int(mesh_activity_tail_cap))
    mesh_buf: deque[str] = deque(maxlen=max(512, hud_mesh_cap * 16))

    ctx = mp.get_context("spawn")
    mesh_activity_queue: Any = ctx.Queue()
    manager = ctx.Manager()
    pose_registry: Any = manager.dict()
    stop_event = ctx.Event()
    q_to_child: dict[int, Any] = {i: ctx.Queue() for i in range(n_agents)}
    q_from_child: dict[int, Any] = {i: ctx.Queue() for i in range(n_agents)}

    procs: list[mp.Process] = []
    for i in range(n_agents):
        p = ctx.Process(
            target=sim_drone_worker_main,
            name=f"sim_drone_{i}",
            args=(
                i,
                layout_name,
                decentralized_policy,
                int(udp_base_port),
                int(n_agents),
                pose_registry,
                q_to_child[i],
                q_from_child[i],
                stop_event,
            ),
            kwargs={
                "perception_radius": perception_radius,
                "beacon_interval": beacon_interval,
                "merge_interval": merge_interval,
                "explorer_phase_ticks": explorer_phase_ticks,
                "radio_cfg": cfg,
                "mesh_activity_queue": mesh_activity_queue,
            },
        )
        p.start()
        procs.append(p)

    def recv_ok(uid: int, timeout: float = 120.0) -> tuple:
        msg = q_from_child[int(uid)].get(timeout=timeout)
        return msg

    for i in range(n_agents):
        tag, u = recv_ok(i)
        if tag != "HELLO":
            raise RuntimeError(f"worker {i} expected HELLO got {tag!r}")

    for i, (sr, sc) in enumerate(spawns):
        q_to_child[i].put(("INIT", sr, sc, int(n_ticks), explorer_phase_ticks))
    for i in range(n_agents):
        tag, u = recv_ok(i)
        if tag != "INIT_OK":
            raise RuntimeError(f"worker {i} expected INIT_OK got {tag!r}")

    overlay = CommsOverlay(ttl_ticks=DEFAULT_OVERLAY_TTL)
    log_buf: deque[str] = deque(maxlen=max(8, rf_log_cap))
    all_events: list[CommEvent] = []
    frames: list[DecentralizedFrame] = []

    def poses_int_registry() -> dict[int, tuple[int, int]]:
        return {
            i: (
                int(round(float(pose_registry[str(i)][0]))),
                int(round(float(pose_registry[str(i)][1]))),
            )
            for i in range(n_agents)
        }

    try:
        for tick in range(n_ticks):
            for uid in range(n_agents):
                q_to_child[uid].put(("DRAIN", int(tick)))
            for uid in range(n_agents):
                tag, _u = recv_ok(uid)
                if tag != "DRAIN_OK":
                    raise RuntimeError(f"tick {tick}: DRAIN expected DRAIN_OK from {uid} got {tag!r}")

            explorer_uid = int((tick // phase_len) % max(n_agents, 1))
            intents: dict[int, tuple[int, int]] = {}

            poses_int = poses_int_registry()

            explorer_rc = poses_int[int(explorer_uid)] if n_agents else (0, 0)

            for uid_i in sorted(range(n_agents)):
                r0, c0 = poses_int[uid_i]
                readings = env.sense_disc(r0, c0, perception_radius)
                wire = [(x.r, x.c, bool(x.is_wall)) for x in readings]
                rng_blob = pickle.dumps(rng)

                if use_layout:
                    q_to_child[uid_i].put(("SENSE_LAYOUT", int(tick), wire, rng_blob))
                else:
                    vis_r = max(perception_radius + 6, 12)
                    dets = env.detect_openings(r0, c0, radius=vis_r, rng=None)
                    det_blob = pickle.dumps(dets)
                    q_to_child[uid_i].put(
                        (
                            "SENSE_LOCAL",
                            int(tick),
                            wire,
                            det_blob,
                            int(explorer_uid),
                            explorer_rc,
                            rng_blob,
                            int(phase_len),
                        )
                    )

                resp = recv_ok(uid_i)
                if resp[0] != "INTENT_OK":
                    raise RuntimeError(resp)
                _tag, uid_r, tr, tc, rng_back = resp
                rng = pickle.loads(rng_back)
                intents[int(uid_r)] = (int(tr), int(tc))

            shells = [
                PoseResolveShell(i, int(poses_int[i][0]), int(poses_int[i][1])) for i in range(n_agents)
            ]
            defer_uid_eff = scout_uid if use_layout else None
            priority_uid_eff = explorer_uid if (not use_layout and n_agents) else None
            if use_layout:
                _layout_relieve_scout_head(shells, intents, env, scout_uid)
            resolve_moves_sequential(
                shells,
                intents,
                rng=rng,
                priority_uid=priority_uid_eff,
                defer_uid=defer_uid_eff,
            )

            for s in shells:
                q_to_child[int(s.uid)].put(("APPLY_POSE", int(s.r), int(s.c)))
            for uid in range(n_agents):
                tag, _u = recv_ok(uid)
                if tag != "APPLY_OK":
                    raise RuntimeError(f"tick {tick}: APPLY pose failed {tag!r}")

            poses_after = poses_int_registry()
            poses_f = {i: (float(poses_after[i][0]), float(poses_after[i][1])) for i in range(n_agents)}
            tick_events: list[CommEvent] = []

            for uid in sorted(range(n_agents)):
                q_to_child[uid].put(("MAYBE_TX", int(tick)))
                tag, uid_b, blob = recv_ok(uid)
                if tag != "TX_BLOB":
                    raise RuntimeError(f"unexpected tag={tag!r}")
                if blob:
                    pkt = packet_from_json_bytes(blob)
                    if pkt is None:
                        continue
                    _deliveries, evs = radio_snap.broadcast_tick(
                        int(tick),
                        uid,
                        poses_f[int(uid)],
                        pkt,
                        receiver_poses=poses_f,
                    )
                    tick_events.extend(evs)

                    q_to_child[int(uid)].put(("UDP_BROADCAST", blob))
                    tagb, _ub = recv_ok(uid)
                    if tagb != "BROADCAST_OK":
                        raise RuntimeError(tagb)

                    for rid in sorted(range(n_agents)):
                        if rid == uid:
                            continue
                        q_to_child[int(rid)].put(("UDP_RECV",))
                        tagr = recv_ok(rid)[0]
                        if tagr not in ("RX_OK", "RX_NONE"):
                            raise RuntimeError(f"bad RX reply {tagr!r}")

            all_events.extend(tick_events)
            for ev in tick_events:
                log_buf.append(ev.format_rf_hud_line())
            overlay.ingest_tick(tick_events)

            explorer_uid_eff = explorer_uid if n_agents else 0

            union_seen_inner: set[int] = set()
            if use_layout:
                stats_agg: list[tuple[Any, ...]] = []
                for uid in range(n_agents):
                    q_to_child[uid].put(("STATS_EXPORT_LAYOUT",))
                for uid in range(n_agents):
                    sta = recv_ok(uid)
                    if sta[0] != "STATS_LAYOUT":
                        raise RuntimeError(sta)
                    stats_agg.append(sta)
                for sta in stats_agg:
                    union_seen_inner |= {int(rid) for rid in sta[7]}
                total_nodes = max(int(sta[2]) for sta in stats_agg) if stats_agg else 0
                total_edges_agg = max(int(sta[3]) for sta in stats_agg) if stats_agg else 0
                belief_edges_n = max(int(sta[4]) for sta in stats_agg) if stats_agg else 0
                vision_hits = sum(int(sta[5]) for sta in stats_agg)
                tree_segments = room_tree_segments
                tree_n = len(tree_segments)
                rooms_disc_t = tuple(sorted(union_seen_inner))
                span_edges_t = tuple(oracle.room_tree_edges)
                discovered_line = (
                    "Rooms ∪ "
                    + ",".join(map(str, sorted(union_seen_inner)))
                    + " — spanning-tree expansion order matches centralized planner."
                )
                belief_panel = (
                    f"UDP mesh backend (workers) · layout-oracle decentralized\n"
                    f"{'─' * 26}\n\n"
                    f"Movement: relays yield lane tiles first; scout UID {scout_uid} resolves last each tick.\n"
                    f"(Discrete grid collision order identical to single-process kernel.)\n"
                    f"Room-tree grid segments (reference overlay): {tree_n}\n"
                    f"Sensed topo nodes (local): {total_nodes}\n"
                    f"Local topo edges: {total_edges_agg}\n"
                    f"Vision doorway hits (sum): {vision_hits}\n\n"
                    f"Neighbors (last beacon):\n"
                    + "\n".join(
                        f"  drone {int(sta[1])}: {sorted(sta[6].keys())}"
                        for sta in sorted(stats_agg, key=lambda z: int(z[1]))
                    )
                )
                caption = (
                    "Omniscient layout — same room BFS tree — **UDP mesh workers**.\n"
                    f"Relays arc-length slots toward parent room; scout (UID {scout_uid}) opens next edge.\n"
                    f"tick={tick}/{max(n_ticks - 1, 1)}. Gray lines: room spanning tree anchors.\n"
                )
            else:
                stats_agg = []
                for uid in range(n_agents):
                    q_to_child[uid].put(("STATS_EXPORT_LOCAL",))
                for uid in range(n_agents):
                    sta = recv_ok(uid)
                    if sta[0] != "STATS_LOCAL":
                        raise RuntimeError(sta)
                    stats_agg.append(sta)

                total_nodes = max(int(sta[2]) for sta in stats_agg) if stats_agg else 0
                total_edges = max(int(sta[3]) for sta in stats_agg) if stats_agg else 0
                belief_edges_n = max(int(sta[4]) for sta in stats_agg) if stats_agg else 0
                vision_hits = sum(int(sta[5]) for sta in stats_agg)

                q_to_child[int(explorer_uid_eff)].put(("TREE_SEGS_EXPORT",))
                tr_resp = recv_ok(int(explorer_uid_eff))
                if tr_resp[0] != "TREE_SEGS":
                    tree_segments = []
                else:
                    tree_segments = list(tr_resp[2])

                tree_n = len(tree_segments)
                rooms_disc_t = ()
                span_edges_t = ()
                discovered_line = "UDP propagation inbox; HUD mirrors RadioMedium."
                belief_panel = (
                    f"Decentralized belief (UDP workers)\n"
                    f"{'─' * 26}\n\n"
                    f"Movement: explorer rotates every {phase_len} ticks (current {explorer_uid_eff}); mesh-follow\n"
                    f"Local topo nodes: {total_nodes}\n"
                    f"Local topo edges: {total_edges}\n"
                    f"BFS tree edges (explorer map): {tree_n}\n"
                    f"Belief portal-edges: {belief_edges_n}\n"
                    f"Vision detections (this tick, sum): {vision_hits}\n\n"
                    f"Neighbors (last beacon):\n"
                    + "\n".join(
                        f"  drone {int(sta[1])}: {sorted(sta[6].keys())}"
                        for sta in sorted(stats_agg, key=lambda z: int(z[1]))
                    )
                )
                caption = (
                    "Decentralized exploration — UDP mesh radios.\n"
                    f"Explorer rotates every {phase_len} ticks (drone {explorer_uid_eff}); path uses frontier BFS.\n"
                    f"tick={tick}/{max(n_ticks - 1, 1)}. Gray lines: explorer BFS tree.\n"
                )

            drones_rc_sorted = [(float(poses_after[i][0]), float(poses_after[i][1])) for i in range(n_agents)]

            while True:
                try:
                    mesh_buf.append(mesh_activity_queue.get_nowait())
                except queue_std.Empty:
                    break

            frames.append(
                DecentralizedFrame(
                    drones_rc=drones_rc_sorted,
                    caption=caption,
                    layout_name=layout_name,
                    belief_panel=belief_panel,
                    phase_line=f"Tick {tick} · UDP propagation · intents serialized RNG order.",
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

    finally:
        stop_event.set()
        for i in range(n_agents):
            try:
                q_to_child[i].put_nowait(("STOP",))
            except Exception:
                pass
        for p in procs:
            p.join(timeout=12.0)
            if p.is_alive():
                p.terminate()
