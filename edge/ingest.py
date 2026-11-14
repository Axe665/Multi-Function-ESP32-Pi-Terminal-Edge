"""摄取管线：HTTP 与 MQTT 共用同一条路径。

两个接入层只负责传输，校验、幂等、k 门槛都在这里，避免两条路走岔。
"""
from __future__ import annotations

import hashlib
import shutil
from typing import Any

from pydantic import ValidationError

from . import catalog, config, models, privacy, store


class IngestError(Exception):
    def __init__(self, code: str, message: str, fields: list[str] | None = None,
                 batch_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or []
        # 拒收也要让端能把回执对回本地批次，不然分不清「永久拒绝」和「可重试」
        self.batch_id = batch_id


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


def disk_free_mb() -> int:
    try:
        return int(shutil.disk_usage(config.DATA_DIR).free / (1024 * 1024))
    except OSError:
        return -1


def storage_ok() -> bool:
    """文档 §8.4：磁盘水位低于阈值时拒收，别把库写爆。"""
    if config.MIN_FREE_MB <= 0:
        return True
    free = disk_free_mb()
    return free < 0 or free >= config.MIN_FREE_MB


def process(body: dict[str, Any], transport_device: str | None = None) -> dict[str, Any]:
    """返回 {accepted, batch_id, code}；不合规抛 IngestError。

    transport_device 是传输层认定的身份（MQTT 是主题里的 deviceId）。载荷里的
    device_id 由发送方随便填，不比对就能往别人的分区里写。
    """
    if transport_device and str(body.get("device_id", "")) != transport_device:
        store.bump("device_mismatch")
        raise IngestError("DEVICE_MISMATCH", "载荷 device_id 与主题不一致")
    if transport_device and store.device_revoked(transport_device):
        raise IngestError("DEVICE_REVOKED", "设备已吊销，先重新配对")
    if not storage_ok():
        store.bump("disk_low")
        raise IngestError("DISK_LOW", "边节点磁盘余量不足，暂时拒收",
                          [f"free_mb={disk_free_mb()}"])
    hits = raw_hits(body)
    if hits:
        store.bump("raw_rejected")
        raise IngestError("RAW_PAYLOAD_REJECTED", "出端载荷不得包含原始字段", hits[:5])

    try:
        msg = models.Telemetry.model_validate(body)
    except ValidationError as e:
        raise IngestError("SCHEMA_INVALID", "载荷不符合 orpi.telemetry.v1",
                          [str(x.get("loc")) for x in e.errors(include_context=False)[:5]])

    # 文档 §8.2：桶内 subject < 5 时丢这个桶，不是丢整批。
    # 以前一个 k=4 的桶会让同批合规桶一起丢掉，端还会以为整批被拒。
    bid = batch_id(msg.device_id, msg.window.from_, msg.window.to)
    k_min = int(store.get_settings().get("k_min", config.K_MIN))
    if msg.privacy.k < k_min:
        store.bump("suppressed_buckets", 1)
        raise IngestError("K_BELOW_MIN", f"批次的 k 小于 {k_min}", batch_id=bid)
    low_rows = [a for a in msg.aggregates if a.k < k_min]
    kept = [a for a in msg.aggregates if a.k >= k_min]
    # 计数器把「端自己抑制的」和「边丢掉的」都算上；回执只报边丢了几行
    if len(low_rows) or msg.privacy.suppressed:
        store.bump("suppressed_buckets", len(low_rows) + (msg.privacy.suppressed or 0))

    agg = [a.model_dump() for a in kept]
    # 建议文案按不可信数据处理：入库前过一遍正则 + 词典
    adv = []
    scrubbed = 0
    for a in msg.advice:
        clean, hits = privacy.scrub(a.text)
        scrubbed += sum(hits.values())
        adv.append({**a.model_dump(), "text": clean})
    if scrubbed:
        store.bump("text_scrubbed", scrubbed)
    safe_body = dict(body)
    if adv:
        safe_body["advice"] = [{**a, "text": b["text"]} for a, b in zip(body.get("advice", []), adv)]
    # 端上报了什么就登记什么：换模块不需要改边
    for a in kept:
        catalog.upsert(msg.device_id, a.metric, a.module_id, a.package_id,
                       a.label, a.unit, a.table, a.decimals)
    store.ensure_device(msg.device_id)
    accepted = store.insert_batch(msg.device_id, bid, msg.window.from_,
                                  msg.window.to, safe_body, agg, adv)
    store.touch_device(msg.device_id, msg.window.to)
    if accepted:
        store.bump("batches")
    return {"accepted": accepted, "batch_id": bid,
            "code": "accepted" if accepted else "duplicate",
            "suppressed": len(low_rows)}


def ack_payload(result: dict[str, Any]) -> dict[str, Any]:
    """MQTT 回执：{batch_id, accepted, code}。"""
    body = {"batch_id": result.get("batch_id"),
            "accepted": bool(result.get("accepted")),
            "code": result.get("code", "accepted")}
    if result.get("error"):
        body["error"] = result["error"]
    return body
