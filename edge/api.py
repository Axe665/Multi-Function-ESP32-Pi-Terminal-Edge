"""边节点 HTTP API。设备侧走 /ingest，管理侧给前端用。"""
from __future__ import annotations

import json

import re
from typing import Any


from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import ValidationError

from . import (analysis, catalog, cloudpush, config, ingest, mdns, models,
               mqtt, scheduler, security, sim, store)

router = APIRouter(prefix="/api/v1")


def _group_on() -> bool:
    """文档 §8.5：群体分析关闭时只留在线/健康计数。"""
    return bool(store.get_settings().get("group_analysis", False))


# ---------------------------------------------------------------- 鉴权

def _model_name(name: str) -> str:
    m = re.search(r"[A-Za-z0-9][A-Za-z0-9 ._-]*$", name or "")
    return (m.group(0).strip() if m else name) or ""


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


def _module_list(device_id: str, module_ids: list[int]) -> list[dict[str, Any]]:
    """设备装了哪些模块：module_id 来自 status，名字取 catalog 里的 package_id。"""
    seen: dict[int, dict[str, Any]] = {}
    for mid in module_ids or []:
        seen[mid] = {"module_id": mid, "package_id": "", "name": ""}
    for row in catalog.for_device(device_id):
        mid = row["module_id"]
        entry = seen.setdefault(mid, {"module_id": mid, "package_id": "", "name": ""})
        entry["package_id"] = entry["package_id"] or (row.get("package_id") or "")
    return list(seen.values())


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
    try:
        return ingest.process(body)
    except ingest.IngestError as e:
        detail: dict[str, Any] = {"code": e.code, "message": e.message}
        if e.fields:
            detail["fields" if e.code == "RAW_PAYLOAD_REJECTED" else "errors"] = e.fields
        raise HTTPException(507 if e.code == "DISK_LOW" else 422, detail)


@router.get("/discovery", dependencies=admin)
def discovery() -> dict[str, Any]:
    """mDNS 广播 + 已登记设备合并。找不到组播时只返回已登记的。"""
    seen = {d["device_id"]: d for d in store.devices()}
    out = []
    for dev in mdns.mdns.browse(0.6):
        base = seen.pop(dev["device_id"], None)
        out.append({**dev, "scene": base["scene"] if base else None,
                    "paired": bool(base and base["paired_at"]),
                    "link": base["link"] if base else "unknown",
                    "last_seen": base["last_seen"] if base else None})
    for d in seen.values():
        out.append({
            # 名字是「诊室屏 Pi 3B」，型号取末尾那串拉丁字母/数字
            "device_id": d["device_id"], "model": _model_name(d["name"]),
            "fw": d["fw"], "port": 4580, "address": None, "scene": d["scene"],
            "link": d["link"], "paired": bool(d["paired_at"]),
            "last_seen": d["last_seen"], "source": "registry",
        })
    return {"service": mdns.DEVICE_TYPE, "edge": mdns.mdns.status(), "devices": out}


@router.post("/devices/{device_id}/pair", dependencies=admin)
def pair(device_id: str) -> dict[str, Any]:
    if not store.device(device_id):
        raise HTTPException(404, "设备不存在")
    code = security.new_pair_code(device_id)
    return {"device_id": device_id, "code": code, "ttl_s": 600}


@router.post("/pair/redeem", dependencies=device)
def pair_redeem(body: dict[str, Any]) -> dict[str, Any]:
    """终端拿配对码 + CSR 换证书。失败次数与锁定在这里生效。"""
    code = str(body.get("code", ""))
    csr = str(body.get("csr", ""))
    if not code or not csr:
        raise HTTPException(400, "需要 code 与 csr")
    try:
        return security.redeem(code, csr)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/ca.crt", dependencies=admin)
def ca_crt() -> dict[str, Any]:
    security.ensure_ca()
    return {"pem": security.CA_CRT.read_text(), "fingerprint": security.ca_fingerprint()}


@router.get("/crl.pem", dependencies=admin)
def crl() -> dict[str, Any]:
    return {"pem": security.crl_pem().decode(), "revoked": len(store.revoked())}


@router.get("/certs", dependencies=admin)
def certs() -> list[dict[str, Any]]:
    return security.device_certs()


