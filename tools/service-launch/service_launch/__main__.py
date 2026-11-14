"""python3 -m service_launch：起控制台。端口和标题都从仓库根的 launcher.toml 读。"""
from __future__ import annotations

import uvicorn

from . import config


def main() -> int:
    cfg = config.load()
    print(f"{cfg.title}：http://127.0.0.1:{cfg.port}/", flush=True)
    uvicorn.run(
        "service_launch.api:app",
        host="127.0.0.1",
        port=cfg.port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
