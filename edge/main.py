"""应用入口：python3 -m edge.main 或 uvicorn edge.main:app。"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api, config, store

DESCRIPTION = """\
边节点管理软件：接收端侧假名聚合、做趋势/热力/词云分析、按小时打包上报云端。

- 只收 L2 聚合（k≥5），原始字段一律 422 并计数
- 管理 API 与设备摄取分开鉴权，见 /api/v1/health
"""


def create_app() -> FastAPI:
    store.init_db()
    if os.environ.get("EDGE_AUTOSEED") == "1":
        from . import sim
        if not store.devices():
            sim.generate(7)
    app = FastAPI(title="Modular Terminal Edge", version="1.0.0",
                  description=DESCRIPTION, docs_url="/api/docs", redoc_url=None)
    app.include_router(api.router)
    app.mount("/", StaticFiles(directory=config.STATIC, html=True), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("edge.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8001")), reload=False)
