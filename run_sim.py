"""Interactive matplotlib demo: BFS tree takeover + RSSI heatmap."""

from __future__ import annotations

import pathlib
import argparse
import sys

# Running ``python run_sim.py`` from inside swarm_sim/ only puts this folder on sys.path,
# so ``import swarm_sim.*`` fails. Add the repo root (parent of this directory).
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_rs = str(_REPO_ROOT)
if _rs not in sys.path:
    sys.path.insert(0, _rs)
from collections import deque
from dataclasses import dataclass

if any(a.startswith("--save-png") or a.startswith("--save-gif") for a in sys.argv[1:]):
    import matplotlib as _mpl

    _mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

from swarm_sim.building import BuildingMap, build_small_office
from swarm_sim.navigation import (
    concat_paths,
    grid_shortest_path,
    interpolate_polyline,
    sample_polyline,
)
from swarm_sim.propagation import field_strength_map


@dataclass
class FrameState:
    drones_rc: list[tuple[float, float]]
    caption: str


def bfs_plan(
    adjacency: dict[int, tuple[int, ...]], root: int
) -> tuple[dict[int, int | None], list[tuple[int, int]], list[list[int]]]:
    """Breadth-first spanning tree over the known floorplan graph."""
    parent: dict[int, int | None] = {root: None}
    edges: list[tuple[int, int]] = []
    queue_snapshots: list[list[int]] = []
    q: deque[int] = deque([root])
    while q:
        u = q.popleft()
        for v in sorted(adjacency[u]):
            if v not in parent:
                parent[v] = u
                edges.append((u, v))
                q.append(v)
                queue_snapshots.append(list(q))
    return parent, edges, queue_snapshots


def rooms_root_to_u(parent: dict[int, int | None], root: int, u: int) -> list[int]:
    seq: list[int] = []
    cur = u
    while True:
        seq.append(cur)
        if cur == root:
            break
        nxt = parent[cur]
        assert nxt is not None
        cur = nxt
    seq.reverse()
    return seq


