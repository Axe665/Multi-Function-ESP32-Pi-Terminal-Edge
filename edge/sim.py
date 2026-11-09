"""演示数据生成器：3 台终端 × 10 个用户 × 7 天 × 5 min 窗口。

噪声用固定种子，重复生成结果一致；不做随机漂移，避免两次截图数字对不上。
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from . import config, store

DEVICES = [
    {"device_id": "mt-3b-01", "name": "诊室屏 · Pi 3B", "scene": "health",
     "modules": [83, 84], "fw": "orpi 1.4.2"},
    {"device_id": "mt-a64-02", "name": "温室无头 · Pine64", "scene": "env",
     "modules": [21, 22], "fw": "orpi 1.4.2"},
    {"device_id": "mt-rk64-03", "name": "配电无头 · Rock64", "scene": "energy",
     "modules": [31, 32], "fw": "orpi 1.4.2"},
]

NOISE = {
    "bp.systolic": 1.1, "spo2": 0.28, "weight": 0.05,
    "env.temp": 0.32, "env.humidity": 1.1, "env.co2": 28.0,
    "energy.load": 0.06, "energy.pv": 0.10,
}


def _value(metric: str, t: float, day_index: int) -> float:
    """t = 一天内的小时数（0–24）。"""
    h = t % 24
    if metric == "bp.systolic":
        return 127 + 5.5 * math.exp(-((h - 7.5) ** 2) / 3.2) + 1.8 * math.exp(-((h - 20) ** 2) / 6) + day_index * 0.12
    if metric == "spo2":
        return 97.2 - 0.8 * math.exp(-((h - 3) ** 2) / 8)
    if metric == "weight":
        return 68.6 - day_index * 0.03
    if metric == "env.temp":
        return 22.4 + 2.6 * math.sin((h - 9) / 24 * 2 * math.pi)
    if metric == "env.humidity":
        return 54 - 9 * math.sin((h - 9) / 24 * 2 * math.pi)
    if metric == "env.co2":
        return 560 + 240 * math.exp(-((h - 14) ** 2) / 12) + 120 * math.exp(-((h - 9) ** 2) / 4)
    if metric == "energy.load":
        return 1.15 + 1.05 * math.exp(-((h - 8) ** 2) / 2.2) + 1.35 * math.exp(-((h - 19) ** 2) / 3)
    if metric == "energy.pv":
        return max(0.0, 3.5 * math.sin((h - 6.5) / 11.5 * math.pi)) if 6.5 < h < 18 else 0.0
    return 0.0


def _spike(metric: str, window_start: int, seed: int) -> float:
    """人工注入的异常，保证演示里一定看得到告警。"""
    rnd = random.Random(f"{metric}-{window_start}-{seed}")
    return rnd.uniform(2.6, 3.4) if rnd.random() < 0.004 else 0.0


def _metrics_for(device_id: str) -> list[str]:
    from . import metrics
    return [m.key for m in metrics.for_device(device_id)]


ADVICE_TEMPLATES = {
    "bp.systolic": [
        ("近 7 天收缩压缓慢上升，建议复测并关注晨间读数", "watch", 0.72),
        ("收缩压连续三个窗口高于基线，建议复测并与医生确认", "alert", 0.81),
        ("收缩压日间平稳，晨间峰值较上周回落", "info", 0.66),
    ],
    "spo2": [
        ("昨夜血氧平稳，未见连续偏低", "info", 0.78),
        ("血氧出现短时偏低，建议关注睡眠时段", "watch", 0.58),
    ],
    "weight": [
        ("体重一周内变化在正常范围，趋势平稳", "info", 0.7),
    ],
    "env.temp": [
        ("室内温度日间波动较大，注意结露风险", "watch", 0.64),
        ("室内温度平稳，与昨日同一时段接近", "info", 0.75),
    ],
    "env.humidity": [
        ("相对湿度偏高，建议通风降低结露风险", "watch", 0.61),
        ("相对湿度处于舒适区间", "info", 0.8),
    ],
    "env.co2": [
        ("午后 CO₂ 连续偏高，建议换气通风", "watch", 0.69),
        ("CO₂ 出现尖峰，与人员集中时段吻合", "alert", 0.74),
    ],
    "energy.load": [
        ("用电负荷尖峰前移，峰谷差扩大", "watch", 0.63),
        ("用电负荷平稳，未见异常尖峰", "info", 0.77),
    ],
    "energy.pv": [
        ("光伏午间出力回落，较昨日低 0.4 kW", "watch", 0.6),
        ("光伏出力与天气预报一致", "info", 0.72),
    ],
}


def _advice(metric: str, z: float, ts: int) -> dict[str, Any] | None:
    """只在真正值得说的时候出建议，避免建议流被噪声淹掉。"""
    texts = ADVICE_TEMPLATES.get(metric, [])
    if not texts:
        return None
    rnd = random.Random(f"{metric}|{ts}")
    if abs(z) >= 2.5 and len(texts) > 1:
        t = texts[1]
    elif abs(z) >= 1.5 and rnd.random() < 0.5:
        t = texts[0]
    elif rnd.random() < 0.04:
        t = texts[-1]
    else:
        return None
    return {"text": t[0], "risk": t[1], "confidence": t[2], "source": "local"}


def generate(days: int = 7) -> dict[str, int]:
    """重建演示库，返回写入统计。"""
    rnd = random.Random(20261109)
    now = store.now_ms()
    window = config.WINDOW_MS
    end = now // window * window
    start = end - days * 24 * 3600_000

    for d in DEVICES:
        store.upsert_device(d["device_id"], d["name"], d["scene"], d["fw"], d["modules"],
                            cert_fp=hashlib.sha256(d["device_id"].encode()).hexdigest()[:16])

    # 先算数值，再算 z（相对同小时的历史均值），保证 z 不是瞎编的
    base: dict[str, list[float]] = {}
    for d in DEVICES:
        for m in _metrics_for(d["device_id"]):
            for ts in range(start, end, window):
                h = (ts / 3600_000) % 24
                day_index = (ts - start) / 86_400_000
                v = _value(m, h, day_index) + rnd.gauss(0, NOISE[m])
                z_spike = _spike(m, ts, 7)
                if z_spike:
                    v += z_spike * NOISE[m]
                base.setdefault(f"{m}|{int(h)}", []).append(v)

    inserted = 0
    suppressed = 0
    with store.connect() as conn:
        conn.execute("DELETE FROM telemetry")
        conn.execute("DELETE FROM aggregates")
        conn.execute("DELETE FROM advice")
        conn.execute("DELETE FROM word_freq")
        conn.execute("DELETE FROM counters")

        for d in DEVICES:
            dev = d["device_id"]
            for ts in range(start, end, window):
                h = (ts / 3600_000) % 24
                day_index = (ts - start) / 86_400_000
                aggs, adv_out = [], []
                # 轮换：8–10 人上报。抑制按「指标 × 窗口」发生（某个模块掉线），
                # 整批仍然会发出，所以链路带看起来是连续的。
                subjects = 8 + rnd.randint(0, 2)
                for m in _metrics_for(dev):
                    if rnd.random() < 0.05:
                        suppressed += 1
                        continue
                    v = _value(m, h, day_index) + rnd.gauss(0, NOISE[m])
                    z_spike = _spike(m, ts, 7)
                    if z_spike:
                        v += z_spike * NOISE[m]
                    if m == "energy.pv":
                        v = max(0.0, v)
                    hist = base[f"{m}|{int(h)}"]
                    mu = sum(hist) / len(hist)
                    sd = math.sqrt(sum((x - mu) ** 2 for x in hist) / len(hist))
                    # 噪声地板：同小时内几乎恒定的指标（夜间光伏）不能让 z 被 sd≈0 放大
                    sd = max(sd, NOISE[m] * 0.9, 1e-6)
                    z = (v - mu) / sd
                    v_prev = _value(m, h - window / 3600_000, day_index) + rnd.gauss(0, NOISE[m])
                    slope = v - v_prev
                    from . import metrics
                    aggs.append({
                        "metric": m, "module_id": metrics.METRICS[m].module_id,
                        "n_subjects": subjects, "n_samples": subjects * rnd.randint(38, 44),
                        "mean": round(v, 2), "slope": round(slope, 3),
                        "z": round(z, 2), "k": subjects,
                    })
                    a = _advice(m, z, ts)
                    if a:
                        adv_out.append(a)

                # 所有指标都被抑制的极端窗口也要更新 last_seen：
                # 终端确实上报了，只是没有可入库的桶。
                if not aggs:
                    conn.execute("UPDATE devices SET last_seen=? WHERE device_id=?",
                                 (ts + window, dev))
                    continue
                batch_id = hashlib.sha256(f"{dev}|{ts}".encode()).hexdigest()[:16]
                payload = {
                    "schema": "orpi.telemetry.v1", "device_id": dev,
                    "edge_id": config.EDGE_ID, "sent_at": ts + window,
                    "window": {"from": ts, "to": ts + window, "step_ms": window},
                    "aggregates": aggs, "advice": adv_out,
                    "privacy": {"k": min(a["k"] for a in aggs), "pseudonym": "hmac16",
                                "raw": False, "suppressed": 0},
                }
                conn.execute(
                    """INSERT OR REPLACE INTO telemetry
                       (device_id, batch_id, ts_from, ts_to, payload, received_at)
                       VALUES(?,?,?,?,?,?)""",
                    (dev, batch_id, ts, ts + window,
                     __import__("json").dumps(payload, ensure_ascii=False), ts + window))
                for a in aggs:
                    conn.execute(
                        """INSERT OR REPLACE INTO aggregates
                           (device_id, metric, module_id, ts_from, ts_to,
                            n_subjects, n_samples, mean, slope, z, k)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (dev, a["metric"], a["module_id"], ts, ts + window,
                         a["n_subjects"], a["n_samples"], a["mean"], a["slope"], a["z"], a["k"]))
                for a in adv_out:
                    conn.execute(
                        """INSERT INTO advice(device_id, text, risk, confidence, source, created_at)
                           VALUES(?,?,?,?,?,?)""",
                        (dev, a["text"], a["risk"], a["confidence"], a["source"], ts + window))
                conn.execute(
                    "UPDATE devices SET last_seen=? WHERE device_id=?", (ts + window, dev))
                inserted += 1

    store.bump("suppressed_buckets", suppressed)
    from . import analysis
    analysis.rebuild_words()
    return {"batches": inserted, "suppressed": suppressed, "days": days}


