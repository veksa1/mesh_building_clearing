import json
import time
import threading
import uuid
from mock_transmission import TransmissionLayer


class FloodingNode:
    def __init__(self, node_id: str, radio: TransmissionLayer, max_delay: float = 2.0):
        self.node_id = node_id
        self.radio = radio
        self.max_delay = max_delay

        # --- STATE SYNCHRONIZATION ---
        self.current_state = "IDLE"
        self.state_version = 0.0  # We will use timestamps as version numbers

        self.seen_messages = {}
        self.pending_rebroadcasts = set()

        self.running = True
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._purge_routine, daemon=True).start()

    def stop(self):
        self.running = False

    def _purge_routine(self):
        while self.running:
            current_time = time.time()
            stale = [msg_id for msg_id, ts in self.seen_messages.items() if current_time - ts > 60]
            for msg_id in stale:
                del self.seen_messages[msg_id]
            time.sleep(5)

    def broadcast_state(self, new_state: str):
        """Update local state and flood the new state to the swarm."""
        self.current_state = new_state
        self.state_version = time.time()  # LWW: Last Write Wins

        msg_id = str(uuid.uuid4())
        packet = {
            "type": "STATE_SYNC",
            "msg_id": msg_id,
            "origin": self.node_id,
            "state": self.current_state,
            "version": self.state_version,
            "ttl": 5
        }

        self.seen_messages[msg_id] = time.time()
        print(f"[APP] -> Initiating swarm state change to: {new_state}")
        self.radio.broadcast(json.dumps(packet).encode('utf-8'))

    def _listen(self):
        while self.running:
            result = self.radio.receive(timeout=1.0)
            if not result or result[0] is None: continue

            sender_mac, raw_bytes, dist = result

            try:
                packet = json.loads(raw_bytes.decode('utf-8'))
                if packet["type"] != "STATE_SYNC": continue

                msg_id = packet.get("msg_id")

                # De-duplication
                if msg_id in self.seen_messages:
                    if msg_id in self.pending_rebroadcasts:
                        self.pending_rebroadcasts.remove(msg_id)
                    continue

                self.seen_messages[msg_id] = time.time()

                # --- STATE ADOPTION LOGIC ---
                # Only adopt the state if its version (timestamp) is newer than our current one
                if packet["version"] > self.state_version:
                    self.current_state = packet["state"]
                    self.state_version = packet["version"]
                    print(f"\n[APP] <- Adopted new state '{self.current_state}' from {packet['origin']}\n> ", end="")

                    # RULE 3: Prepare to Rebroadcast (Managed Flooding)
                    if packet["ttl"] > 1:
                        packet["ttl"] -= 1
                        self.pending_rebroadcasts.add(msg_id)

                        ratio = min(dist / self.radio.radio_range, 1.0)
                        delay = (1.0 - ratio) * self.max_delay

                        threading.Timer(delay, self._rebroadcast, args=(msg_id, packet)).start()

            except json.JSONDecodeError:
                pass

    def _rebroadcast(self, msg_id: str, packet: dict):
        if msg_id in self.pending_rebroadcasts:
            self.pending_rebroadcasts.remove(msg_id)
            print(f"[MESH] Rebroadcasting state '{packet['state']}' (TTL: {packet['ttl']})")
            self.radio.broadcast(json.dumps(packet).encode('utf-8'))