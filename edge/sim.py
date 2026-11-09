"""演示数据生成器：3 台终端（1 带屏 + 2 无头）× 10 个用户 × 7 天 × 5 min。

指标名与终端仓的列名一致（systolic / temperature_c / counter_delta …），
噪声用固定种子，重复生成结果一致。
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any

from . import config, metrics, store

NOISE = {
    "systolic": 1.1, "diastolic": 0.9, "pulse": 1.2,
    "temperature_c": 0.32, "humidity_rh": 1.1, "light_lux": 260.0,
    "counter_delta": 0.8, "counter_rate": 0.15,
}

# 每个指标在一天里的形状（t = 小时 0–24）
def _value(metric: str, t: float, day_index: int, module_id: int) -> float:
    h = t % 24
    if metric == "systolic":
        return 126 + 5.5 * math.exp(-((h - 7.5) ** 2) / 3.2) + 1.8 * math.exp(-((h - 20) ** 2) / 6) + day_index * 0.12
    if metric == "diastolic":
        return 78 + 2.4 * math.exp(-((h - 7.5) ** 2) / 4) + day_index * 0.05
    if metric == "pulse":
        return 69 + 6 * math.exp(-((h - 8) ** 2) / 5) + 4 * math.exp(-((h - 18) ** 2) / 6)
    if metric == "temperature_c" and module_id == 80:
        return 23.4 + 1.6 * math.sin((h - 9) / 24 * 2 * math.pi)
    if metric == "humidity_rh" and module_id == 80:
        return 52 - 6 * math.sin((h - 9) / 24 * 2 * math.pi)
    if metric == "temperature_c" and module_id == 129:
        return 24.5 + 4.2 * math.sin((h - 10) / 24 * 2 * math.pi)
    if metric == "humidity_rh" and module_id == 129:
        return 68 - 9 * math.sin((h - 10) / 24 * 2 * math.pi)
    if metric == "light_lux":
        return max(0.0, 28000 * math.sin((h - 6.2) / 11.6 * math.pi)) if 6.2 < h < 18 else 0.0
    if metric == "counter_delta":
        # 计数增量：白天平稳，晚间做饭时段尖峰
        return 9 + 7 * math.exp(-((h - 8) ** 2) / 2.2) + 9 * math.exp(-((h - 19) ** 2) / 3)
    if metric == "counter_rate":
        return (9 + 7 * math.exp(-((h - 8) ** 2) / 2.2) + 9 * math.exp(-((h - 19) ** 2) / 3)) / 5
    return 0.0


def _spike(metric: str, window_start: int) -> float:
    """人工注入的异常，保证演示里一定看得到告警。"""
    rnd = random.Random(f"spike-{metric}-{window_start}")
    return rnd.uniform(2.6, 3.4) if rnd.random() < 0.004 else 0.0


ADVICE = {
    83: [
        ("收缩压连续三个窗口高于基线，建议复测并与医生确认", "alert", 0.81),
        ("近 7 天收缩压缓慢上升，建议复测并关注晨间读数", "watch", 0.72),
        ("脉搏与血压同步平稳，未见异常", "info", 0.78),
        ("舒张压夜间低于基线，建议关注睡眠时长", "watch", 0.63),
    ],
    80: [
        ("盆土温度偏低，建议检查摆放位置", "watch", 0.64),
        ("环境湿度不足，建议补水并观察叶片", "watch", 0.67),
        ("盆栽环境平稳，与昨日同一时段接近", "info", 0.75),
    ],
    129: [
        ("温室内温度偏高，建议开启通风", "watch", 0.69),
        ("光照低于生长区间，建议补光", "watch", 0.66),
        ("温湿度平稳，处于适宜区间", "info", 0.8),
    ],
    130: [
        ("计数速率出现尖峰，与晚间时段吻合", "alert", 0.74),
        ("夜间计数速率偏高，建议核对用电设备", "watch", 0.62),
        ("计数增量平稳，未见异常尖峰", "info", 0.77),
    ],
}


def _advice(metric: str, module_id: int, z: float, ts: int) -> dict[str, Any] | None:
    texts = ADVICE.get(module_id, [])
    if not texts:
        return None
    rnd = random.Random(f"{metric}|{ts}")
    if abs(z) >= 2.5:
        t = texts[0] if texts[0][1] == "alert" else texts[1]
    elif abs(z) >= 1.5 and rnd.random() < 0.5:
        t = texts[1] if len(texts) > 2 else texts[0]
    elif rnd.random() < 0.04:
        t = texts[-1]
    else:
        return None
    return {"text": t[0], "risk": t[1], "confidence": t[2], "source": "local"}


def generate(days: int = 7) -> dict[str, int]:
    rnd = random.Random(20261109)
    now = store.now_ms()
    window = config.WINDOW_MS
    end = now // window * window
    start = end - days * 24 * 3600_000

    for d in metrics.DEVICES:
        store.upsert_device(d["device_id"], d["name"], d["scene"], d["fw"],
                            d["modules"], cert_fp=_fp(d["device_id"]))

    # 先算数值，再算 z（相对同小时历史），z 不是编的
    base: dict[str, list[float]] = {}
    for d in metrics.DEVICES:
        for m in metrics.for_device(d["device_id"]):
            for ts in range(start, end, window):
                h = (ts / 3600_000) % 24
                day_index = (ts - start) / 86_400_000
                v = _value(m.key, h, day_index, m.module_id) + rnd.gauss(0, NOISE[m.key])
                z_spike = _spike(m.key, ts)
                if z_spike:
                    v += z_spike * NOISE[m.key]
                base.setdefault(f"{d['device_id']}|{m.key}|{int(h)}", []).append(v)

    inserted = 0
    suppressed = 0
    with store.connect() as conn:
        conn.execute("DELETE FROM telemetry")
        conn.execute("DELETE FROM aggregates")
        conn.execute("DELETE FROM advice")
        conn.execute("DELETE FROM word_freq")
        conn.execute("DELETE FROM counters")

        for d in metrics.DEVICES:
            dev = d["device_id"]
            for ts in range(start, end, window):
                h = (ts / 3600_000) % 24
                day_index = (ts - start) / 86_400_000
                aggs, adv_out = [], []
                # 10 个用户里多数在报；抑制按「指标 × 窗口」发生
                subjects = 8 + rnd.randint(0, 2)
                for m in metrics.for_device(dev):
                    if rnd.random() < 0.05:
                        suppressed += 1
                        continue
                    v = _value(m.key, h, day_index, m.module_id) + rnd.gauss(0, NOISE[m.key])
                    z_spike = _spike(m.key, ts)
                    if z_spike:
                        v += z_spike * NOISE[m.key]
                    if m.key == "light_lux":
                        v = max(0.0, v)
                    if m.key in ("counter_delta", "counter_rate"):
                        v = max(0.0, v)
                    hist = base[f"{dev}|{m.key}|{int(h)}"]
                    mu = sum(hist) / len(hist)
                    sd = math.sqrt(sum((x - mu) ** 2 for x in hist) / len(hist))
                    # 噪声地板：夜间光照这类同小时几乎恒定的指标不能让 z 被 sd≈0 放大
                    sd = max(sd, NOISE[m.key] * 0.9, 1e-6)
                    z = (v - mu) / sd
                    v_prev = _value(m.key, h - window / 3600_000, day_index, m.module_id)
                    aggs.append({
                        "metric": m.key, "module_id": m.module_id,
                        "n_subjects": subjects, "n_samples": subjects * rnd.randint(38, 44),
                        "mean": round(v, 3), "slope": round(v - v_prev, 3),
                        "z": round(z, 2), "k": subjects,
                    })
                    a = _advice(m.key, m.module_id, z, ts)
                    if a:
                        adv_out.append(a)

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
                     json.dumps(payload, ensure_ascii=False), ts + window))
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
                conn.execute("UPDATE devices SET last_seen=? WHERE device_id=?",
                             (ts + window, dev))
                inserted += 1

    store.bump("suppressed_buckets", suppressed)
    from . import analysis
    analysis.rebuild_words()
    return {"batches": inserted, "suppressed": suppressed, "days": days}


def _fp(device_id: str) -> str:
    return hashlib.sha256(f"device:{device_id}".encode()).hexdigest()[:16]


def append_window(ts: int | None = None) -> int:
    """模拟一次上报：追加一个窗口（默认当前窗口）。"""
    now = ts or (store.now_ms() // config.WINDOW_MS * config.WINDOW_MS)
    rnd = random.Random(now)
    n = 0
    for d in metrics.DEVICES:
        dev = d["device_id"]
        aggs, adv_out = [], []
        h = (now / 3600_000) % 24
        subjects = 8 + rnd.randint(0, 2)
        for m in metrics.for_device(dev):
            v = _value(m.key, h, 7, m.module_id) + rnd.gauss(0, NOISE[m.key])
            v = max(0.0, v)
            z = rnd.gauss(0, 0.8)
            aggs.append({
                "metric": m.key, "module_id": m.module_id,
                "n_subjects": subjects, "n_samples": subjects * 40,
                "mean": round(v, 3), "slope": round(rnd.gauss(0, 0.2), 3),
                "z": round(z, 2), "k": subjects,
            })
            a = _advice(m.key, m.module_id, z, now)
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
    from . import analysis
    analysis.rebuild_words()
    return n


def backfill(max_windows: int = 288) -> int:
    """把最后一个批次到现在的空窗口补齐，演示环境不会显示成「断线」。"""
    window = config.WINDOW_MS
    current = store.now_ms() // window * window
    with store.connect() as conn:
        row = conn.execute("SELECT MAX(ts_to) AS m FROM telemetry").fetchone()
    last = row["m"] or (current - window)
    ts = max(last, current - max_windows * window)
    n = 0
    while ts < current:
        append_window(ts)
        ts += window
        n += 1
    return n
