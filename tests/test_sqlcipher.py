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
