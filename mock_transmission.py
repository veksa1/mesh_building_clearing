import socket
import random
import json
import math
from abc import ABC, abstractmethod


class TransmissionLayer(ABC):
    @abstractmethod
    def broadcast(self, payload: bytes):
        pass

    @abstractmethod
    def receive(self, timeout: float = None) -> tuple[str, bytes]:
        pass

    @abstractmethod
    def stop(self):
        pass


class UDPMockTransmission(TransmissionLayer):
    """
    Simulates raw 802.11 frames, including spatial physics (X, Y)
    to determine who can hear the transmission based on distance.
    """

    def __init__(self, my_port: int, x: float, y: float, radio_range: float = 15.0, drop_rate: float = 0.1):
        self.my_port = my_port
        self.x = x
        self.y = y
        self.radio_range = radio_range
        self.drop_rate = drop_rate

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', self.my_port))

        self.ether_ports = range(8000, 8050) # Expanded to support 50 drones

        print(f"[HARDWARE] Radio active on port {my_port}.")
        print(f"[PHYSICS] Position: ({x}, {y}) | Range: {radio_range}m | Drop rate: {drop_rate * 100}%")

    def broadcast(self, payload: bytes):
        physics_header = {
            "tx_port": self.my_port,
            "x": self.x,
            "y": self.y,
            "range": self.radio_range
        }

        simulated_ether_frame = json.dumps(physics_header).encode('utf-8') + b'|||' + payload

        for port in self.ether_ports:
            if port != self.my_port:
                if random.random() >= self.drop_rate:
                    try:
                        self.sock.sendto(simulated_ether_frame, ('127.0.0.1', port))
                    except ConnectionRefusedError:
                        pass
                    except OSError:
                        pass # Socket might be closed during shutdown

    def receive(self, timeout: float = 1.0) -> tuple[str, bytes, float]:
        self.sock.settimeout(timeout)
        try:
            data, addr = self.sock.recvfrom(4096)

            parts = data.split(b'|||', 1)
            if len(parts) != 2:
                return None, None, None

            header_bytes, mesh_payload = parts
            header = json.loads(header_bytes.decode('utf-8'))

            dist = math.hypot(self.x - header["x"], self.y - header["y"])

            if dist <= header["range"]:
                sender_id = f"node_{header['tx_port']}"
                # NEW: Return distance alongside the payload
                return sender_id, mesh_payload, dist
            else:
                return None, None, None

        except socket.timeout:
            return None, None, None
        except Exception:
            return None, None, None

    def stop(self):
        """Closes the socket so the port is freed immediately."""
        try:
            self.sock.close()
        except Exception:
            pass