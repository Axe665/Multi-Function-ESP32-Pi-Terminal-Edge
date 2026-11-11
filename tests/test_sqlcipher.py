"""SQLCipher：设了 EDGE_DB_KEY 就必须真的加密，且错误口令打不开。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SqlcipherTest(unittest.TestCase):
    def _run(self, db: str, key: str) -> subprocess.CompletedProcess:
        code = (
            "from edge import store\n"
            "store.init_db()\n"
            "store.ensure_device('mt-cipher-01')\n"
            "store.add_advice('mt-cipher-01', '加密库里的建议', 'info', 0.8, 'local', store.now_ms())\n"
            "print([d['device_id'] for d in store.devices()])\n"
        )
        env = {**os.environ, "EDGE_DB": db, "EDGE_DB_KEY": key,
               "EDGE_DATA_DIR": str(Path(db).parent)}
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                              capture_output=True, text=True)

    def _run_auto(self, db: str) -> subprocess.CompletedProcess:
        """不设 EDGE_DB_KEY，走新装默认加密。"""
        code = (
            "import json\n"
            "from edge import store, config\n"
            "store.init_db()\n"
            "print('STATE', json.dumps([config.DB_KEY_SOURCE,"
            " config.DB_PLAINTEXT_EXISTING, bool(config.DB_KEY)]))\n"
        )
        env = {k: v for k, v in os.environ.items() if k != "EDGE_DB_KEY"}
        env.update({"EDGE_DB": db, "EDGE_DATA_DIR": str(Path(db).parent)})
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                              capture_output=True, text=True)

    def _state(self, out: subprocess.CompletedProcess) -> list:
        import json
        return json.loads(out.stdout.split("STATE", 1)[1].strip())

    def test_auto_encrypt_new_and_reuse_key(self):
        try:
            import sqlcipher3  # noqa: F401
        except ImportError:
            self.skipTest("没有 sqlcipher3 驱动")
        tmp = tempfile.mkdtemp(prefix="edge-auto-cipher-")
        db = os.path.join(tmp, "edge.db")
        first = self._run_auto(db)
        self.assertEqual(first.returncode, 0, first.stderr[-400:])
        self.assertEqual(self._state(first), ["file", False, True])
        with open(db, "rb") as f:
            self.assertNotEqual(f.read(16), b"SQLite format 3\x00")
        key = Path(tmp) / "edge.key"
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        # 重启：已有库 + 已有 key → 继续用同一把 key，不误判成明文库
        second = self._run_auto(db)
        self.assertEqual(second.returncode, 0, second.stderr[-400:])
        self.assertEqual(self._state(second), ["file", False, True])

    def test_legacy_plaintext_is_flagged_not_rewritten(self):
        try:
            import sqlcipher3  # noqa: F401
        except ImportError:
            self.skipTest("没有 sqlcipher3 驱动")
        import sqlite3
        tmp = tempfile.mkdtemp(prefix="edge-legacy-")
        db = os.path.join(tmp, "edge.db")
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE legacy(x)")
        out = self._run_auto(db)
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        # source 为空、plaintext_existing=True、没有生成 key
        self.assertEqual(self._state(out), ["", True, False])
        with open(db, "rb") as f:
            self.assertEqual(f.read(16), b"SQLite format 3\x00")

    def test_encrypted_db_and_wrong_key(self):
        try:
            import sqlcipher3  # noqa: F401
        except ImportError:
            self.skipTest("没有 sqlcipher3 驱动")
        tmp = tempfile.mkdtemp(prefix="edge-cipher-")
        db = os.path.join(tmp, "edge.db")
        ok = self._run(db, "correct-horse-battery-staple")
        self.assertEqual(ok.returncode, 0, ok.stderr[-400:])
        self.assertIn("mt-cipher-01", ok.stdout)
        with open(db, "rb") as f:
            self.assertNotEqual(f.read(16), b"SQLite format 3\x00")

        bad = self._run(db, "wrong-key")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("not a database", bad.stderr)
