"""边节点 HTTP API。设备侧走 /ingest，管理侧给前端用。"""
from __future__ import annotations

import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import ValidationError

from . import analysis, config, metrics, models, sim, store

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------- 鉴权

def admin_guard(authorization: str | None = Header(default=None)) -> None:
    """设了 EDGE_ADMIN_TOKEN 才校验；单机演示默认关闭，见 README。"""
    if not config.ADMIN_TOKEN:
        return
    if authorization != f"Bearer {config.ADMIN_TOKEN}":
        raise HTTPException(401, "需要管理员令牌")


def ingest_guard(authorization: str | None = Header(default=None),
                 x_forwarded_for: str | None = Header(default=None)) -> None:
    if not config.INGEST_TOKEN:
        return
    if authorization != f"Bearer {config.INGEST_TOKEN}":
        raise HTTPException(401, "设备令牌无效")


admin = [Depends(admin_guard)]
device = [Depends(ingest_guard)]


def _raw_hits(node: Any, path: str = "") -> list[str]:
    """递归找出载荷里的原始数据字段。privacy.raw 是合法的降级标记。"""
    hits: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k in models.RAW_KEYS and p != "privacy.raw":
                hits.append(p)
            hits += _raw_hits(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits += _raw_hits(v, f"{path}[{i}]")
    return hits


# ---------------------------------------------------------------- 设备接入

@router.post("/ingest/telemetry", dependencies=device)
def ingest_telemetry(body: dict[str, Any]) -> dict[str, Any]:
    hits = _raw_hits(body)
    if hits:
        store.bump("raw_rejected")
        raise HTTPException(
            422, {"code": "raw_payload_rejected",
                  "message": "出端载荷不得包含原始字段", "fields": hits[:5]})

    try:
        msg = models.Telemetry.model_validate(body)
    except ValidationError as e:
        raise HTTPException(422, {"code": "schema_invalid",
                                  "errors": e.errors(include_url=False, include_context=False)[:5]})

    if msg.privacy.k < config.K_MIN:
        store.bump("suppressed_buckets")
        return {"accepted": False, "code": "k_below_min", "batch_id": None}

    agg = [a.model_dump() for a in msg.aggregates]
    adv = [a.model_dump() for a in msg.advice]
    batch_id = _batch_id(msg.device_id, msg.window.from_, msg.window.to)
    accepted = store.insert_batch(msg.device_id, batch_id, msg.window.from_,
                                  msg.window.to, body, agg, adv)
    store.touch_device(msg.device_id, msg.window.to)
    if msg.privacy.suppressed:
        store.bump("suppressed_buckets", msg.privacy.suppressed)
    return {"accepted": accepted, "batch_id": batch_id, "code": "ok" if accepted else "duplicate"}


def _batch_id(device_id: str, ts_from: int, ts_to: int) -> str:
    import hashlib
    return hashlib.sha256(f"{device_id}{ts_from}{ts_to}".encode()).hexdigest()[:16]


@router.get("/discovery", dependencies=admin)
def discovery() -> dict[str, Any]:
    """mDNS 发现的服务记录。演示里由静态清单提供，真机走 _orpi-device._tcp。"""
    return {
        "service": "_orpi-device._tcp.local",
        "edge": {"id": config.EDGE_ID, "port": 8001, "ca_fp": "sha256:9f3c…"},
        "devices": [{
            "device_id": d["device_id"], "model": d["name"].split("·")[-1].strip(),
            "fw": d["fw"], "scene": d["scene"], "paired": bool(d["paired_at"]),
            "last_seen": d["last_seen"],
        } for d in store.devices()],
    }


@router.post("/devices/{device_id}/pair", dependencies=admin)
def pair(device_id: str) -> dict[str, Any]:
    if not store.device(device_id):
        raise HTTPException(404, "设备不存在")
    code = f"{secrets.randbelow(1_000_000):06d}"
    store.create_pair_code(code, 10 * 60 * 1000)
    return {"device_id": device_id, "code": code, "ttl_s": 600}


@router.get("/pair-codes", dependencies=admin)
def pair_codes() -> list[dict[str, Any]]:
    return store.pair_codes()


# ---------------------------------------------------------------- 查询

@router.get("/overview", dependencies=admin)
def overview() -> dict[str, Any]:
    return analysis.overview()


@router.get("/devices", dependencies=admin)
def devices() -> list[dict[str, Any]]:
    out = []
    for d in store.devices():
        latest = store.latest_aggregates(d["device_id"])
        out.append({**d, "metrics": [{
            "metric": a["metric"], "label": metrics.label(a["metric"]),
            "unit": metrics.unit(a["metric"]), "decimals": metrics.decimals(a["metric"]),
            "mean": a["mean"], "z": a["z"], "k": a["k"], "ts": a["ts_from"],
        } for a in latest]})
    return out


@router.get("/devices/{device_id}", dependencies=admin)
def device_detail(device_id: str) -> dict[str, Any]:
    d = store.device(device_id)
    if not d:
        raise HTTPException(404, "设备不存在")
    return {
        "device": d,
        "metrics": [{"key": m.key, "label": m.label, "unit": m.unit,
                     "decimals": m.decimals, "module_id": m.module_id}
                    for m in metrics.for_device(device_id)],
        "finding": analysis.finding(device_id),
        "batches": store.batches(device_id, 12),
        "advice": store.advice(device_id, limit=8),
    }


@router.get("/devices/{device_id}/series", dependencies=admin)
def device_series(device_id: str, metric: str,
                  hours: int = Query(default=24, ge=1, le=168)) -> dict[str, Any]:
    if not store.device(device_id):
        raise HTTPException(404, "设备不存在")
    if metric not in metrics.METRICS:
        raise HTTPException(404, "未知指标")
    return analysis.trend(device_id, metric, hours)


@router.get("/heatmap", dependencies=admin)
def heatmap(device: str, metric: str, days: int = Query(default=7, ge=1, le=30)) -> dict[str, Any]:
    if metric not in metrics.METRICS:
        raise HTTPException(404, "未知指标")
    since = store.now_ms() - days * 86_400_000
    cells = store.heatmap(device, metric, since)
    return {
        "metric": metric, "label": metrics.label(metric), "unit": metrics.unit(metric),
        "days": days, "cells": cells,
        "k_min": min([c["n"] for c in cells] or [0]),
    }


@router.get("/wordcloud", dependencies=admin)
def wordcloud(days: int = Query(default=7, ge=1, le=30)) -> dict[str, Any]:
    today = analysis.day_of(store.now_ms())
    return {"words": store.wordcloud(days, today)}


@router.get("/advice", dependencies=admin)
def advice(device: str | None = None, risk: str | None = None,
           limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    return store.advice(device, risk, limit)


@router.get("/batches", dependencies=admin)
def batches(device: str | None = None,
            limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, Any]]:
    return store.batches(device, limit)


@router.get("/anomalies", dependencies=admin)
def anomalies(days: int = Query(default=7, ge=1, le=30)) -> list[dict[str, Any]]:
    rows = store.anomalies(store.now_ms() - days * 86_400_000, 60)
    return [{**r, "label": metrics.label(r["metric"])} for r in rows]


# ---------------------------------------------------------------- 命令与上云

@router.post("/devices/{device_id}/cmd", dependencies=admin)
def command(device_id: str, body: dict[str, Any]) -> dict[str, Any]:
    if not store.device(device_id):
        raise HTTPException(404, "设备不存在")
    cmd = body.get("cmd")
    if cmd == "report_now":
        sim.append_window()
        return {"ok": True, "cmd": cmd, "queued": 1}
    if cmd == "ping":
        return {"ok": True, "cmd": cmd, "rtt_ms": 12}
    if cmd == "set_cadence":
        seconds = int(body.get("seconds", 300))
        store.set_settings({"report_cadence_min": max(1, seconds // 60)})
        return {"ok": True, "cmd": cmd, "cadence_s": seconds}
    raise HTTPException(400, f"不支持的指令: {cmd}")


@router.get("/outbox", dependencies=admin)
def outbox() -> list[dict[str, Any]]:
    return [{k: v for k, v in o.items() if k != "payload"} for o in store.outbox(50)]


@router.get("/report/preview", dependencies=admin)
def report_preview() -> dict[str, Any]:
    """不落发件箱，只给前端看这份报表长什么样。"""
    r = analysis.build_report()
    return {
        "report_id": r["report_id"], "edge_id": r["edge_id"],
        "period": r["period"],
        "counts": {
            "devices": len(r["devices"]),
            "telemetry_daily": len(r["telemetry_daily"]),
            "advice": len(r["advice"]),
            "word_freq": len(r["word_freq"]),
        },
        "privacy": r["privacy"],
        "sample": r["telemetry_daily"][:8],
    }


@router.post("/report/cloud", dependencies=admin)
def report_cloud() -> dict[str, Any]:
    payload = analysis.build_report()
    # 契约自检：发给云之前先用同一份模型验一遍
    models.EdgeReport.model_validate(payload)
    store.enqueue_report(payload["report_id"], payload)

    if not config.CLOUD_URL:
        return {"queued": True, "report_id": payload["report_id"],
                "cloud": "not_configured", "detail": "未配置 EDGE_CLOUD_URL，报表留在发件箱"}
    try:
        # trust_env=False：边→云是内网调用，不能踩到宿主机上的 HTTP_PROXY
        headers = ({"Authorization": f"Bearer {config.CLOUD_TOKEN}"}
                   if config.CLOUD_TOKEN else {})
        with httpx.Client(timeout=8, trust_env=False) as c:
            r = c.post(f"{config.CLOUD_URL}/api/v1/ingest/edge-report",
                       json=payload, headers=headers)
        if r.status_code >= 400:
            store.mark_sent(payload["report_id"], f"HTTP {r.status_code}: {r.text[:120]}")
            return {"queued": True, "report_id": payload["report_id"],
                    "cloud": f"http_{r.status_code}", "detail": r.text[:200]}
        store.mark_sent(payload["report_id"], None)
        return {"queued": False, "report_id": payload["report_id"], "cloud": "ok",
                "bytes": len(r.content)}
    except (httpx.HTTPError, ValueError) as e:
        store.mark_sent(payload["report_id"], str(e))
        return {"queued": True, "report_id": payload["report_id"],
                "cloud": "unreachable", "detail": str(e)[:200]}


@router.get("/health", dependencies=admin)
def health() -> dict[str, Any]:
    try:
        with store.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:  # noqa: BLE001 —— 自检要吞掉任何异常并如实报告
        db_ok = False
    c = store.counters()
    return {
        "ok": db_ok,
        "edge_id": config.EDGE_ID,
        "db": "ok" if db_ok else "fail",
        "ingest_token": "set" if config.INGEST_TOKEN else "open",
        "admin_token": "set" if config.ADMIN_TOKEN else "open",
        "cloud_url": config.CLOUD_URL or None,
        "batches": c.get("batches", 0),
        "raw_rejected": c.get("raw_rejected", 0),
        "suppressed_buckets": c.get("suppressed_buckets", 0),
    }


# ---------------------------------------------------------------- 设置与隐私

@router.get("/settings", dependencies=admin)
def get_settings() -> dict[str, Any]:
    return store.get_settings()


@router.put("/settings", dependencies=admin)
def put_settings(patch: dict[str, Any]) -> dict[str, Any]:
    allowed = {"report_cadence_min", "cloud_enabled", "personalization",
               "group_analysis", "k_min", "retention_days"}
    clean = {k: v for k, v in patch.items() if k in allowed}
    if not clean:
        raise HTTPException(400, "没有可更新的字段")
    return store.set_settings(clean)


@router.get("/privacy", dependencies=admin)
def privacy() -> dict[str, Any]:
    now = store.now_ms()
    cols = analysis.daily_aggregates(now - 7 * 86_400_000)
    ks = [c["k"] for c in cols]
    dist: dict[str, int] = {}
    for k in ks:
        b = "5" if k <= 5 else "6-7" if k <= 7 else "8-9" if k <= 9 else "10+"
        dist[b] = dist.get(b, 0) + 1
    c = store.counters()
    return {
        "k_min": config.K_MIN,
        "buckets": len(ks),
        "k_distribution": dist,
        "k_min_seen": min(ks) if ks else 0,
        "suppressed_buckets": c.get("suppressed_buckets", 0),
        "raw_rejected": c.get("raw_rejected", 0),
        "pseudonym": "HMAC-SHA256(device_salt, userId)[:8]",
        "retention": store.get_settings().get("retention_days", 180),
        "fields_allowed": ["mean", "slope", "z", "n", "k", "window"],
        "fields_stripped": ["min", "max", "subject", "user_id", "values"],
    }