@router.post("/devices/{device_id}/renew", dependencies=device)
def renew_cert(device_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """设备到期前拿新证书；旧证书保留到自然过期，避免交接期断链。"""
    try:
        return security.renew(device_id, str(body.get("csr", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/devices/{device_id}/wifi-config", dependencies=admin)
def wifi_config(device_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """给无头终端生成 wpa_supplicant.conf（文档 §5.7.5）。

    PSK 只在这次请求里出现：不落库、不进日志、审计只记设备与 SSID 长度。
    """
    if not store.device(device_id):
        raise HTTPException(404, "设备不存在")
    ssid = str(body.get("ssid") or "")
    psk = str(body.get("psk") or "")
    country = str(body.get("country") or "CN").upper()[:2]
    if not 1 <= len(ssid) <= 32:
        raise HTTPException(400, "SSID 长度必须是 1–32")
    if not 8 <= len(psk) <= 63:
        raise HTTPException(400, "WPA2 口令长度必须是 8–63")
    if not country.isalpha():
        raise HTTPException(400, "country 必须是两位字母国家码")
    content = (
        f"country={country}\n"
        "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
        "update_config=1\n\n"
        "network={\n"
        f'    ssid="{ssid}"\n'
        f'    psk="{psk}"\n'
        "    key_mgmt=WPA-PSK\n"
        "}\n"
    )
    store.audit_action("admin", "device.wifi_config", device_id,
                       {"ssid_len": len(ssid), "country": country})
    return {"filename": f"wpa_supplicant-{device_id}.conf", "content": content,
            "note": "复制到 U 盘根目录，终端启动时读取；口令不做服务端保存"}


@router.post("/devices/{device_id}/revoke", dependencies=admin)
def revoke(device_id: str) -> dict[str, Any]:
    n = security.revoke(device_id, "admin")
    store.audit_action("admin", "device.revoke", device_id, {"certs": n})
    return {"device_id": device_id, "revoked": n, "crl_size": len(store.revoked())}


@router.post("/certs/verify", dependencies=admin)
def verify_cert(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return security.verify(str(body.get("pem", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/pair-codes", dependencies=admin)
def pair_codes() -> list[dict[str, Any]]:
    return store.pair_codes()


# ---------------------------------------------------------------- 查询

@router.get("/overview", dependencies=admin)
def overview() -> dict[str, Any]:
    return analysis.overview()


@router.get("/metrics", dependencies=admin)
def metric_catalog() -> list[dict[str, Any]]:
    """端上报过的所有指标 —— 前端下拉框的数据源，没有写死的列表。"""
    return catalog.all_labels()


@router.get("/devices", dependencies=admin)
def devices() -> list[dict[str, Any]]:
    out = []
    for d in store.devices():
        latest = store.latest_aggregates(d["device_id"]) if _group_on() else []
        out.append({**d,
                    "module_list": _module_list(d["device_id"], d["modules"]),
                    "metrics": [{
                        "metric": a["metric"],
                        "label": catalog.label(d["device_id"], a["metric"]),
                        "unit": catalog.unit(d["device_id"], a["metric"]),
                        "decimals": catalog.decimals(d["device_id"], a["metric"]),
                        "module_id": a["module_id"], "mean": a["mean"], "z": a["z"],
                        "k": a["k"], "ts": a["ts_from"],
                    } for a in latest]})
    return out


@router.get("/devices/{device_id}", dependencies=admin)
def device_detail(device_id: str) -> dict[str, Any]:
    d = store.device(device_id)
    if not d:
        raise HTTPException(404, "设备不存在")
    if not _group_on():
        return {"device": d, "modules": _module_list(device_id, d["modules"]),
                "metrics": [], "k_min": 0, "finding": None, "batches": [], "advice": [],
                "insufficient": True,
                "reason": "群体分析已关闭，只保留在线与健康计数"}
    latest = {a["metric"]: a for a in store.latest_aggregates(device_id)}
    metrics = []
    for m in catalog.for_device(device_id):
        a = latest.get(m["metric"], {})
        metrics.append({"metric": m["metric"], "key": m["metric"], "label": m["label"],
                        "unit": m["unit"], "decimals": m["decimals"],
                        "module_id": m["module_id"], "table": m["table_name"],
                        "mean": a.get("mean"), "z": a.get("z"), "k": a.get("k")})
    return {
        "device": d,
        "modules": _module_list(device_id, d["modules"]),
        "metrics": metrics,
        "k_min": min([m["k"] for m in metrics if m.get("k")] or [0]),
        "finding": analysis.finding(device_id),
        "batches": store.batches(device_id, 12),
        "advice": store.advice(device_id, limit=8),
    }


@router.get("/devices/{device_id}/series", dependencies=admin)
def device_series(device_id: str, metric: str,
                  hours: int = Query(default=24, ge=1, le=168),
                  from_: int | None = Query(default=None, alias="from"),
                  to: int | None = Query(default=None)) -> dict[str, Any]:
    """文档 §5.5 写的是 from/to；本机页面用 hours 更方便，两种都收。"""
    if not store.device(device_id):
        raise HTTPException(404, "设备不存在")
    if not catalog.get(device_id, metric):
        raise HTTPException(404, "这台设备没有这个指标")
    if not _group_on():
        return analysis.empty_trend(device_id, metric)
    if from_ and to and to > from_:
        return analysis.trend_range(device_id, metric, from_, to)
    return analysis.trend(device_id, metric, hours)


@router.get("/heatmap", dependencies=admin)
def heatmap(device: str, metric: str, days: int = Query(default=7, ge=1, le=30)) -> dict[str, Any]:
    if not catalog.get(device, metric):
        raise HTTPException(404, "这台设备没有这个指标")
    if not _group_on():
        return {"metric": metric, "label": catalog.label(device, metric),
                "unit": catalog.unit(device, metric), "days": days,
                "cells": [], "k_min": 0, "insufficient": True,
                "reason": "群体分析已关闭，只保留在线与健康计数"}
    since = store.now_ms() - days * 86_400_000
    cells = store.heatmap(device, metric, since)
    return {
        "metric": metric, "label": catalog.label(device, metric),
        "unit": catalog.unit(device, metric),
        "days": days, "cells": cells,
        "k_min": min([c["n"] for c in cells] or [0]),
    }


@router.get("/wordcloud", dependencies=admin)
def wordcloud(days: int = Query(default=7, ge=1, le=30)) -> dict[str, Any]:
    if not store.get_settings().get("group_analysis", False):
        # 词云是全体建议文本的聚合，属于群体分析（文档 §8.5）
        return {"words": [], "insufficient": True, "reason": "群体分析已关闭"}
    today = analysis.day_of(store.now_ms())
    return {"words": store.wordcloud(days, today)}


@router.get("/advice", dependencies=admin)
def advice(device: str | None = None, risk: str | None = None,
           limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    if not _group_on():
        return []
    return store.advice(device, risk, limit)


@router.get("/batches", dependencies=admin)
def batches(device: str | None = None,
            limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, Any]]:
    if not _group_on():
        return []
    return store.batches(device, limit)


@router.get("/alerts", dependencies=admin)
def alerts(days: int = Query(default=7, ge=1, le=30),
           state: str = Query(default="open")) -> list[dict[str, Any]]:
    rows = store.alert_feed(store.now_ms() - days * 86_400_000,
                            stale_ms=3 * config.WINDOW_MS)
    for r in rows:
        r["label"] = "数据过期" if r["kind"] == "stale" \
            else catalog.label(r["device_id"], r["metric"])
        r["unit"] = "" if r["kind"] == "stale" \
            else catalog.unit(r["device_id"], r["metric"])
        r["device_name"] = (store.device(r["device_id"]) or {}).get("name", r["device_id"])
    if state == "open":
        rows = [r for r in rows if r["state"] in ("pending", "acked", "muted")]
    return rows


def _alert_target(body: dict[str, Any]) -> tuple[str, str, int]:
    try:
        return (str(body["device_id"]), str(body["metric"]), int(body["ts_from"]))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "需要 device_id、metric、ts_from") from None


@router.post("/alerts/ack", dependencies=admin)
def ack(body: dict[str, Any]) -> dict[str, Any]:
    device_id, metric, ts_from = _alert_target(body)
    actor = "admin"
    store.ack_alert(device_id, metric, ts_from, actor)
    return {"ok": True}


@router.post("/alerts/mute", dependencies=admin)
def mute(body: dict[str, Any]) -> dict[str, Any]:
    device_id, metric, ts_from = _alert_target(body)
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(422, "静音需要填写理由")
    hours = int(body.get("hours") or 0)
    if hours <= 0:
        raise HTTPException(422, "静音需要有效期")
    actor = "admin"
    until = store.now_ms() + hours * 3_600_000
    store.mute_alert(device_id, metric, ts_from, until, reason, actor)
    return {"ok": True, "muted_until": until}


@router.post("/alerts/unmute", dependencies=admin)
def unmute(body: dict[str, Any]) -> dict[str, Any]:
    device_id, metric, ts_from = _alert_target(body)
    store.unmute_alert(device_id, metric, ts_from)
    return {"ok": True}


@router.get("/anomalies", dependencies=admin)
def anomalies(days: int = Query(default=7, ge=1, le=30)) -> list[dict[str, Any]]:
    if not _group_on():
        return []
    rows = store.anomalies(store.now_ms() - days * 86_400_000, 60)
    return [{**r, "label": catalog.label(r["device_id"], r["metric"])} for r in rows]


# ---------------------------------------------------------------- 命令与上云

@router.post("/devices/{device_id}/cmd", dependencies=admin)
def command(device_id: str, body: dict[str, Any]) -> dict[str, Any]:
    if not store.device(device_id):
        raise HTTPException(404, "设备不存在")
    cmd = body.get("cmd")
    if cmd not in ("report_now", "ping", "set_cadence"):
        raise HTTPException(400, f"不支持的指令: {cmd}")

    payload: dict[str, Any] = {"cmd": cmd}
    if cmd == "set_cadence":
        seconds = max(60, int(body.get("seconds", 300)))
        payload["seconds"] = seconds
        store.set_settings({"report_cadence_min": max(1, seconds // 60)})

    # 真设备走 MQTT；演示里没有终端在听，本地补一个窗口让界面有反应
    sent = mqtt.mqtt_ingest.publish_cmd(device_id, payload)
    if cmd == "report_now" and config.DEMO:
        sim.append_window()
    store.audit_action("admin", "device.cmd", device_id, {"cmd": cmd, "mqtt": sent})
    return {"ok": bool(sent) or config.DEMO, "cmd": cmd,
            "via": "mqtt" if sent else "sim" if config.DEMO else "none",
            **({"seconds": payload["seconds"]} if cmd == "set_cadence" else {})}


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


@router.post("/cloud/config", dependencies=admin)
def set_cloud_config(body: dict[str, Any]) -> dict[str, Any]:
    """运行时配置云地址/令牌（落盘 data/cloud.json，重启仍生效）。"""
    from . import config as cfg

    url = str(body.get("url", "")).strip()
    token = str(body.get("token", "")).strip()
    if url and not url.startswith(("https://", "http://")):
        raise HTTPException(400, "云地址必须以 http:// 或 https:// 开头")
    data = {"url": url, "token": token}
    cfg.CLOUD_OVERRIDE_PATH.write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cfg.CLOUD_URL = url
    cfg.CLOUD_TOKEN = token
    return {"configured": bool(url), "url": url}


@router.post("/report/cloud", dependencies=admin)
def report_cloud() -> dict[str, Any]:
    """手动上报：和定时任务走同一条路径（cloudpush.push_now），别维护两份。"""
    out = cloudpush.push_now()
    body = {"queued": out["queued"], "report_id": out["report_id"],
            "cloud": out["status"], "detail": (out.get("detail") or "")[:200]}
    if out.get("bytes"):
        body["bytes"] = out["bytes"]
    return body


@router.get("/health", dependencies=admin)
def health() -> dict[str, Any]:
    try:
        with store.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:  # noqa: BLE001 —— 自检要吞掉任何异常并如实报告
        db_ok = False
    c = store.counters()
    last = (store.outbox(1) or [None])[0]
    return {
        "ok": db_ok,
        "edge_id": config.EDGE_ID,
        "demo": config.DEMO,
        "build": config.BUILD,
        "db": "ok" if db_ok else "fail",
        "ingest_token": "set" if config.INGEST_TOKEN else "open",
        "admin_token": "set" if config.ADMIN_TOKEN else "open",
        "cloud_url": config.CLOUD_URL or None,
        "cloud": {"configured": bool(config.CLOUD_URL),
                  "last_sent_at": (last or {}).get("sent_at"),
                  "last_error": (last or {}).get("last_error")},
        "batches": c.get("batches", 0),
        "raw_rejected": c.get("raw_rejected", 0),
        "suppressed_buckets": c.get("suppressed_buckets", 0),
        "mqtt": mqtt.mqtt_ingest.status(),
        "mdns": mdns.mdns.status(),
        "scheduler": {"ticks": scheduler.scheduler.ticks,
                      "last": scheduler.scheduler.last},
        "db_cipher": "sqlcipher" if config.DB_KEY else "plain",
        "db_key": config.DB_KEY_SOURCE or None,
        "db_plaintext_existing": config.DB_PLAINTEXT_EXISTING,
        "disk_free_mb": ingest.disk_free_mb(),
        "ca_fp": security.ca_fingerprint(),
        "certs_expiring": len(security.expiring()),
        "text_scrubbed": c.get("text_scrubbed", 0),
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
    before = store.get_settings()
    after = store.set_settings(clean)
    # 文档 §8.3：授权变更要留审计（时间、操作者、改动前后）
    for k in ("personalization", "group_analysis"):
        if k in clean and clean[k] != before.get(k):
            store.audit_action("admin", "consent.change", k,
                               {"from": before.get(k), "to": clean[k]})
    return after


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
