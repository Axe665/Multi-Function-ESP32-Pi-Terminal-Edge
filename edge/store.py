"""SQLite 存储层。单机演示用 SQLite WAL；表结构与 docs 里的 DDL 一一对应。"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from statistics import median
from typing import Any, Iterable

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
  device_id   TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  scene       TEXT NOT NULL,
  cert_fp     TEXT,
  last_seen   INTEGER,
  fw          TEXT,
  modules_json TEXT,
  paired_at   INTEGER,
  link        TEXT
);

CREATE TABLE IF NOT EXISTS telemetry (
  id          INTEGER PRIMARY KEY,
  device_id   TEXT NOT NULL,
  batch_id    TEXT NOT NULL,
  ts_from     INTEGER NOT NULL,
  ts_to       INTEGER NOT NULL,
  payload     TEXT NOT NULL,
  received_at INTEGER NOT NULL,
  UNIQUE(device_id, batch_id)
);

CREATE TABLE IF NOT EXISTS aggregates (
  device_id  TEXT NOT NULL,
  metric     TEXT NOT NULL,
  module_id  INTEGER NOT NULL,
  ts_from    INTEGER NOT NULL,
  ts_to      INTEGER NOT NULL,
  n_subjects INTEGER NOT NULL,
  n_samples  INTEGER NOT NULL,
  mean       REAL NOT NULL,
  slope      REAL NOT NULL,
  z          REAL NOT NULL,
  k          INTEGER NOT NULL,
  PRIMARY KEY (device_id, metric, ts_from)
);
CREATE INDEX IF NOT EXISTS ix_agg_metric ON aggregates(device_id, metric, ts_from);

CREATE TABLE IF NOT EXISTS catalog (
  device_id  TEXT NOT NULL,
  metric     TEXT NOT NULL,
  module_id  INTEGER NOT NULL,
  package_id TEXT,
  label      TEXT,
  unit       TEXT,
  table_name TEXT,
  decimals   INTEGER NOT NULL DEFAULT 1,
  first_seen INTEGER NOT NULL,
  last_seen  INTEGER NOT NULL,
  PRIMARY KEY (device_id, metric)
);

CREATE TABLE IF NOT EXISTS advice (
  id         INTEGER PRIMARY KEY,
  device_id  TEXT NOT NULL,
  text       TEXT NOT NULL,
  risk       TEXT NOT NULL,
  confidence REAL NOT NULL,
  source     TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_advice_time ON advice(created_at);

CREATE TABLE IF NOT EXISTS word_freq (
  day   TEXT NOT NULL,
  word  TEXT NOT NULL,
  count INTEGER NOT NULL,
  PRIMARY KEY (day, word)
);

CREATE TABLE IF NOT EXISTS outbox (
  report_id  TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  payload    TEXT NOT NULL,
  sent_at    INTEGER,
  attempts   INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS audit (
  id         INTEGER PRIMARY KEY,
  actor      TEXT NOT NULL,
  action     TEXT NOT NULL,
  target     TEXT NOT NULL,
  detail     TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_state (
  device_id   TEXT NOT NULL,
  metric      TEXT NOT NULL,
  ts_from     INTEGER NOT NULL,
  acked_at    INTEGER,
  acked_by    TEXT,
  muted_until INTEGER,
  mute_reason TEXT,
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (device_id, metric, ts_from)
);

CREATE TABLE IF NOT EXISTS counters (
  key   TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pair_codes (
  code        TEXT PRIMARY KEY,
  device_id   TEXT,
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER NOT NULL,
  used_at     INTEGER,
  pubkey_fp   TEXT,
  attempts    INTEGER NOT NULL DEFAULT 0,
  locked_until INTEGER
);

CREATE TABLE IF NOT EXISTS device_certs (
  serial     TEXT PRIMARY KEY,
  device_id  TEXT NOT NULL,
  pubkey_fp  TEXT,
  issued_at  INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS revoked (
  serial     TEXT PRIMARY KEY,
  device_id  TEXT,
  reason     TEXT,
  revoked_at INTEGER NOT NULL
);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


def _sqlcipher():
    try:
        from sqlcipher3 import dbapi2 as cipher  # type: ignore
    except ImportError:
        return None
    return cipher


_key_checked = False


def _ensure_key() -> None:
    """新装默认加密：没有 EDGE_DB_KEY 时自动生成 data/edge.key。

    老明文库不自动迁移（避免启动时重写），只标记 DB_PLAINTEXT_EXISTING，
    由运维跑 scripts/encrypt_db.py。没有 sqlcipher3 驱动时保持明文。
    """
    global _key_checked
    if _key_checked:
        return
    _key_checked = True
    if config.DB_KEY or not config.AUTO_ENCRYPT or _sqlcipher() is None:
        return
    if config.DB_PATH.exists() and config.DB_PATH.stat().st_size > 0:
        config.DB_PLAINTEXT_EXISTING = True
        return

    key_file = config.DATA_DIR / "edge.key"
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not key_file.exists():
            try:
                fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(secrets.token_hex(32))
        key = key_file.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if key:
        config.DB_KEY = key
        config.DB_KEY_SOURCE = "file"


def _driver():
    """设了 EDGE_DB_KEY 就必须用 SQLCipher；没有驱动直接失败，不写明文。"""
    if not config.DB_KEY:
        return sqlite3
    cipher = _sqlcipher()
    if cipher is None:  # pragma: no cover - 取决于部署环境
        raise RuntimeError(
            "EDGE_DB_KEY 已设置但缺少 sqlcipher3 驱动；"
            "请安装 libsqlcipher-dev + pysqlcipher3，或取消该变量")
    return cipher


@contextmanager
def connect():
    config.ensure_dirs()
    _ensure_key()
    driver = _driver()
    conn = driver.connect(str(config.DB_PATH), timeout=10)
    if config.DB_KEY:
        conn.execute(f"PRAGMA key='{config.DB_KEY.replace(chr(39), '')}'")
    # sqlcipher3 的 Row 与 sqlite3.Row 不通用，跟着驱动走
    conn.row_factory = driver.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """老库补列：SQLite 没有 ADD COLUMN IF NOT EXISTS。"""
    def cols(table: str) -> set[str]:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}

    if "pubkey_fp" not in cols("pair_codes"):
        conn.execute("ALTER TABLE pair_codes ADD COLUMN pubkey_fp TEXT")
    if "attempts" not in cols("pair_codes"):
        conn.execute("ALTER TABLE pair_codes ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
    if "locked_until" not in cols("pair_codes"):
        conn.execute("ALTER TABLE pair_codes ADD COLUMN locked_until INTEGER")
    outbox = cols("outbox")
    dev_cols = cols("devices")
    if "link" not in dev_cols:
        conn.execute("ALTER TABLE devices ADD COLUMN link TEXT")
    if "next_at" not in outbox:
        conn.execute("ALTER TABLE outbox ADD COLUMN next_at INTEGER")
        conn.execute("UPDATE outbox SET next_at = created_at WHERE next_at IS NULL")
    if "queue_depth" not in dev_cols:
        conn.execute("ALTER TABLE devices ADD COLUMN queue_depth INTEGER")


# ---------------------------------------------------------------- 设备

def upsert_device(device_id: str, name: str, scene: str, fw: str,
                  modules: list[int], cert_fp: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO devices(device_id, name, scene, fw, modules_json, cert_fp, last_seen, paired_at)
               VALUES(?,?,?,?,?,?,NULL,?)
               ON CONFLICT(device_id) DO UPDATE SET
                 name=excluded.name, scene=excluded.scene, fw=excluded.fw,
                 modules_json=excluded.modules_json""",
            (device_id, name, scene, fw, json.dumps(modules), cert_fp, now_ms()),
        )


