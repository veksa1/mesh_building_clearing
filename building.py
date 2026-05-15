"""Small synthetic floorplan + room graph for BFS takeover."""

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
    door_lobby_rc: tuple[int, int]  # lobby cell north of split used for staging layout
    adjacency: dict[int, tuple[int, ...]]
    entrance_room: int


def build_small_office() -> BuildingMap:
    """
    Hand-authored micro-building:

          [ R3 ] | [ R1 ] | [ R2 ]
          foyer------door-------upper split
                 [ R0 lobby ]

    BFS tree from entrance R0 fans into R1 & R2, then R3 attaches to R1 only.
    """
    h, w = 54, 72
    wall = np.ones((h, w), dtype=bool)

    # Outer shell interior walkable placeholder
    wall[8 : h - 8, 10 : w - 10] = False

    # Horizontal slab between lobby (south) and upper floors
    split_row = 37
    wall[split_row, 10 : w - 10] = True
    wall[split_row, 33:39] = False  # door lobby↔upper

    # Vertical split between upper-left (R1) and upper-right (R2)
    mid_col = 43
    wall[8:split_row, mid_col] = True
    wall[22:25, mid_col] = False

    # Wall separating west wing R3 from R1
    sep_col = 26
    wall[8:split_row, sep_col] = True
    wall[29:32, sep_col] = False

    # Decorative outer walls already closed by border carve — thicken weak corners
    wall[8 : split_row + 1, 10] = True
    wall[8 : split_row + 1, w - 11] = True
    wall[8, 11 : w - 11] = True

    # Re-open doors if vertical lines clobbered them
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

    # Any lingering floor cells default to lobby for safety
    stray = floor & (rid < 0)
    rid[stray] = 0

    centers: dict[int, tuple[float, float]] = {}
    for k in range(4):
        mask = rid == k
        if not np.any(mask):
            continue
        ys, xs = np.where(mask)
        centers[k] = float(ys.mean()) + 0.5, float(xs.mean()) + 0.5

    anchors: dict[int, tuple[int, int]] = {}
    for k in centers:
        cr, cc = centers[k]
        anchors[k] = nearest_floor_in_room(wall, rid, k, cr, cc)

    # Lobby cell closest to the stairwell door (columns 33–39), still in room 0
    door_lobby_rc = nearest_floor_in_room(wall, rid, 0, float(split_row) + 2.0, 36.0)

    adjacency: dict[int, tuple[int, ...]] = {
        0: (1, 2),
        1: (0, 3),
        2: (0,),
        3: (1,),
    }

    return BuildingMap(
        wall=wall,
        room_id=rid,
        centers=centers,
        anchors=anchors,
        door_lobby_rc=door_lobby_rc,
        adjacency=adjacency,
        entrance_room=0,
    )
