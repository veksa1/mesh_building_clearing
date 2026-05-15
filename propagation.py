"""
Radio propagation helpers for the tactical mesh demo.

Path loss follows the compact indoor/outdoor fit documented in Report ITU-R P.2346
(equation (2) in P.2346-5), relating distance-dependent attenuation to free space:

    L(dB) = 20 log10(f_MHz) + N log10(d_m) - 27.55 + L_f(dB)

When N = 20 and L_f = 0 this reduces to free-space path loss; indoor measurements in
the report use larger N (e.g. ~30 within timber-framed houses) and/or fixed excess L_f
for wall penetration — see ITU-R P.2346 for context & measurement scenarios.

Reference (user-provided series): https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-P.2346-3-2019-PDF-E.pdf
"""

from __future__ import annotations

import numpy as np


def path_loss_db(
    distance_m: np.ndarray | float,
    freq_mhz: float,
    *,
    distance_exponent: float = 28.0,
    lf_fixed_db: float = 0.0,
    d_floor_m: float = 0.5,
) -> np.ndarray | float:
    """
    ITU-R P.2346-style path loss (equation (2), log-distance form).

    Parameters
    ----------
    distance_exponent:
        Coefficient N multiplying log10(d). Use 20 for free-space trend; larger values
        emulate stronger indoor multipath / clutter loss versus distance.
    lf_fixed_db:
        Aggregate non-distance loss L_f. In ``field_strength_map`` this is built from
        wall-pixel hits along each LOS multiplied by ``lf_per_wall_cell_db``.
    d_floor_m:
        Minimum separation to avoid log singularity at d = 0.
    """
    d = np.maximum(np.asarray(distance_m, dtype=np.float64), d_floor_m)
    return (
        20.0 * np.log10(freq_mhz)
        + distance_exponent * np.log10(d)
        - 27.55
        + lf_fixed_db
    )


def received_power_dbm(
    tx_power_dbm: float,
    distance_m: np.ndarray | float,
    freq_mhz: float,
    *,
    distance_exponent: float,
    lf_wall_db: float,
    wall_crossings: np.ndarray | float,
) -> np.ndarray | float:
    """RSS at receiver using P.2346-style PL plus incremental wall loss."""
    lf = lf_wall_db * np.asarray(wall_crossings)
    pl = path_loss_db(
        distance_m,
        freq_mhz,
        distance_exponent=distance_exponent,
        lf_fixed_db=lf,
    )
    return tx_power_dbm - pl


def field_strength_map(
    wall: np.ndarray,
    drone_rc: list[tuple[float, float]],
    cell_size_m: float,
    freq_mhz: float,
    tx_power_dbm: float,
    *,
    distance_exponent: float = 28.0,
    lf_per_wall_cell_db: float = 9.0,
    stride: int = 3,
    ray_samples: int = 48,
) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray]]:
    """
    Downsampled max-RSSI field (dBm) for fast redraw.

    Returns
    -------
    rss_lowres : 2D array whose pixels correspond to cell centers ``rs[i], cs[j]``.
    (rs, cs) : mesh grid coordinates in **full-map cell units** (same frame as drone_rc).
    """
    h, w = wall.shape
    rs_ix = np.arange(0, h, stride, dtype=np.float64) + 0.5 * stride
    cs_ix = np.arange(0, w, stride, dtype=np.float64) + 0.5 * stride
    gr, gc = np.meshgrid(rs_ix, cs_ix, indexing="ij")
    rss = np.full(gr.shape, -np.inf, dtype=np.float64)

    t = np.linspace(0.0, 1.0, ray_samples, dtype=np.float64)[:, np.newaxis, np.newaxis]

    for dr, dc in drone_rc:
        dist_m = np.hypot((gr - dr) * cell_size_m, (gc - dc) * cell_size_m)

        rsamp = dr + t * (gr - dr)
        csamp = dc + t * (gc - dc)
        ri = np.clip(rsamp.astype(np.int32), 0, h - 1)
        ci = np.clip(csamp.astype(np.int32), 0, w - 1)
        hits = np.sum(wall[ri, ci], axis=0).astype(np.float64)

        pw = received_power_dbm(
            tx_power_dbm,
            dist_m,
            freq_mhz,
            distance_exponent=distance_exponent,
            lf_wall_db=lf_per_wall_cell_db,
            wall_crossings=hits,
        )
        rss = np.maximum(rss, pw)

    return rss, (rs_ix, cs_ix)
