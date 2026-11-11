"""按角色组装应用：ingest / api / all。

文档 §5.1 把边拆成四个服务：mosquitto、ingest、api、web。三个 Python
进程共用这份代码，只是挂的路由和启动的后台任务不同：
- ingest：写入口（MQTT 订阅 + HTTP 摄取）+ 演示补数 + 定时上云 + mDNS 广播
- api：查询与管理接口，不碰 MQTT，也不跑定时任务
- all：本机调试用的单进程，等同改造前的 edge.main
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import time

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import api, config, ingest, mdns, mqtt, scheduler, sim, store

DESCRIPTION = """\
边节点管理软件：接收端侧假名聚合、做趋势/热力/词云分析、按小时打包上报云端。

- 只收 L2 聚合（k≥5），原始字段一律 422 并计数
- 管理 API 与设备摄取分开鉴权，见 /api/v1/health
"""

# ingest 只留写入口与健康检查，其余都归 api 服务
INGEST_PATHS = ("/api/v1/ingest", "/api/v1/health")

# 写入口限速：按客户端 IP 每分钟计数（文档 §8.4）。进程内即可，
# 边是单机单副本，不做分布式桶。
_hits: dict[tuple[str, str], list[float]] = {}


def _rate_limited(path: str, ip: str) -> bool:
    limit = config.INGEST_RATE_PER_MIN
    if limit <= 0:
        return False
    now = time.time()
    key = (path, ip)
    seen = [t for t in _hits.get(key, []) if now - t < 60]
    if len(seen) >= limit:
        return True
    seen.append(now)
    _hits[key] = seen
    return False


async def _ticker() -> None:
    """演示用：每 5 分钟补一个窗口，省得界面看起来像断了线。"""
    while True:
        await asyncio.sleep(config.WINDOW_MS / 1000)
        await asyncio.to_thread(sim.backfill, 12)


def _lifespan_ingest():
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if os.environ.get("EDGE_SIM", "1") != "0" and store.devices():
            try:
                n = await asyncio.to_thread(sim.backfill, 288)
                print(f"sim: 启动补数 {n} 个窗口", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"sim: 启动补数失败 {e}", flush=True)
            task = asyncio.create_task(_ticker())

        await asyncio.to_thread(mqtt.mqtt_ingest.start)
        await asyncio.to_thread(mdns.mdns.start)
        scheduler.scheduler.start()

        yield

        await scheduler.scheduler.stop()
        await asyncio.to_thread(mqtt.mqtt_ingest.stop)
        await asyncio.to_thread(mdns.mdns.stop)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    return lifespan


def create_app(role: str = "all") -> FastAPI:
    store.init_db()
    if os.environ.get("EDGE_AUTOSEED") == "1" and not store.devices():
        sim.generate(7)
    app = FastAPI(title=f"Modular Terminal Edge ({role})", version="1.0.0",
                  description=DESCRIPTION, docs_url="/api/docs", redoc_url=None,
                  lifespan=_lifespan_ingest() if role in ("ingest", "all") else None)

    @app.middleware("http")
    async def ingest_guard(request: Request, call_next):
        if request.url.path.startswith("/api/v1/ingest") and request.method != "OPTIONS":
            if not ingest.storage_ok():
                return JSONResponse({"detail": {
                    "code": "DISK_LOW",
                    "message": f"边节点磁盘余量不足（{ingest.disk_free_mb()} MB），暂时拒收",
                }}, status_code=507)
            ip = request.client.host if request.client else "-"
            if _rate_limited(request.url.path, ip):
                return JSONResponse({"detail": {
                    "code": "RATE_LIMITED",
                    "message": f"写入口超过 {config.INGEST_RATE_PER_MIN} 次/分，稍后再试",
                }}, status_code=429, headers={"Retry-After": "60"})
        return await call_next(request)

    if role == "ingest":
        # 只留写入口：新版本 FastAPI 的 include_router 不再展开路由，先筛再挂
        subset = APIRouter()
        subset.routes = [r for r in api.router.routes
                         if getattr(r, "path", "").startswith(INGEST_PATHS)]
        app.include_router(subset)
    elif role == "api":
        # 写入口不在这里：摄取只由 ingest 服务接，避免两个进程同时写库
        subset = APIRouter()
        subset.routes = [r for r in api.router.routes
                         if not getattr(r, "path", "").startswith("/api/v1/ingest")]
        app.include_router(subset)
    else:
        app.include_router(api.router)
    if role == "all" and config.STATIC.is_dir():
        app.mount("/", StaticFiles(directory=config.STATIC, html=True), name="static")
    return app
