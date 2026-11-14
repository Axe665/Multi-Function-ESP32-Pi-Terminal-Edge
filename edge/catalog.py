"""指标目录：端上报什么，这里就登记什么。

不再有写死的「设备 → 模块 → 指标」表。终端第一次上报某个指标时，
边把它的 module_id / 单位 / 标签 / 所属表登记进 catalog，
前端与分析层全部从这里读。换一块板子、换一个模块，不需要改代码。
"""
from __future__ import annotations

from typing import Any

from . import store

# (device_id, metric) -> (取值时刻, 行)
_CACHE: dict[tuple[str, str], tuple[int, dict[str, Any] | None]] = {}
_CACHE_MS = 5_000


def upsert(device_id: str, metric: str, module_id: int, package_id: str = "",
           label: str = "", unit: str = "", table: str = "samples",
           decimals: int = 1, conn=None) -> None:
    """按 (device, metric) 登记；已存在就只补空字段，不覆盖终端给的元信息。

    conn 用于已经在事务里的调用方（演示数据生成器），避免嵌套连接把库锁住。
    """
    if conn is not None:
        _write(conn, device_id, metric, module_id, package_id, label, unit, table, decimals)
        return
    with store.connect() as own:
        _write(own, device_id, metric, module_id, package_id, label, unit, table, decimals)


def _write(conn, device_id, metric, module_id, package_id, label, unit, table, decimals) -> None:
    conn.execute(
            """INSERT INTO catalog(device_id, metric, module_id, package_id, label, unit,
                                   table_name, decimals, first_seen, last_seen)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(device_id, metric) DO UPDATE SET
                 module_id=excluded.module_id,
                 package_id=COALESCE(NULLIF(excluded.package_id,''), catalog.package_id),
                 label=COALESCE(NULLIF(excluded.label,''), catalog.label),
                 unit=COALESCE(NULLIF(excluded.unit,''), catalog.unit),
                 table_name=COALESCE(NULLIF(excluded.table_name,''), catalog.table_name),
                 decimals=excluded.decimals,
                 last_seen=excluded.last_seen""",
        (device_id, metric, module_id, package_id, label, unit, table,
         decimals, store.now_ms(), store.now_ms()))
    _CACHE.pop((device_id, metric), None)


def for_device(device_id: str) -> list[dict[str, Any]]:
    with store.connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM catalog WHERE device_id=? ORDER BY module_id, metric",
            (device_id,))]


def get(device_id: str, metric: str) -> dict[str, Any] | None:
    # 每次连接 SQLCipher 都要跑一遍 KDF（约 80 ms），而 label/unit/decimals 是
    # 列表页的热点：一个 overview 就能触发几十次。目录只在 upsert 时变，短缓存够用。
    key = (device_id, metric)
    hit = _CACHE.get(key)
    now = store.now_ms()
    if hit and now - hit[0] < _CACHE_MS:
        return hit[1]
    with store.connect() as conn:
        r = conn.execute(
            "SELECT * FROM catalog WHERE device_id=? AND metric=?",
            key).fetchone()
    row = dict(r) if r else None
    _CACHE[key] = (now, row)
    return row


def label(device_id: str, metric: str) -> str:
    row = get(device_id, metric)
    return (row or {}).get("label") or metric


def unit(device_id: str, metric: str) -> str:
    return (get(device_id, metric) or {}).get("unit") or ""


def decimals(device_id: str, metric: str) -> int:
    row = get(device_id, metric)
    return int(row["decimals"]) if row else 1


def metrics_of(device_id: str) -> list[str]:
    return [r["metric"] for r in for_device(device_id)]


def all_labels() -> list[dict[str, Any]]:
    """去重后的指标字典，给前端下拉框用。"""
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT metric, MAX(label) AS label, MAX(unit) AS unit,
                      MIN(decimals) AS decimals, COUNT(DISTINCT device_id) AS devices
               FROM catalog GROUP BY metric ORDER BY metric""").fetchall()
    return [dict(r) for r in rows]


def forget(device_id: str) -> None:
    with store.connect() as conn:
        conn.execute("DELETE FROM catalog WHERE device_id=?", (device_id,))
