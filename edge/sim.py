"""演示数据生成器：每次生成都重新抽一组板子与模块。

三块板子接什么模块是随机的 —— 带屏机也一样。指标名、单位、所属表
随模块一起上报，边登记进 catalog，界面全部照它渲染。
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any

from . import catalog, config, modules, store

NOISE = {
    "systolic": 1.1, "diastolic": 0.9, "pulse": 1.2,
    "temperature_c": 0.32, "humidity_rh": 1.1, "light_lux": 260.0,
    "battery_v": 0.03, "battery_pct": 0.4,
    "counter_delta": 0.8, "counter_rate": 0.15,
    "intrusion_count": 0.12, "frames": 0.9,
}


def _value(metric: str, t: float, day_index: int) -> float:
    h = t % 24
    if metric == "systolic":
        return 126 + 5.5 * math.exp(-((h - 7.5) ** 2) / 3.2) + 1.8 * math.exp(-((h - 20) ** 2) / 6) + day_index * 0.12
    if metric == "diastolic":
        return 78 + 2.4 * math.exp(-((h - 7.5) ** 2) / 4) + day_index * 0.05
    if metric == "pulse":
        return 69 + 6 * math.exp(-((h - 8) ** 2) / 5) + 4 * math.exp(-((h - 18) ** 2) / 6)
    if metric == "temperature_c":
        return 23.4 + 3.1 * math.sin((h - 9) / 24 * 2 * math.pi) + day_index * 0.02
    if metric == "humidity_rh":
        return 56 - 8 * math.sin((h - 9) / 24 * 2 * math.pi)
    if metric == "light_lux":
        return max(0.0, 26000 * math.sin((h - 6.2) / 11.6 * math.pi)) if 6.2 < h < 18 else 0.0
    if metric == "battery_v":
        return 3.92 - day_index * 0.004 + 0.02 * math.sin(h / 24 * 2 * math.pi)
    if metric == "battery_pct":
        return 86 - day_index * 0.35
    if metric == "counter_delta":
        return 9 + 7 * math.exp(-((h - 8) ** 2) / 2.2) + 9 * math.exp(-((h - 19) ** 2) / 3)
    if metric == "counter_rate":
        return (9 + 7 * math.exp(-((h - 8) ** 2) / 2.2) + 9 * math.exp(-((h - 19) ** 2) / 3)) / 5
    if metric == "intrusion_count":
        return max(0.0, 0.6 * math.exp(-((h - 2) ** 2) / 3))
    if metric == "frames":
        return 4 + 3 * (h % 6 < 1)
    return 10.0


def _spike(metric: str, window_start: int) -> float:
    rnd = random.Random(f"spike-{metric}-{window_start}")
    return rnd.uniform(2.6, 3.4) if rnd.random() < 0.004 else 0.0


ADVICE = {
    83: [
        ("收缩压连续三个窗口高于基线，建议复测并与医生确认", "alert", 0.81),
        ("近 7 天收缩压缓慢上升，建议复测并关注晨间读数", "watch", 0.72),
        ("脉搏与血压同步平稳，未见异常", "info", 0.78),
    ],
    80: [
        ("盆土温度偏低，建议检查摆放位置", "watch", 0.64),
        ("环境湿度不足，建议补水并观察叶片", "watch", 0.67),
        ("盆栽环境平稳，与昨日同一时段接近", "info", 0.75),
    ],
    82: [
        ("红外围界夜间触发次数偏高，建议核对布防时段", "watch", 0.66),
        ("围界电池电压下降，建议更换电池", "alert", 0.71),
        ("围界运行平稳，未见异常触发", "info", 0.79),
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
    131: [
        ("抓拍帧数下降，建议检查存储空间", "watch", 0.63),
        ("相机运行平稳，电量充足", "info", 0.76),
    ],
}

GENERIC_ADVICE = [
    ("指标出现短时波动，建议对照设备侧记录复核", "watch", 0.6),
    ("数据平稳，未见异常", "info", 0.7),
]


def _advice(module_id: int, z: float, ts: int) -> dict[str, Any] | None:
    texts = ADVICE.get(module_id, GENERIC_ADVICE)
    rnd = random.Random(f"{module_id}|{ts}")
    # 告警门槛比异常清单（2.5σ）更严：提醒要值钱
    if abs(z) >= 3.0:
        t = texts[0]
    elif abs(z) >= 1.5 and rnd.random() < 0.5:
        t = texts[1] if len(texts) > 2 else texts[0]
    elif rnd.random() < 0.04:
        t = texts[-1]
    else:
        return None
    return {"text": t[0], "risk": t[1], "confidence": t[2], "source": "local"}


def fleet(seed: int | None = None) -> list[dict]:
    """抽三块板子（1 带屏 + 2 无头），各自接 1–2 个模块。

    seed 固定时结果可复现（测试用）；不传就每次不同 —— 模块组合本来就不该是常量。
    """
    rnd = random.Random(seed)
    screens = [b for b in modules.BOARDS if not b["headless"]]
    headless = [b for b in modules.BOARDS if b["headless"]]
    boards = [rnd.choice(screens)] + rnd.sample(headless, k=min(2, len(headless)))
    out = []
    for board in boards:
        pool = [m for m in modules.CAPS if m != 82]  # 围界偶发，不进默认池
        if rnd.random() < 0.35:
            pool.append(82)
        picked = rnd.sample(sorted(pool), k=rnd.choice([1, 1, 2]))
        # 带屏机至少要有一个能看的模块
        if not board["headless"] and not set(picked) & {83, 80, 129}:
            picked[0] = 83
        scenes = {modules.CAPS[m].scene for m in picked if m in modules.CAPS}
        out.append({
            **board,
            "modules": sorted(set(picked)),
            "scene": scenes.pop() if len(scenes) == 1 else "mixed",
        })
    return out


def _register(device: dict) -> None:
    store.upsert_device(device["device_id"], device["name"], device["scene"],
                        device["fw"], device["modules"],
                        cert_fp=hashlib.sha256(device["device_id"].encode()).hexdigest()[:16])
    for row in modules.metrics_for(device["modules"]):
        catalog.upsert(device["device_id"], row["metric"], row["module_id"],
                       row["package_id"], row["label"], row["unit"], row["table"],
                       row["decimals"])


def generate(days: int = 7, seed: int | None = None) -> dict[str, int]:
    rnd = random.Random(seed if seed is not None else 20261109)
    now = store.now_ms()
    window = config.WINDOW_MS
    end = now // window * window
    start = end - days * 24 * 3600_000
    devices = fleet(seed)

    # 先清库，再登记本轮抽到的设备，最后灌数据（三个短事务，避免锁库）
    with store.connect() as conn:
        for table in ("telemetry", "aggregates", "advice", "word_freq",
                      "catalog", "counters", "devices", "outbox"):
            conn.execute(f"DELETE FROM {table}")
    for i, d in enumerate(devices):
        _register(d)
        store.set_link(d["device_id"], "wifi" if i % 2 else "ethernet")
        _issue_demo_cert(d["device_id"])

    inserted = 0
    suppressed = 0
    with store.connect() as conn:
        for device in devices:
            dev = device["device_id"]
            rows = modules.metrics_for(device["modules"])
            for ts in range(start, end, window):
                h = (ts / 3600_000) % 24
                day_index = (ts - start) / 86_400_000
                aggs, adv_out = [], []
                subjects = 8 + rnd.randint(0, 2)
                for row in rows:
                    if rnd.random() < 0.05:
                        suppressed += 1
                        continue
                    metric = row["metric"]
                    v = _value(metric, h, day_index) + rnd.gauss(0, NOISE.get(metric, 0.5))
                    z_spike = _spike(metric, ts)
                    if z_spike:
                        v += z_spike * NOISE.get(metric, 0.5)
                    if metric in ("light_lux", "counter_delta", "counter_rate",
                                  "intrusion_count", "frames"):
                        v = max(0.0, v)
                    # z：同小时的历史均值与标准差
                    hist = [b for b in _baseline(metric, h, day_index, devices, window, start)]
                    mu = sum(hist) / len(hist) if hist else v
                    sd = math.sqrt(sum((x - mu) ** 2 for x in hist) / len(hist)) if hist else 0.0
                    sd = max(sd, NOISE.get(metric, 0.5) * 0.9, 1e-6)
                    z = (v - mu) / sd
                    aggs.append({
                        "metric": metric, "module_id": row["module_id"],
                        "label": row["label"], "unit": row["unit"], "table": row["table"],
                        "package_id": row["package_id"], "decimals": row["decimals"],
                        "n_subjects": subjects, "n_samples": subjects * rnd.randint(38, 44),
                        "mean": round(v, 3),
                        "slope": round(v - _value(metric, h - window / 3600_000, day_index), 3),
                        "z": round(z, 2), "k": subjects,
                    })
                    a = _advice(row["module_id"], z, ts)
                    if a:
                        adv_out.append(a)

                if not aggs:
                    conn.execute("UPDATE devices SET last_seen=? WHERE device_id=?",
                                 (ts + window, dev))
                    continue
                batch = hashlib.sha256(f"{dev}|{ts}".encode()).hexdigest()[:16]
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
                    (dev, batch, ts, ts + window,
                     json.dumps(payload, ensure_ascii=False), ts + window))
                for a in aggs:
                    conn.execute(
                        """INSERT OR REPLACE INTO aggregates
                           (device_id, metric, module_id, ts_from, ts_to,
                            n_subjects, n_samples, mean, slope, z, k)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (dev, a["metric"], a["module_id"], ts, ts + window,
                         a["n_subjects"], a["n_samples"], a["mean"], a["slope"], a["z"], a["k"]))
                    catalog.upsert(dev, a["metric"], a["module_id"], a["package_id"],
                               a["label"], a["unit"], a["table"], a["decimals"], conn=conn)
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
    # 文档 §8.3/§8.5：演示环境显式开启群体分析，并把初始化写进审计
    if config.DEMO:
        store.set_settings({"group_analysis": True})
        store.audit_action("system", "seed.demo", config.EDGE_ID,
                           {"operator": "sim", "build": config.BUILD, "days": days,
                            "batches": inserted, "suppressed": suppressed})
    return {"batches": inserted, "suppressed": suppressed, "days": days,
            "devices": len(devices)}


