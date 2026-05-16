"""One OS process running a single swarm agent + UDP propagation radio (UDP mesh backend)."""

from __future__ import annotations

import pickle
import queue
from collections.abc import Callable
from multiprocessing.synchronize import Event
from typing import Any

from swarm_sim.agent import DroneAgent
from swarm_sim.building import BuildingMap, load_layout
from swarm_sim.environment import CellReading, Environment
from swarm_sim.layout_bfs_agent import LayoutBFSDrone
from swarm_sim.mock_transmission import PropagationUDPTransmission, swarm_udp_destinations
from swarm_sim.packet_codec import packet_from_json_bytes, packet_to_json_bytes
from swarm_sim.radio import RadioConfig
from swarm_sim.sim_kernel import _exploration_bfs_tree_segments, follower_mesh_intent_from_explorer_rc


def _readings_wire_to_cell(wire: list[tuple[int, int, bool]]) -> list[CellReading]:
    return [CellReading(int(r), int(c), bool(w)) for r, c, w in wire]


def sim_drone_worker_main(
    uid: int,
    layout_name: str,
    decentralized_policy: str,
    base_port: int,
    fleet_n: int,
    pose_registry: dict[str, Any],
    inbound: Any,
    outbound: Any,
    stop_event: Event,
    *,
    perception_radius: int = 5,
    beacon_interval: int = 4,
    merge_interval: int = 10,
    explorer_phase_ticks: int | None = None,
    radio_cfg: RadioConfig | None = None,
    mesh_activity_queue: Any | None = None,
) -> None:
    """Worker loop driven by tuples on ``inbound``; replies on ``outbound``."""

    rng_state: bytes | None = None
    building_map: BuildingMap = load_layout(layout_name)
    env = Environment(building_map)
    cfg = radio_cfg or RadioConfig()
    ethers = swarm_udp_destinations(fleet_n, base_port)

    spawn_r: int = 0
    spawn_c: int = 0

    outbound.put(("HELLO", int(uid)))

    def get_pose() -> tuple[float, float]:
        p = pose_registry.get(str(uid), (0.5, 0.5))
        return float(p[0]), float(p[1])

    radio = PropagationUDPTransmission(
        building_map.wall,
        cfg,
        int(base_port) + int(uid),
        get_pose,
        ether_ports=ethers,
        verbose=False,
    )

    agent: DroneAgent | LayoutBFSDrone | None = None
    explorer_phase_ticks_i: int | None = explorer_phase_ticks
    n_ticks_hint = 480

    def mesh_sink_factory() -> Callable[[str], None] | None:
        q = mesh_activity_queue
        if q is None:
            return None
        return lambda line: q.put(line)

    sink_template = mesh_sink_factory()

    def rebuild_agent(sr: int, sc: int) -> None:
        nonlocal agent, spawn_r, spawn_c
        spawn_r, spawn_c = int(sr), int(sc)
        mesh_sink = sink_template
        if decentralized_policy == "layout_bfs":
            agent = LayoutBFSDrone(
                uid=int(uid),
                start_rc=(spawn_r, spawn_c),
                building=building_map,
                perception_radius=perception_radius,
                beacon_interval=beacon_interval,
                merge_interval=merge_interval,
                fleet_n=max(1, int(fleet_n)),
                mesh_activity_sink=mesh_sink,
            )
        else:
            agent = DroneAgent(
                uid=int(uid),
                start_rc=(spawn_r, spawn_c),
                perception_radius=perception_radius,
                beacon_interval=beacon_interval,
                merge_interval=merge_interval,
                fleet_n=max(1, int(fleet_n)),
                mesh_activity_sink=mesh_sink,
            )

    try:
        while not stop_event.is_set():
            try:
                cmd = inbound.get(timeout=0.35)
            except queue.Empty:
                continue
            tag = cmd[0]
            if agent is None and tag not in {"STOP", "INIT"}:
                continue

            if tag == "STOP":
                break
            if tag == "INIT":
                _, sr, sc, n_thr, ex_ph = cmd
                n_ticks_hint = max(1, int(n_thr))
                explorer_phase_ticks_i = None if ex_ph is None else int(ex_ph)
                rebuild_agent(int(sr), int(sc))
                pose_registry[str(uid)] = (float(spawn_r), float(spawn_c))
                outbound.put(("INIT_OK", int(uid)))
            elif tag == "DRAIN":
                _, tick_i = cmd
                assert agent is not None
                agent.drain_inbox(int(tick_i))
                outbound.put(("DRAIN_OK", int(uid)))
            elif tag == "SENSE_LAYOUT":
                _, tick_i, readings_wire, rng_blob = cmd
                assert agent is not None
                rng_loc = pickle.loads(rng_blob)
                agent.absorb_readings(_readings_wire_to_cell(readings_wire))
                intent = agent.decide_move(env, rng_loc, tick=int(tick_i))
                outbound.put(
                    (
                        "INTENT_OK",
                        int(uid),
                        int(intent.target_rc[0]),
                        int(intent.target_rc[1]),
                        pickle.dumps(rng_loc),
                    )
                )
            elif tag == "SENSE_LOCAL":
                _, tick_i, readings_wire, det_blob, explorer_uid_calc, explorer_rc, rng_blob, phase_len = cmd
                assert agent is not None
                rng_loc = pickle.loads(rng_blob)
                agent.absorb_readings(_readings_wire_to_cell(readings_wire))
                agent.observe_visual(pickle.loads(det_blob))
                erc = (int(explorer_rc[0]), int(explorer_rc[1]))
                ex_uid_i = int(explorer_uid_calc)
                if int(uid) == ex_uid_i:
                    tr, tc = agent.decide_move(
                        env,
                        rng_loc,
                        tick=int(tick_i),
                        portal_cross_allowed=True,
                    ).target_rc
                else:
                    tr, tc = follower_mesh_intent_from_explorer_rc(
                        agent,
                        erc,
                        env,
                        rng_loc,
                    )
                outbound.put(
                    (
                        "INTENT_OK",
                        int(uid),
                        int(tr),
                        int(tc),
                        pickle.dumps(rng_loc),
                    )
                )
            elif tag == "APPLY_POSE":
                _, rr, cc = cmd
                assert agent is not None
                agent.apply_pose(int(rr), int(cc))
                pose_registry[str(uid)] = (float(agent.r), float(agent.c))
                outbound.put(("APPLY_OK", int(uid)))
            elif tag == "MAYBE_TX":
                _, tick_i = cmd
                assert agent is not None
                pkt_o = agent.maybe_transmit(int(tick_i))
                if pkt_o is not None:
                    agent.emit_mesh_tx_activity(pkt_o, int(tick_i))
                blob = packet_to_json_bytes(pkt_o) if pkt_o is not None else b""
                outbound.put(("TX_BLOB", int(uid), blob))
            elif tag == "UDP_BROADCAST":
                _, blob = cmd
                if blob:
                    radio.broadcast(bytes(blob))
                outbound.put(("BROADCAST_OK", int(uid)))
            elif tag == "UDP_RECV":
                _ignored_sender, pl, rss = radio.receive(timeout=1.25)
                assert agent is not None
                if pl is None or rss is None:
                    outbound.put(("RX_NONE", int(uid)))
                else:
                    parsed = packet_from_json_bytes(pl)
                    if parsed is None:
                        outbound.put(("RX_NONE", int(uid)))
                    else:
                        agent.on_receive(parsed, float(rss))
                        outbound.put(("RX_OK", int(uid)))
            elif tag == "TREE_SEGS_EXPORT":
                assert agent is not None
                segs = _exploration_bfs_tree_segments(agent)
                outbound.put(("TREE_SEGS", int(uid), segs))
            elif tag == "STATS_EXPORT_LAYOUT":
                assert agent is not None
                rooms = tuple(sorted(agent._rooms_seen)) if isinstance(agent, LayoutBFSDrone) else ()
                outbound.put(
                    (
                        "STATS_LAYOUT",
                        int(uid),
                        len(agent.topo_nodes),
                        len(agent.topo_edges),
                        len(agent.belief_edges),
                        len(agent.recent_detections),
                        dict(agent.neighbors_last),
                        rooms,
                    )
                )
            elif tag == "STATS_EXPORT_LOCAL":
                assert agent is not None
                outbound.put(
                    (
                        "STATS_LOCAL",
                        int(uid),
                        len(agent.topo_nodes),
                        len(agent.topo_edges),
                        len(agent.belief_edges),
                        len(agent.recent_detections),
                        dict(agent.neighbors_last),
                    )
                )
    finally:
        try:
            radio.stop()
        except Exception:
            pass
