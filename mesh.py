import json
import threading
import time
import uuid
from typing import Any, Callable

from swarm_sim.mock_transmission import (
    PropagationUDPTransmission,
    TransmissionLayer,
    UDPMockTransmission,
)
from swarm_sim.viz_mesh_log import format_mesh_log_record


class FloodingNode:
    """
    Managed flooding over a :class:`TransmissionLayer`.

    On receive, the radio triple is ``(sender_id, raw_bytes, link_metric)``:

    - With :class:`~swarm_sim.mock_transmission.PropagationUDPTransmission`, the third value is **RSSI in dBm**.
    - With :class:`~swarm_sim.mock_transmission.UDPMockTransmission` (legacy), the third value is **distance in meters**; relay delay still uses ``distance / radio_range``.
    """

    def __init__(
        self,
        node_id: str,
        radio: TransmissionLayer,
        max_delay: float = 2.0,
        *,
        sensitivity_dbm: float = -92.0,
        strong_rssi_dbm: float = -45.0,
    ):
        self.node_id = node_id
        self.radio = radio
        self.max_delay = max_delay
        self._sensitivity_dbm = float(sensitivity_dbm)
        self._strong_rssi_dbm = float(strong_rssi_dbm)

        self.current_state = "IDLE"
        self.state_version = 0.0

        self.seen_messages: dict[str, float] = {}
        self.pending_rebroadcasts: set[str] = set()

        self.running = True
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._purge_routine, daemon=True).start()

    def _emit(self, payload: dict[str, Any]) -> None:
        payload.setdefault("node_id", self.node_id)
        payload["epoch_ns"] = time.time_ns()
        if self._log_emit is not None:
            self._log_emit(payload)
        if self._sink_prints:
            print(format_mesh_log_record(payload))

    def _relay_delay_from_rssi(self, rssi_dbm: float) -> float:
        """Map weaker RSSI to longer jitter (bounded)."""
        sens = self._sensitivity_dbm
        strong = self._strong_rssi_dbm
        span = strong - sens
        if span <= 1e-9:
            return 0.0
        ratio = min(1.0, max(0.0, (rssi_dbm - sens) / span))
        return (1.0 - ratio) * self.max_delay

    def _relay_delay_from_mock_dist(self, dist_m: float) -> float:
        radio_range = getattr(self.radio, "radio_range", 1.0)
        ratio = min(dist_m / max(radio_range, 1e-9), 1.0)
        return (1.0 - ratio) * self.max_delay

    def stop(self) -> None:
        self.running = False

    def _purge_routine(self) -> None:
        while self.running:
            current_time = time.time()
            stale = [msg_id for msg_id, ts in self.seen_messages.items() if current_time - ts > 60]
            for msg_id in stale:
                del self.seen_messages[msg_id]
            time.sleep(5)

    def broadcast_state(self, new_state: str) -> None:
        self.current_state = new_state
        self.state_version = time.time()

        msg_id = str(uuid.uuid4())
        packet = {
            "type": "STATE_SYNC",
            "msg_id": msg_id,
            "origin": self.node_id,
            "state": self.current_state,
            "version": self.state_version,
            "ttl": 5,
        }

        self.seen_messages[msg_id] = time.time()
        self._emit(
            {
                "action": "broadcast_state",
                "channel": "APP",
                "state": new_state,
            }
        )
        self.radio.broadcast(json.dumps(packet).encode("utf-8"))

    def _listen(self) -> None:
        while self.running:
            result = self.radio.receive(timeout=1.0)
            if not result or result[0] is None:
                continue

            _sender_mac, raw_bytes, link_metric = result
            assert link_metric is not None

            try:
                packet = json.loads(raw_bytes.decode("utf-8"))
                if packet["type"] != "STATE_SYNC":
                    continue

                msg_id = packet.get("msg_id")

                if msg_id in self.seen_messages:
                    if msg_id in self.pending_rebroadcasts:
                        self.pending_rebroadcasts.remove(msg_id)
                    continue

                self.seen_messages[msg_id] = time.time()

                if packet["version"] > self.state_version:
                    self.current_state = packet["state"]
                    self.state_version = packet["version"]
                    self._emit(
                        {
                            "action": "adopt",
                            "channel": "APP",
                            "state": self.current_state,
                            "origin": str(packet["origin"]),
                        }
                    )

                    if packet["ttl"] > 1:
                        packet["ttl"] -= 1
                        self.pending_rebroadcasts.add(msg_id)

                        if isinstance(self.radio, PropagationUDPTransmission):
                            delay = self._relay_delay_from_rssi(float(link_metric))
                        elif isinstance(self.radio, UDPMockTransmission):
                            delay = self._relay_delay_from_mock_dist(float(link_metric))
                        else:
                            delay = self._relay_delay_from_rssi(float(link_metric))

                        threading.Timer(delay, self._rebroadcast, args=(msg_id, packet)).start()

            except json.JSONDecodeError:
                pass

    def _rebroadcast(self, msg_id: str, packet: dict) -> None:
        if msg_id in self.pending_rebroadcasts:
            self.pending_rebroadcasts.remove(msg_id)
            self._emit(
                {
                    "action": "rebroadcast",
                    "channel": "MESH",
                    "state": packet["state"],
                    "ttl": int(packet["ttl"]),
                }
            )
            self.radio.broadcast(json.dumps(packet).encode("utf-8"))