def set_link(device_id: str, link: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE devices SET link=? WHERE device_id=?", (link, device_id))


def ensure_device(device_id: str) -> None:
    """第一次见到的设备就登记，模块与场景留空，等 status 主题补。"""
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO devices(device_id, name, scene, modules_json, last_seen, paired_at) "
            "VALUES(?,?,?,?,NULL,?)",
            (device_id, device_id, "unknown", "[]", now_ms()))


def touch_device(device_id: str, ts: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE devices SET last_seen=? WHERE device_id=?", (ts, device_id))


def devices() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY scene, device_id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["modules"] = json.loads(d.pop("modules_json") or "[]")
        d["link"] = d.get("link") or "unknown"
        d["online"] = bool(d["last_seen"]) and now_ms() - d["last_seen"] < 3 * config.WINDOW_MS
        out.append(d)
    return out


def device(device_id: str) -> dict[str, Any] | None:
    return next((d for d in devices() if d["device_id"] == device_id), None)


# ---------------------------------------------------------------- 批次与聚合

def insert_batch(device_id: str, batch_id: str, ts_from: int, ts_to: int,
                 payload: dict[str, Any], aggregates: Iterable[dict[str, Any]],
                 advice: Iterable[dict[str, Any]]) -> bool:
    """返回 False 表示重复投递（幂等）。"""
    with connect() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO telemetry(device_id, batch_id, ts_from, ts_to, payload, received_at)
               VALUES(?,?,?,?,?,?)""",
            (device_id, batch_id, ts_from, ts_to,
             json.dumps(payload, ensure_ascii=False), now_ms()),
        )
        if cur.rowcount == 0:
            return False
        for a in aggregates:
            conn.execute(
                """INSERT OR REPLACE INTO aggregates
                   (device_id, metric, module_id, ts_from, ts_to,
                    n_subjects, n_samples, mean, slope, z, k)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (device_id, a["metric"], a["module_id"], ts_from, ts_to,
                 a["n_subjects"], a["n_samples"], a["mean"], a["slope"], a["z"], a["k"]),
            )
        for a in advice:
            conn.execute(
                """INSERT INTO advice(device_id, text, risk, confidence, source, created_at)
                   VALUES(?,?,?,?,?,?)""",
                (device_id, a["text"], a["risk"], a["confidence"], a["source"], ts_to),
            )
        return True


