"""摄取服务：MQTT 订阅 + HTTP 写入 + 演示补数 + 定时上云。

docker compose 里的 `ingest` 服务跑这个，端口 8001。
"""
from __future__ import annotations

import os

from .roles import create_app

app = create_app("ingest")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("edge.ingest_main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8001")), reload=False)
