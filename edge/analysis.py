"""分析层：趋势、热力、词云、异常、上云报表。

所有数字都从 aggregates 表重算，没有任何写死的 KPI。
"""
from __future__ import annotations

import datetime as dt
import hashlib
from collections import defaultdict
from typing import Any

from . import catalog, config, privacy, store


def day_of(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def daily_aggregates(since_ms: int) -> list[dict[str, Any]]:
    """把 5 min 聚合按 (device, metric, day) 折叠成日聚合。"""
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT device_id, metric, ts_from, n_subjects, n_samples, mean, slope, z, k
               FROM aggregates WHERE ts_from>=? ORDER BY ts_from""",
            (since_ms,),
        ).fetchall()
    buckets: dict[tuple[str, str, str], list] = defaultdict(list)
    for r in rows:
        buckets[(r["device_id"], r["metric"], day_of(r["ts_from"]))].append(r)
    out = []
    for (dev, met, day), xs in sorted(buckets.items()):
        m = catalog.get(dev, met) or {}
        out.append({
            "device_id": dev, "day": day, "metric": met,
            "module_id": m.get("module_id", 0),
            "label": m.get("label") or met,
            "unit": m.get("unit") or "",
            "table": m.get("table_name") or "samples",
            "n_subjects": max(x["n_subjects"] for x in xs),
            "n_samples": sum(x["n_samples"] for x in xs),
            "mean": round(sum(x["mean"] for x in xs) / len(xs), 3),
            "slope": round(sum(x["slope"] for x in xs) / len(xs), 4),
            "z": round(sum(x["z"] for x in xs) / len(xs), 3),
            "k": min(x["k"] for x in xs),
        })
    return out


def tokenize(text: str) -> list[str]:
    """jieba 分词 + 停用词；没装 jieba 时退回词典精确匹配。"""
    try:
        import jieba
        words = [w.strip() for w in jieba.lcut(text)]
    except ImportError:  # pragma: no cover - 只在精简部署里走到
        words = [w for w in _LEXICON if w in text.lower()]
    return [w for w in words if len(w) >= 2 and w not in _STOP]


_STOP = {
    "建议", "关注", "需要", "可以", "已经", "当前", "这个", "那个", "一个", "我们",
    "你们", "他们", "以及", "或者", "因为", "所以", "如果", "并且", "同一", "时段",
    "出现", "进行", "确认", "观察", "检查", "与", "并", "的", "了", "在", "有",
}

_LEXICON = ["收缩压", "舒张压", "血压", "脉搏", "温度", "湿度", "光照", "计数",
            "基线", "晨间", "夜间", "午后", "温室", "盆栽", "通风", "补光", "尖峰"]


def rebuild_words() -> None:
    per_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with store.connect() as conn:
        rows = conn.execute("SELECT text, created_at FROM advice").fetchall()
    for r in rows:
        day = day_of(r["created_at"])
        for w in tokenize(r["text"]):
            per_day[day][w] += 1
    store.rebuild_word_freq(per_day)


def trend(device_id: str, metric: str, hours: int = 24) -> dict[str, Any]:
    now = store.now_ms()
    span = hours * 3_600_000
    # 24 小时视图按 15 分钟聚合：5 分钟点的窗口噪声太大，折线读不出趋势
    step = 3 * config.WINDOW_MS if hours <= 24 else 3_600_000
    pts = store.series(device_id, metric, now - span, now, step)
    hist = store.series(device_id, metric, now - 7 * 24 * 3_600_000, now - span, 3_600_000)
    baseline = sum(p["mean"] for p in hist) / len(hist) if hist else 0.0

    info = catalog.get(device_id, metric) or {}
    if not pts:
        return {"metric": metric, "points": [], "baseline": baseline, "delta": 0.0,
                "slope": 0.0, "current": 0.0, "k": 0,
                "unit": info.get("unit", ""), "label": info.get("label") or metric,
                "decimals": info.get("decimals", 1),
                "module_id": info.get("module_id", 0)}

    # 结论里的"平均"必须是窗口平均，不能拿最后一个瞬时点去比 7 天均值
    current = sum(p["mean"] for p in pts) / len(pts)
    n = len(pts)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(p["mean"] for p in pts) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1
    slope = sum((x - mx) * (p["mean"] - my) for x, p in zip(xs, pts)) / denom
    return {
        "metric": metric,
        "unit": info.get("unit", ""),
        "label": info.get("label") or metric,
        "decimals": info.get("decimals", 1),
        "module_id": info.get("module_id", 0),
        "table": info.get("table_name") or "samples",
        "points": pts,
        "current": round(current, 3),
        "baseline": round(baseline, 3),
        "delta": round(current - baseline, 3),
        "slope": round(slope * n, 4),
        "k": min(p["k"] for p in pts),
        "anomalies": [p for p in pts if abs(p["z"]) >= 2.5],
    }


def trend_range(device_id: str, metric: str, start_ms: int, end_ms: int) -> dict[str, Any]:
    """文档 §5.5 的 from/to 形式：按跨度自动选步长。"""
    span = max(1, end_ms - start_ms)
    step = 3 * config.WINDOW_MS if span <= 86_400_000 else 3_600_000
    pts = store.series(device_id, metric, start_ms, end_ms, step)
    info = catalog.get(device_id, metric) or {}
    return {"metric": metric, "label": info.get("label", metric),
            "unit": info.get("unit", ""), "table": info.get("table_name", ""),
            "decimals": info.get("decimals", 1), "module_id": info.get("module_id", 0),
            "points": pts}


def finding(device_id: str) -> dict[str, Any] | None:
    """该设备最近 24h 最值得说的一句话。"""
    best = None
    for row in catalog.for_device(device_id):
        t = trend(device_id, row["metric"], 24)
        if not t["points"]:
            continue
        pct = (t["delta"] / t["baseline"] * 100) if t["baseline"] else 0.0
        z_max = max((abs(p["z"]) for p in t["points"]), default=0.0)
        # 相对变化与统计显著性取大的那个：绝对值大小不该决定谁上榜
        score = max(abs(pct), z_max * 5)
        if best is None or score > best["score"]:
            best = {"score": score, "pct": pct, "z_max": z_max, **t}
    # 都在基线附近就直说，不硬凑一条
    if not best or best["score"] < 2:
        return None
    d = best["delta"]
    direction = "高于" if d >= 0 else "低于"
    dec = best["decimals"]
    ddec = max(dec, 1)   # 变化量至少保留一位，别把 -0.4 显示成 0
    head = f"{best['label']}近 24 h 平均 {best['current']:.{dec}f}{best['unit']}"
    if abs(best["pct"]) >= 1:
        body = f"，{direction} 7 天同段基线 {abs(d):.{ddec}f}（{best['pct']:+.1f}%）"
    else:
        body = "，与 7 天同段基线基本持平"
    text = f"{head}{body}，峰值偏离 {best['z_max']:.1f}σ"
    return {"text": text, "metric": best["metric"], "delta": d,
            "label": best["label"], "unit": best["unit"], "pct": best["pct"]}


def build_report() -> dict[str, Any]:
    """组装 orpi.edge.report.v1。report_id 由内容决定，重复生成保持幂等。"""
    now = store.now_ms()
    since = now - 24 * 3_600_000
    devices = store.devices()
    daily = daily_aggregates(since)
    adv = store.advice(limit=200, since_ms=since)
    rebuild_words()

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT day, word, count FROM word_freq WHERE day>=? ORDER BY day, count DESC",
            (day_of(since),),
        ).fetchall()
    words = [dict(r) for r in rows][:512]

    c = store.counters()
    payload = {
        "schema": "orpi.edge.report.v1",
        "report_id": "",
        "edge_id": config.EDGE_ID,
        "edge_name": config.EDGE_NAME,
        "sent_at": now,
        "period": {"from": since, "to": now},
        "devices": [{
            "device_id": d["device_id"], "scene": d["scene"], "modules": d["modules"],
            "last_seen": d["last_seen"], "online": d["online"],
        } for d in devices],
        # 出端前二次脱敏：mean 只保留 1 位小数，min/max 本来就不在契约里
        "telemetry_daily": [{**r, "mean": round(r["mean"], 1)} for r in daily],
        "advice": [{
            "device_id": a["device_id"], "text": privacy.scrub(a["text"])[0],
            "risk": a["risk"],
            "confidence": a["confidence"], "source": a["source"],
            "created_at": a["created_at"],
        } for a in adv],
        "word_freq": words,
        "privacy": {
            "k_min": config.K_MIN,
            "suppressed_buckets": c.get("suppressed_buckets", 0),
            "raw_rejected": c.get("raw_rejected", 0),
            "subjects_total": sum(max([a["n_subjects"] for a in daily if a["device_id"] == d["device_id"]] or [0])
                                  for d in devices),
        },
    }
    seed = f"{config.EDGE_ID}|{payload['period']['from']}|{payload['period']['to']}"
    payload["report_id"] = hashlib.sha256(seed.encode()).hexdigest()[:16]
    assert payload["report_id"], "report_id 不能为空"
    return payload


def overview() -> dict[str, Any]:
    now = store.now_ms()
    devs = store.devices()
    online = sum(1 for d in devs if d["online"])
    day_ago = now - 24 * 3_600_000
    with store.connect() as conn:
        batches_24h = conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE ts_from>=?", (day_ago,)).fetchone()[0]
        advice_24h = conn.execute(
            "SELECT COUNT(*) FROM advice WHERE created_at>=?", (day_ago,)).fetchone()[0]
        alerts = conn.execute(
            "SELECT COUNT(*) FROM advice WHERE created_at>=? AND risk='alert'", (day_ago,)).fetchone()[0]
        prev = day_ago - 24 * 3_600_000
        batches_prev = conn.execute(
            "SELECT COUNT(*) FROM telemetry WHERE ts_from>=? AND ts_from<?", (prev, day_ago)).fetchone()[0]
        advice_prev = conn.execute(
            "SELECT COUNT(*) FROM advice WHERE created_at>=? AND created_at<?", (prev, day_ago)).fetchone()[0]
        alerts_by_dev = {r[0]: r[1] for r in conn.execute(
            "SELECT device_id, COUNT(*) FROM advice WHERE created_at>=? AND risk='alert'"
            " GROUP BY device_id", (day_ago,))}
    c = store.counters()
    settings = store.get_settings()
    pending = [o for o in store.outbox(100) if not o["sent_at"]]

    lanes = []
    for d in devs:
        latest = store.latest_aggregates(d["device_id"])
        with store.connect() as conn:
            got = {r["ts_from"] for r in conn.execute(
                "SELECT ts_from FROM telemetry WHERE device_id=? AND ts_from>=?",
                (d["device_id"], now - 24 * config.WINDOW_MS))}
        ticks = []
        for i in range(23, -1, -1):
            t = (now // config.WINDOW_MS - i) * config.WINDOW_MS
            ticks.append(1 if t in got else 0)
        lanes.append({
            "device_id": d["device_id"], "name": d["name"], "scene": d["scene"],
            "online": d["online"], "last_seen": d["last_seen"],
            "alerts_24h": alerts_by_dev.get(d["device_id"], 0),
            "modules": d["modules"],
            "ticks": ticks, "fill": round(sum(ticks) / len(ticks) * 100),
            "k": min([a["k"] for a in latest] or [0]),
            "metrics": [{
                "metric": a["metric"], "label": catalog.label(d["device_id"], a["metric"]),
                "mean": a["mean"], "unit": catalog.unit(d["device_id"], a["metric"]),
                "decimals": catalog.decimals(d["device_id"], a["metric"]),
                "z": a["z"], "k": a["k"], "module_id": a["module_id"],
            } for a in latest],
        })

    feed = store.alert_feed(now - 7 * 86_400_000, stale_ms=3 * config.WINDOW_MS)
    open_alerts = [a for a in feed if a["state"] in ("pending", "acked", "muted")]
    pending = [a for a in open_alerts if a["state"] == "pending"]
    critical = sum(1 for a in pending if a["severity"] == "critical")
    notice = sum(1 for a in pending if a["severity"] == "notice")
    status = "critical" if critical else "notice" if notice else "ok"

    # 一台设备一条，带上设备名：前端按设备分行，否则三行看起来是同一句话
    findings = []
    for lane in lanes:
        f = finding(lane["device_id"])
        if f:
            f["device_id"] = lane["device_id"]
            f["device_name"] = lane["name"]
            findings.append(f)
    return {
        "status": {
            "level": status,
            "critical": critical,
            "notice": notice,
            "acked": sum(1 for a in open_alerts if a["state"] == "acked"),
            "muted": sum(1 for a in open_alerts if a["state"] == "muted"),
            "stale_devices": sum(1 for a in pending if a["kind"] == "stale"),
            "top": pending[:3],
        },
        "k_min": min([lane["k"] for lane in lanes if lane["k"]] or [0]),
        "edge_id": config.EDGE_ID, "edge_name": config.EDGE_NAME,
        "demo": config.DEMO, "generated_at": now,
        "devices_total": len(devs), "devices_online": online,
        "batches_24h": batches_24h, "advice_24h": advice_24h, "alerts_24h": alerts,
        "batches_prev_24h": batches_prev, "advice_prev_24h": advice_prev,
        "suppressed_buckets": c.get("suppressed_buckets", 0),
        "raw_rejected": c.get("raw_rejected", 0),
        "pending_reports": len(pending),
        "cloud_enabled": settings.get("cloud_enabled", True),
        "cloud_url": config.CLOUD_URL,
        "cloud_ok": bool(config.CLOUD_URL) and settings.get("cloud_enabled", True),
        "lanes": lanes,
        "findings": findings[:3],
    }
