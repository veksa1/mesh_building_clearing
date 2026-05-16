"""One-line HUD strings for decentralized gossip adoption + honest TX (no TTL relay semantics)."""

from __future__ import annotations

from .radio import MsgKind, Packet
from .viz_mesh_log import drone_gate_label


def _tick_str(payload: dict[str, object], tick: int) -> str:
    t = payload.get("tick")
    if isinstance(t, int):
        return str(int(t))
    return str(int(tick))


def _short_rooms_preview(raw: object, *, limit: int = 12) -> str:
    if not isinstance(raw, list) or not raw:
        return ""
    nums: list[int] = []
    for x in raw:
        if isinstance(x, int):
            nums.append(int(x))
        if len(nums) >= limit:
            break
    if not nums:
        return ""
    if len(nums) < len(raw):
        return f" rooms={nums!r}+{len(raw)-len(nums)}more"
    return f" rooms={nums!r}"


def format_mesh_activity_adopt(receiver_uid: int, pkt: Packet, tick: int) -> str:
    """Inbound gossip applied at drain_inbox ([APP], direction <- sender)."""
    me = drone_gate_label(int(receiver_uid))
    them = drone_gate_label(int(pkt.sender_uid))
    ts = _tick_str(pkt.payload, tick)
    if pkt.kind == MsgKind.BEACON:
        rr = pkt.payload.get("r")
        cc = pkt.payload.get("c")
        pos = ""
        if rr is not None and cc is not None:
            pos = f" pos=({int(rr)},{int(cc)})"
        rooms = _short_rooms_preview(pkt.payload.get("seen_rooms"))
        return (
            f"[{me}] [APP] <- Adopted BEACON from {them} "
            f"(seq={int(pkt.seq)}{pos} tick={ts}{rooms})"
        )
    if pkt.kind == MsgKind.TOPOLOGY_MERGE:
        nodes = pkt.payload.get("nodes") or []
        edges = pkt.payload.get("edges") or []
        belief = pkt.payload.get("belief_edges") or []
        nn = len(nodes) if isinstance(nodes, list) else 0
        ne = len(edges) if isinstance(edges, list) else 0
        nb = len(belief) if isinstance(belief, list) else 0
        return (
            f"[{me}] [APP] <- Adopted TOPOLOGY_MERGE from {them} "
            f"(seq={int(pkt.seq)} tick={ts}; nodes={nn} edges={ne} belief={nb})"
        )
    if pkt.kind == MsgKind.TOKEN:
        sig = pkt.payload.get("signature")
        ttl = pkt.payload.get("ttl_ticks")
        sig_s = str(sig)[:24] + ("…" if isinstance(sig, str) and len(sig) > 24 else "")
        ttl_s = str(int(ttl)) if isinstance(ttl, int) else str(ttl or "—")
        return (
            f"[{me}] [APP] <- Adopted TOKEN from {them} "
            f"(seq={int(pkt.seq)} tick={ts}; sig={sig_s} ttl={ttl_s})"
        )
    return f"[{me}] [APP] <- Adopted {pkt.kind.value} from {them} (seq={int(pkt.seq)} tick={ts})"


def format_mesh_activity_tx(uid: int, pkt: Packet, tick: int) -> str:
    """Originated packet this drone is about to put on RF ([MESH] Broadcasting …)."""
    me = drone_gate_label(int(uid))
    ts = _tick_str(pkt.payload, tick)
    if pkt.kind == MsgKind.BEACON:
        rooms = _short_rooms_preview(pkt.payload.get("seen_rooms"))
        br = pkt.payload.get("r")
        bc = pkt.payload.get("c")
        pos = "(?,?)" if br is None or bc is None else f"({int(br)},{int(bc)})"
        return (
            f"[{me}] [MESH] Broadcasting BEACON "
            f"(seq={int(pkt.seq)} tick={ts}; pos={pos}{rooms})"
        )
    if pkt.kind == MsgKind.TOPOLOGY_MERGE:
        nodes = pkt.payload.get("nodes") or []
        edges = pkt.payload.get("edges") or []
        belief = pkt.payload.get("belief_edges") or []
        nn = len(nodes) if isinstance(nodes, list) else 0
        ne = len(edges) if isinstance(edges, list) else 0
        nb = len(belief) if isinstance(belief, list) else 0
        return (
            f"[{me}] [MESH] Broadcasting TOPOLOGY_MERGE "
            f"(seq={int(pkt.seq)} tick={ts}; nodes={nn} edges={ne} belief={nb})"
        )
    if pkt.kind == MsgKind.TOKEN:
        sig = pkt.payload.get("signature")
        ttl = pkt.payload.get("ttl_ticks")
        sig_s = str(sig)[:24] + ("…" if isinstance(sig, str) and len(sig) > 24 else "")
        ttl_s = str(int(ttl)) if isinstance(ttl, int) else str(ttl or "—")
        return (
            f"[{me}] [MESH] Broadcasting TOKEN "
            f"(seq={int(pkt.seq)} tick={ts}; sig={sig_s} ttl={ttl_s})"
        )
    return f"[{me}] [MESH] Broadcasting {pkt.kind.value} (seq={int(pkt.seq)} tick={ts})"
