"""Run the local-sense decentralized sim and export a renderer-ready JSON bundle.

The bundle is consumed by the static Next.js web app: it contains the rasterised
floorplan, the radio params used during export, and a per-tick timeline carrying
drone poses, CV detections, belief edges, RF comm links, and (oracle-only, view-
side) room IDs / room-graph edges so the web can offer a Drone vs Oracle toggle.

Usage:
    python -m swarm_sim.export_sim web/public/floorplans/default.json \
        -o web/public/sim/default.bundle.json --ticks 400 --n-drones 7

The Python side is the single source of truth for movement and perception logic;
the web only renders. Re-run after editing perception / agent / kernel and commit
the regenerated bundle.
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from collections import deque
from typing import Any

import numpy as np

_log = logging.getLogger("swarm_sim.export_sim")

# Allow ``python -m <pkg>.export_sim …`` from the repo parent directory.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_rs = str(_REPO_ROOT)
if _rs not in sys.path:
    sys.path.insert(0, _rs)

if __package__ in (None, ""):
    # Allow ``python export_sim.py …`` from inside the package directory.
    from floorplan_io import (  # type: ignore
        FloorplanRaster,
        building_from_raster,
        load_floorplan,
        rasterize_floorplan,
    )
    from radio import RadioConfig  # type: ignore
    from sim_kernel import DecentralizedFrame, run_decentralized  # type: ignore
    from viz_comms import FadedLink  # type: ignore
else:
    from .floorplan_io import (
        FloorplanRaster,
        building_from_raster,
        load_floorplan,
        rasterize_floorplan,
    )
    from .radio import RadioConfig
    from .sim_kernel import DecentralizedFrame, run_decentralized
    from .viz_comms import FadedLink


VALID_COMM_BACKENDS = ("udp", "inprocess")

# Same defaults as web/constants.ts DEFAULT_SIM_PARAMS.
DEFAULT_PARAMS: dict[str, float] = {
    "freqMhz": 2400.0,
    "txPowerDbm": 20.0,
    "distanceExponent": 28.0,
    "nDrones": 7,
    "framesPerEdge": 32,
    "dwellFrames": 10,
    "heatmapStride": 3,
    "raySamples": 48,
}


def _bool_grid_to_uint(arr: np.ndarray) -> list[int]:
    return [int(x) for x in arr.flatten().tolist()]


def _float_grid(arr: np.ndarray) -> list[float]:
    return [round(float(x), 4) for x in arr.flatten().tolist()]


def _serialize_link(lk: FadedLink, ttl: int) -> dict[str, Any]:
    return {
        "ticksLeft": int(lk.ticks_left),
        "ttlTicks": int(ttl),
        "r0": round(float(lk.r0), 2),
        "c0": round(float(lk.c0), 2),
        "r1": round(float(lk.r1), 2),
        "c1": round(float(lk.c1), 2),
        "msgType": str(lk.msg_type),
        "outcome": str(lk.outcome),
    }


def _is_fresh(lk: FadedLink, ttl_window: int) -> bool:
    """Only emit links from the same tick they were ingested.

    ``CommsOverlay.ingest_tick`` adds new links with ``ticks_left = ttl_ticks``
    and then decrements every link, so freshly added links sit at ``ttl - 1``
    when the frame snapshot is taken. The renderer applies its own decay TTL.
    """
    return int(lk.ticks_left) >= max(1, ttl_window - 1)


def _rooms_with_drones(
    rid: np.ndarray, drones: list[tuple[float, float]]
) -> list[int]:
    seen: set[int] = set()
    h, w = rid.shape
    for r, c in drones:
        ri = int(round(r))
        ci = int(round(c))
        if 0 <= ri < h and 0 <= ci < w:
            v = int(rid[ri, ci])
            if v >= 0:
                seen.add(v)
    return sorted(seen)


def _entrance_bfs_room_order(
    adjacency: dict[int, tuple[int, ...]], entrance: int
) -> list[tuple[int, int]]:
    """BFS spanning-tree edge list rooted at the entrance — oracle-view discovery order."""
    edges: list[tuple[int, int]] = []
    visited: set[int] = {entrance}
    q: deque[int] = deque([entrance])
    while q:
        u = q.popleft()
        for v in adjacency.get(u, ()):
            if v in visited:
                continue
            visited.add(v)
            edges.append((u, v))
            q.append(v)
    return edges


def _oracle_overlay(
    raster: FloorplanRaster,
    frame: DecentralizedFrame,
    spanning_edges_all: list[tuple[int, int]],
) -> dict[str, Any]:
    """Ground-truth view: which rooms each tick has been physically visited + BFS tree."""
    rooms_now = _rooms_with_drones(raster.room_id, frame.drones_rc)
    return {
        "roomsWithDrones": rooms_now,
        "spanningEdges": [list(e) for e in spanning_edges_all],
    }


def _serialize_frame(
    raster: FloorplanRaster,
    frame: DecentralizedFrame,
    spanning_edges_all: list[tuple[int, int]],
    rooms_seen_acc: set[int],
    overlay_ttl: int,
    *,
    include_tree: bool,
) -> dict[str, Any]:
    rooms_seen_acc.update(_rooms_with_drones(raster.room_id, frame.drones_rc))
    committed = [
        list(e)
        for e in spanning_edges_all
        if e[0] in rooms_seen_acc and e[1] in rooms_seen_acc
    ]
    queue_rooms = sorted(
        {
            v
            for u, v in spanning_edges_all
            if u in rooms_seen_acc and v not in rooms_seen_acc
        }
    )

    fresh_links = [lk for lk in frame.comm_links if _is_fresh(lk, overlay_ttl)]
    return {
        "tick": 0,  # placeholder — overwritten by caller
        "phase": str(frame.phase),
        "dronesRC": [
            {"row": round(r, 2), "col": round(c, 2)} for r, c in frame.drones_rc
        ],
        "commLinks": [_serialize_link(lk, overlay_ttl) for lk in fresh_links],
        "rfLogTail": list(frame.rf_log_tail)[-12:],
        "cvDetections": list(frame.cv_detections),
        "beliefEdges": [list(t) for t in frame.belief_edges],
        "knownFreeDelta": [[r, c] for r, c in frame.known_free_delta],
        # Flat int array [r0,c0,r1,c1,...] — only refreshed on keyframes.
        # Renderer carries the last refreshed segments forward across in-between ticks.
        "treeSegmentsRC": (
            [
                int(v)
                for a, b in frame.tree_segments_rc
                for v in (a[0], a[1], b[0], b[1])
            ]
            if include_tree
            else None
        ),
        "targetSeen": bool(frame.target_seen),
        "targetWitness": (
            None
            if frame.target_witness is None
            else {
                "uid": int(frame.target_witness[0]),
                "row": int(frame.target_witness[1]),
                "col": int(frame.target_witness[2]),
                "confidence": round(float(frame.target_witness[3]), 3),
            }
        ),
        "phaseLine": str(frame.phase_line),
        "discoveredLine": str(frame.discovered_line),
        "caption": str(frame.caption),
        "oracle": {
            "roomsDiscovered": sorted(rooms_seen_acc),
            "queueRooms": queue_rooms,
            "committedEdges": committed,
            "spanningEdges": [list(e) for e in spanning_edges_all],
        },
    }


def _run_local_sense(
    building: Any,
    *,
    layout_name: str,
    n_drones: int,
    ticks: int,
    radio_cfg: RadioConfig,
    seed: int,
    explorer_phase_ticks: int | None,
    target_rc: tuple[int, int] | None,
    comm_backend: str,
    udp_base_port: int,
) -> tuple[list[DecentralizedFrame], list, str]:
    """Run the local-sense kernel via the requested backend; fall back to in-process on UDP errors.

    Returns ``(frames, events, backend_used)`` so callers can record which kernel produced the bundle.
    """
    if comm_backend not in VALID_COMM_BACKENDS:
        raise ValueError(f"unknown comm_backend: {comm_backend!r}")

    common_kwargs = dict(
        layout_name=layout_name,
        n_drones=n_drones,
        n_ticks=ticks,
        radio_cfg=radio_cfg,
        rng=np.random.default_rng(int(seed)),
        rf_log_cap=24,
        seed=int(seed),
        explorer_phase_ticks=explorer_phase_ticks,
        decentralized_policy="local_sense",
        target_rc=target_rc,
    )

    if comm_backend == "udp":
        try:
            from .sim_kernel_udp import run_decentralized_udp_mesh

            frames, events = run_decentralized_udp_mesh(
                building,
                udp_base_port=int(udp_base_port),
                **common_kwargs,
            )
            return frames, events, "udp"
        except Exception as exc:  # noqa: BLE001 — record & fall back so exports stay reliable
            _log.warning(
                "UDP mesh backend failed (%s); falling back to in-process kernel.", exc
            )
    frames, events = run_decentralized(building, **common_kwargs)
    return frames, events, "inprocess"


def build_bundle_from_raster(
    raster: FloorplanRaster,
    *,
    ticks: int,
    n_drones: int,
    seed: int,
    params: dict[str, float],
    # Must match the value used inside ``run_decentralized``'s ``CommsOverlay``.
    overlay_ttl: int = 4,
    explorer_phase_ticks: int | None = None,
    comm_backend: str = "udp",
    udp_base_port: int = 8700,
) -> dict[str, Any]:
    """Run the local-sense kernel and serialize the bundle dict (no disk I/O).

    ``comm_backend`` selects the simulation backend: ``"udp"`` (default, multiprocess
    UDP mesh) or ``"inprocess"`` (single-process fallback). UDP failures auto-fall
    back; the chosen backend is recorded in ``bundle["meta"]["commBackend"]``.
    """
    building = building_from_raster(raster)

    radio_cfg = RadioConfig(
        cell_size_m=raster.cell_size_m,
        freq_mhz=float(params["freqMhz"]),
        tx_power_dbm=float(params["txPowerDbm"]),
        distance_exponent=float(params["distanceExponent"]),
        ray_samples=int(params["raySamples"]),
    )

    frames, _events, backend_used = _run_local_sense(
        building,
        layout_name=raster.name,
        n_drones=n_drones,
        ticks=ticks,
        radio_cfg=radio_cfg,
        seed=seed,
        explorer_phase_ticks=explorer_phase_ticks,
        target_rc=raster.target_rc,
        comm_backend=comm_backend,
        udp_base_port=udp_base_port,
    )

    spanning_edges_all = _entrance_bfs_room_order(raster.adjacency, raster.entrance_room)
    rooms_seen_acc: set[int] = {raster.entrance_room}

    timeline = []
    tree_keyframe_every = 10
    for i, fr in enumerate(frames):
        include_tree = (i % tree_keyframe_every == 0) or (i == len(frames) - 1)
        serialized = _serialize_frame(
            raster,
            fr,
            spanning_edges_all,
            rooms_seen_acc,
            overlay_ttl,
            include_tree=include_tree,
        )
        serialized["tick"] = i
        timeline.append(serialized)

    rooms_meta: list[dict[str, Any]] = []
    for room_id, anchor in sorted(building.anchors.items()):
        rooms_meta.append(
            {
                "id": int(room_id),
                "anchorCell": {"row": int(anchor[0]), "col": int(anchor[1])},
            }
        )

    bundle: dict[str, Any] = {
        "schemaVersion": 1,
        "meta": {
            "name": raster.name,
            "ticks": len(timeline),
            "nDrones": n_drones,
            "seed": seed,
            "policy": "local_sense",
            "commBackend": backend_used,
        },
        "rasterized": {
            "rows": raster.rows,
            "cols": raster.cols,
            "cellSizeM": raster.cell_size_m,
            "wallGrid": _bool_grid_to_uint(raster.wall_grid),
            "wallGridFull": _bool_grid_to_uint(raster.wall_grid_full),
            "wallDbGrid": _float_grid(raster.wall_db_grid),
        },
        "floorplan": raster.raw,
        "params": params,
        "roomGraph": {
            "rooms": rooms_meta,
            "adjacency": [
                {"room": int(k), "neighbors": [int(x) for x in v]}
                for k, v in sorted(raster.adjacency.items())
            ],
            "entranceRoomId": int(raster.entrance_room),
            "targetRoomId": int(raster.target_room),
            "spanningEdges": [list(e) for e in spanning_edges_all],
        },
        "entrance": {"row": int(raster.entrance_rc[0]), "col": int(raster.entrance_rc[1])},
        "target": {"row": int(raster.target_rc[0]), "col": int(raster.target_rc[1])},
        "timeline": timeline,
    }
    return bundle


def export_bundle_from_dict(
    floorplan: dict[str, Any],
    *,
    ticks: int,
    n_drones: int,
    seed: int,
    params: dict[str, float],
    overlay_ttl: int = 4,
    explorer_phase_ticks: int | None = None,
    comm_backend: str = "udp",
    udp_base_port: int = 8700,
) -> dict[str, Any]:
    """Rasterize an in-memory floorplan dict and return the bundle dict.

    HTTP-friendly entry point: matches the contract the FastAPI service exposes.
    """
    raster = rasterize_floorplan(floorplan)
    return build_bundle_from_raster(
        raster,
        ticks=ticks,
        n_drones=n_drones,
        seed=seed,
        params=params,
        overlay_ttl=overlay_ttl,
        explorer_phase_ticks=explorer_phase_ticks,
        comm_backend=comm_backend,
        udp_base_port=udp_base_port,
    )


def export_bundle(
    floorplan_path: pathlib.Path,
    output_path: pathlib.Path,
    *,
    ticks: int,
    n_drones: int,
    seed: int,
    params: dict[str, float],
    overlay_ttl: int = 4,
    explorer_phase_ticks: int | None = None,
    comm_backend: str = "udp",
    udp_base_port: int = 8700,
) -> dict[str, Any]:
    """CLI wrapper: load floorplan JSON from disk, build bundle, write JSON to disk."""
    raster = load_floorplan(floorplan_path)
    bundle = build_bundle_from_raster(
        raster,
        ticks=ticks,
        n_drones=n_drones,
        seed=seed,
        params=params,
        overlay_ttl=overlay_ttl,
        explorer_phase_ticks=explorer_phase_ticks,
        comm_backend=comm_backend,
        udp_base_port=udp_base_port,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, separators=(",", ":")), encoding="utf-8")
    return bundle


def _parse_params(args: argparse.Namespace) -> dict[str, float]:
    params = dict(DEFAULT_PARAMS)
    params["nDrones"] = int(args.n_drones)
    params["txPowerDbm"] = float(args.tx_dbm)
    params["freqMhz"] = float(args.freq_mhz)
    params["distanceExponent"] = float(args.n_exp)
    params["raySamples"] = int(args.ray_samples)
    params["heatmapStride"] = int(args.stride)
    params["dwellFrames"] = int(args.dwell)
    params["framesPerEdge"] = int(args.frames_per_edge)
    return params


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a local-sense simulation bundle for the web renderer.",
    )
    parser.add_argument("floorplan", type=pathlib.Path, help="Path to floorplan JSON.")
    parser.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("web/public/sim/default.bundle.json"),
        help="Destination bundle JSON path (default: web/public/sim/default.bundle.json).",
    )
    parser.add_argument("--ticks", type=int, default=400, help="Simulation horizon.")
    parser.add_argument("--n-drones", type=int, default=7)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--explorer-phase",
        type=int,
        default=0,
        help="Ticks per explorer before rotating UID. 0 = auto from horizon and fleet size.",
    )
    parser.add_argument("--tx-dbm", type=float, default=20.0)
    parser.add_argument("--freq-mhz", type=float, default=2400.0)
    parser.add_argument("--n-exp", type=float, default=28.0)
    parser.add_argument("--ray-samples", type=int, default=48)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--dwell", type=int, default=10)
    parser.add_argument("--frames-per-edge", type=int, default=32)
    parser.add_argument(
        "--comm-backend",
        choices=VALID_COMM_BACKENDS,
        default="udp",
        help="Mesh backend (default: udp, multiprocess); inprocess is the single-process fallback.",
    )
    parser.add_argument(
        "--udp-base-port",
        type=int,
        default=8700,
        help="With --comm-backend udp: drone uid i listens on PORT+i (default 8700).",
    )
    args = parser.parse_args(argv)

    params = _parse_params(args)
    explorer_phase = None if int(args.explorer_phase) <= 0 else int(args.explorer_phase)
    bundle = export_bundle(
        args.floorplan,
        args.output,
        ticks=int(args.ticks),
        n_drones=int(args.n_drones),
        seed=int(args.seed),
        params=params,
        explorer_phase_ticks=explorer_phase,
        comm_backend=str(args.comm_backend),
        udp_base_port=int(args.udp_base_port),
    )
    print(
        f"wrote {args.output} — ticks={len(bundle['timeline'])} "
        f"rooms={len(bundle['roomGraph']['rooms'])} "
        f"target_seen_at_end={bundle['timeline'][-1]['targetSeen']} "
        f"backend={bundle['meta'].get('commBackend')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