def snapshot(keep: int = 7) -> str | None:
    """每日一次 SQLite 快照，保留最近 keep 份（文档 §5.1）。

    SQLCipher 库用 VACUUM INTO 生成同样加密的副本；明文库仍走 backup。
    """
    import datetime as dt
    import sqlite3

    out = config.DATA_DIR / "snapshots"
    out.mkdir(parents=True, exist_ok=True)
    name = out / f"edge-{dt.date.today():%Y%m%d}.db"
    if name.exists():
        return name.name
    if config.DB_KEY:
        with connect() as src:
            src.execute("VACUUM INTO ?", (str(name),))
    else:
        with connect() as src, sqlite3.connect(name) as dst:
            src.backup(dst)
    for old in sorted(out.glob("edge-*.db"))[:-keep]:
        old.unlink(missing_ok=True)
    return name.name


def set_status(device_id: str, fw: str | None, queue_depth: int | None) -> None:
    sets, args = [], []
    if fw:
        sets.append("fw=?")
        args.append(fw)
    if queue_depth is not None:
        sets.append("queue_depth=?")
        args.append(queue_depth)
    if not sets:
        return
    with connect() as conn:
        conn.execute(f"UPDATE devices SET {', '.join(sets)} WHERE device_id=?",
                     (*args, device_id))


