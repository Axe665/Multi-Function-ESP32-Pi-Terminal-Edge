#!/usr/bin/env python3
"""从 Material Symbols 全量字体里抽出用到的图标，生成子集字体与名字表。

用法（需要 fonttools + brotli）：
    python3 scripts/icons.py

图标写在源码里 `<Icon name="settings" />`，脚本扫 src/ 收集名字，重新生成：
    public/fonts/material-symbols.woff2   子集（约 20 KB，含 FILL 轴）
    src/lib/icons.js                      name -> 字符

名字拼错、或全量字体里没有这个图标，脚本直接报错退出。
全量字体（3.9 MB）缓存在 ~/.cache/mt-icons/，离线时用已缓存的副本。
"""
from __future__ import annotations

import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT_FONT = ROOT / "public" / "fonts" / "material-symbols.woff2"
OUT_MAP = SRC / "lib" / "icons.js"
CACHE = Path.home() / ".cache" / "mt-icons" / "material-symbols-outlined.woff2"
CDN = "https://cdn.jsdelivr.net/npm/material-symbols@0.49.0/material-symbols-outlined.woff2"

# 导航与常用动作：页面里没写也会带上，避免每次加图标都改脚本
BASE = """
dashboard hub devices settings compare_arrows summarize privacy_tip insights cable
light_mode dark_mode refresh arrow_back arrow_forward chevron_right open_in_new
check_circle warning error info close expand_more download search
""".split()

USED = re.compile(r'<Icon\s+name="([a-z0-9_]+)"')


def wanted() -> list[str]:
    names = set(BASE)
    for path in SRC.rglob("*.vue"):
        names.update(USED.findall(path.read_text(encoding="utf-8")))
    return sorted(names)


def full_font() -> Path:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"下载全量字体 -> {CACHE}")
        urllib.request.urlretrieve(CDN, CACHE)
    return CACHE


def codepoints(path: Path) -> dict[str, int]:
    """图标名的 ligature 目标 glyph 名就是图标名，再从 cmap 反查私用区码位。"""
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    rev = {name: cp for cp, name in font.getBestCmap().items()}
    found: dict[str, int] = {}

    def walk(st) -> None:
        ext = getattr(st, "ExtSubTable", None)
        if ext is not None:
            return walk(ext)
        for arr in getattr(st, "ligatures", {}).values():
            for lig in arr:
                if lig.LigGlyph in rev:
                    found[lig.LigGlyph] = rev[lig.LigGlyph]

    for lookup in font["GSUB"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            walk(st)
    return found


def main() -> int:
    try:
        from fontTools import subset  # noqa: F401
    except ModuleNotFoundError:
        print("缺 fonttools：pip install --user fonttools brotli", file=sys.stderr)
        return 2
    import brotli  # noqa: F401  仅在输出 woff2 时用到

    names = wanted()
    source = full_font()
    table = codepoints(source)
    missing = [n for n in names if n not in table]
    if missing:
        print(f"全量字体里没有这些图标：{', '.join(missing)}", file=sys.stderr)
        return 1

    OUT_FONT.parent.mkdir(parents=True, exist_ok=True)
    unicodes = ",".join(f"U+{table[n]:04X}" for n in names)
    # 用 CLI 而不是 API：--layout-features 为空才真的丢掉整张 GSUB，
    # 否则 ligature 闭包会把 4000 个图标全带回来（3.9 MB）
    subprocess.run(
        [sys.executable, "-m", "fontTools.subset", str(source),
         f"--unicodes={unicodes}", "--layout-features=", "--flavor=woff2",
         f"--output-file={OUT_FONT}"],
        check=True,
    )

    OUT_MAP.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "// 由 scripts/icons.py 生成，勿手改。加图标改源码后重跑脚本。",
        "export const ICONS = {",
        *[f"  {n}: '\\u{table[n]:04x}'," for n in names],
        "}",
        "",
    ]
    OUT_MAP.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(names)} 个图标 -> {OUT_FONT.relative_to(ROOT)} ({OUT_FONT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
