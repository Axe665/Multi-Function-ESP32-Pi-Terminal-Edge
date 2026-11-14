"""共享目录的校验和。

边、云两仓的 tools/service-launch/ 必须字节相同，差异只在仓库根的
launcher.toml。改完一边跑 `python3 tools/service-launch/checksums.py` 重写
CHECKSUMS，再拷到另一边；CI 用 --check 拦住漏同步。
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent
MANIFEST = BASE / "CHECKSUMS"
SKIP = {"CHECKSUMS"}


def build() -> str:
    lines = []
    for path in sorted(BASE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(BASE).as_posix()
        if rel in SKIP:
            continue
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    want = build()
    if "--check" in argv:
        have = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
        if have != want:
            print("CHECKSUMS 和目录内容对不上，重跑：python3 tools/service-launch/checksums.py", file=sys.stderr)
            return 1
        print("CHECKSUMS 一致")
        return 0
    MANIFEST.write_text(want, encoding="utf-8")
    print(f"已写入 {MANIFEST.relative_to(BASE.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