def add_advice(device_id: str, text: str, risk: str, confidence: float,
               source: str, created_at: int) -> int:
    """单条建议入库（advice 主题用）。同一 (device, text, 分钟) 只算一次。"""
    with connect() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO advice(device_id, text, risk, confidence, source, created_at)
               VALUES(?,?,?,?,?,?)""",
            (device_id, text, risk, confidence, source, created_at))
        return 1 if cur.rowcount else 0


def bump(key: str, n: int = 1) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO counters(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
            (key, n),
        )


def audit_action(actor: str, action: str, target: str,
                 detail: dict[str, Any] | None = None) -> None:
    """审计动作沿用终端仓的写法：小写点分动作 + 结构化 detail。"""
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit(actor, action, target, detail, created_at) VALUES(?,?,?,?,?)",
            (actor, action, target, json.dumps(detail or {}, ensure_ascii=False), now_ms()))


def audit(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit ORDER BY created_at DESC LIMIT ?", (limit,))]


def counters() -> dict[str, int]:
    with connect() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT * FROM counters")}


def series(device_id: str, metric: str, ts_from: int, ts_to: int,
           step_ms: int) -> list[dict[str, Any]]:
    """按 step 重采样（均值），返回 [{ts, mean, k, n_subjects, z}]。"""
    with connect() as conn:
        rows = conn.execute(
            """SELECT ts_from, mean, z, k, n_subjects FROM aggregates
               WHERE device_id=? AND metric=? AND ts_from>=? AND ts_from<=?
               ORDER BY ts_from""",
            (device_id, metric, ts_from, ts_to),
        ).fetchall()
    if step_ms <= config.WINDOW_MS:
        return [{"ts": r["ts_from"], "mean": r["mean"], "z": r["z"],
                 "k": r["k"], "n_subjects": r["n_subjects"]} for r in rows]
    buckets: dict[int, list[sqlite3.Row]] = {}
    for r in rows:
        buckets.setdefault(r["ts_from"] // step_ms * step_ms, []).append(r)
    return [
        {"ts": b, "mean": sum(x["mean"] for x in xs) / len(xs),
         "z": sum(x["z"] for x in xs) / len(xs),
         "k": min(x["k"] for x in xs),
         "n_subjects": max(x["n_subjects"] for x in xs)}
        for b, xs in sorted(buckets.items())
    ]


def latest_aggregates(device_id: str | None = None) -> list[dict[str, Any]]:
    sql = """SELECT a.* FROM aggregates a
             JOIN (SELECT device_id, metric, MAX(ts_from) AS m FROM aggregates GROUP BY device_id, metric) t
               ON a.device_id=t.device_id AND a.metric=t.metric AND a.ts_from=t.m"""
    args: tuple = ()
    if device_id:
        sql += " WHERE a.device_id=?"
        args = (device_id,)
    sql += " ORDER BY a.device_id, a.metric"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def heatmap(device_id: str, metric: str, since_ms: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT ts_from, z, mean FROM aggregates WHERE device_id=? AND metric=? AND ts_from>=?",
            (device_id, metric, since_ms),
        ).fetchall()
    cells: dict[tuple[int, int], list] = {}
    for r in rows:
        t = time.localtime(r["ts_from"] / 1000)
        cells.setdefault((t.tm_wday, t.tm_hour), []).append(r)
    return [{"dow": d, "hour": h,
             "mean": sum(x["mean"] for x in v) / len(v),
             "z": sum(x["z"] for x in v) / len(v),
             "n": len(v)}
            for (d, h), v in sorted(cells.items())]


def batches(device_id: str | None, limit: int = 20) -> list[dict[str, Any]]:
    sql = ("SELECT device_id, batch_id, ts_from, ts_to, received_at, payload "
           "FROM telemetry")
    args: tuple = ()
    if device_id:
        sql += " WHERE device_id=?"
        args = (device_id,)
    sql += " ORDER BY ts_from DESC LIMIT ?"
    with connect() as conn:
        rows = conn.execute(sql, args + (limit,)).fetchall()
    out = []
    for r in rows:
        p = json.loads(r["payload"])
        out.append({
            "device_id": r["device_id"], "batch_id": r["batch_id"],
            "ts_from": r["ts_from"], "ts_to": r["ts_to"],
            "received_at": r["received_at"],
            "metrics": len(p.get("aggregates", [])),
            "k_min": min([a["k"] for a in p.get("aggregates", [])] or [0]),
            "advice": len(p.get("advice", [])),
        })
    return out


def advice(device_id: str | None = None, risk: str | None = None,
           limit: int = 30, since_ms: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM advice WHERE 1=1"
    args: list[Any] = []
    if device_id:
        sql += " AND device_id=?"
        args.append(device_id)
    if risk:
        sql += " AND risk=?"
        args.append(risk)
    if since_ms:
        sql += " AND created_at>=?"
        args.append(since_ms)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def anomalies(since_ms: int, limit: int = 40) -> list[dict[str, Any]]:
    """文档 §5.4：稳健 z（MAD）+ 连续窗口。

    每个窗口拿过去 24 h 的 mean 算 median / MAD，稳健 z = 0.6745*(x-med)/MAD；
    样本 <5 或 MAD=0 时退回端上报的基线 z。只有相邻两个窗口都越界才算异常。
    """
    from collections import defaultdict

    history_since = since_ms - 24 * 3_600_000
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT device_id, metric, ts_from, z, mean FROM aggregates
               WHERE ts_from>=? ORDER BY device_id, metric, ts_from""",
            (history_since,)).fetchall()]

    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_key[(r["device_id"], r["metric"])].append(r)

    out: list[dict[str, Any]] = []
    for xs in by_key.values():
        for i, r in enumerate(xs):
            window = [p["mean"] for p in xs[max(0, i - 288):i]
                      if p["ts_from"] >= r["ts_from"] - 24 * 3_600_000]
            if len(window) >= 5:
                med = median(window)
                mad = median([abs(x - med) for x in window])
                if mad > 0:
                    r["robust_z"] = round(0.6745 * (r["mean"] - med) / mad, 3)
                    r["robust"] = True
                    r["gate"] = 3.5
                else:
                    r["robust_z"] = r["z"]
                    r["robust"] = False
                    r["gate"] = 2.5
            else:
                r["robust_z"] = r["z"]
                r["robust"] = False
                r["gate"] = 2.5

        prev: dict[str, Any] | None = None
        for r in xs:
            if (abs(r["robust_z"]) >= r["gate"] and prev is not None
                    and abs(prev["robust_z"]) >= prev["gate"]
                    and r["ts_from"] - prev["ts_from"] <= 2 * config.WINDOW_MS):
                out.append({**r, "windows": 2,
                            "ts_to": r["ts_from"] + config.WINDOW_MS})
            prev = r

    out = [r for r in out if r["ts_from"] >= since_ms]
    out.sort(key=lambda x: -x["ts_from"])
    return out[:limit]


