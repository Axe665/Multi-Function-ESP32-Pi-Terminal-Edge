"""后台任务：定时上云、发件箱退避重试、保留期清理。

用 asyncio 单循环，不引入 APScheduler —— 三个任务的周期差得很远，
一个 sleep 循环足够，也更容易在测试里手动 tick 一次。
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from . import analysis, cloudpush, config, store


def prune(retention_days: int) -> dict[str, int]:
    """按天清理边上的聚合与建议，保留期默认 180 天。"""
    cutoff = store.now_ms() - retention_days * 86_400_000
    with store.connect() as conn:
        agg = conn.execute("DELETE FROM aggregates WHERE ts_to < ?", (cutoff,)).rowcount
        tel = conn.execute("DELETE FROM telemetry WHERE ts_to < ?", (cutoff,)).rowcount
        adv = conn.execute("DELETE FROM advice WHERE created_at < ?", (cutoff,)).rowcount
        out = conn.execute(
            "DELETE FROM outbox WHERE sent_at IS NOT NULL AND created_at < ?", (cutoff,)).rowcount
    return {"aggregates": agg, "telemetry": tel, "advice": adv, "outbox": out}


def tick(now: int | None = None) -> dict[str, Any]:
    """一次调度：到点就生成报表，然后把到期的发出去。"""
    now = now or store.now_ms()
    settings = store.get_settings()
    out: dict[str, Any] = {"report": None, "drain": None, "pruned": None}

    if config.CLOUD_URL and settings.get("cloud_enabled", True):
        with store.connect() as conn:
            last = conn.execute("SELECT MAX(created_at) AS m FROM outbox").fetchone()["m"] or 0
        if now - last >= config.PUSH_INTERVAL_MS:
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
