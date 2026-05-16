"""Interactive matplotlib demo: BFS tree takeover + RSSI heatmap."""

from __future__ import annotations

import pathlib
import argparse
import sys
from dataclasses import dataclass

# Running ``python run_sim.py`` from inside swarm_sim/ only puts this folder on sys.path,
# so ``import swarm_sim.*`` fails. Add the repo root (parent of this directory).
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_rs = str(_REPO_ROOT)
if _rs not in sys.path:
    sys.path.insert(0, _rs)

if any(a.startswith("--save-png") or a.startswith("--save-gif") for a in sys.argv[1:]):
    import matplotlib as _mpl

    _mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib.collections import LineCollection

from swarm_sim.building import BuildingMap, LAYOUT_CHOICES, load_layout
from swarm_sim.radio import RadioConfig
from swarm_sim.sim_kernel import DecentralizedFrame, run_decentralized
from swarm_sim.navigation import (
    concat_paths,
    grid_shortest_path,
    interpolate_polyline,
    sample_polyline,
)
from swarm_sim.propagation import field_strength_map
from swarm_sim.room_bfs_plan import bfs_plan, rooms_root_to_u
from swarm_sim.viz_comms import DEFAULT_OVERLAY_TTL, format_decentralized_telemetry_panel, plot_comm_links


@dataclass
class FrameState:
    drones_rc: list[tuple[float, float]]
    caption: str
    layout_name: str
    queue_rooms: list[int]
    phase_line: str
    discovered_line: str


def format_side_panel(st: FrameState) -> str:
    q_fmt = " │ ".join(str(x) for x in st.queue_rooms) if st.queue_rooms else "∅"
    return (
        f"Layout: {st.layout_name}\n"
        f"{'─' * 26}\n\n"
        "BFS frontier Q\n(head → tail)\n\n"
        f"   [ {q_fmt} ]\n\n"
        "Phase\n"
        f"   {st.phase_line}\n\n"
        "Discovery trace\n"
        f"   {st.discovered_line}\n"
    )


def _room_tree_xy(building: BuildingMap) -> dict[int, tuple[float, float]]:
    """Room-node positions for side graph: x = col, y = -row (math-up)."""
    return {int(k): (float(cc), float(-cr)) for k, (cr, cc) in building.centers.items()}


def _init_room_tree_panel(ax_tree, building: BuildingMap, span_edges: tuple[tuple[int, int], ...]) -> dict:
    ax_tree.set_facecolor("#f8fafc")
    ax_tree.set_xticks([])
    ax_tree.set_yticks([])
    ax_tree.set_title("Room tree (discovery)")
    pos = _room_tree_xy(building)
    if not span_edges or not pos:
        ax_tree.text(
            0.5,
            0.52,
            "Spanning tree graph\n(available in layout_bfs)",
            ha="center",
            va="center",
            transform=ax_tree.transAxes,
            fontsize=10,
            color="#64748b",
        )
        return {"empty": True}
    segs: list[list[tuple[float, float]]] = []
    for u, v in span_edges:
        pu, pv = pos.get(u), pos.get(v)
        if pu is not None and pv is not None:
            segs.append([pu, pv])
    lc = LineCollection(segs, colors="#475569", linewidths=2.6, alpha=0.88, zorder=1)
    ax_tree.add_collection(lc)
    room_ids = sorted(pos.keys())
    xs = [pos[r][0] for r in room_ids]
    ys = [pos[r][1] for r in room_ids]
    sc = ax_tree.scatter(xs, ys, s=440, c="#cbd5e1", edgecolors="white", linewidths=2.0, zorder=3)
    for rid in room_ids:
        x, y = pos[rid]
        ax_tree.text(
            x,
            y,
            str(rid),
            ha="center",
            va="center",
            fontsize=11,
            fontweight="bold",
            color="#0f172a",
            zorder=4,
        )
    xs_arr = np.asarray(xs, dtype=np.float64)
    ys_arr = np.asarray(ys, dtype=np.float64)
    dx = float(np.ptp(xs_arr)) if xs_arr.size else 1.0
    dy = float(np.ptp(ys_arr)) if ys_arr.size else 1.0
    pad = max(2.5, 0.12 * max(dx, dy))
    ax_tree.set_xlim(float(xs_arr.min()) - pad, float(xs_arr.max()) + pad)
    ax_tree.set_ylim(float(ys_arr.min()) - pad, float(ys_arr.max()) + pad)
    ax_tree.set_aspect("equal")
    return {"empty": False, "scatter": sc, "room_ids": room_ids}


