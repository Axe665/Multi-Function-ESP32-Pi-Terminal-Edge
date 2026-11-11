"""契约与边界：示例必须过关，原始字段必须被拒。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 测试库放临时目录，绝不碰 data/edge.db
_TMP = tempfile.mkdtemp(prefix="edge-test-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from fastapi.testclient import TestClient  # noqa: E402

from edge import config, models, store  # noqa: E402
from edge.main import app  # noqa: E402

CONTRACTS = ROOT / "contracts"


def load(name: str) -> dict:
    return json.loads((CONTRACTS / "examples" / name).read_text(encoding="utf-8"))


class ContractTest(unittest.TestCase):
    def test_telemetry_example_validates(self):
        msg = models.Telemetry.model_validate(load("telemetry.v1.json"))
        self.assertEqual(msg.device_id, "mt-3b-01")
        self.assertFalse(msg.privacy.raw)

    def test_edge_report_example_validates(self):
        rep = models.EdgeReport.model_validate(load("edge-report.v1.json"))
        self.assertGreater(len(rep.telemetry_daily), 0)
        # k<5 的行不允许出现在上云报表里
        self.assertTrue(all(r.k >= 5 for r in rep.telemetry_daily))
        self.assertGreaterEqual(rep.privacy.k_min, 5)

    def test_report_example_has_no_raw_fields(self):
        text = json.dumps(load("edge-report.v1.json"), ensure_ascii=False)
        for key in ("user_id", "subject", "values", "raw_samples"):
            self.assertNotIn(f'"{key}"', text)

    def test_extra_field_is_rejected(self):
        payload = load("telemetry.v1.json")
        payload["user_id"] = "u-1"
        with self.assertRaises(Exception):
            models.Telemetry.model_validate(payload)


class IngestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()
        cls.client = TestClient(app)
        # 写入口现在默认要令牌，测试用同一份配置
        cls.client.headers.update({"Authorization": f"Bearer {config.INGEST_TOKEN}"})
        cls.payload = load("telemetry.v1.json")

    def test_ingest_requires_token(self):
        client = TestClient(app)   # 没有带 Authorization
        r = client.post("/api/v1/ingest/telemetry", json=self.payload)
        self.assertEqual(r.status_code, 401)

    def test_accept_then_dedupe(self):
        first = self.client.post("/api/v1/ingest/telemetry", json=self.payload)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["accepted"])

        second = self.client.post("/api/v1/ingest/telemetry", json=self.payload)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["accepted"])
        self.assertEqual(second.json()["code"], "duplicate")
        self.assertEqual(first.json()["batch_id"], second.json()["batch_id"])

    def test_raw_field_rejected_and_counted(self):
        bad = dict(self.payload, user_id="u-1")
        r = self.client.post("/api/v1/ingest/telemetry", json=bad)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["code"], "RAW_PAYLOAD_REJECTED")
        self.assertIn("user_id", r.json()["detail"]["fields"])
        self.assertGreaterEqual(store.counters().get("raw_rejected", 0), 1)

    def test_k_below_min_is_suppressed(self):
        low = json.loads(json.dumps(self.payload))
        low["window"] = {"from": 1, "to": 2, "step_ms": 1000}
        low["privacy"]["k"] = 4
        r = self.client.post("/api/v1/ingest/telemetry", json=low)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["accepted"])
        self.assertEqual(r.json()["code"], "suppressed")

    def test_low_k_row_is_suppressed(self):
        """批次 k 正常、某一行 k<5：云端按行拒收，边也不能先存下来。"""
        low = json.loads(json.dumps(self.payload))
        low["window"] = {"from": 3, "to": 4, "step_ms": 1000}
        low["aggregates"][0]["k"] = 4
        r = self.client.post("/api/v1/ingest/telemetry", json=low)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["accepted"])
        self.assertEqual(r.json()["code"], "suppressed")

    def test_schema_violation(self):
        broken = json.loads(json.dumps(self.payload))
        broken["schema"] = "orpi.telemetry.v2"
        r = self.client.post("/api/v1/ingest/telemetry", json=broken)
        self.assertEqual(r.status_code, 422)


class HealthTest(unittest.TestCase):
    def test_health(self):
        store.init_db()
        r = TestClient(app).get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["db"], "ok")


if __name__ == "__main__":
    unittest.main()