def hour_baseline(device_id: str, metric: str, ts: int,
                  days: int = 7) -> tuple[float, float]:
    """同小时的历史均值与标准差。实况窗口用它算 z，跟种子数据同一套口径。"""
    with connect() as conn:
        r = conn.execute(
            """SELECT AVG(mean) AS mu, AVG(mean*mean) - AVG(mean)*AVG(mean) AS var,
                      COUNT(*) AS n
               FROM aggregates
               WHERE device_id=? AND metric=? AND ts_from>=? AND ts_from<?
                 AND (ts_from/3600000) % 24 = ?""",
            (device_id, metric, ts - days * 86_400_000, ts,
             int(ts / 3_600_000) % 24)).fetchone()
    if not r or (r["n"] or 0) < 8:
        return (0.0, 0.0)
    return (float(r["mu"] or 0.0), max(float(r["var"] or 0.0), 0.0) ** 0.5)


# ---------------------------------------------------------------- 告警

ANOMALY_Z = 2.0      # 注意门槛
SEVERE_Z = 2.5       # 严重门槛，需连续两个窗口


def _alert_states() -> dict[tuple[str, str, int], dict[str, Any]]:
    with connect() as conn:
        return {(r["device_id"], r["metric"], r["ts_from"]): dict(r)
                for r in conn.execute("SELECT * FROM alert_state")}


