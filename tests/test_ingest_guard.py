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

    def test_k_min_cannot_go_below_5(self):
        # 5 是文档 §8.2 的硬门槛：允许写更低等于自己给自己开洞
        r = self.client.put("/api/v1/settings", json={"k_min": 1})
        self.assertEqual(r.status_code, 422, r.text)
        r = self.client.put("/api/v1/settings", json={"k_min": 5})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(store.get_settings().get("k_min"), 5)


class CloudConfigTest(unittest.TestCase):
    """云地址与令牌：只收 https，文件必须是 0600；模型代理没配云就 503。"""

    @classmethod
    def setUpClass(cls):
        from edge import config

        store.init_db()
        cls.client = TestClient(app)
        cls.config = config

    def setUp(self):
        self._old = (self.config.CLOUD_URL, self.config.CLOUD_TOKEN)

    def tearDown(self):
        self.config.CLOUD_URL, self.config.CLOUD_TOKEN = self._old

    def test_cloud_url_must_be_https(self):
        for url in ("http://127.0.0.1:9000", "http://cloud.local"):
            r = self.client.post("/api/v1/cloud/config", json={"url": url, "token": "t"})
            self.assertEqual(r.status_code, 400, r.text)
        self.assertFalse(any(
            (self.config.CLOUD_OVERRIDE_PATH.exists()
             and url in self.config.CLOUD_OVERRIDE_PATH.read_text(encoding="utf-8"))
            for url in ("http://127.0.0.1:9000", "http://cloud.local")))

    def test_token_file_is_owner_only(self):
        r = self.client.post("/api/v1/cloud/config",
                             json={"url": "https://cloud.local", "token": "tok"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.config.CLOUD_OVERRIDE_PATH.stat().st_mode & 0o777, 0o600)

    def test_ai_proxy_without_cloud_is_503(self):
        self.config.CLOUD_URL, self.config.CLOUD_TOKEN = "", ""
        r = self.client.post("/api/v1/ai/generate", json={"prompt": "hi"})
        self.assertEqual(r.status_code, 503, r.text)

    def test_ai_proxy_passes_cloud_answer_through(self):
        from unittest import mock

        from edge import api

        self.config.CLOUD_URL, self.config.CLOUD_TOKEN = "https://cloud.local", "tok"
        answer = mock.Mock(status_code=200)
        answer.json.return_value = {"text": "好的"}
        with mock.patch.object(api.httpx, "Client") as client_cls:
            post = client_cls.return_value.__enter__.return_value.post
            post.return_value = answer
            r = self.client.post("/api/v1/ai/generate", json={"prompt": "hi"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"text": "好的"})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://cloud.local/api/v1/ai/reports")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok")

    def test_ai_proxy_keeps_cloud_error_code(self):
        from unittest import mock

        from edge import api

        self.config.CLOUD_URL, self.config.CLOUD_TOKEN = "https://cloud.local", "tok"
        answer = mock.Mock(status_code=429, text="rate limited")
        with mock.patch.object(api.httpx, "Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.return_value = answer
            r = self.client.post("/api/v1/ai/generate", json={"prompt": "hi"})
        self.assertEqual(r.status_code, 429, r.text)
        self.assertEqual(r.json()["body"], "rate limited")


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
