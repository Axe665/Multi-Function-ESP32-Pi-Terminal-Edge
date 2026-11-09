"""应用入口：python3 -m edge.main 或 uvicorn edge.main:app。"""
from __future__ import annotations

import asyncio
import contextlib
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api, config, mdns, mqtt, scheduler, sim, store

DESCRIPTION = """\
边节点管理软件：接收端侧假名聚合、做趋势/热力/词云分析、按小时打包上报云端。

- 只收 L2 聚合（k≥5），原始字段一律 422 并计数
- 管理 API 与设备摄取分开鉴权，见 /api/v1/health
"""


async def _ticker() -> None:
    """演示用：每 5 分钟补一个窗口，省得界面看起来像断了线。

    EDGE_SIM=0 关掉；没有演示设备（mt-3b-01）时也不会启动。
    """
    while True:
        await asyncio.sleep(config.WINDOW_MS / 1000)
        await asyncio.to_thread(sim.backfill, 12)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if os.environ.get("EDGE_SIM", "1") != "0" and store.device("mt-3b-01"):
        await asyncio.to_thread(sim.backfill, 288)
        task = asyncio.create_task(_ticker())

    # 主通道：MQTT + mTLS（配了 EDGE_MQTT_HOST 才起）
    await asyncio.to_thread(mqtt.mqtt_ingest.start)
    # 发现：广播 _orpi-edge._tcp（组播不可用时自动降级）
    await asyncio.to_thread(mdns.mdns.start)
    # 定时上云 + 保留期清理
    scheduler.scheduler.start()

    yield

    await scheduler.scheduler.stop()
    await asyncio.to_thread(mqtt.mqtt_ingest.stop)
    await asyncio.to_thread(mdns.mdns.stop)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    store.init_db()
    if os.environ.get("EDGE_AUTOSEED") == "1" and not store.devices():
        sim.generate(7)
    app = FastAPI(title="Modular Terminal Edge", version="1.0.0",
                  description=DESCRIPTION, docs_url="/api/docs", redoc_url=None,
                  lifespan=lifespan)
    app.include_router(api.router)
    app.mount("/", StaticFiles(directory=config.STATIC, html=True), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("edge.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8001")), reload=False)