def alert_feed(since_ms: int, stale_ms: int, at: int | None = None) -> list[dict[str, Any]]:
    """一条告警 = 一段连续越界的窗口，而不是每个窗口一条。

    注意：单窗口 |z|≥2。严重：段内有两个相隔不超过 2 个窗口的 |z|≥2.5。
    这里用端上报的基线 z；MAD 稳健 z 只用于异常页的时间轴（anomalies）。
    已恢复在读取时按后续窗口算，不落库。
    """
    now = at if at is not None else now_ms()
    with connect() as conn:
        rows = conn.execute(
            """SELECT device_id, metric, ts_from, mean, z, k FROM aggregates
               WHERE ts_from>=? ORDER BY device_id, metric, ts_from""",
            (since_ms,)).fetchall()

    runs: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for r in rows:
        key = (r["device_id"], r["metric"])
        z = abs(r["z"] or 0)
        if z < ANOMALY_Z:
            # 后面出现了正常窗口就算恢复
            if cur is not None and (cur["device_id"], cur["metric"]) == key:
                cur["resolved"] = True
                cur = None
            continue
        contiguous = (cur is not None
                      and (cur["device_id"], cur["metric"]) == key
                      and r["ts_from"] - cur["ts_to"] <= config.WINDOW_MS)
        if contiguous:
            cur["ts_to"] = r["ts_from"] + config.WINDOW_MS
            cur["windows"] += 1
            cur["max_z"] = max(cur["max_z"], z)
            if z >= SEVERE_Z:
                if cur["_severe_at"] and r["ts_from"] - cur["_severe_at"] <= 2 * config.WINDOW_MS:
                    cur["critical"] = True
                cur["_severe_at"] = r["ts_from"]
        else:
            if cur is not None and (cur["device_id"], cur["metric"]) == key:
                cur["resolved"] = True      # 中间断了，上一段结束
            cur = {
                "kind": "anomaly", "device_id": r["device_id"], "metric": r["metric"],
                "ts_from": r["ts_from"], "ts_to": r["ts_from"] + config.WINDOW_MS,
                "mean": r["mean"], "z": r["z"], "k": r["k"],
                "windows": 1, "max_z": z, "critical": False, "resolved": False,
                "_severe_at": r["ts_from"] if z >= SEVERE_Z else 0,
            }
            runs.append(cur)

    # 数据过期本身就是一条严重告警：没有上报比数值漂移更需要处理
    for d in devices():
        last = d["last_seen"] or 0
        if now - last <= stale_ms:
            continue
        runs.append({
            "kind": "stale", "device_id": d["device_id"], "metric": "__stale__",
            "ts_from": last or 0, "ts_to": last or 0,
            "mean": None, "z": None, "k": None, "windows": 0,
            "max_z": 0, "critical": True, "resolved": False,
        })

    states = _alert_states()
    for a in runs:
        st = states.get((a["device_id"], a["metric"], a["ts_from"])) or {}
        muted = bool(st.get("muted_until")) and st["muted_until"] > now
        a["severity"] = "critical" if a["critical"] else "notice"
        a["state"] = ("muted" if muted
                      else "resolved" if a["resolved"]
                      else "acked" if st.get("acked_at") else "pending")
        a["acked_at"] = st.get("acked_at")
        a["acked_by"] = st.get("acked_by")
        a["muted_until"] = st.get("muted_until")
        a["mute_reason"] = st.get("mute_reason")
        a.pop("_severe_at", None)

    order = {"critical": 0, "notice": 1}
    rank = {"pending": 0, "acked": 1, "muted": 2, "resolved": 3}
    runs.sort(key=lambda a: (rank[a["state"]], order[a["severity"]], -a["ts_from"]))
    return runs


def ack_alert(device_id: str, metric: str, ts_from: int, actor: str) -> None:
    now = now_ms()
    with connect() as conn:
        conn.execute(
            """INSERT INTO alert_state(device_id, metric, ts_from, acked_at, acked_by, updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(device_id, metric, ts_from) DO UPDATE SET
                 acked_at=excluded.acked_at, acked_by=excluded.acked_by,
                 updated_at=excluded.updated_at""",
            (device_id, metric, ts_from, now, actor, now))
    audit_action(actor, "alert.ack", f"{device_id}/{metric}", {"ts_from": ts_from})


