"""Load editor-shaped floorplan JSON into a ``BuildingMap`` + raster grids.

The schema mirrors ``web/types/index.ts FloorplanData`` exactly so the same JSON
can seed the browser editor and the Python simulation. Rasterization parity with
``web/lib/rasterize.ts`` is kept by porting the Bresenham line algorithm and the
two-grid trick (full grid for room flood-fill, doors-erased grid for navigation).
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .building import BuildingMap


# Wall material attenuation table — matches web/constants.ts WALL_MATERIALS.
_MATERIAL_DB: dict[str, float] = {
    "concrete": 15.0,
    "brick": 10.0,
    "drywall": 5.0,
    "glass": 3.0,
}


@dataclass(frozen=True)
class FloorplanRaster:
    """Result of loading + rasterizing a floorplan JSON file."""

    name: str
    rows: int
    cols: int
    cell_size_m: float
    wall_grid: np.ndarray  # bool HxW — navigation: doors erased
    wall_grid_full: np.ndarray  # bool HxW — room flood-fill: walls intact at door cells
    wall_db_grid: np.ndarray  # float HxW — per-wall-cell attenuation
    room_id: np.ndarray  # int16 HxW — flood-fill room labels (-1 = wall/outside)
    adjacency: dict[int, tuple[int, ...]]
    entrance_rc: tuple[int, int]
    target_rc: tuple[int, int]
    entrance_room: int
    target_room: int
    door_lobby_rc: tuple[int, int]
    raw: dict[str, Any]


def _bresenham(r0: int, c0: int, r1: int, c1: int) -> list[tuple[int, int]]:
    """Integer Bresenham line — same convention as web/lib/algorithms/bresenham.ts."""
    out: list[tuple[int, int]] = []
    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    sr = 1 if r0 < r1 else -1
    sc = 1 if c0 < c1 else -1
    err = dc - dr
    rr, cc = r0, c0
    while True:
        out.append((rr, cc))
        if rr == r1 and cc == c1:
            break
        e2 = 2 * err
        if e2 > -dr:
            err -= dr
            cc += sc
        if e2 < dc:
            err += dc
            rr += sr
    return out


def _label_regions(wall_grid_full: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected flood-fill on free cells; -1 marks wall/outside. Same as web floodFill.ts."""
    h, w = wall_grid_full.shape
    labels = np.full((h, w), -1, dtype=np.int16)
    next_id = 0
    for r in range(h):
        for c in range(w):
            if wall_grid_full[r, c] or labels[r, c] != -1:
                continue
            stack: list[tuple[int, int]] = [(r, c)]
            labels[r, c] = next_id
            while stack:
                rr, cc = stack.pop()
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = rr + dr, cc + dc
                    if 0 <= nr < h and 0 <= nc < w and not wall_grid_full[nr, nc] and labels[nr, nc] == -1:
                        labels[nr, nc] = next_id
                        stack.append((nr, nc))
            next_id += 1
    return labels, next_id


def _door_room_pair(
    door: dict[str, Any], labels: np.ndarray
) -> tuple[int, int] | None:
    """Sample 1–3 cells perpendicular to the door axis to find the two rooms it joins."""
    h, w = labels.shape
    cr = int(door["centerCell"]["row"])
    cc = int(door["centerCell"]["col"])
    axis = door.get("dominantAxis", "row")
    side_a = -1
    side_b = -1
    for off in (1, 2, 3):
        if axis == "col":
            ar, ac = cr - off, cc
            br, bc = cr + off, cc
        else:
            ar, ac = cr, cc - off
            br, bc = cr, cc + off
        if side_a < 0 and 0 <= ar < h and 0 <= ac < w:
            v = int(labels[ar, ac])
            if v >= 0:
                side_a = v
        if side_b < 0 and 0 <= br < h and 0 <= bc < w:
            v = int(labels[br, bc])
            if v >= 0:
                side_b = v
        if side_a >= 0 and side_b >= 0:
            break
    if side_a < 0 or side_b < 0 or side_a == side_b:
        return None
    return (side_a, side_b)


