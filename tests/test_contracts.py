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

    def test_advice_example_validates(self):
        item = load("advice.v1.json")["advice"][0]
        msg = models.Advice.model_validate(item)
        self.assertEqual(msg.risk, "watch")
        self.assertEqual(msg.source, "local")

    def test_status_and_cmd_examples_validate(self):
        st = models.StatusMessage.model_validate(load("status.v1.json"))
        self.assertEqual(st.queue_depth, 3)
        cmd = models.Command.model_validate(load("cmd.v1.json"))
        self.assertEqual(cmd.seconds, 300)
        with self.assertRaises(Exception):
            models.Command.model_validate({"cmd": "rm -rf"})

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

    def test_min_max_rejected_and_counted(self):
        # 文档 §8.2：出端前必须去掉 min/max，出现就算事故
        bad = dict(self.payload, min=10, max=99)
        r = self.client.post("/api/v1/ingest/telemetry", json=bad)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["code"], "RAW_PAYLOAD_REJECTED")
        self.assertIn("min", r.json()["detail"]["fields"])
        self.assertIn("max", r.json()["detail"]["fields"])

    def test_low_k_claim_with_compliant_rows_is_accepted(self):
        """批次声明的 k 只是端自述：行都合规就照收，只记审计（§8.2 丢的是桶，不是整批）。"""
        low = json.loads(json.dumps(self.payload))
        low["window"] = {"from": 1, "to": 2, "step_ms": 1000}
        low["privacy"]["k"] = 4
        r = self.client.post("/api/v1/ingest/telemetry", json=low)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["accepted"])
        self.assertEqual(r.json()["suppressed"], 0)
        actions = {a["action"] for a in store.audit(200)}
        self.assertIn("privacy.k_claimed_low", actions)

    def test_low_k_row_is_dropped_not_whole_batch(self):
        """文档 §8.2：丢的是这个桶，不是整批。合规的桶必须照常入库。"""
        low = json.loads(json.dumps(self.payload))
        low["window"] = {"from": 3, "to": 4, "step_ms": 1000}
        bad = low["aggregates"][0]
        bad["k"] = 4
        good = json.loads(json.dumps(bad))
        good["k"] = 8   # 不能超过 n_subjects（示例里是 8）
        good["metric"] = "temp_good"
        low["aggregates"] = [bad, good]

        r = self.client.post("/api/v1/ingest/telemetry", json=low)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["accepted"])
        self.assertEqual(r.json()["suppressed"], 1)

        kept = store.series(low["device_id"], "temp_good", 3, 4, 1000)
        dropped = store.series(low["device_id"], bad["metric"], 3, 4, 1000)
        self.assertTrue(kept, "k≥5 的桶必须入库")
        self.assertEqual(dropped, [], "k<5 的桶不能入库")

    def test_ingest_rate_limit(self):
        from edge import roles

        roles._hits.clear()
        config.INGEST_RATE_PER_MIN = 2
        try:
            codes = [self.client.post("/api/v1/ingest/telemetry", json=self.payload).status_code
                     for _ in range(3)]
        finally:
            config.INGEST_RATE_PER_MIN = 120
            roles._hits.clear()
        self.assertEqual(codes[:2], [200, 200])
        self.assertEqual(codes[2], 429)

    def test_disk_low_is_rejected(self):
        config.MIN_FREE_MB = 10 ** 9
        try:
            r = self.client.post("/api/v1/ingest/telemetry", json=self.payload)
        finally:
            config.MIN_FREE_MB = 512
        self.assertEqual(r.status_code, 507)
        self.assertEqual(r.json()["detail"]["code"], "DISK_LOW")

    def test_schema_violation(self):
        broken = json.loads(json.dumps(self.payload))
        broken["schema"] = "orpi.telemetry.v2"
        r = self.client.post("/api/v1/ingest/telemetry", json=broken)
        self.assertEqual(r.status_code, 422)

    def test_oversize_body_is_refused(self):
        """一条 5 min 聚合报文顶多几十 KB：2 MB 以上直接 413，不读进内存。"""
        big = b'{"pad":"' + b"x" * (2 * 1024 * 1024) + b'"}'
        r = self.client.post("/api/v1/ingest/telemetry", content=big,
                             headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413, r.text)
        self.assertEqual(r.json()["detail"]["code"], "PAYLOAD_TOO_LARGE")

    def test_oversize_chunked_body_is_refused(self):
        """分块传输没有 Content-Length：按读到的字节数截断。"""
        big = b'{"pad":"' + b"x" * (2 * 1024 * 1024 + 1) + b'"}'
        r = self.client.post("/api/v1/ingest/telemetry", content=iter([big]),
                             headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413, r.text)

    def test_chunked_body_still_reaches_ingest(self):
        """中间件自己读了体，下游必须还能读到同一份，否则合规报文会被吞。"""
        body = json.loads(json.dumps(self.payload))
        body["window"] = {"from": 20, "to": 21, "step_ms": 1000}
        r = self.client.post("/api/v1/ingest/telemetry",
                             content=iter([json.dumps(body).encode()]),
                             headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["accepted"])


