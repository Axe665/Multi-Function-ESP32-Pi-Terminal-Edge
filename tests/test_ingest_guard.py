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

    def test_revoked_device_is_refused_without_transport_identity(self):
        """吊销以前只拦 MQTT：换到 HTTP 通道（没有 transport_device）就绕过了。"""
        body = json.loads(json.dumps(EXAMPLE))
        body["device_id"] = "mt-revoked-http"
        store.revoke_serial("serial-http", "mt-revoked-http", "测试")
        with self.assertRaises(ingest.IngestError) as ctx:
            ingest.process(body)
        self.assertEqual(ctx.exception.code, "DEVICE_REVOKED")

    def test_payload_for_another_edge_is_refused(self):
        body = json.loads(json.dumps(EXAMPLE))
        body["edge_id"] = "edge-somewhere-else"
        with self.assertRaises(ingest.IngestError) as ctx:
            ingest.process(body, transport_device=body["device_id"])
        self.assertEqual(ctx.exception.code, "EDGE_MISMATCH")

    def test_future_window_does_not_pin_device_online(self):
        body = json.loads(json.dumps(EXAMPLE))
        body["device_id"] = "mt-future-01"
        body["window"] = {"from": 1, "to": 99_999_999_999_999, "step_ms": 300000}
        body["aggregates"][0]["n_subjects"] = 8
        body["aggregates"][0]["k"] = 8
        ingest.process(body, transport_device="mt-future-01")
        dev = store.device("mt-future-01")
        self.assertLess(dev["last_seen"], 99_999_999_999_999, "未来时间戳不能写进 last_seen")


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


class HttpIngestIdentityTest(unittest.TestCase):
    """HTTP 通道也要有身份：以前它不比对 device_id，也不查吊销。"""

    @classmethod
    def setUpClass(cls):
        store.init_db()
        cls.client = TestClient(app)
        from edge import config

        cls.client.headers.update({"Authorization": f"Bearer {config.INGEST_TOKEN}"})

    def test_header_identity_must_match_payload(self):
        body = json.loads(json.dumps(EXAMPLE))
        r = self.client.post("/api/v1/ingest/telemetry", json=body,
                             headers={"x-device-id": "mt-someone-else"})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()["detail"]["code"], "DEVICE_MISMATCH")

    def test_revoked_device_cannot_post(self):
        body = json.loads(json.dumps(EXAMPLE))
        body["device_id"] = "mt-http-revoked"
        store.revoke_serial("serial-http-2", "mt-http-revoked", "测试")
        r = self.client.post("/api/v1/ingest/telemetry", json=body,
                             headers={"x-device-id": "mt-http-revoked"})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()["detail"]["code"], "DEVICE_REVOKED")

    def test_missing_token_is_not_treated_as_open(self):
        """令牌生成失败（目录只读）时必须拒绝，不能退回「不校验」。"""
        from unittest import mock

        from edge import config

        with mock.patch.object(config, "INGEST_TOKEN", ""):
            r = self.client.post("/api/v1/ingest/telemetry",
                                 json=json.loads(json.dumps(EXAMPLE)))
        self.assertEqual(r.status_code, 503, r.text)


if __name__ == "__main__":
    unittest.main()
