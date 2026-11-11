#!/usr/bin/env python3
"""把已有的明文 edge.db 迁移成 SQLCipher 加密库（文档 §8.2）。

新装默认已经加密；这个脚本只给“升级前就是明文”的库用。步骤：
1. WAL checkpoint 后把原库复制成 .plain.bak；
2. 用 sqlcipher3 打开明文库，ATTACH 加密临时库，sqlcipher_export；
3. 对比关键表行数，一致才替换原库。

用法：python3 scripts/encrypt_db.py [--db data/edge.db] [--key-file data/edge.key]
需要宿主机/容器里装了 sqlcipher3。
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge import config  # noqa: E402

TABLES = ("devices", "telemetry", "aggregates", "advice", "word_freq", "outbox", "audit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(config.DB_PATH))
    parser.add_argument("--key-file", default=str(config.DATA_DIR / "edge.key"))
    args = parser.parse_args()

    db = Path(args.db)
    key_file = Path(args.key_file)
    if not db.exists():
        print(f"没有找到明文库：{db}")
        return 1
    if not key_file.exists():
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
        key_file.chmod(0o600)
        print(f"已生成密钥：{key_file}")
    key = key_file.read_text(encoding="utf-8").strip()

    try:
        from sqlcipher3 import dbapi2 as cipher  # type: ignore
    except ImportError:
        print("缺少 sqlcipher3；先安装 sqlcipher3-binary 或 pysqlcipher3")
        return 1

    # 1. checkpoint + 备份
    with sqlite3.connect(str(db)) as plain:
        plain.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    backup = db.with_suffix(db.suffix + f".plain-{time.strftime('%Y%m%d%H%M%S')}.bak")
    shutil.copy2(db, backup)
    backup.chmod(0o600)  # 明文备份只给自己读
    print(f"已备份：{backup}（验证无误后请离线保存或删除）")

    tmp = db.with_suffix(db.suffix + ".enc.tmp")
    for p in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
        p.unlink(missing_ok=True)

    # 2. 明文 main → 加密 attached
    src = cipher.connect(str(db))
    try:
        src.execute("ATTACH DATABASE ? AS encrypted KEY ?", (str(tmp), key))
        src.execute("SELECT sqlcipher_export('encrypted')")
        src.execute("DETACH DATABASE encrypted")
        src.commit()
    finally:
        src.close()

    # 3. 行数校验
    def counts(conn) -> dict[str, int]:
        out = {}
        for t in TABLES:
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:  # noqa: BLE001 —— 老库可能缺表，缺就记 -1
                out[t] = -1
        return out

    with sqlite3.connect(str(db)) as plain:
        before = counts(plain)
    enc = cipher.connect(str(tmp))
    try:
        enc.execute(f"PRAGMA key='{key.replace(chr(39), '')}'")
        after = counts(enc)
    finally:
        enc.close()
    if before != after:
        print("行数不一致，已保留临时库供排查：")
        print("  明文：", before)
        print("  加密：", after)
        return 2

    # 4. 替换
    for suffix in ("-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    os.replace(tmp, db)
    print(f"迁移完成：{db}（密钥 {key_file}，请和数据库分开备份）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
