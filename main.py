import argparse
import time
from mock_transmission import UDPMockTransmission
from mesh import FloodingNode

def main():
    parser = argparse.ArgumentParser(description="Start a Drone Mesh Node")
    parser.add_argument("--id", type=str, required=True, help="Unique Drone ID")
    parser.add_argument("--port", type=int, required=True, help="UDP port")
    parser.add_argument("--x", type=float, default=0.0, help="X coordinate (meters)")
    parser.add_argument("--y", type=float, default=0.0, help="Y coordinate (meters)")
    args = parser.parse_args()

    # Initialize Hardware with spatial coordinates and a 15-meter radio range
    radio = UDPMockTransmission(my_port=args.port, x=args.x, y=args.y, radio_range=15.0, drop_rate=0.0)

    # FIX: Removed ogm_interval. Optionally add max_delay=2.0 if you want to tweak it.
    node = FloodingNode(node_id=args.id, radio=radio)

    time.sleep(1)
    print(f"\n--- {args.id} Active ---")

    while True:
        try:
            user_input = input("> ").strip()
            if not user_input: continue
            if user_input.lower() == "exit": break

            # FIX: Change 'routes' command to view the message cache instead of a routing table
            if user_input.lower() == "cache":
                print(f"Seen Messages: {list(node.seen_messages.keys())}")
                print(f"Pending Rebroadcasts: {node.pending_rebroadcasts}")
                continue

            # Allow Ground Control Station to update physical coordinates
            if user_input.startswith("SET_POS"):
                try:
                    _, new_x, new_y = user_input.split()
                    radio.x = float(new_x)
                    radio.y = float(new_y)
                except ValueError:
                    pass
                continue

            # Replace the part that handled `<destination_id> <message>` with this:
            parts = user_input.split(" ", 1)
            if len(parts) == 2 and parts[0].upper() == "STATE":
                node.broadcast_state(new_state=parts[1].upper())
            else:
                print("Invalid format. Use: STATE <NEW_STATE> (e.g., STATE SEARCH)")

        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main()