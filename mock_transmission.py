import json
import math
import random
import socket
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence

import numpy as np

from swarm_sim.radio import RadioConfig, pairwise_rssi_dbm


class TransmissionLayer(ABC):
    @abstractmethod
    def broadcast(self, payload: bytes) -> None:
        pass

    @abstractmethod
    def receive(self, timeout: float | None = None) -> tuple[str | None, bytes | None, float | None]:
        """Return (sender_id, payload, link_metric).

        For :class:`PropagationUDPTransmission`, the third value is **RSSI in dBm**.
        For :class:`UDPMockTransmission`, the third value is **distance in meters** (legacy mock).
        """

    @abstractmethod
    def stop(self) -> None:
        pass


class UDPMockTransmission(TransmissionLayer):
    """
    Legacy spatial mock: deliveries when Euclidean distance in meters is within the
    sender-declared circular range. The third tuple element from ``receive`` is **distance (m)**.
    """

    def __init__(self, my_port: int, x: float, y: float, radio_range: float = 15.0, drop_rate: float = 0.1):
        self.my_port = my_port
        self.x = x
        self.y = y
        self.radio_range = radio_range
        self.drop_rate = drop_rate

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", self.my_port))

        self.ether_ports = range(8000, 8050)

        print(f"[HARDWARE] Radio active on port {my_port}.")
        print(f"[PHYSICS] Position: ({x}, {y}) | Range: {radio_range}m | Drop rate: {drop_rate * 100}%")

    def broadcast(self, payload: bytes) -> None:
        physics_header = {
            "tx_port": self.my_port,
            "x": self.x,
            "y": self.y,
            "range": self.radio_range,
        }

        simulated_ether_frame = json.dumps(physics_header).encode("utf-8") + b"|||" + payload

        for port in self.ether_ports:
            if port != self.my_port:
                if random.random() >= self.drop_rate:
                    try:
                        self.sock.sendto(simulated_ether_frame, ("127.0.0.1", port))
                    except ConnectionRefusedError:
                        pass
                    except OSError:
                        pass

    def receive(self, timeout: float | None = 1.0) -> tuple[str | None, bytes | None, float | None]:
        self.sock.settimeout(timeout)
        try:
            data, _addr = self.sock.recvfrom(4096)

            parts = data.split(b"|||", 1)
            if len(parts) != 2:
                return None, None, None

            header_bytes, mesh_payload = parts
            header = json.loads(header_bytes.decode("utf-8"))

            dist = math.hypot(self.x - header["x"], self.y - header["y"])

            if dist <= header["range"]:
                sender_id = f"node_{header['tx_port']}"
                return sender_id, mesh_payload, dist
            return None, None, None

        except socket.timeout:
            return None, None, None
        except Exception:
            return None, None, None

    def stop(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


def swarm_udp_destinations(n_fleet: int, base_port: int) -> tuple[int, ...]:
    """Union of default demo port range with ``base_port..base_port+n_fleet`` (kernel fleet binds)."""
    ports = set(range(8000, 8050))
    ports.update(range(int(base_port), int(base_port) + int(n_fleet)))
    return tuple(sorted(ports))


def classify_link_budget(
    wall: np.ndarray,
    tx_rc: tuple[float, float],
    rx_rc: tuple[float, float],
    cfg: RadioConfig,
    *,
    noise_floor_dbm: float | None,
    min_snr_db: float,
) -> tuple[float, bool]:
    """
    Match :meth:`swarm_sim.radio.RadioMedium.broadcast_tick` decode semantics:
    deliver when RSSI >= sensitivity; if ``noise_floor_dbm`` is set, also require
    ``RSSI - noise_floor_dbm >= min_snr_db``. When ``noise_floor_dbm`` is ``None``,
    the SNR gate is skipped (RSSI-only reception).
    """
    rssi = pairwise_rssi_dbm(
        wall,
        tx_rc,
        rx_rc,
        cell_size_m=cfg.cell_size_m,
        freq_mhz=cfg.freq_mhz,
        tx_power_dbm=cfg.tx_power_dbm,
        distance_exponent=cfg.distance_exponent,
        lf_per_wall_cell_db=cfg.lf_per_wall_cell_db,
        ray_samples=cfg.ray_samples,
    )
    if rssi < cfg.sensitivity_dbm:
        return rssi, False
    if noise_floor_dbm is not None and (rssi - noise_floor_dbm) < min_snr_db:
        return rssi, False
    return rssi, True


class PropagationUDPTransmission(TransmissionLayer):
    """
    UDP transport with the same P.2346-style link budget as :func:`~swarm_sim.radio.pairwise_rssi_dbm`.

    Header JSON uses grid floats ``tx_r``, ``tx_c`` (row, col) consistent with the discrete sim.
    ``receive`` returns **RSSI (dBm)** as the third element on success.

    Optional ``drop_rate`` models extra MAC/frame loss on top of physics (default 0).
    """

    def __init__(
        self,
        wall: np.ndarray,
        cfg: RadioConfig,
        my_port: int,
        get_pose: Callable[[], tuple[float, float]],
        *,
        noise_floor_dbm: float | None = None,
        min_snr_db: float = 6.0,
        drop_rate: float = 0.0,
        ether_ports: Sequence[int] | range | None = None,
        pose_lock: threading.Lock | None = None,
        verbose: bool = True,
    ) -> None:
        self.wall = wall
        self.cfg = cfg
        self.my_port = int(my_port)
        self.get_pose = get_pose
        self.noise_floor_dbm = noise_floor_dbm
        self.min_snr_db = float(min_snr_db)
        self.drop_rate = float(drop_rate)
        ports = ether_ports if ether_ports is not None else range(8000, 8050)
        self.ether_ports: Iterable[int] = ports
        self._pose_lock = pose_lock or threading.Lock()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", self.my_port))

        if verbose:
            snr_note = "off" if noise_floor_dbm is None else f"on (floor={noise_floor_dbm} dBm, min_snr={min_snr_db} dB)"
            print(
                f"[HARDWARE] Propagation UDP on port {my_port}. "
                f"SNR gate: {snr_note} | MAC drop: {drop_rate * 100:.2f}%"
            )

    def _tx_pose(self) -> tuple[float, float]:
        with self._pose_lock:
            return self.get_pose()

    def broadcast(self, payload: bytes) -> None:
        tr, tc = self._tx_pose()
        physics_header = {
            "tx_port": self.my_port,
            "tx_r": float(tr),
            "tx_c": float(tc),
        }
        frame = json.dumps(physics_header).encode("utf-8") + b"|||" + payload
        for port in self.ether_ports:
            if port != self.my_port:
                if random.random() >= self.drop_rate:
                    try:
                        self.sock.sendto(frame, ("127.0.0.1", port))
                    except (ConnectionRefusedError, OSError):
                        pass

    def receive(self, timeout: float | None = 1.0) -> tuple[str | None, bytes | None, float | None]:
        self.sock.settimeout(timeout)
        try:
            data, _addr = self.sock.recvfrom(4096)
            parts = data.split(b"|||", 1)
            if len(parts) != 2:
                return None, None, None
            header_bytes, mesh_payload = parts
            header = json.loads(header_bytes.decode("utf-8"))
            tx_rc = (float(header["tx_r"]), float(header["tx_c"]))
            with self._pose_lock:
                rx_rc = self.get_pose()
            rssi, ok = classify_link_budget(
                self.wall,
                tx_rc,
                rx_rc,
                self.cfg,
                noise_floor_dbm=self.noise_floor_dbm,
                min_snr_db=self.min_snr_db,
            )
            if not ok:
                return None, None, None
            sender_id = f"node_{header['tx_port']}"
            return sender_id, mesh_payload, rssi
        except socket.timeout:
            return None, None, None
        except Exception:
            return None, None, None

    def stop(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass
