"""Simulation truth: walls, motion, local sensing. Agents never receive global adjacency."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .building import BuildingMap


@dataclass(frozen=True)
class CellReading:
    """One sensed cell: coordinates + whether it is a wall (True) or walkable floor (False)."""

    r: int
    c: int
    is_wall: bool


class Environment:
    """
    Wraps ``BuildingMap`` for physics only.

    Agents interact through ``sense_disc``, ``legal_steps``, ``walkable`` — not ``adjacency``.
    """

    def __init__(self, building: BuildingMap) -> None:
        self._b = building
        self.wall = building.wall

    @property
    def shape(self) -> tuple[int, int]:
        return self.wall.shape

    def walkable(self, r: int, c: int) -> bool:
        h, w = self.shape
        return 0 <= r < h and 0 <= c < w and not self.wall[r, c]

    def legal_steps(self, r: int, c: int) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if self.walkable(nr, nc):
                out.append((nr, nc))
        return out

    def sense_disc(self, r: int, c: int, radius: int) -> list[CellReading]:
        """
        Local occupancy sensing: all cells with Manhattan distance <= ``radius`` from (r,c).

        Clipped to map bounds. This is the only geometric truth exposed to agents (no room IDs).
        """
        h, w = self.shape
        readings: list[CellReading] = []
        for dr in range(-radius, radius + 1):
            rem = radius - abs(dr)
            for dc in range(-rem, rem + 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < h and 0 <= cc < w:
                    readings.append(CellReading(rr, cc, bool(self.wall[rr, cc])))
        return readings

    def detect_openings(
        self,
        r: int,
        c: int,
        *,
        radius: int,
        rng: np.random.Generator | None = None,
    ) -> list:
        """Local vision helper: doorway-shaped openings from ``wall`` patch only."""
        from .perception import detect_openings as _detect

        return _detect(self.wall, r, c, radius=radius, rng=rng)
