#!/usr/bin/env python3
"""同步 vendor 契约：--check 只校验，--update 重新拉取。

消费方不改 vendor 副本；要改就回 owner 仓提 PR，然后再跑 --update。
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "contracts" / "vendor" / "terminal"

# 本地文件名 → owner 仓里的路径
FILES = {
    "telemetry@v1.json": "contracts/wire/telemetry.v1.json",
}


def parse_source() -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in (VENDOR / "SOURCE").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def check() -> int:
    sums = {}
    for line in (VENDOR / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split()
        sums[name] = digest
    bad = 0
    for name, digest in sums.items():
        path = VENDOR / name
        if not path.exists():
            print(f"MISSING {name}")
            bad += 1
        elif sha256(path) != digest:
            print(f"CHANGED {name}")
            bad += 1
    for name in FILES:
        if name not in sums:
            print(f"NOT-IN-SUMS {name}")
            bad += 1
    print("契约校验通过" if not bad else f"契约校验失败：{bad} 个文件")
    return 0 if not bad else 1


def update() -> int:
    meta = parse_source()
    repo = meta["repo"].rstrip("/").replace("https://github.com/", "")
    tag = meta["tag"]
    for name, remote in FILES.items():
        url = f"https://raw.githubusercontent.com/{repo}/{tag}/{remote}"
        with urllib.request.urlopen(url, timeout=20) as r:
            data = r.read()
        (VENDOR / name).write_bytes(data)
        print(f"更新 {name} ← {url}")
    with (VENDOR / "SHA256SUMS").open("w", encoding="utf-8") as f:
        for name in sorted(FILES):
            f.write(f"{sha256(VENDOR / name)}  {name}\n")
    print("SHA256SUMS 已重写")
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if action == "--update":
        raise SystemExit(update())
    if action == "--check":
        raise SystemExit(check())
    print("用法: sync_contracts.py [--check|--update]")
    raise SystemExit(2)