def build_timeline(
    building: BuildingMap,
    *,
    n_drones: int,
    frames_per_edge: int,
    dwell_frames: int,
) -> tuple[list[FrameState], dict[int, int | None], list[tuple[int, int]]]:
    root = building.entrance_room
    wall = building.wall
    anchors = building.anchors

    parent, edges, queue_snapshots = bfs_plan(building.adjacency, root)

    n_relays = max(0, n_drones - 1)

    edge_paths: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for u, v in edges:
        edge_paths[(u, v)] = grid_shortest_path(wall, anchors[u], anchors[v])

    stage_path = grid_shortest_path(wall, anchors[root], building.door_lobby_rc)

    def backbone_cells_upto(room_id: int) -> list[tuple[int, int]]:
        """Tree backbone polyline from root toward ``room_id`` (open corridors only)."""
        chain = rooms_root_to_u(parent, root, room_id)
        if len(chain) == 1:
            return stage_path
        parts = [edge_paths[(chain[i], chain[i + 1])] for i in range(len(chain) - 1)]
        return concat_paths(parts)

    timeline: list[FrameState] = []

    def caption_idle(q_repr: str, depth: str) -> str:
        return (
            "BFS tree takeover (rooms = vertices)\n"
            f"Frontier queue Q after enqueue (FIFO snapshot): {q_repr}\n"
            f"{depth}\n"
            "Drone paths: grid shortest paths on walkable cells (no wall clipping).\n"
            "Relays hold the backbone to the parent room while the scout opens the next edge.\n"
            "Path loss model (Rep. ITU-R P.2346 eq. (2) style):\n"
            "  L = 20·log10(f_MHz) + N·log10(d_m) − 27.55 + L_f\n"
            "  L_f ≈ (wall pixel hits along LOS) × L_wall — heuristic grid penetration."
        )

    # Idle — relays spaced toward the upper doorway; scout at door staging point.
    relay_pts = sample_polyline(stage_path, n_relays)
    scout_idle = interpolate_polyline(stage_path, 1.0)
    idle_swarm = relay_pts + [scout_idle]
    q0 = [building.entrance_room]
    for _ in range(dwell_frames):
        timeline.append(
            FrameState(
                drones_rc=idle_swarm,
                caption=caption_idle(str(q0), "Staging at entrance — relays line toward lobby doorway."),
            )
        )

    discovered_msg = f"Discovered (BFS order): [{root}]"

    assert len(queue_snapshots) == len(edges)

    for (u, w), q_snap in zip(edges, queue_snapshots):
        backbone_parent = backbone_cells_upto(u)
        relay_hold = sample_polyline(backbone_parent, n_relays)
        motion_path = edge_paths[(u, w)]

        discovered_msg += f" → {w}"

        for k in range(frames_per_edge):
            t = (k + 1) / frames_per_edge
            scout_xy = interpolate_polyline(motion_path, t)
            timeline.append(
                FrameState(
                    drones_rc=relay_hold + [scout_xy],
                    caption=caption_idle(
                        str(q_snap),
                        f"Edge ({u}→{w})  |  relays on backbone≤{u}, scout along corridor grid path.",
                    )
                    + "\n"
                    + discovered_msg,
                )
            )

        backbone_child = backbone_cells_upto(w)
        relay_pts = sample_polyline(backbone_child, n_relays)
        scout_settled = interpolate_polyline(backbone_child, 1.0)
        settled_swarm = relay_pts + [scout_settled]

        for _ in range(max(1, dwell_frames // 2)):
            timeline.append(
                FrameState(
                    drones_rc=settled_swarm,
                    caption=caption_idle(
                        str(q_snap),
                        f"Committed parent[{w}]={u}; relays redistributed along backbone to room {w}.",
                    )
                    + "\n"
                    + discovered_msg,
                )
            )

    return timeline, parent, edges


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BFS swarm takeover simulation with RSSI map.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "From inside swarm_sim/:\n"
            "  python run_sim.py\n"
            "From repo root (parent of swarm_sim/):\n"
            "  python -m swarm_sim\n"
            "  python -m swarm_sim.run_sim\n"
            "Examples:\n"
            '  python run_sim.py --save-png preview.png\n'
            '  python -m swarm_sim --save-gif takeover.gif --dwell 4 --interval-ms 70\n'
        ),
    )
    parser.add_argument("--cell-m", type=float, default=0.22, help="Meters per raster cell edge.")
    parser.add_argument("--freq-mhz", type=float, default=2400.0)
    parser.add_argument("--tx-dbm", type=float, default=20.0)
    parser.add_argument("--n-exp", type=float, default=28.0, help="Distance exponent N in P.2346 eq. (2).")
    parser.add_argument("--wall-db", type=float, default=9.0, help="dB added per wall pixel hit along LOS.")
    parser.add_argument("--n-drones", type=int, default=7)
    parser.add_argument("--stride", type=int, default=3, help="Heatmap raster stride (performance).")
    parser.add_argument("--frames-per-edge", type=int, default=32)
    parser.add_argument("--dwell", type=int, default=10)
    parser.add_argument("--interval-ms", type=int, default=90)
    parser.add_argument("--save-gif", type=str, default="", help="Optional path to save animated GIF.")
    parser.add_argument("--save-png", type=str, default="", help="Save first frame snapshot to PNG and exit.")
    args = parser.parse_args()

    building = build_small_office()
    timeline, parent, edges = build_timeline(
        building,
        n_drones=args.n_drones,
        frames_per_edge=args.frames_per_edge,
        dwell_frames=args.dwell,
    )

    h, w = building.wall.shape
    wall = building.wall

    first_rss, _ = field_strength_map(
        wall,
        timeline[0].drones_rc,
        args.cell_m,
        args.freq_mhz,
        args.tx_dbm,
        distance_exponent=args.n_exp,
        lf_per_wall_cell_db=args.wall_db,
        stride=args.stride,
    )
    vmin = np.percentile(first_rss[np.isfinite(first_rss)], 5) - 5
    vmax = np.percentile(first_rss[np.isfinite(first_rss)], 95) + 8

    fig, ax = plt.subplots(figsize=(11, 7))
    extent_m = [0.0, w * args.cell_m, h * args.cell_m, 0.0]
    im = ax.imshow(
        first_rss,
        origin="upper",
        extent=extent_m,
        cmap="inferno",
        vmin=vmin,
        vmax=vmax,
        interpolation="nearest",
        aspect="equal",
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Received power (dBm), max over airborne relays")

    wy, wx = np.where(wall)
    _ = ax.scatter(
        (wx.astype(np.float64) + 0.5) * args.cell_m,
        (wy.astype(np.float64) + 0.5) * args.cell_m,
        s=4,
        c="#101820",
        marker="s",
        alpha=0.55,
        label="Wall raster",
    )

    drone_colors = plt.cm.cool(np.linspace(0.15, 0.95, args.n_drones))
    dr_xy = np.array(timeline[0].drones_rc)
    sc = ax.scatter(
        (dr_xy[:, 1]) * args.cell_m,
        (dr_xy[:, 0]) * args.cell_m,
        s=120,
        c=drone_colors,
        edgecolors="white",
        linewidths=1.2,
        label="Drones",
        zorder=5,
    )

    txt = fig.text(0.02, 0.02, timeline[0].caption, fontsize=10, family="monospace", va="bottom")

    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Breadth-first spanning-tree takeover + tactical RSSI map")

    def update(frame_idx: int):
        state = timeline[frame_idx]
        rss, _ = field_strength_map(
            wall,
            state.drones_rc,
            args.cell_m,
            args.freq_mhz,
            args.tx_dbm,
            distance_exponent=args.n_exp,
            lf_per_wall_cell_db=args.wall_db,
            stride=args.stride,
        )
        im.set_data(rss)
        pts = np.asarray(state.drones_rc)
        sc.set_offsets(np.c_[pts[:, 1] * args.cell_m, pts[:, 0] * args.cell_m])
        txt.set_text(state.caption)
        return im, sc, txt

    if args.save_png:
        fig.savefig(args.save_png, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return 0

    ani = FuncAnimation(
        fig,
        update,
        frames=len(timeline),
        interval=args.interval_ms,
        blit=False,
    )

    if args.save_gif:
        ani.save(args.save_gif, writer="pillow", fps=max(1, int(1000 / args.interval_ms)))
        plt.close(fig)
        return 0

    plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
