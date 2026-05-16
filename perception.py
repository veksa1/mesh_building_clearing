"""Simulated onboard vision: doorway-shaped detections from local wall geometry only."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from enum import Enum

import numpy as np


class VisualDetectionKind(str, Enum):
    DOORWAY_GAP = "DOORWAY_GAP"
    CORRIDOR_BRANCH = "CORRIDOR_BRANCH"


@dataclass(frozen=True)
class VisualDetection:
    """YOLO-like structured detection (bearing + corridor axis + patch signature)."""

    kind: VisualDetectionKind
    bearing_dr: int
    bearing_dc: int
    corridor_dr: int
    corridor_dc: int
    anchor_r: int
    anchor_c: int
    width_cells: int
    confidence: float
    signature: str


def _oob_wall(wall: np.ndarray, r: int, c: int) -> bool:
    h, w = wall.shape
    if r < 0 or c < 0 or r >= h or c >= w:
        return True
    return bool(wall[r, c])


def _patch_signature(wall: np.ndarray, ar: int, ac: int, half: int = 2) -> str:
    """Stable short digest of wall bits in (2*half+1)^2 around anchor."""
    h, w = wall.shape
    bits: list[int] = []
    for dr in range(-half, half + 1):
        for dc in range(-half, half + 1):
            rr, cc = ar + dr, ac + dc
            bits.append(1 if _oob_wall(wall, rr, cc) else 0)
    raw = bytes(bits)
    return hex(zlib.adler32(raw) & 0xFFFFFFFF)[2:]


def _bearing_from_ego(er: int, ec: int, ar: int, ac: int) -> tuple[int, int]:
    dr = ar - er
    dc = ac - ec
    if dr == 0 and dc == 0:
        return 0, 0
    adr = abs(dr)
    adc = abs(dc)
    if adr >= adc:
        return (1 if dr > 0 else -1), 0
    return 0, (1 if dc > 0 else -1)


def detect_openings(
    wall: np.ndarray,
    ego_r: int,
    ego_c: int,
    *,
    radius: int,
    rng: np.random.Generator | None = None,
    dropout_prob: float = 0.0,
    noise_span: float = 0.04,
) -> list[VisualDetection]:
    """
    Find doorway-shaped anchors in a square patch from ``wall`` only (no room ids).

    Templates cover classic slits (E/W pinch by N+S walls), multi-cell widths, and slab-gap edges:
    N/S corridor pinch with one lateral wall and cleared diagonal throats (no oracle geometry).

    Optional RNG perturbs confidence / dropout.
    """
    h, w = wall.shape
    out: list[VisualDetection] = []
    seen_sig: set[tuple[object, ...]] = set()

    r0 = max(0, ego_r - radius)
    r1 = min(h - 1, ego_r + radius)
    c0 = max(0, ego_c - radius)
    c1 = min(w - 1, ego_c + radius)

    for rr in range(r0, r1 + 1):
        for cc in range(c0, c1 + 1):
            if _oob_wall(wall, rr, cc):
                continue
            # N-S corridor through vertical slit (walls E/W)
            ns_door = (
                _oob_wall(wall, rr, cc - 1)
                and _oob_wall(wall, rr, cc + 1)
                and not _oob_wall(wall, rr - 1, cc)
                and not _oob_wall(wall, rr + 1, cc)
            )
            # E-W corridor through horizontal slit (walls N/S)
            ew_door = (
                _oob_wall(wall, rr - 1, cc)
                and _oob_wall(wall, rr + 1, cc)
                and not _oob_wall(wall, rr, cc - 1)
                and not _oob_wall(wall, rr, cc + 1)
            )
            # Wide E-W opening (two adjacent throat cells): common in raster floorplans
            ew_wide = False
            if cc + 1 < w:
                ew_wide = (
                    not _oob_wall(wall, rr, cc)
                    and not _oob_wall(wall, rr, cc + 1)
                    and _oob_wall(wall, rr - 1, cc)
                    and _oob_wall(wall, rr + 1, cc)
                    and _oob_wall(wall, rr - 1, cc + 1)
                    and _oob_wall(wall, rr + 1, cc + 1)
                )
            ns_wide = False
            if rr + 1 < h:
                ns_wide = (
                    not _oob_wall(wall, rr, cc)
                    and not _oob_wall(wall, rr + 1, cc)
                    and _oob_wall(wall, rr, cc - 1)
                    and _oob_wall(wall, rr, cc + 1)
                    and _oob_wall(wall, rr + 1, cc - 1)
                    and _oob_wall(wall, rr + 1, cc + 1)
                )

            if ew_wide:
                kind = VisualDetectionKind.DOORWAY_GAP
                mid_c = cc + 1
                bdr, bdc = _bearing_from_ego(ego_r, ego_c, rr, mid_c)
                cdr, cdc = 0, 1
                sig = _patch_signature(wall, rr, cc, half=3)
                key = (bdr, bdc, cdr, cdc, sig, "eww")
                if key in seen_sig:
                    continue
                seen_sig.add(key)
                conf = 0.9
                if rng is not None and rng.random() < dropout_prob:
                    continue
                if rng is not None:
                    conf = float(np.clip(conf + rng.uniform(-noise_span, noise_span), 0.05, 0.99))
                out.append(
                    VisualDetection(
                        kind=kind,
                        bearing_dr=bdr,
                        bearing_dc=bdc,
                        corridor_dr=cdr,
                        corridor_dc=cdc,
                        anchor_r=rr,
                        anchor_c=cc,
                        width_cells=2,
                        confidence=conf,
                        signature=sig,
                    )
                )
                continue

            if ns_wide:
                kind = VisualDetectionKind.DOORWAY_GAP
                mid_r = rr + 1
                bdr, bdc = _bearing_from_ego(ego_r, ego_c, mid_r, cc)
                cdr, cdc = 1, 0
                sig = _patch_signature(wall, rr, cc, half=3)
                key = (bdr, bdc, cdr, cdc, sig, "nsw")
                if key in seen_sig:
                    continue
                seen_sig.add(key)
                conf = 0.9
                if rng is not None and rng.random() < dropout_prob:
                    continue
                if rng is not None:
                    conf = float(np.clip(conf + rng.uniform(-noise_span, noise_span), 0.05, 0.99))
                out.append(
                    VisualDetection(
                        kind=kind,
                        bearing_dr=bdr,
                        bearing_dc=bdc,
                        corridor_dr=cdr,
                        corridor_dc=cdc,
                        anchor_r=rr,
                        anchor_c=cc,
                        width_cells=2,
                        confidence=conf,
                        signature=sig,
                    )
                )
                continue

            # Wide openings miss slab-gap edges: N/S corridor pinch with exactly one lateral wall.
            # Require corners on the blocked lateral side to be walkable (past the pinch) *and* corners
            # on the barrier normal to show clear throat — rules out hollow rectangles whose rim still
            # matches XOR lateral walls (maps edge).
            lw_side = _oob_wall(wall, rr, cc - 1)
            rw_side = _oob_wall(wall, rr, cc + 1)
            hb_ns_pinch = False
            if (
                not _oob_wall(wall, rr, cc)
                and not _oob_wall(wall, rr - 1, cc)
                and not _oob_wall(wall, rr + 1, cc)
                and lw_side != rw_side
            ):
                if lw_side and not rw_side:
                    hb_ns_pinch = not _oob_wall(wall, rr - 1, cc - 1) and not _oob_wall(
                        wall, rr + 1, cc - 1
                    )
                elif rw_side and not lw_side:
                    hb_ns_pinch = not _oob_wall(wall, rr - 1, cc + 1) and not _oob_wall(
                        wall, rr + 1, cc + 1
                    )

            nw_side = _oob_wall(wall, rr - 1, cc)
            sw_side = _oob_wall(wall, rr + 1, cc)
            vb_ew_pinch = False
            if (
                not _oob_wall(wall, rr, cc)
                and not _oob_wall(wall, rr, cc - 1)
                and not _oob_wall(wall, rr, cc + 1)
                and nw_side != sw_side
            ):
                if nw_side and not sw_side:
                    vb_ew_pinch = (
                        not _oob_wall(wall, rr + 1, cc - 1)
                        and not _oob_wall(wall, rr + 1, cc + 1)
                        and not _oob_wall(wall, rr - 1, cc - 1)
                        and not _oob_wall(wall, rr - 1, cc + 1)
                    )
                elif sw_side and not nw_side:
                    vb_ew_pinch = (
                        not _oob_wall(wall, rr - 1, cc - 1)
                        and not _oob_wall(wall, rr - 1, cc + 1)
                        and not _oob_wall(wall, rr + 1, cc - 1)
                        and not _oob_wall(wall, rr + 1, cc + 1)
                    )

            if hb_ns_pinch:
                kind = VisualDetectionKind.DOORWAY_GAP
                bdr, bdc = _bearing_from_ego(ego_r, ego_c, rr, cc)
                cdr, cdc = 1, 0
                sig = _patch_signature(wall, rr, cc, half=3)
                key = (bdr, bdc, cdr, cdc, sig, "hp")
                if key in seen_sig:
                    continue
                seen_sig.add(key)
                conf = 0.89
                if rng is not None and rng.random() < dropout_prob:
                    continue
                if rng is not None:
                    conf = float(np.clip(conf + rng.uniform(-noise_span, noise_span), 0.05, 0.99))
                out.append(
                    VisualDetection(
                        kind=kind,
                        bearing_dr=bdr,
                        bearing_dc=bdc,
                        corridor_dr=cdr,
                        corridor_dc=cdc,
                        anchor_r=rr,
                        anchor_c=cc,
                        width_cells=1,
                        confidence=conf,
                        signature=sig,
                    )
                )
                continue

            if vb_ew_pinch:
                kind = VisualDetectionKind.DOORWAY_GAP
                bdr, bdc = _bearing_from_ego(ego_r, ego_c, rr, cc)
                cdr, cdc = 0, 1
                sig = _patch_signature(wall, rr, cc, half=3)
                key = (bdr, bdc, cdr, cdc, sig, "vp")
                if key in seen_sig:
                    continue
                seen_sig.add(key)
                conf = 0.89
                if rng is not None and rng.random() < dropout_prob:
                    continue
                if rng is not None:
                    conf = float(np.clip(conf + rng.uniform(-noise_span, noise_span), 0.05, 0.99))
                out.append(
                    VisualDetection(
                        kind=kind,
                        bearing_dr=bdr,
                        bearing_dc=bdc,
                        corridor_dr=cdr,
                        corridor_dc=cdc,
                        anchor_r=rr,
                        anchor_c=cc,
                        width_cells=1,
                        confidence=conf,
                        signature=sig,
                    )
                )
                continue

            if ns_door:
                kind = VisualDetectionKind.DOORWAY_GAP
                bdr, bdc = _bearing_from_ego(ego_r, ego_c, rr, cc)
                cdr, cdc = 1, 0
            elif ew_door:
                kind = VisualDetectionKind.DOORWAY_GAP
                bdr, bdc = _bearing_from_ego(ego_r, ego_c, rr, cc)
                cdr, cdc = 0, 1
            else:
                continue

            sig = _patch_signature(wall, rr, cc)
            key = (bdr, bdc, cdr, cdc, sig, "1")
            if key in seen_sig:
                continue
            seen_sig.add(key)

            conf = 0.92
            if rng is not None:
                if rng.random() < dropout_prob:
                    continue
                conf = float(np.clip(conf + rng.uniform(-noise_span, noise_span), 0.05, 0.99))

            out.append(
                VisualDetection(
                    kind=kind,
                    bearing_dr=bdr,
                    bearing_dc=bdc,
                    corridor_dr=cdr,
                    corridor_dc=cdc,
                    anchor_r=rr,
                    anchor_c=cc,
                    width_cells=1,
                    confidence=conf,
                    signature=sig,
                )
            )

    return out
