"""Grid-based shortest paths for drones (walkable = not wall)."""

from __future__ import annotations

from collections import deque

import numpy as np


def nearest_floor_in_room(
    wall: np.ndarray,
    rid: np.ndarray,
    room_id: int,
    pref_r: float,
    pref_c: float,
) -> tuple[int, int]:
    """Closest walkable cell inside ``room_id`` to a preferred (row, col) float position."""
    ys, xs = np.where((rid == room_id) & (~wall))
    if ys.size == 0:
        raise ValueError(f"no floor cells for room {room_id}")
    d = (ys.astype(np.float64) - pref_r) ** 2 + (xs.astype(np.float64) - pref_c) ** 2
    j = int(np.argmin(d))
    return int(ys[j]), int(xs[j])


def grid_shortest_path(
    wall: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]]:
    """4-neighbour BFS shortest path on ``~wall`` cells."""
    if start == goal:
        return [start]
    h, w = wall.shape
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    q: deque[tuple[int, int]] = deque([start])
    found = False
    while q:
        r, c = q.popleft()
        if (r, c) == goal:
            found = True
            break
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not wall[nr, nc]:
                if (nr, nc) not in prev:
                    prev[(nr, nc)] = (r, c)
                    q.append((nr, nc))
    if not found:
        return [start, goal]

    out: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = goal
    while cur is not None:
        out.append(cur)
        cur = prev[cur]
    out.reverse()
    return out


def cell_to_rcf(cell: tuple[int, int]) -> tuple[float, float]:
    return float(cell[0]) + 0.5, float(cell[1]) + 0.5


def polyline_rcf(path_cells: list[tuple[int, int]]) -> list[tuple[float, float]]:
    return [cell_to_rcf(c) for c in path_cells]


def interpolate_polyline(path_cells: list[tuple[int, int]], t: float) -> tuple[float, float]:
    """Arc-length interpolation, ``t`` in [0, 1]."""
    pts = polyline_rcf(path_cells)
    if len(pts) == 1:
        return pts[0]
    seg_len: list[float] = []
    for i in range(len(pts) - 1):
        seg_len.append(float(np.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])))
    total = float(sum(seg_len))
    if total < 1e-9:
        return pts[0]
    target = float(np.clip(t, 0.0, 1.0)) * total
    acc = 0.0
    for i, ln in enumerate(seg_len):
        if acc + ln >= target - 1e-12:
            u = 0.0 if ln < 1e-12 else (target - acc) / ln
            return (
                pts[i][0] + u * (pts[i + 1][0] - pts[i][0]),
                pts[i][1] + u * (pts[i + 1][1] - pts[i][1]),
            )
        acc += ln
    return pts[-1]


def sample_polyline(path_cells: list[tuple[int, int]], k: int) -> list[tuple[float, float]]:
    """Return ``k`` positions spaced by arc length along the polyline (endpoints included when k>=2)."""
    if k <= 0:
        return []
    if len(path_cells) == 0:
        return []
    if k == 1:
        return [interpolate_polyline(path_cells, 0.5)]
    return [interpolate_polyline(path_cells, j / (k - 1)) for j in range(k)]


def concat_paths(parts: list[list[tuple[int, int]]]) -> list[tuple[int, int]]:
    full: list[tuple[int, int]] = []
    for p in parts:
        if not p:
            continue
        if full and full[-1] == p[0]:
            full.extend(p[1:])
        else:
            full.extend(p)
    return full