def _baseline(metric: str, hour: float, day_index: float, devices: list,
              window: int, start: int):
    """同一小时、相邻几天的取值，用来算 z。"""
    for back in (1, 2, 3):
        d = day_index - back
        if d < 0:
            continue
        yield _value(metric, hour, d) + random.Random(f"b|{metric}|{int(hour)}|{d}").gauss(0, NOISE.get(metric, 0.5))


def append_window(ts: int | None = None) -> int:
    """模拟一次上报：追加一个窗口（默认当前窗口）。"""
    now = ts or (store.now_ms() // config.WINDOW_MS * config.WINDOW_MS)
    rnd = random.Random(now)
    n = 0
    for d in store.devices():
        dev = d["device_id"]
        rows = catalog.for_device(dev)
        if not rows:
            continue
        aggs, adv_out = [], []
        h = (now / 3600_000) % 24
        subjects = 8 + rnd.randint(0, 2)
        for row in rows:
            metric = row["metric"]
            v = max(0.0, _value(metric, h, 7) + rnd.gauss(0, NOISE.get(metric, 0.5)))
            z = rnd.gauss(0, 0.8)
            aggs.append({
                "metric": metric, "module_id": row["module_id"],
                "label": row["label"], "unit": row["unit"], "table": row["table_name"],
                "package_id": row["package_id"], "decimals": row["decimals"],
                "n_subjects": subjects, "n_samples": subjects * 40,
                "mean": round(v, 3), "slope": round(rnd.gauss(0, 0.2), 3),
                "z": round(z, 2), "k": subjects,
            })
            a = _advice(row["module_id"], z, now)
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
        # 补的窗口也要推进 last_seen，否则界面会显示成掉线
        store.touch_device(dev, now + config.WINDOW_MS)
        n += 1
    from . import analysis
    analysis.rebuild_words()
    return n


def backfill(max_windows: int = 288) -> int:
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


def _issue_demo_cert(device_id: str) -> None:
    """给演示设备签一张真证书，接入页才不是空的。"""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        from . import security
        key = ec.generate_private_key(ec.SECP256R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, device_id)]))
               .sign(key, hashes.SHA256()))
        security.issue(device_id, csr.public_bytes(serialization.Encoding.PEM).decode())
    except Exception:  # noqa: BLE001 —— 演示数据不该因为证书失败而中断
        pass
