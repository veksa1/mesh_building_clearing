"""HUD helpers for RF-plane visualization (sim observer, not agent knowledge)."""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.axes import Axes

from .radio import CommEvent

DEFAULT_OVERLAY_TTL = 14


def kind_color(msg_type: str) -> str:
    upper = msg_type.upper()
    if upper == "BEACON":
        return "#33bbee"
    if upper == "TOPOLOGY_MERGE":
        return "#ee7733"
    if upper == "TOKEN":
        return "#669933"
    return "#aaaaaa"


def outcome_alpha(outcome: str) -> float:
    if outcome == "delivered":
        return 0.9
    if outcome == "below_threshold":
        return 0.35
    return 0.5


@dataclass
class FadedLink:
    ticks_left: int
    r0: float
    c0: float
    r1: float
    c1: float
    msg_type: str
    outcome: str


class CommsOverlay:
    """Keeps recent RF links alive for a few ticks so bursts remain visible."""

    def __init__(self, ttl_ticks: int = DEFAULT_OVERLAY_TTL) -> None:
        self.ttl_ticks = ttl_ticks
        self.links: list[FadedLink] = []

    def ingest_tick(self, events: list[CommEvent]) -> None:
        for ev in events:
            if ev.src_pose_rcf is None or ev.dst_pose_rcf is None:
                continue
            if ev.outcome not in ("delivered", "below_threshold"):
                continue
            sr, sc = ev.src_pose_rcf
            dr, dc = ev.dst_pose_rcf
            self.links.append(
                FadedLink(
                    ticks_left=self.ttl_ticks,
                    r0=sr,
                    c0=sc,
                    r1=dr,
                    c1=dc,
                    msg_type=ev.msg_type,
                    outcome=ev.outcome,
                )
            )

        for lk in self.links:
            lk.ticks_left -= 1
        self.links = [lk for lk in self.links if lk.ticks_left > 0]


def format_rf_panel(*, lines: list[str], tail: int) -> str:
    tail_n = max(0, int(tail))
    shown = lines[-tail_n:] if tail_n else lines
    body = "\n".join(shown) if shown else "(no RF traffic yet)"
    return "RF plane (sim observer)\n" + "─" * 26 + "\n\n" + body


def plot_comm_links(
    ax: Axes,
    links: list[FadedLink],
    *,
    cell_m: float,
    ttl_ticks: int = DEFAULT_OVERLAY_TTL,
    linestyle: str = "--",
    linewidth: float = 1.35,
) -> list:
    """Returns matplotlib artists for all drawn segments (caller may remove between frames)."""
    artists: list = []
    ttl = max(ttl_ticks, 1)
    for lk in links:
        fade = max(float(lk.ticks_left) / float(ttl), 0.06)
        alpha = outcome_alpha(lk.outcome) * fade
        x0, x1 = lk.c0 * cell_m, lk.c1 * cell_m
        y0, y1 = lk.r0 * cell_m, lk.r1 * cell_m
        (ln,) = ax.plot(
            [x0, x1],
            [y0, y1],
            color=kind_color(lk.msg_type),
            linestyle=linestyle,
            linewidth=linewidth,
            alpha=alpha,
            zorder=4.5,
        )
        artists.append(ln)
    return artists
