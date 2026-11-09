"""单进程入口（本机调试）：python3 -m edge.main 或 uvicorn edge.main:app。

生产部署按文档 §5.1 拆成四个服务，见 docker/compose.yml：
ingest 用 edge.ingest_main，api 用 edge.api_main，web 由 Caddy 直接服务。
"""
from __future__ import annotations

import os

from .roles import create_app

app = create_app("all")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("edge.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8001")), reload=False)
