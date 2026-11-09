"""摄取管线：HTTP 与 MQTT 共用同一条路径。

两个接入层只负责传输，校验、幂等、k 门槛都在这里，避免两条路走岔。
"""
from __future__ import annotations

import hashlib
from typing import Any

from pydantic import ValidationError

from . import config, models, store


class IngestError(Exception):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or []


def batch_id(device_id: str, ts_from: int, ts_to: int) -> str:
    return hashlib.sha256(f"{device_id}{ts_from}{ts_to}".encode()).hexdigest()[:16]


def raw_hits(node: Any, path: str = "") -> list[str]:
    """递归找出载荷里的原始数据字段。privacy.raw 是合法的降级标记。"""
    hits: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k in models.RAW_KEYS and p != "privacy.raw":
                hits.append(p)
            hits += raw_hits(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits += raw_hits(v, f"{path}[{i}]")
    return hits


def process(body: dict[str, Any]) -> dict[str, Any]:
    """返回 {accepted, batch_id, code}；不合规抛 IngestError。"""
    hits = raw_hits(body)
    if hits:
        store.bump("raw_rejected")
        raise IngestError("raw_payload_rejected", "出端载荷不得包含原始字段", hits[:5])

    try:
        msg = models.Telemetry.model_validate(body)
    except ValidationError as e:
        raise IngestError("schema_invalid", "载荷不符合 orpi.telemetry.v1",
                          [str(x.get("loc")) for x in e.errors(include_context=False)[:5]])

    if msg.privacy.k < config.K_MIN:
        store.bump("suppressed_buckets")
        return {"accepted": False, "batch_id": None, "code": "k_below_min"}

    agg = [a.model_dump() for a in msg.aggregates]
    adv = [a.model_dump() for a in msg.advice]
    bid = batch_id(msg.device_id, msg.window.from_, msg.window.to)
    accepted = store.insert_batch(msg.device_id, bid, msg.window.from_,
                                  msg.window.to, body, agg, adv)
    store.touch_device(msg.device_id, msg.window.to)
    if accepted:
        store.bump("batches")
    if msg.privacy.suppressed:
        store.bump("suppressed_buckets", msg.privacy.suppressed)
    return {"accepted": accepted, "batch_id": bid,
            "code": "ok" if accepted else "duplicate"}


def ack_payload(result: dict[str, Any]) -> dict[str, Any]:
    """MQTT 回执：{batch_id, accepted, code}。"""
    return {"batch_id": result.get("batch_id"), "accepted": bool(result.get("accepted")),
            "code": result.get("code", "ok")}
