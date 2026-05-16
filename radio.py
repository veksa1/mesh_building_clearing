"""Simulated mesh: RSSI-aware broadcast deliveries + structured comm logging."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .propagation import received_power_dbm
from .viz_mesh_log import drone_gate_label, rf_destination_label


class MsgKind(str, Enum):
    BEACON = "BEACON"
    TOPOLOGY_MERGE = "TOPOLOGY_MERGE"
    TOKEN = "TOKEN"


@dataclass
class Packet:
    kind: MsgKind
    sender_uid: int
    seq: int
    payload: dict[str, object] = field(default_factory=dict)


@dataclass
class CommEvent:
    """Kernel telemetry for HUD / exporter — never passed into agents."""

    tick: int
    msg_type: str
    src_id: int
    dst_id: str  # receiver uid as str or "broadcast"
    rssi_dbm: float | None
    outcome: str  # delivered | below_threshold | tx
    hop: int
    detail: str = ""
    src_pose_rcf: tuple[float, float] | None = None
    dst_pose_rcf: tuple[float, float] | None = None

    def format_line(self) -> str:
        rs = f"{self.rssi_dbm:.1f}" if self.rssi_dbm is not None else "—"
        return (
            f"t={self.tick:04d}  {self.msg_type:<14}  {self.src_id}→{self.dst_id}  "
            f"RSSI={rs} dBm  [{self.outcome}] {self.detail}"
        )

    def format_rf_hud_line(self) -> str:
        """Bracket-style line for decentralized matplotlib RF panel."""
        rs = f"{self.rssi_dbm:.1f}" if self.rssi_dbm is not None else "—"
        sd = drone_gate_label(int(self.src_id))
        dd = rf_destination_label(self.dst_id)
        return (
            f"t={self.tick:04d}  [RF]  [{sd}]  {self.msg_type:<14}  {sd}→{dd}  "
            f"RSSI={rs} dBm  [{self.outcome}] {self.detail}"
        )


def wall_hits_along_ray(
    wall: np.ndarray,
    r0: float,
    c0: float,
    r1: float,
    c1: float,
    *,
    samples: int = 48,
) -> int:
    rs = np.linspace(r0, r1, samples)
    cs = np.linspace(c0, c1, samples)
    ri = np.clip(rs.astype(np.int32), 0, wall.shape[0] - 1)
    ci = np.clip(cs.astype(np.int32), 0, wall.shape[1] - 1)
    return int(np.sum(wall[ri, ci]))


def pairwise_rssi_dbm(
    wall: np.ndarray,
    tx_rc: tuple[float, float],
    rx_rc: tuple[float, float],
    *,
    cell_size_m: float,
    freq_mhz: float,
    tx_power_dbm: float,
    distance_exponent: float,
    lf_per_wall_cell_db: float,
    ray_samples: int,
) -> float:
    dr_t = tx_rc[0] * cell_size_m
    dc_t = tx_rc[1] * cell_size_m
    dr_r = rx_rc[0] * cell_size_m
    dc_r = rx_rc[1] * cell_size_m
    dist_m = float(np.hypot(dr_r - dr_t, dc_r - dc_t))
    crosses = wall_hits_along_ray(wall, tx_rc[0], tx_rc[1], rx_rc[0], rx_rc[1], samples=ray_samples)
    return float(
        received_power_dbm(
            tx_power_dbm,
            dist_m,
            freq_mhz,
            distance_exponent=distance_exponent,
            lf_wall_db=lf_per_wall_cell_db,
            wall_crossings=crosses,
        )
    )


@dataclass
class RadioConfig:
    cell_size_m: float = 0.22
    freq_mhz: float = 2400.0
    tx_power_dbm: float = 20.0
    sensitivity_dbm: float = -92.0
    distance_exponent: float = 28.0
    lf_per_wall_cell_db: float = 9.0
    ray_samples: int = 48


class RadioMedium:
    """Opaque RF plane: transmit schedules deliveries + emits ``CommEvent`` rows."""

    def __init__(self, wall: np.ndarray, cfg: RadioConfig | None = None) -> None:
        self.wall = wall
        self.cfg = cfg or RadioConfig()

    def broadcast_tick(
        self,
        tick: int,
        sender_uid: int,
        pose_xy_rc: tuple[float, float],
        packet: Packet,
        *,
        receiver_poses: dict[int, tuple[float, float]],
    ) -> tuple[list[tuple[int, Packet, float]], list[CommEvent]]:
        """
        One simultaneous broadcast from ``sender_uid``.

        Returns list of (receiver_uid, packet_copy, rssi) for delivered copies + CommEvents for all attempts.
        """
        delivered: list[tuple[int, Packet, float]] = []
        events: list[CommEvent] = []

        for rid, pose in receiver_poses.items():
            if rid == sender_uid:
                continue
            rssi = pairwise_rssi_dbm(
                self.wall,
                pose_xy_rc,
                pose,
                cell_size_m=self.cfg.cell_size_m,
                freq_mhz=self.cfg.freq_mhz,
                tx_power_dbm=self.cfg.tx_power_dbm,
                distance_exponent=self.cfg.distance_exponent,
                lf_per_wall_cell_db=self.cfg.lf_per_wall_cell_db,
                ray_samples=self.cfg.ray_samples,
            )
            if rssi >= self.cfg.sensitivity_dbm:
                delivered.append((rid, packet, rssi))
                events.append(
                    CommEvent(
                        tick=tick,
                        msg_type=packet.kind.value,
                        src_id=sender_uid,
                        dst_id=str(rid),
                        rssi_dbm=rssi,
                        outcome="delivered",
                        hop=1,
                        detail=f"seq={packet.seq}",
                        src_pose_rcf=tuple(pose_xy_rc),
                        dst_pose_rcf=tuple(pose),
                    )
                )
            else:
                events.append(
                    CommEvent(
                        tick=tick,
                        msg_type=packet.kind.value,
                        src_id=sender_uid,
                        dst_id=str(rid),
                        rssi_dbm=rssi,
                        outcome="below_threshold",
                        hop=1,
                        detail=f"seq={packet.seq}",
                        src_pose_rcf=tuple(pose_xy_rc),
                        dst_pose_rcf=tuple(pose),
                    )
                )

        events.insert(
            0,
            CommEvent(
                tick=tick,
                msg_type=packet.kind.value,
                src_id=sender_uid,
                dst_id="broadcast",
                rssi_dbm=None,
                outcome="tx",
                hop=0,
                detail=f"seq={packet.seq} listeners={len(receiver_poses) - 1}",
                src_pose_rcf=tuple(pose_xy_rc),
                dst_pose_rcf=None,
            ),
        )
        return delivered, events
