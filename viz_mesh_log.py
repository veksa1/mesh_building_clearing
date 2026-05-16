"""Shared HUD formatters for mesh flooding telemetry and decentralized RF tails."""

from __future__ import annotations

import re
from typing import Any

_DRONE_UID_RE = re.compile(r"^drone_(\d+)$")


def drone_gate_label(uid: int) -> str:
    """1-based gate label aligned with decentralized HUD conventions (uid 0 -> D1)."""
    return f"D{int(uid) + 1}"


def gate_label_from_node_id(node_id: str) -> str:
    m = _DRONE_UID_RE.match(str(node_id).strip())
    if m:
        return drone_gate_label(int(m.group(1)))
    return str(node_id)


def origin_node_id_to_gate_label(origin_id: str) -> str:
    return gate_label_from_node_id(origin_id)


def rf_destination_label(dst_id: str) -> str:
    if dst_id == "broadcast":
        return "*"
    try:
        return drone_gate_label(int(dst_id))
    except ValueError:
        return dst_id


def format_mesh_log_record(evt: dict[str, Any]) -> str:
    """Pretty one-line string for STATE_SYNC flooding (parallel mesh HUD / optional stdout)."""
    if "worker_uid" in evt:
        gate = drone_gate_label(int(evt["worker_uid"]))
    else:
        gate = gate_label_from_node_id(str(evt.get("node_id", "?")))

    action = evt.get("action")
    channel = evt.get("channel", "APP")

    if action == "broadcast_state":
        state = evt["state"]
        return f"[{gate}] [{channel}] -> Initiating swarm state change to: {state}"

    if action == "adopt":
        state = evt["state"]
        origin_lab = origin_node_id_to_gate_label(str(evt["origin"]))
        return f"[{gate}] [{channel}] <- Adopted new state '{state}' from {origin_lab}"

    if action == "rebroadcast":
        state = evt["state"]
        ttl = int(evt["ttl"])
        return f"[{gate}] [{channel}] Rebroadcasting state '{state}' (TTL: {ttl})"

    return f"[{gate}] [{channel}] (unknown:{action})"
