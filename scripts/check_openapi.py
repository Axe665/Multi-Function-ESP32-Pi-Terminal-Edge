"""检查「实现的路由」是否都写进了 contracts/openapi/*.yaml。

sync_contracts.py 只比对 vendor 契约的 SHA256，管不到自家 API：边仓有 15 条、
云仓有 8 条路由长期没进契约，CI 一直绿。这个脚本补上那一段。

用法：python3 scripts/check_openapi.py   （CI 的 test job 会跑）
"""
from __future__ import annotations

import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parents[1]
API = BASE / "edge/api.py"
OPENAPI = BASE / "contracts/openapi/edge.yaml"


def implemented() -> list[str]:
    text = API.read_text(encoding="utf-8")
    prefix = re.search(r'APIRouter\(prefix="([^"]+)"', text)
    if not prefix:
        raise SystemExit(f"{API.name} 里找不到 APIRouter(prefix=...)")
    base = prefix.group(1)
    paths = re.findall(r'@router\.(?:get|post|put|delete|patch)\("([^"]+)"', text)
    return sorted({base + p for p in paths})


def documented() -> set[str]:
    # yaml 的路径键是两格缩进的 `/...:`，不引 yaml 库，CI 里少一个依赖
    text = OPENAPI.read_text(encoding="utf-8")
    return set(re.findall(r"^  (/[^\s:]+):\s*$", text, re.M))


def main() -> int:
    impl, doc = implemented(), documented()
    missing = [p for p in impl if p not in doc]
    if missing:
        print(f"有 {len(missing)} 条路由没写进 {OPENAPI.relative_to(BASE)}：", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        print("重跑：python3 scripts/export_openapi.py", file=sys.stderr)
        return 1
    print(f"OpenAPI 覆盖全部 {len(impl)} 条路由")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