def _update_room_tree_panel(artists: dict, discovered: tuple[int, ...]) -> None:
    if artists.get("empty"):
        return
    disc = set(discovered)
    room_ids = artists["room_ids"]
    colors = np.array(["#22c55e" if rid in disc else "#94a3b8" for rid in room_ids])
    artists["scatter"].set_facecolors(colors)


def _interp_decentralized_pose(
    timeline: list[DecentralizedFrame], frame_idx: int, substeps: int
) -> tuple[DecentralizedFrame, list[tuple[float, float]]]:
    """Map animation frame → sim metadata row + interpolated drone float poses."""
    n = len(timeline)
    substeps = max(1, substeps)
    max_f = max(0, (n - 1) * substeps)
    fi = int(np.clip(frame_idx, 0, max_f))
    tick_from = fi // substeps
    sub = fi % substeps
    if tick_from >= n - 1:
        st = timeline[-1]
        return st, list(st.drones_rc)
    alpha = sub / substeps
    d0 = np.asarray(timeline[tick_from].drones_rc, dtype=np.float64)
    d1 = np.asarray(timeline[tick_from + 1].drones_rc, dtype=np.float64)
    blend = (1.0 - alpha) * d0 + alpha * d1
    drones_rc = [tuple(float(x) for x in row) for row in blend]
    return timeline[tick_from], drones_rc


