"""从实现导出 contracts/openapi/edge.yaml。

手工维护的那份落后 15 条路由（alerts、certs、cloud、metrics、pair/redeem 等），
所以改成以 FastAPI 的 app.openapi() 为准：加路由就重跑本脚本。
CI 里的 check_openapi.py 会拦住「实现了但没导出」的情况。

用法：python3 scripts/export_openapi.py
"""
from __future__ import annotations

import pathlib
import sys

import yaml
from fastapi import FastAPI

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from edge.api import router  # noqa: E402

OUT = BASE / "contracts/openapi/edge.yaml"


def build() -> dict:
    app = FastAPI(
        title="Modular Terminal Edge API",
        version="1.0.0",
        description="边节点查询与管理 API（文档 §5.5）。由实现导出，勿手改。",
    )
    app.include_router(router)
    return app.openapi()


def main() -> int:
    spec = build()
    OUT.write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"已写入 {OUT.relative_to(BASE)}：{len(spec['paths'])} 条路径")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