class VendorContractTest(unittest.TestCase):
    """contracts/vendor 只放两种东西：真 schema，或 SOURCE 里标了 (example) 的示例载荷。"""

    SOURCE = CONTRACTS / "vendor" / "terminal" / "SOURCE"

    def _marked_examples(self) -> set[str]:
        marked: set[str] = set()
        in_files = False
        for line in self.SOURCE.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text.startswith("files:"):
                in_files = True
                continue
            if not in_files or not text or text.startswith("#"):
                continue
            if "(example)" in text:
                marked.add(text.split()[0])
        return marked

    def test_vendor_json_is_schema_or_marked_example(self):
        marked = self._marked_examples()
        for path in sorted((CONTRACTS / "vendor").rglob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            is_schema = any(k in data for k in ("$schema", "type", "properties"))
            self.assertTrue(is_schema or path.name in marked,
                            f"{path} 既不是 schema，也没在 SOURCE 里标 (example)")


class ConsentApiTest(unittest.TestCase):
    """文档 §8.5：群体分析关掉后，分析类端点只留在线/健康计数。"""

    @classmethod
    def setUpClass(cls):
        store.init_db()
        store.ensure_device("mt-consent")
        cls.client = TestClient(app)

    def test_group_off_gates_analysis_endpoints(self):
        store.set_settings({"group_analysis": False})
        try:
            devs = self.client.get("/api/v1/devices").json()
            self.assertTrue(all(d["metrics"] == [] for d in devs))
            detail = self.client.get("/api/v1/devices/mt-consent").json()
            self.assertTrue(detail["insufficient"])
            self.assertEqual(detail["metrics"], [])
            self.assertEqual(self.client.get("/api/v1/anomalies").json(), [])
            self.assertEqual(self.client.get("/api/v1/advice").json(), [])
            self.assertEqual(self.client.get("/api/v1/batches").json(), [])
            from edge import catalog
            catalog.upsert("mt-consent", "consent_metric", 1, label="指标", unit="u")
            heat = self.client.get(
                "/api/v1/heatmap?device=mt-consent&metric=consent_metric").json()
            self.assertTrue(heat["insufficient"])
            self.assertEqual(heat["cells"], [])
            series = self.client.get(
                "/api/v1/devices/mt-consent/series?metric=consent_metric").json()
            self.assertTrue(series["insufficient"])
            self.assertEqual(series["points"], [])
        finally:
            store.set_settings({"group_analysis": True})

    def test_group_on_returns_normal_shape(self):
        store.set_settings({"group_analysis": True})
        detail = self.client.get("/api/v1/devices/mt-consent").json()
        self.assertNotIn("insufficient", detail)
        self.assertIsInstance(detail["metrics"], list)


class HealthTest(unittest.TestCase):
    def test_health(self):
        store.init_db()
        r = TestClient(app).get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["db"], "ok")


if __name__ == "__main__":
    unittest.main()
