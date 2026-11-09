"""查询与管理服务：只读接口 + 配对/证书/设置，不碰 MQTT。

docker compose 里的 `api` 服务跑这个，端口 8001（容器内），由 Caddy 反代。
"""
from __future__ import annotations

import os

from .roles import create_app

app = create_app("api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("edge.api_main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8001")), reload=False)
