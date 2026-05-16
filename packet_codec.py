"""Serialize ``Packet`` for UDP mesh payloads (kernel comms)."""

from __future__ import annotations

import json

from swarm_sim.radio import MsgKind, Packet


def packet_to_json_bytes(pkt: Packet) -> bytes:
    obj = {
        "kind": pkt.kind.value,
        "sender_uid": pkt.sender_uid,
        "seq": pkt.seq,
        "payload": pkt.payload,
    }
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def kind_is_known(kind_raw: object) -> bool:
    return isinstance(kind_raw, str) and kind_raw in {k.value for k in MsgKind}


def packet_from_json_bytes(raw: bytes) -> Packet | None:
    try:
        obj = json.loads(raw.decode("utf-8"))
        kind_raw = obj.get("kind")
        if not kind_is_known(kind_raw):
            return None
        return Packet(
            kind=MsgKind(kind_raw),
            sender_uid=int(obj["sender_uid"]),
            seq=int(obj["seq"]),
            payload=dict(obj.get("payload") or {}),
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
