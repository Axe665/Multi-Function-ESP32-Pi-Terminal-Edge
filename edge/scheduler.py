"""后台任务：定时上云、发件箱退避重试、保留期清理。

用 asyncio 单循环，不引入 APScheduler —— 三个任务的周期差得很远，
一个 sleep 循环足够，也更容易在测试里手动 tick 一次。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from . import analysis, cloudpush, config, store


def prune(retention_days: int) -> dict[str, int]:
    """按天清理：L2 聚合/原始批 retention_days，L3 文本 365 天，其余各有线。"""
    now = store.now_ms()
    cutoff = now - retention_days * 86_400_000
    text_cutoff = now - config.TEXT_KEEP_DAYS * 86_400_000
    word_cutoff = analysis.day_of(now - config.WORD_KEEP_DAYS * 86_400_000)
    audit_cutoff = now - config.AUDIT_KEEP_DAYS * 86_400_000
    alert_cutoff = now - config.ALERT_STATE_KEEP_DAYS * 86_400_000
    with store.connect() as conn:
        agg = conn.execute("DELETE FROM aggregates WHERE ts_to < ?", (cutoff,)).rowcount
        tel = conn.execute("DELETE FROM telemetry WHERE ts_to < ?", (cutoff,)).rowcount
        adv = conn.execute("DELETE FROM advice WHERE created_at < ?", (text_cutoff,)).rowcount
        words = conn.execute("DELETE FROM word_freq WHERE day < ?", (word_cutoff,)).rowcount
        audit_rows = conn.execute(
            "DELETE FROM audit WHERE created_at < ?", (audit_cutoff,)).rowcount
        alerts = conn.execute(
            "DELETE FROM alert_state WHERE updated_at < ?", (alert_cutoff,)).rowcount
        out = conn.execute(
            "DELETE FROM outbox WHERE sent_at IS NOT NULL AND created_at < ?", (cutoff,)).rowcount
        expired = conn.execute(
            "DELETE FROM outbox WHERE sent_at IS NULL AND created_at < ?",
            (store.now_ms() - store.OUTBOX_MAX_AGE_MS,)).rowcount
    if expired:
        store.bump("outbox_expired", expired)
    counts = {"aggregates": agg, "telemetry": tel, "advice": adv, "word_freq": words,
              "audit": audit_rows, "alert_state": alerts,
              "outbox": out, "outbox_expired": expired}
    # 一次清理只留一条审计，明细里写清各表删了多少、用的是哪条线
    store.audit_action("system", "retention.prune", "edge",
                       {**counts, "l2_days": retention_days,
                        "l3_days": config.TEXT_KEEP_DAYS,
                        "word_days": config.WORD_KEEP_DAYS,
                        "audit_days": config.AUDIT_KEEP_DAYS,
                        "alert_days": config.ALERT_STATE_KEEP_DAYS})
    return counts


def snapshot() -> dict[str, Any]:
    name = store.snapshot(config.SNAPSHOT_KEEP)
    if name:
        store.audit_action("system", "db.snapshot", "edge",
                           {"file": name, "keep": config.SNAPSHOT_KEEP})
    return {"snapshot": name}


def check_certs() -> dict[str, int]:
    """每天看一次证书剩余天数；到期前 30 天写审计，前端会标红。"""
    from . import security
    soon = security.expiring()
    if soon:
        store.audit_action("system", "cert.expiring", "edge",
                           {"count": len(soon),
                            "devices": [c["device_id"] for c in soon][:10]})
        store.bump("certs_expiring", len(soon))
    return {"expiring": len(soon)}


def tick(now: int | None = None) -> dict[str, Any]:
    """一次调度：到点就生成报表，然后把到期的发出去。"""
    now = now or store.now_ms()
    settings = store.get_settings()
    out: dict[str, Any] = {"report": None, "drain": None, "pruned": None}

    if cloudpush.configured() and settings.get("cloud_enabled", True):
        with store.connect() as conn:
            last = conn.execute("SELECT MAX(created_at) AS m FROM outbox").fetchone()["m"] or 0
            # 设置页的「上报节奏」是分钟：只在库里真的存过时才用它，
            # 否则退回 config 的 PUSH_INTERVAL_MS（环境变量调过就该生效）
            row = conn.execute(
                "SELECT value FROM settings WHERE key='report_cadence_min'").fetchone()
        cadence = (int(json.loads(row["value"])) * 60_000
                   if row else config.PUSH_INTERVAL_MS)
        if now - last >= cadence:
            out["report"] = cloudpush.push_now()
        out["drain"] = cloudpush.drain()
    return out


class Scheduler:
    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.last: dict[str, Any] = {}
        self.ticks = 0

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                self.last = await asyncio.to_thread(tick)
                self.ticks += 1
            except Exception as e:  # noqa: BLE001 —— 后台任务不能把服务带崩
                self.last = {"error": str(e)[:200]}

    async def _janitor(self) -> None:
        while True:
            await asyncio.sleep(config.JANITOR_INTERVAL_MS / 1000)
            retention = store.get_settings().get("retention_days", config.KEEP_DAYS)
            await asyncio.to_thread(prune, int(retention))
            await asyncio.to_thread(check_certs)
            await asyncio.to_thread(snapshot)

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._loop())
            asyncio.create_task(self._janitor())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
            self.task = None


scheduler = Scheduler()
