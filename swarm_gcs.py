import tkinter as tk
from tkinter import ttk
import subprocess
import threading
import sys

SCALE = 10
RADIO_RANGE_M = 15.0
RADIO_RANGE_PX = RADIO_RANGE_M * SCALE

# Map Mission States to visual colors
STATE_COLORS = {
    "IDLE": "#9E9E9E",  # Gray
    "SEARCH": "#FF9800",  # Orange
    "ENGAGE": "#F44336",  # Red
    "RETURN": "#2196F3"  # Blue
}


class ThreadSafeConsole(tk.Text):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.config(state=tk.DISABLED)

    def write_log(self, source, text):
        if not text.strip() or text.strip() == ">": return
        formatted_text = f"[{source}] {text}"
        self.after(0, self._write, formatted_text)

    def _write(self, text):
        self.config(state=tk.NORMAL)
        self.insert(tk.END, text)
        self.see(tk.END)
        self.config(state=tk.DISABLED)


class SwarmGCS(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Drone Mesh - Subprocess GCS")
        self.geometry("1100x750")

        self.nodes = {}
        self.available_ports = list(range(8000, 8050))
        self.next_id = 1

        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        self.map_frame = tk.Frame(self, bg="white", width=600, height=600, bd=2, relief=tk.SUNKEN)
        self.map_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(self.map_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_drone_click)
        self.canvas.bind("<B1-Motion>", self.on_drone_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_drone_release)

        self.selected_drone = None
        self.range_circle = None

        self.control_frame = tk.Frame(self, width=400)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        tk.Label(self.control_frame, text="Subprocess Controls", font=("Arial", 14, "bold")).pack(pady=5)
        tk.Button(self.control_frame, text="Boot Drone Process", command=self.add_drone, bg="#4CAF50", fg="white",
                  width=20).pack(pady=5)
        tk.Button(self.control_frame, text="Kill Last Drone", command=self.remove_drone, bg="#f44336", fg="white",
                  width=20).pack(pady=5)

        # --- STATE INJECTION CONTROLS ---
        tk.Label(self.control_frame, text="Inject State Change", font=("Arial", 12, "bold")).pack(pady=(20, 5))

        tk.Label(self.control_frame, text="Initiating Drone:").pack()
        self.src_var = tk.StringVar()
        self.src_dropdown = ttk.Combobox(self.control_frame, textvariable=self.src_var, state="readonly")
        self.src_dropdown.pack(pady=5)

        tk.Label(self.control_frame, text="New Mission State:").pack()
        self.state_var = tk.StringVar()
        self.state_dropdown = ttk.Combobox(self.control_frame, textvariable=self.state_var, state="readonly")
        self.state_dropdown['values'] = list(STATE_COLORS.keys())
        self.state_dropdown.current(1)  # Default to SEARCH
        self.state_dropdown.pack(pady=5)

        tk.Button(self.control_frame, text="Push State", command=self.trigger_state, bg="#2196F3", fg="white",
                  width=20).pack(pady=10)

        self.console_frame = tk.Frame(self.control_frame)
        self.console_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        tk.Label(self.console_frame, text="Subprocess Outputs").pack()

        self.console = ThreadSafeConsole(self.console_frame, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
        self.console.pack(fill=tk.BOTH, expand=True)

    def update_dropdowns(self):
        active_ids = list(self.nodes.keys())
        self.src_dropdown['values'] = active_ids
        if active_ids:
            if not self.src_var.get() in active_ids: self.src_dropdown.current(0)
        else:
            self.src_dropdown.set("")

    def _update_drone_color(self, node_id, color):
        """Thread-safe way to update canvas colors from the subprocess listener."""
        if node_id in self.nodes:
            self.canvas.itemconfig(self.nodes[node_id]["ui_circle"], fill=color)

    def _read_subprocess_stdout(self, proc, node_id):
        """Passively listens to standard logs and parses them for state changes."""
        for line in iter(proc.stdout.readline, ''):
            self.console.write_log(node_id, line)

            # --- PARSE STATE CHANGES TO UPDATE COLORS ---
            if "Adopted new state" in line or "Initiating swarm state change to:" in line:
                for state, color in STATE_COLORS.items():
                    if state in line:
                        self.after(0, self._update_drone_color, node_id, color)
                        break

        proc.stdout.close()

    def add_drone(self):
        if not self.available_ports: return

        node_id = f"D{self.next_id}"
        self.next_id += 1
        port = self.available_ports.pop(0)

        x_m, y_m = 10.0 + (self.next_id * 5 % 40), 10.0 + (self.next_id * 3 % 40)

        cmd = [sys.executable, "-u", "main.py", "--id", node_id, "--port", str(port), "--x", str(x_m), "--y", str(y_m)]

        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1
        )

        threading.Thread(target=self._read_subprocess_stdout, args=(proc, node_id), daemon=True).start()

        x_px, y_px = x_m * SCALE, y_m * SCALE

        # Start the drone as IDLE (Gray)
        circle_id = self.canvas.create_oval(x_px - 10, y_px - 10, x_px + 10, y_px + 10, fill=STATE_COLORS["IDLE"],
                                            tags=node_id)
        text_id = self.canvas.create_text(x_px, y_px - 15, text=node_id, tags=node_id)

        self.nodes[node_id] = {
            "process": proc,
            "port": port,
            "ui_circle": circle_id,
            "ui_text": text_id
        }

        self.console.write_log("SYSTEM", f"Started {node_id} (PID: {proc.pid}) at ({x_m}m, {y_m}m)\n")
        self.update_dropdowns()

    def remove_drone(self):
        if not self.nodes: return
        node_id = list(self.nodes.keys())[-1]
        drone = self.nodes.pop(node_id)

        try:
            drone["process"].stdin.write("exit\n")
            drone["process"].stdin.flush()
            drone["process"].terminate()
        except Exception:
            pass

        self.available_ports.insert(0, drone["port"])
        self.canvas.delete(drone["ui_circle"])
        self.canvas.delete(drone["ui_text"])

        self.console.write_log("SYSTEM", f"Terminated {node_id}\n")
        self.update_dropdowns()

    def on_drone_drag(self, event):
        if not self.selected_drone: return

        data = self.nodes[self.selected_drone]
        x_px, y_px = event.x, event.y

        self.canvas.coords(data["ui_circle"], x_px - 10, y_px - 10, x_px + 10, y_px + 10)
        self.canvas.coords(data["ui_text"], x_px, y_px - 15)

        if self.range_circle:
            r = RADIO_RANGE_PX
            self.canvas.coords(self.range_circle, x_px - r, y_px - r, x_px + r, y_px + r)

        x_m, y_m = x_px / SCALE, y_px / SCALE
        try:
            data["process"].stdin.write(f"SET_POS {x_m} {y_m}\n")
            data["process"].stdin.flush()
        except Exception:
            pass

    def trigger_state(self):
        """Sends the STATE <NEW_STATE> command to the targeted drone process."""
        src = self.src_var.get()
        new_state = self.state_var.get()

        if src in self.nodes and new_state:
            cmd = f"STATE {new_state}\n"
            proc = self.nodes[src]["process"]
            try:
                proc.stdin.write(cmd)
                proc.stdin.flush()
            except Exception:
                pass

    def on_drone_click(self, event):
        items = self.canvas.find_withtag("current")
        if not items: return

        item_id = items[0]
        for node_id, data in self.nodes.items():
            if data["ui_circle"] == item_id or data["ui_text"] == item_id:
                self.selected_drone = node_id

                coords = self.canvas.coords(data["ui_circle"])
                cx, cy = coords[0] + 10, coords[1] + 10
                r = RADIO_RANGE_PX

                self.range_circle = self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="gray", dash=(4, 4))
                self.canvas.tag_lower(self.range_circle)
                break

    def on_drone_release(self, event):
        if self.range_circle:
            self.canvas.delete(self.range_circle)
            self.range_circle = None
        self.selected_drone = None

    def on_close(self):
        for data in self.nodes.values():
            try:
                data["process"].kill()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = SwarmGCS()
    app.mainloop()