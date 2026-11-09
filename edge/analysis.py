"""分析层：趋势、热力、词云、异常、上云报表。

所有数字都从 aggregates 表重算，没有任何写死的 KPI。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import time
from collections import defaultdict
from typing import Any

from . import config, metrics, store

# 领域词表。没装 jieba，用受控词表的精确匹配代替分词：
# shortcut: 词表固定，新增建议模板时要同步加词，换 jieba 后可去掉。
LEXICON = [
    "收缩压", "血氧", "晨间", "复测", "基线", "连续偏高", "波动",
    "室内温度", "相对湿度", "通风", "结露", "co2", "二氧化碳", "换气",
    "用电负荷", "光伏", "峰谷", "夜间", "午间", "尖峰", "回落",
    "关注", "建议", "异常", "趋势", "平稳", "偏高", "偏低",
]


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
        out.append({
            "device_id": dev, "day": day, "metric": met,
            "n_subjects": max(x["n_subjects"] for x in xs),
            "n_samples": sum(x["n_samples"] for x in xs),
            "mean": round(sum(x["mean"] for x in xs) / len(xs), 3),
            "slope": round(sum(x["slope"] for x in xs) / len(xs), 4),
            "z": round(sum(x["z"] for x in xs) / len(xs), 3),
            "k": min(x["k"] for x in xs),
        })
    return out


def tokenize(text: str) -> list[str]:
    low = text.lower()
    return [w for w in LEXICON if w in low]


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

    # 7 天同段基线：同一小时窗口的历史均值
    hist = store.series(device_id, metric, now - 7 * 24 * 3_600_000, now - span, 3_600_000)
    baseline = sum(p["mean"] for p in hist) / len(hist) if hist else 0.0

    if not pts:
        return {"metric": metric, "points": [], "baseline": baseline, "delta": 0.0,
                "slope": 0.0, "current": 0.0, "k": 0}
    current = pts[-1]["mean"]
    n = len(pts)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(p["mean"] for p in pts) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1
    slope = sum((x - mx) * (p["mean"] - my) for x, p in zip(xs, pts)) / denom
    return {
        "metric": metric,
        "unit": metrics.unit(metric),
        "label": metrics.label(metric),
        "decimals": metrics.decimals(metric),
        "points": pts,
        "current": round(current, 3),
        "baseline": round(baseline, 3),
        "delta": round(current - baseline, 3),
        "slope": round(slope * n, 4),  # 每窗口平均变化
        "k": min(p["k"] for p in pts),
        "anomalies": [p for p in pts if abs(p["z"]) >= 2.5],
    }


def finding(device_id: str) -> dict[str, Any] | None:
    """该设备最近 24h 最值得说的一句话。"""
    best = None
    for m in metrics.for_device(device_id):
        t = trend(device_id, m.key, 24)
        if not t["points"]:
            continue
        score = max(abs(t["delta"]), abs(t["slope"]) * 10)
        if best is None or score > best["score"]:
            best = {"score": score, **t}
    if not best:
        return None
    d = best["delta"]
    direction = "高于" if d >= 0 else "低于"
    text = (f"{best['label']}近 24 h 平均 {best['current']:.{best['decimals']}f}"
            f"{best['unit']}，{direction} 7 天同段基线 {abs(d):.{best['decimals']}f}")
    return {"text": text, "metric": best["metric"], "delta": d}


def build_report() -> dict[str, Any]:
    """组装 orpi.edge.report.v1。report_id 由内容决定，重复生成保持幂等。"""
    now = store.now_ms()
    since = now - 24 * 3_600_000
    devices = store.devices()
    daily = daily_aggregates(since)
    adv = store.advice(limit=200, since_ms=since)
    rebuild_words()

    today = day_of(now)
    words = []
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
        "telemetry_daily": daily,
        "advice": [{
            "device_id": a["device_id"], "text": a["text"], "risk": a["risk"],
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
    c = store.counters()
    settings = store.get_settings()
    pending = [o for o in store.outbox(100) if not o["sent_at"]]

    lanes = []
    for d in devs:
        latest = store.latest_aggregates(d["device_id"])
        # 最近 24 个 5 min 窗口是否收到批次
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
            "ticks": ticks, "fill": round(sum(ticks) / len(ticks) * 100),
            "k": min([a["k"] for a in latest] or [0]),
            "metrics": [{
                "metric": a["metric"], "label": metrics.label(a["metric"]),
                "mean": a["mean"], "unit": metrics.unit(a["metric"]),
                "decimals": metrics.decimals(a["metric"]), "z": a["z"], "k": a["k"],
            } for a in latest],
        })

    findings = [f for f in (finding(d["device_id"]) for d in devs) if f]
    return {
        "edge_id": config.EDGE_ID, "edge_name": config.EDGE_NAME,
        "generated_at": now,
        "devices_total": len(devs), "devices_online": online,
        "batches_24h": batches_24h, "advice_24h": advice_24h, "alerts_24h": alerts,
        "suppressed_buckets": c.get("suppressed_buckets", 0),
        "raw_rejected": c.get("raw_rejected", 0),
        "pending_reports": len(pending),
        "cloud_enabled": settings.get("cloud_enabled", True),
        "cloud_url": config.CLOUD_URL,
        "cloud_ok": bool(config.CLOUD_URL) and settings.get("cloud_enabled", True),
        "lanes": lanes,
        "findings": findings[:3],
    }