def append_window(ts: int | None = None) -> int:
    """模拟一次上报：追加一个窗口（默认当前窗口）。"""
    now = ts or (store.now_ms() // config.WINDOW_MS * config.WINDOW_MS)
    rnd = random.Random(now)
    n = 0
    from . import analysis, metrics
    for d in DEVICES:
        dev = d["device_id"]
        aggs, adv_out = [], []
        h = (now / 3600_000) % 24
        subjects = 8 + rnd.randint(0, 2)
        for m in metrics.for_device(dev):
            v = _value(m.key, h, 7) + rnd.gauss(0, NOISE[m.key])
            z = rnd.gauss(0, 0.8)
            aggs.append({
                "metric": m.key, "module_id": m.module_id, "n_subjects": subjects,
                "n_samples": subjects * 40, "mean": round(v, 2),
                "slope": round(rnd.gauss(0, 0.2), 3), "z": round(z, 2), "k": subjects,
            })
            a = _advice(m.key, z, now)
            if a:
                adv_out.append(a)
        payload = {
            "schema": "orpi.telemetry.v1", "device_id": dev, "edge_id": config.EDGE_ID,
            "sent_at": now + config.WINDOW_MS,
            "window": {"from": now, "to": now + config.WINDOW_MS, "step_ms": config.WINDOW_MS},
            "aggregates": aggs, "advice": adv_out,
            "privacy": {"k": subjects, "pseudonym": "hmac16", "raw": False, "suppressed": 0},
        }
        store.insert_batch(dev, hashlib.sha256(f"{dev}|{now}|live".encode()).hexdigest()[:16],
                           now, now + config.WINDOW_MS, payload, aggs, adv_out)
        n += 1
    analysis.rebuild_words()
    return n


def backfill(max_windows: int = 288) -> int:
    """把最后一个批次到现在的空窗口补齐，演示环境不会显示成「断线」。"""
    window = config.WINDOW_MS
    current = store.now_ms() // window * window
    with store.connect() as conn:
        row = conn.execute("SELECT MAX(ts_to) AS m FROM telemetry").fetchone()
    last = row["m"] or (current - window)
    start = max(last, current - max_windows * window)
    n = 0
    ts = start
    while ts < current:
        append_window(ts)
        ts += window
        n += 1
    return n
