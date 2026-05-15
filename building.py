"""Floorplans + room graphs for BFS takeover simulations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .navigation import nearest_floor_in_room


@dataclass(frozen=True)
class BuildingMap:
    wall: np.ndarray  # bool HxW — True blocks motion / treated as wall pixel for rays
    room_id: np.ndarray  # int HxW, -1 wall/outside
    centers: dict[int, tuple[float, float]]  # room -> centroid (row, col) float cell coords
    anchors: dict[int, tuple[int, int]]  # snapped grid cell per room for routing
    door_lobby_rc: tuple[int, int]  # lobby cell near primary upward doorway / staging
    adjacency: dict[int, tuple[int, ...]]
    entrance_room: int


def _finalize_building(
    wall: np.ndarray,
    rid: np.ndarray,
    adjacency: dict[int, tuple[int, ...]],
    entrance_room: int,
    *,
    door_pref_rc: tuple[float, float],
) -> BuildingMap:
    floor = ~wall
    rid = np.array(rid, dtype=np.int16, copy=True)
    stray = floor & (rid < 0)
    rid[stray] = entrance_room

    centers: dict[int, tuple[float, float]] = {}
    labels = np.unique(rid[floor])
    for k in labels:
        kk = int(k)
        mask = rid == kk
        if not np.any(mask):
            continue
        ys, xs = np.where(mask)
        centers[kk] = float(ys.mean()) + 0.5, float(xs.mean()) + 0.5

    anchors: dict[int, tuple[int, int]] = {}
    for kk in centers:
        cr, cc = centers[kk]
        anchors[kk] = nearest_floor_in_room(wall, rid, kk, cr, cc)

    door_lobby_rc = nearest_floor_in_room(wall, rid, entrance_room, door_pref_rc[0], door_pref_rc[1])

    return BuildingMap(
        wall=wall,
        room_id=rid,
        centers=centers,
        anchors=anchors,
        door_lobby_rc=door_lobby_rc,
        adjacency=adjacency,
        entrance_room=entrance_room,
    )


def build_small_office() -> BuildingMap:
    """
    Original demo building:

          [ R3 ] | [ R1 ] | [ R2 ]
          foyer------door-------upper split
                 [ R0 lobby ]

    BFS edges (by discovery): (0→1), (0→2), (1→3).
    """
    h, w = 54, 72
    wall = np.ones((h, w), dtype=bool)

    wall[8 : h - 8, 10 : w - 10] = False

    split_row = 37
    wall[split_row, 10 : w - 10] = True
    wall[split_row, 33:39] = False

    mid_col = 43
    wall[8:split_row, mid_col] = True
    wall[22:25, mid_col] = False

    sep_col = 26
    wall[8:split_row, sep_col] = True
    wall[29:32, sep_col] = False

    wall[8 : split_row + 1, 10] = True
    wall[8 : split_row + 1, w - 11] = True
    wall[8, 11 : w - 11] = True

    wall[22:25, mid_col] = False
    wall[29:32, sep_col] = False

    floor = ~wall
    rid = np.full((h, w), -1, dtype=np.int16)

    lobby = floor & (np.arange(h)[:, None] > split_row)
    upper = floor & (np.arange(h)[:, None] <= split_row)

    r3 = upper & (np.arange(w)[None, :] <= sep_col)
    r1 = upper & (np.arange(w)[None, :] >= sep_col + 1) & (np.arange(w)[None, :] <= mid_col - 1)
    r2 = upper & (np.arange(w)[None, :] >= mid_col + 1)

    rid[lobby] = 0
    rid[r3] = 3
    rid[r1] = 1
    rid[r2] = 2

    adjacency = {
        0: (1, 2),
        1: (0, 3),
        2: (0,),
        3: (1,),
    }

    return _finalize_building(wall, rid, adjacency, 0, door_pref_rc=(float(split_row) + 2.0, 36.0))


def build_vertical_corridor() -> BuildingMap:
    """
    Narrow tower / corridor stack — purely linear graph:

        [ R3 ]
        [ R2 ]
        [ R1 ]
        [ R0 lobby ]

    BFS order follows the chain 0→1→2→3.
    """
    h, w = 58, 44
    wall = np.ones((h, w), dtype=bool)
    wall[8 : h - 8, 12 : w - 12] = False

    split01, split12, split23 = 45, 33, 21

    def band_wall(row: int) -> None:
        wall[row, 12 : w - 12] = True
        wall[row, 19:25] = False

    band_wall(split01)
    band_wall(split12)
    band_wall(split23)

    wall[8 : split23, 12] = True
    wall[8 : split23, w - 13] = True
    wall[8, 13 : w - 13] = True

    wall[split01, 19:25] = False
    wall[split12, 19:25] = False
    wall[split23, 19:25] = False

    floor = ~wall
    rid = np.full((h, w), -1, dtype=np.int16)

    rid[floor & (np.arange(h)[:, None] > split01)] = 0
    rid[floor & (np.arange(h)[:, None] > split12) & (np.arange(h)[:, None] <= split01)] = 1
    rid[floor & (np.arange(h)[:, None] > split23) & (np.arange(h)[:, None] <= split12)] = 2
    rid[floor & (np.arange(h)[:, None] <= split23)] = 3

    adjacency = {
        0: (1,),
        1: (0, 2),
        2: (1, 3),
        3: (2,),
    }

    return _finalize_building(wall, rid, adjacency, 0, door_pref_rc=(float(split01) + 1.5, 22.0))


def build_wing_office() -> BuildingMap:
    """
    Same logical graph as ``office`` but a different footprint:

        [ R3 ]──[ R1 ]──[ R2 ]
                  │
                [ R0 ]

    Long horizontal upper floor + lobby tucked under R1.
    """
    h, w = 54, 76
    wall = np.ones((h, w), dtype=bool)
    wall[8 : h - 8, 10 : w - 10] = False

    split_row = 38
    wall[split_row, 10 : w - 10] = True
    wall[split_row, 34:42] = False

    mid_col = 46
    wall[8 : split_row, mid_col] = True
    wall[18:21, mid_col] = False

    spine_col = 30
    wall[split_row + 1 : h - 8, spine_col] = True
    wall[split_row + 1 : h - 8, spine_col + 1] = True
    wall[42:46, spine_col] = False
    wall[42:46, spine_col + 1] = False

    wall[8 : split_row + 1, 10] = True
    wall[8 : split_row + 1, w - 11] = True
    wall[8, 11 : w - 11] = True

    wall[18:21, mid_col] = False

    floor = ~wall
    rid = np.full((h, w), -1, dtype=np.int16)

    lobby = floor & (np.arange(h)[:, None] > split_row) & (np.arange(w)[None, :] >= spine_col + 2)
    upper = floor & (np.arange(h)[:, None] <= split_row)

    r3 = upper & (np.arange(w)[None, :] <= spine_col - 1)
    r1 = upper & (np.arange(w)[None, :] >= spine_col + 2) & (np.arange(w)[None, :] <= mid_col - 1)
    r2 = upper & (np.arange(w)[None, :] >= mid_col + 1)

    rid[lobby] = 0
    rid[r3] = 3
    rid[r1] = 1
    rid[r2] = 2

    adjacency = {
        0: (1,),
        1: (0, 2, 3),
        2: (1,),
        3: (1,),
    }

    return _finalize_building(wall, rid, adjacency, 0, door_pref_rc=(float(split_row) + 2.0, 37.0))


def load_layout(name: str) -> BuildingMap:
    """Return a floorplan by layout key (see ``LAYOUT_CHOICES``)."""
    builders = {
        "office": build_small_office,
        "corridor": build_vertical_corridor,
        "wing": build_wing_office,
    }
    key = name.strip().lower()
    if key not in builders:
        raise ValueError(f"unknown layout {name!r}; choose one of {sorted(builders)}")
    return builders[key]()


LAYOUT_CHOICES = ("office", "corridor", "wing")
