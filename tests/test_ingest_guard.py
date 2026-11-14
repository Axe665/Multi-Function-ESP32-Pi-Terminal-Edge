"""摄取与设置的安全边界：身份必须对上、吊销必须生效、保留期不能被写崩。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-guard-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from fastapi.testclient import TestClient  # noqa: E402

from edge import ingest, store  # noqa: E402
from edge.main import app  # noqa: E402

EXAMPLE = json.loads((ROOT / "contracts/examples/telemetry.v1.json").read_text(encoding="utf-8"))


class DeviceIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()

    def test_payload_device_must_match_topic(self):
        body = dict(EXAMPLE)
        with self.assertRaises(ingest.IngestError) as ctx:
            ingest.process(body, transport_device="mt-other-01")
        self.assertEqual(ctx.exception.code, "DEVICE_MISMATCH")

    def test_revoked_device_is_refused(self):
        body = dict(EXAMPLE)
        body["device_id"] = "mt-revoked-01"
        store.revoke_serial("serial-test", "mt-revoked-01", "测试")
        with self.assertRaises(ingest.IngestError) as ctx:
            ingest.process(body, transport_device="mt-revoked-01")
        self.assertEqual(ctx.exception.code, "DEVICE_REVOKED")


class SettingsBoundsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()
        cls.client = TestClient(app)

    def test_retention_days_cannot_be_zero(self):
        # 0 会被 prune 当成「删掉全部历史」
        r = self.client.put("/api/v1/settings", json={"retention_days": 0})
        self.assertEqual(r.status_code, 422, r.text)

    def test_retention_days_out_of_range(self):
        r = self.client.put("/api/v1/settings", json={"retention_days": 99999})
        self.assertEqual(r.status_code, 422, r.text)

    def test_retention_days_normal_value_is_saved(self):
        r = self.client.put("/api/v1/settings", json={"retention_days": 30})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(store.get_settings().get("retention_days"), 30)

    def test_non_integer_is_refused(self):
        r = self.client.put("/api/v1/settings", json={"retention_days": "abc"})
        self.assertEqual(r.status_code, 422, r.text)


if __name__ == "__main__":
    unittest.main()