def _animate_decentralized(
    *,
    args: argparse.Namespace,
    building: BuildingMap,
    timeline: list[DecentralizedFrame],
) -> int:
    if not timeline:
        raise SystemExit("decentralized mode requires --ticks >= 1")

    substeps = max(1, int(args.viz_substeps))
    n_sim = len(timeline)
    n_anim = max(1, (n_sim - 1) * substeps + 1)
    vfm = int(getattr(args, "viz_frame_ms", 0) or 0)
    if vfm > 0:
        anim_interval_ms = max(1, vfm)
    else:
        anim_interval_ms = max(1, int(args.interval_ms) // substeps)

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

    fig = plt.figure(figsize=(18.8, 7.85))
    gs = fig.add_gridspec(1, 4, width_ratios=[3.2, 1.05, 0.92, 1.0], wspace=0.075)
    ax = fig.add_subplot(gs[0, 0])
    ax_tree = fig.add_subplot(gs[0, 1])
    ax_belief = fig.add_subplot(gs[0, 2])
    ax_rf = fig.add_subplot(gs[0, 3])
    for side_ax in (ax_belief, ax_rf):
        side_ax.set_facecolor("#f4f4f4")
        side_ax.grid(False)
        side_ax.set_xticks([])
        side_ax.set_yticks([])
    ax_belief.set_title("Belief / HUD")
    ax_rf.set_title("Telemetry")

    extent_m = [0.0, w * args.cell_m, h * args.cell_m, 0.0]
    im = ax.imshow(
        first_rss,
        origin="upper",
        extent=extent_m,
        cmap="inferno",
        vmin=vmin,
        vmax=vmax,
        interpolation="bilinear",
        aspect="equal",
    )
    oracle_artist = None
    if args.debug_oracle:
        oracle = np.where(wall, np.nan, building.room_id.astype(np.float64))
        floor_ids = building.room_id[~wall]
        oracle_vmax = float(np.max(floor_ids)) if floor_ids.size else 4.0
        oracle_artist = ax.imshow(
            oracle,
            origin="upper",
            extent=extent_m,
            cmap="tab10",
            alpha=0.22,
            vmin=-0.5,
            vmax=oracle_vmax,
            interpolation="bilinear",
            aspect="equal",
            zorder=2,
        )

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
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
    _, drones0 = _interp_decentralized_pose(timeline, 0, substeps)
    dr_xy = np.array(drones0)
    sc = ax.scatter(
        (dr_xy[:, 1]) * args.cell_m,
        (dr_xy[:, 0]) * args.cell_m,
        s=120,
        c=drone_colors,
        edgecolors="white",
        linewidths=1.2,
        label="Drones",
        zorder=6,
    )

    tree_lc = LineCollection(
        [],
        colors="#b0b0b0",
        linewidths=1.35,
        alpha=0.55,
        zorder=4,
        capstyle="round",
    )
    ax.add_collection(tree_lc)

    span0 = timeline[0].room_spanning_edges if timeline else tuple()
    tree_artists = _init_room_tree_panel(ax_tree, building, span0)
    _update_room_tree_panel(tree_artists, timeline[0].rooms_discovered_sorted)

    fig.subplots_adjust(left=0.038, right=0.988, bottom=0.21, top=0.90)

    txt = fig.text(0.038, 0.035, timeline[0].caption, fontsize=9.5, family="monospace", va="bottom")

    belief_txt = ax_belief.text(
        0.05,
        0.97,
        timeline[0].belief_panel,
        transform=ax_belief.transAxes,
        fontsize=9.2,
        family="monospace",
        va="top",
        ha="left",
        linespacing=1.35,
    )
    mesh_tail_n = int(getattr(args, "viz_mesh_activity_tail", 36))
    rf_body = (
        format_decentralized_telemetry_panel(
            rf_lines=timeline[0].rf_log_tail,
            mesh_lines=list(timeline[0].mesh_activity_tail),
            rf_tail=args.viz_comms_tail,
            mesh_tail=mesh_tail_n,
            show_rf=bool(args.viz_comms_panel),
        )
        if (args.viz_comms_panel or mesh_tail_n > 0)
        else "Telemetry disabled (--no-viz-comms-panel; --viz-mesh-activity-tail 0)."
    )
    rf_txt = ax_rf.text(
        0.04,
        0.97,
        rf_body,
        transform=ax_rf.transAxes,
        fontsize=8.7,
        family="monospace",
        va="top",
        ha="left",
        linespacing=1.25,
    )

    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(f"Decentralized swarm + RSSI — layout “{args.layout}”")

    comm_artists: list = []

    def update(frame_idx: int):
        nonlocal comm_artists
        for artist in comm_artists:
            artist.remove()
        comm_artists.clear()

        state, drones_rc = _interp_decentralized_pose(timeline, frame_idx, substeps)
        fi = int(np.clip(frame_idx, 0, max(0, (n_sim - 1) * substeps)))
        tick_from = fi // substeps
        sub = fi % substeps
        if tick_from + 1 < n_sim and sub > substeps // 2:
            disc_src = timeline[tick_from + 1]
        else:
            disc_src = state

        rss, _ = field_strength_map(
            wall,
            drones_rc,
            args.cell_m,
            args.freq_mhz,
            args.tx_dbm,
            distance_exponent=args.n_exp,
            lf_per_wall_cell_db=args.wall_db,
            stride=args.stride,
        )
        im.set_data(rss)
        pts = np.asarray(drones_rc)
        sc.set_offsets(np.c_[pts[:, 1] * args.cell_m, pts[:, 0] * args.cell_m])
        cm = float(args.cell_m)
        tree_lc.set_segments(
            [
                [
                    ((c1 + 0.5) * cm, (r1 + 0.5) * cm),
                    ((c2 + 0.5) * cm, (r2 + 0.5) * cm),
                ]
                for (r1, c1), (r2, c2) in state.tree_segments_rc
            ]
        )
        txt.set_text(state.caption)
        belief_txt.set_text(state.belief_panel)

        mtn = int(getattr(args, "viz_mesh_activity_tail", 36))
        if args.viz_comms_panel or mtn > 0:
            rf_txt.set_text(
                format_decentralized_telemetry_panel(
                    rf_lines=state.rf_log_tail,
                    mesh_lines=list(state.mesh_activity_tail),
                    rf_tail=args.viz_comms_tail,
                    mesh_tail=mtn,
                    show_rf=bool(args.viz_comms_panel),
                )
            )
        else:
            rf_txt.set_text("Telemetry disabled (--no-viz-comms-panel; --viz-mesh-activity-tail 0).")

        _update_room_tree_panel(tree_artists, disc_src.rooms_discovered_sorted)

        if args.viz_comms_lines:
            comm_artists.extend(
                plot_comm_links(ax, state.comm_links, cell_m=args.cell_m, ttl_ticks=DEFAULT_OVERLAY_TTL)
            )

        out = [im, sc, tree_lc, txt, belief_txt, rf_txt]
        if oracle_artist is not None:
            out.append(oracle_artist)
        out.extend(comm_artists)
        return out

    if args.save_png:
        update(0)
        fig.savefig(args.save_png, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return 0

    ani = FuncAnimation(fig, update, frames=n_anim, interval=anim_interval_ms, blit=False)

    if args.save_gif:
        ani.save(args.save_gif, writer="pillow", fps=max(1, int(1000 / anim_interval_ms)))
        plt.close(fig)
        return 0

    plt.show()
    return 0


def build_timeline(
    building: BuildingMap,
    *,
    layout_name: str,
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

    def caption_body(depth: str, discovery_trace: str) -> str:
        return (
            "BFS tree takeover (rooms = vertices)\n"
            f"{depth}\n"
            f"Discovery trace: {discovery_trace}\n\n"
            "Drone paths: grid shortest paths on walkable cells (no wall clipping).\n"
            "Relays stay put across openings — only the scout crosses each new edge;\n"
            "relay spacing refreshes once after each room commits.\n\n"
            "Path loss model (Rep. ITU-R P.2346 eq. (2) style):\n"
            "  L = 20·log10(f_MHz) + N·log10(d_m) − 27.55 + L_f\n"
            "  L_f ≈ (wall pixel hits along LOS) × L_wall — heuristic grid penetration.\n\n"
            "See side panel for FIFO frontier queue state."
        )

    discovered_msg = "0"

    # Idle — relays spaced toward the upper doorway; scout at door staging point.
    relay_pts = sample_polyline(stage_path, n_relays)
    scout_idle = interpolate_polyline(stage_path, 1.0)
    idle_swarm = relay_pts + [scout_idle]
    q0 = [building.entrance_room]
    for _ in range(dwell_frames):
        timeline.append(
            FrameState(
                drones_rc=idle_swarm,
                caption=caption_body(
                    "Staging at entrance — relays line toward primary doorway.",
                    discovered_msg,
                ),
                layout_name=layout_name,
                queue_rooms=list(q0),
                phase_line="Idle — waiting to expand first frontier.",
                discovered_line=discovered_msg,
            )
        )

    assert len(queue_snapshots) == len(edges)

    for (u, w), q_snap in zip(edges, queue_snapshots):
        motion_path = edge_paths[(u, w)]

        discovered_msg += f" → {w}"

        for k in range(frames_per_edge):
            t = (k + 1) / frames_per_edge
            scout_xy = interpolate_polyline(motion_path, t)
            timeline.append(
                FrameState(
                    drones_rc=relay_pts + [scout_xy],
                    caption=caption_body(
                        f"Edge ({u}→{w}) — relays frozen; scout follows corridor grid path.",
                        discovered_msg,
                    ),
                    layout_name=layout_name,
                    queue_rooms=list(q_snap),
                    phase_line=f"Scout moving along tree edge {u} → {w} ({k + 1}/{frames_per_edge})",
                    discovered_line=discovered_msg,
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
                    caption=caption_body(
                        f"Committed parent[{w}]={u}; relays redistributed along backbone to room {w}.",
                        discovered_msg,
                    ),
                    layout_name=layout_name,
                    queue_rooms=list(q_snap),
                    phase_line=f"Settled — relays parked along backbone to room {w}.",
                    discovered_line=discovered_msg,
                )
            )

    return timeline, parent, edges


def _animate_centralized(
    *,
    args: argparse.Namespace,
    building: BuildingMap,
    timeline: list[FrameState],
) -> int:
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

    fig = plt.figure(figsize=(14.5, 7.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[3.2, 0.95], wspace=0.07)
    ax = fig.add_subplot(gs[0, 0])
    ax_panel = fig.add_subplot(gs[0, 1])
    ax_panel.set_facecolor("#f4f4f4")
    ax_panel.grid(False)
    ax_panel.set_xticks([])
    ax_panel.set_yticks([])
    ax_panel.set_title("Planner")

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
    if args.debug_oracle:
        oracle = np.where(wall, np.nan, building.room_id.astype(np.float64))
        floor_ids = building.room_id[~wall]
        oracle_vmax = float(np.max(floor_ids)) if floor_ids.size else 4.0
        ax.imshow(
            oracle,
            origin="upper",
            extent=extent_m,
            cmap="tab10",
            alpha=0.22,
            vmin=-0.5,
            vmax=oracle_vmax,
            interpolation="nearest",
            aspect="equal",
            zorder=2,
        )

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
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

    fig.subplots_adjust(left=0.06, right=0.98, bottom=0.21, top=0.90)

    txt = fig.text(0.06, 0.035, timeline[0].caption, fontsize=9.5, family="monospace", va="bottom")

    panel_txt = ax_panel.text(
        0.05,
        0.97,
        format_side_panel(timeline[0]),
        transform=ax_panel.transAxes,
        fontsize=10,
        family="monospace",
        va="top",
        ha="left",
        linespacing=1.35,
    )

    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(f"BFS takeover + RSSI — layout “{args.layout}”")

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
        panel_txt.set_text(format_side_panel(state))
        return im, sc, txt, panel_txt

    if args.save_png:
        update(0)
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Swarm RF simulation: centralized BFS demo or decentralized exploration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Layouts (--layout):\n"
            "  office   — split-level demo (default)\n"
            "  corridor — narrow vertical chain R0→R1→R2→R3\n"
            "  wing     — long upper wing + tucked lobby\n\n"
            "Modes (--mode):\n"
            "  centralized_demo — legacy omniscient BFS planner timeline\n"
            "  decentralized    — full discrete takeover simulation + RF HUD (Environment + kernels)\n"
            "                     (default policy: layout-oracle room BFS; see --decentralized-policy)\n\n"
            "Radio / mesh backends (decentralized only):\n"
            "  --comm-backend udp (default): one OS process per drone; packets go over real UDP\n"
            "                     localhost with RSSI-style decode (--udp-base-port selects base listen port).\n"
            "  --comm-backend inproc — single-process RadioMedium fallback when UDP/multiprocessing isn't available.\n\n"
            "Examples:\n"
            "  python -m swarm_sim --mode decentralized --ticks 400 --layout office\n"
            "  python -m swarm_sim --mode decentralized --comm-backend udp --udp-base-port 8700 --ticks 120 --layout office\n"
            "  python -m swarm_sim --mode decentralized --viz-substeps 6 --viz-frame-ms 16\n"
            "  python -m swarm_sim --mode decentralized --decentralized-policy local_sense --layout office\n"
            "  python run_sim.py --save-png preview.png --layout office\n"
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
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=90,
        help="Animation timing (ms): centralized demo uses this as delay between frames. "
        "Decentralized: delay per sim tick is spread across viz substeps (interval/substeps) unless --viz-frame-ms is set.",
    )
    parser.add_argument(
        "--layout",
        choices=list(LAYOUT_CHOICES),
        default="office",
        help="Floor-plan preset: office | corridor | wing.",
    )
    parser.add_argument("--save-gif", type=str, default="", help="Optional path to save animated GIF.")
    parser.add_argument("--save-png", type=str, default="", help="Save first frame snapshot to PNG and exit.")
    parser.add_argument(
        "--mode",
        choices=("centralized_demo", "decentralized"),
        default="centralized_demo",
        help="centralized_demo: legacy BFS planner; decentralized: discrete kernel + RF HUD.",
    )
    parser.add_argument(
        "--decentralized-policy",
        choices=("layout_bfs", "local_sense"),
        default="layout_bfs",
        help="layout_bfs: full layout + matching room BFS tree per drone (default). "
        "local_sense: limited sensing, frontier-BFS explorer + followers.",
    )
    parser.add_argument("--ticks", type=int, default=480, help="Decentralized horizon (simulation ticks).")
    parser.add_argument(
        "--explorer-phase-ticks",
        type=int,
        default=0,
        help="Decentralized: ticks per explorer before rotating to next UID. 0 = auto from horizon and fleet size.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--viz-comms-lines",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Draw faded RF links on-map (decentralized). Use --no-viz-comms-lines to disable.",
    )
    parser.add_argument(
        "--viz-comms-panel",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="RF telemetry side panel (decentralized). Use --no-viz-comms-panel to disable.",
    )
    parser.add_argument("--viz-comms-tail", type=int, default=18, help="Lines kept in RF telemetry tail.")
    parser.add_argument(
        "--viz-mesh-activity-tail",
        type=int,
        default=36,
        help=(
            "Lines kept in Telemetry for app/mesh gossip ([APP] adopt + [MESH] broadcast). "
            "0 disables that subsection."
        ),
    )
    parser.add_argument(
        "--viz-substeps",
        type=int,
        default=2,
        help=(
            "Decentralized: animation substeps between each discrete sim tick (minimum 1). "
            "Use 1 for fastest playback (no interpolation); increase for smoother motion. "
            "Frame delay is --viz-frame-ms if set, else --interval-ms / substeps."
        ),
    )
    parser.add_argument(
        "--viz-frame-ms",
        type=int,
        default=0,
        help=(
            "Decentralized: milliseconds between each drawn animation frame (each substep). "
            "If >0, sets playback speed directly (~1000/value Hz) and overrides --interval-ms for matplotlib timing. "
            "Example: --viz-substeps 6 --viz-frame-ms 16 ≈ 60 FPS with six interpolated poses per sim tick."
        ),
    )
    parser.add_argument(
        "--comms-log",
        type=str,
        default="",
        help="Decentralized: append-or-create this UTF-8 file with every RF CommEvent line (full mesh log).",
    )
    parser.add_argument(
        "--debug-oracle",
        action="store_true",
        help="Overlay ground-truth room IDs on the map (debug only).",
    )
    parser.add_argument(
        "--comm-backend",
        choices=("inproc", "udp"),
        default="udp",
        help="Decentralized: RF path — "
        "`udp` (default) multiprocess takeover sim via PropagationUDPTransmission (listen port = udp-base-port + uid); "
        "`inproc` single-process RadioMedium fallback.",
    )
    parser.add_argument(
        "--udp-base-port",
        type=int,
        default=8700,
        metavar="PORT",
        help="With --comm-backend udp: UDP listen port for drone UID i is PORT+i.",
    )
    args = parser.parse_args()

    building = load_layout(args.layout)

    if args.mode == "decentralized":
        radio_cfg = RadioConfig(
            cell_size_m=args.cell_m,
            freq_mhz=args.freq_mhz,
            tx_power_dbm=args.tx_dbm,
            distance_exponent=args.n_exp,
            lf_per_wall_cell_db=args.wall_db,
        )
        dec_kwargs = dict(
            layout_name=args.layout,
            n_drones=args.n_drones,
            n_ticks=max(1, args.ticks),
            radio_cfg=radio_cfg,
            rng=np.random.default_rng(int(args.seed)),
            rf_log_cap=max(256, int(args.viz_comms_tail) * 16),
            seed=int(args.seed),
            explorer_phase_ticks=(None if int(args.explorer_phase_ticks) <= 0 else int(args.explorer_phase_ticks)),
            decentralized_policy=str(args.decentralized_policy),
            mesh_activity_tail_cap=max(0, int(getattr(args, "viz_mesh_activity_tail", 0))),
        )
        if args.comm_backend == "udp":
            from swarm_sim.sim_kernel_udp import run_decentralized_udp_mesh

            timeline_dec, trace_events = run_decentralized_udp_mesh(
                building,
                udp_base_port=int(args.udp_base_port),
                **dec_kwargs,
            )
        else:
            timeline_dec, trace_events = run_decentralized(
                building,
                **dec_kwargs,
            )
        if args.comms_log.strip():
            log_path = pathlib.Path(args.comms_log.strip())
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as fh:
                fh.write("# swarm_sim decentralized RF mesh — all CommEvent rows\n")
                for ev in trace_events:
                    fh.write(ev.format_line() + "\n")
        return _animate_decentralized(args=args, building=building, timeline=timeline_dec)

    timeline, _parent, _edges = build_timeline(
        building,
        layout_name=args.layout,
        n_drones=args.n_drones,
        frames_per_edge=args.frames_per_edge,
        dwell_frames=args.dwell,
    )
    return _animate_centralized(args=args, building=building, timeline=timeline)


if __name__ == "__main__":
    raise SystemExit(main())