def mute_alert(device_id: str, metric: str, ts_from: int, until: int,
               reason: str, actor: str) -> None:
    now = now_ms()
    with connect() as conn:
        conn.execute(
            """INSERT INTO alert_state(device_id, metric, ts_from, muted_until,
                                       mute_reason, acked_by, updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(device_id, metric, ts_from) DO UPDATE SET
                 muted_until=excluded.muted_until, mute_reason=excluded.mute_reason,
                 acked_by=excluded.acked_by, updated_at=excluded.updated_at""",
            (device_id, metric, ts_from, until, reason, actor, now))
    audit_action(actor, "alert.mute", f"{device_id}/{metric}",
                 {"ts_from": ts_from, "until": until, "reason": reason})


def unmute_alert(device_id: str, metric: str, ts_from: int) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE alert_state SET muted_until=NULL, mute_reason=NULL, updated_at=?
               WHERE device_id=? AND metric=? AND ts_from=?""",
            (now_ms(), device_id, metric, ts_from))
    audit_action("admin", "alert.unmute", f"{device_id}/{metric}", {"ts_from": ts_from})


# ---------------------------------------------------------------- 词频

def rebuild_word_freq(terms: dict[str, dict[str, int]]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM word_freq")
        for day, counts in terms.items():
            conn.executemany(
                "INSERT INTO word_freq(day, word, count) VALUES(?,?,?)",
                [(day, w, c) for w, c in counts.items()],
            )


def wordcloud(days: int, today: str) -> list[dict[str, Any]]:
    """词频 + TF-IDF：跨天出现越多权重越低，避免"建议""设备"这类词占满屏。"""
    import math

    since = today if days <= 0 else _shift_day(today, -(days - 1))
    with connect() as conn:
        rows = conn.execute(
            "SELECT word, SUM(count) AS count, COUNT(DISTINCT day) AS df "
            "FROM word_freq WHERE day>=? GROUP BY word ORDER BY count DESC LIMIT 120",
            (since,)).fetchall()
        span = conn.execute(
            "SELECT COUNT(DISTINCT day) AS n FROM word_freq WHERE day>=?", (since,)).fetchone()
    n_days = max(1, int(span["n"] if span else 1))
    out = []
    for r in rows:
        tf = float(r["count"])
        df = max(1, int(r["df"]))
        score = tf * (math.log((n_days + 1) / (df + 1)) + 1.0)
        out.append({"word": r["word"], "count": int(tf), "df": df,
                    "score": round(score, 1)})
    out.sort(key=lambda x: -x["score"])
    return out[:40]


def _shift_day(day: str, delta: int) -> str:
    import datetime as dt
    d = dt.date.fromisoformat(day) + dt.timedelta(days=delta)
    return d.isoformat()


# ---------------------------------------------------------------- 发件箱

def enqueue_report(report_id: str, payload: dict[str, Any]) -> None:
    t = now_ms()
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO outbox(report_id, created_at, payload, next_at) VALUES(?,?,?,?)",
            (report_id, t, json.dumps(payload, ensure_ascii=False), t),
        )


def outbox(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM outbox ORDER BY created_at DESC LIMIT ?",
                            (limit,)).fetchall()
    return [dict(r) for r in rows]


def mark_sent(report_id: str, error: str | None) -> None:
    with connect() as conn:
        if error is None:
            conn.execute("UPDATE outbox SET sent_at=?, attempts=attempts+1, last_error=NULL "
                         "WHERE report_id=?", (now_ms(), report_id))
        else:
            conn.execute("UPDATE outbox SET attempts=attempts+1, last_error=?, next_at=? "
                         "WHERE report_id=?", (error[:300], now_ms(), report_id))


# ---------------------------------------------------------------- 设置

def get_settings() -> dict[str, Any]:
    defaults = {
        "report_cadence_min": 60,
        "cloud_enabled": True,
        "personalization": True,
        "group_analysis": False,
        "k_min": config.K_MIN,
        "retention_days": 180,
    }
    with connect() as conn:
        rows = conn.execute("SELECT * FROM settings").fetchall()
    for r in rows:
        try:
            defaults[r["key"]] = json.loads(r["value"])
        except json.JSONDecodeError:
            defaults[r["key"]] = r["value"]
    return defaults


def set_settings(patch: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        for k, v in patch.items():
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)",
                         (k, json.dumps(v, ensure_ascii=False)))
    return get_settings()


# ---------------------------------------------------------------- 配对码

def create_pair_code(code: str, device_id: str, ttl_ms: int) -> None:
    t = now_ms()
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO pair_codes(code, device_id, created_at, expires_at)
               VALUES(?,?,?,?)""", (code, device_id, t, t + ttl_ms))