def _compute_door_lobby_rc(
    wall_grid: np.ndarray,
    labels: np.ndarray,
    entrance_room: int,
    entrance_rc: tuple[int, int],
    doors_for_entrance: list[dict[str, Any]],
) -> tuple[int, int]:
    """Pick a walkable cell on the entrance side of the closest door — used for spawn staging."""
    if not doors_for_entrance:
        return entrance_rc
    h, w = wall_grid.shape
    best_cell: tuple[int, int] = entrance_rc
    best_d = float("inf")
    er, ec = entrance_rc
    for door in doors_for_entrance:
        cr = int(door["centerCell"]["row"])
        cc = int(door["centerCell"]["col"])
        radius = max(1, int(door.get("widthCells", 4)) // 2)
        axis = door.get("dominantAxis", "row")
        for off in range(-radius - 2, radius + 3):
            for side in (-2, -1, 0, 1, 2):
                if axis == "col":
                    rr = cr + side
                    ccc = cc + off
                else:
                    rr = cr + off
                    ccc = cc + side
                if not (0 <= rr < h and 0 <= ccc < w):
                    continue
                if wall_grid[rr, ccc]:
                    continue
                if int(labels[rr, ccc]) != entrance_room:
                    continue
                d = (rr - er) ** 2 + (ccc - ec) ** 2
                if d < best_d:
                    best_d = d
                    best_cell = (rr, ccc)
    return best_cell


def _bfs_floor_neighbor(
    wall_grid: np.ndarray, r: int, c: int
) -> tuple[int, int]:
    """If (r,c) is a wall, fall back to the nearest walkable cell."""
    h, w = wall_grid.shape
    if 0 <= r < h and 0 <= c < w and not wall_grid[r, c]:
        return (r, c)
    seen: set[tuple[int, int]] = {(r, c)}
    q: deque[tuple[int, int]] = deque([(r, c)])
    while q:
        rr, cc = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = rr + dr, cc + dc
            if not (0 <= nr < h and 0 <= nc < w):
                continue
            if (nr, nc) in seen:
                continue
            seen.add((nr, nc))
            if not wall_grid[nr, nc]:
                return (nr, nc)
            q.append((nr, nc))
    return (r, c)


def rasterize_floorplan(data: dict[str, Any]) -> FloorplanRaster:
    """Apply walls + doors → grids + room labels + adjacency."""
    rows = int(data["gridRows"])
    cols = int(data["gridCols"])
    cell_size_m = float(data.get("cellSizeM", 0.22))
    wall_grid_full = np.zeros((rows, cols), dtype=bool)
    wall_db_grid = np.zeros((rows, cols), dtype=np.float32)

    for seg in data.get("walls", []):
        material = str(seg.get("material", "drywall"))
        db = _MATERIAL_DB.get(material, 5.0)
        cells = _bresenham(
            int(seg["start"]["row"]),
            int(seg["start"]["col"]),
            int(seg["end"]["row"]),
            int(seg["end"]["col"]),
        )
        for r, c in cells:
            if 0 <= r < rows and 0 <= c < cols:
                wall_grid_full[r, c] = True
                wall_db_grid[r, c] = db

    wall_grid = wall_grid_full.copy()
    for door in data.get("doors", []):
        radius = max(1, int(door.get("widthCells", 4)) // 2)
        cr = int(door["centerCell"]["row"])
        cc = int(door["centerCell"]["col"])
        axis = door.get("dominantAxis", "row")
        for off in range(-radius, radius + 1):
            r = cr + (off if axis == "row" else 0)
            c = cc + (off if axis == "col" else 0)
            if 0 <= r < rows and 0 <= c < cols:
                wall_grid[r, c] = False
                wall_db_grid[r, c] = 0.0

    labels, _ = _label_regions(wall_grid_full)

    entrance_pt = data.get("entrance")
    target_pt = data.get("target")
    if entrance_pt is None or target_pt is None:
        raise ValueError("floorplan must specify entrance and target points")
    entrance_rc = _bfs_floor_neighbor(wall_grid, int(entrance_pt["row"]), int(entrance_pt["col"]))
    target_rc = _bfs_floor_neighbor(wall_grid, int(target_pt["row"]), int(target_pt["col"]))

    entrance_room = int(labels[entrance_rc[0], entrance_rc[1]])
    target_room = int(labels[target_rc[0], target_rc[1]])
    if entrance_room < 0 or target_room < 0:
        raise ValueError("entrance / target cells fall on a wall — adjust the floorplan")

    adjacency: dict[int, set[int]] = {}
    for door in data.get("doors", []):
        pair = _door_room_pair(door, labels)
        if pair is None:
            continue
        a, b = pair
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    for room in np.unique(labels[labels >= 0]):
        adjacency.setdefault(int(room), set())

    # Drop rooms unreachable from the entrance through doors — the web compiler
    # filters those out (an "outside perimeter" region from flood-fill is the
    # common offender), so we keep parity here.
    reachable: set[int] = {entrance_room}
    stack = [entrance_room]
    while stack:
        u = stack.pop()
        for v in adjacency.get(u, ()):
            if v not in reachable:
                reachable.add(v)
                stack.append(v)

    if target_room not in reachable:
        raise ValueError(
            f"target room {target_room} is not reachable from entrance {entrance_room} via doors"
        )

    adjacency_t: dict[int, tuple[int, ...]] = {
        k: tuple(sorted(x for x in v if x in reachable))
        for k, v in adjacency.items()
        if k in reachable
    }
    rid_filtered = labels.copy()
    if reachable:
        mask_unreachable = np.isin(labels, sorted(reachable), invert=True) & (labels >= 0)
        rid_filtered[mask_unreachable] = -1

    doors_for_entrance: list[dict[str, Any]] = []
    for door in data.get("doors", []):
        pair = _door_room_pair(door, labels)
        if pair is None:
            continue
        if entrance_room in pair:
            doors_for_entrance.append(door)
    door_lobby_rc = _compute_door_lobby_rc(
        wall_grid, labels, entrance_room, entrance_rc, doors_for_entrance
    )

    return FloorplanRaster(
        name=str(data.get("name", "floorplan")),
        rows=rows,
        cols=cols,
        cell_size_m=cell_size_m,
        wall_grid=wall_grid,
        wall_grid_full=wall_grid_full,
        wall_db_grid=wall_db_grid,
        room_id=rid_filtered,
        adjacency=adjacency_t,
        entrance_rc=entrance_rc,
        target_rc=target_rc,
        entrance_room=entrance_room,
        target_room=target_room,
        door_lobby_rc=door_lobby_rc,
        raw=data,
    )


def building_from_raster(raster: FloorplanRaster) -> BuildingMap:
    """Wrap a rasterized floorplan as a ``BuildingMap`` (centroids + anchors snapped to floor)."""
    floor = ~raster.wall_grid
    rid = raster.room_id

    centers: dict[int, tuple[float, float]] = {}
    anchors: dict[int, tuple[int, int]] = {}
    for room_id in np.unique(rid[rid >= 0]):
        mask = rid == int(room_id)
        if not np.any(mask):
            continue
        ys, xs = np.where(mask)
        cr = float(ys.mean()) + 0.5
        cc = float(xs.mean()) + 0.5
        centers[int(room_id)] = (cr, cc)
        free_mask = mask & floor
        if not np.any(free_mask):
            anchors[int(room_id)] = (int(ys[0]), int(xs[0]))
            continue
        fys, fxs = np.where(free_mask)
        d2 = (fys.astype(np.float64) - cr) ** 2 + (fxs.astype(np.float64) - cc) ** 2
        j = int(np.argmin(d2))
        anchors[int(room_id)] = (int(fys[j]), int(fxs[j]))

    if raster.entrance_room not in anchors:
        anchors[raster.entrance_room] = raster.entrance_rc
        centers[raster.entrance_room] = (
            float(raster.entrance_rc[0]) + 0.5,
            float(raster.entrance_rc[1]) + 0.5,
        )

    return BuildingMap(
        wall=raster.wall_grid,
        room_id=rid,
        centers=centers,
        anchors=anchors,
        door_lobby_rc=raster.door_lobby_rc,
        adjacency=raster.adjacency,
        entrance_room=raster.entrance_room,
    )


def load_floorplan(path: str | Path) -> FloorplanRaster:
    """Read JSON from disk and return rasterized + labelled floorplan."""
    text = Path(path).read_text(encoding="utf-8")
    return rasterize_floorplan(json.loads(text))