def pair_codes() -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM pair_codes ORDER BY created_at DESC LIMIT 10")]


def pair_code(code: str) -> dict[str, Any] | None:
    with connect() as conn:
        r = conn.execute("SELECT * FROM pair_codes WHERE code=?", (code,)).fetchone()
    return dict(r) if r else None


def bind_pair_pubkey(code: str, fp: str) -> None:
    """首次兑换时把公钥指纹钉在配对码上。"""
    with connect() as conn:
        conn.execute("UPDATE pair_codes SET pubkey_fp=? WHERE code=? AND pubkey_fp IS NULL",
                     (fp, code))


def mark_pair_used(code: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE pair_codes SET used_at=? WHERE code=? AND used_at IS NULL",
            (now_ms(), code))
        return cur.rowcount == 1


def pair_failure(code: str, max_attempts: int, lock_ms: int) -> None:
    with connect() as conn:
        row = conn.execute("SELECT attempts FROM pair_codes WHERE code=?", (code,)).fetchone()
        attempts = (row["attempts"] if row else 0) + 1
        locked = now_ms() + lock_ms if attempts >= max_attempts else None
        conn.execute("UPDATE pair_codes SET attempts=?, locked_until=? WHERE code=?",
                     (attempts, locked, code))


# ---------------------------------------------------------------- 证书

def device_certs() -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM device_certs ORDER BY issued_at DESC LIMIT 50")]


def revoke_serial(serial: str, device_id: str, reason: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO revoked(serial, device_id, reason, revoked_at)
               VALUES(?,?,?,?)""", (serial, device_id, reason, now_ms()))


def is_revoked(serial: str) -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM revoked WHERE serial=?", (serial,)).fetchone() is not None


def device_revoked(device_id: str) -> bool:
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM revoked WHERE device_id=? LIMIT 1", (device_id,)).fetchone() is not None


def revoked() -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM revoked ORDER BY revoked_at DESC")]


# ---------------------------------------------------------------- 发件箱退避

BACKOFF_MS = [60_000, 5 * 60_000, 30 * 60_000, 2 * 3600_000]
# 文档 §5.8：最多重试 7 天，过期就丢，不再无限占库
OUTBOX_MAX_AGE_MS = 7 * 86_400_000


def due_reports(limit: int = 20) -> list[dict[str, Any]]:
    now = now_ms()
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM outbox WHERE sent_at IS NULL AND created_at >= ?
               AND (next_at IS NULL OR next_at <= ?) ORDER BY created_at LIMIT ?""",
            (now - OUTBOX_MAX_AGE_MS, now, limit)).fetchall()
    return [dict(r) for r in rows]


def schedule_retry(report_id: str, error: str) -> int:
    """按 1 min / 5 min / 30 min / 2 h 退避；返回下一次尝试时间。"""
    with connect() as conn:
        row = conn.execute("SELECT attempts FROM outbox WHERE report_id=?",
                           (report_id,)).fetchone()
        attempts = row["attempts"] if row else 0
        delay = BACKOFF_MS[min(attempts, len(BACKOFF_MS) - 1)]
        nxt = now_ms() + delay
        conn.execute(
            """UPDATE outbox SET attempts=attempts+1, last_error=?, next_at=? WHERE report_id=?""",
            (error[:300], nxt, report_id))
    return nxt
