"""MQTT 接入：连假 broker，发一条 telemetry，检查入库、回执、状态主题。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-mqtt-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from edge import config, mqtt, store  # noqa: E402
from tests.fake_broker import FakeBroker  # noqa: E402

BATCH = {
    "schema": "orpi.telemetry.v1",
    "device_id": "mt-3b-01",
    "edge_id": "edge-lab-01",
    "sent_at": 1794220000000,
    "window": {"from": 1794219600000, "to": 1794219900000, "step_ms": 300000},
    "aggregates": [{
        "metric": "systolic", "module_id": 83, "n_subjects": 8,
        "n_samples": 320, "mean": 131.4, "slope": 0.27, "z": 1.6, "k": 8,
    }],
    "advice": [{"text": "近 7 天收缩压缓慢上升，建议复测", "risk": "watch",
                "confidence": 0.72, "source": "local"}],
    "privacy": {"k": 8, "pseudonym": "hmac16", "raw": False, "suppressed": 1},
}


class MqttTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()
        cls.broker = FakeBroker()
        config.MQTT_HOST = "127.0.0.1"
        config.MQTT_PORT = cls.broker.port
        config.MQTT_TLS = False
        started = mqtt.mqtt_ingest.start()
        assert started, "客户端没起来"
        for _ in range(50):
            if mqtt.mqtt_ingest.connected:
                break
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        mqtt.mqtt_ingest.stop()
        cls.broker.close()

    def test_subscribed_to_both_topics(self):
        self.assertEqual(mqtt.mqtt_ingest.connected, True)
        joined = " ".join(self.broker.subscriptions)
        self.assertIn("orpi/v1/+/telemetry", joined)
        self.assertIn("orpi/v1/+/status", joined)

    def test_telemetry_lands_and_acks(self):
        before = len(self.broker.published)
        self.broker.inject("orpi/v1/mt-3b-01/telemetry",
                           json.dumps(BATCH, ensure_ascii=False).encode())
        for _ in range(40):
            if len(self.broker.published) > before:
                break
            time.sleep(0.05)
        acks = [p for t, p in self.broker.published if t == "orpi/v1/mt-3b-01/ack"]
        self.assertTrue(acks, "没有收到 ack")
        ack = json.loads(acks[-1])
        self.assertTrue(ack["accepted"])
        self.assertEqual(ack["code"], "accepted")

        rows = store.series("mt-3b-01", "systolic", 0, 2 ** 62, config.WINDOW_MS)
        self.assertTrue(any(r["mean"] == 131.4 for r in rows))

    def test_raw_payload_is_rejected_on_mqtt(self):
        bad = dict(BATCH, user_id="u-1")
        bad["window"] = {"from": 1, "to": 2, "step_ms": 1000}
        before = len(self.broker.published)
        self.broker.inject("orpi/v1/mt-3b-01/telemetry",
                           json.dumps(bad, ensure_ascii=False).encode())
        for _ in range(40):
            if len(self.broker.published) > before:
                break
            time.sleep(0.05)
        acks = [p for t, p in self.broker.published if t == "orpi/v1/mt-3b-01/ack"]
        self.assertEqual(json.loads(acks[-1])["code"], "RAW_PAYLOAD_REJECTED")
        self.assertGreaterEqual(store.counters().get("raw_rejected", 0), 1)

    def test_status_updates_modules(self):
        store.upsert_device("mt-a64-02", "温室无头 · Pine64", "env", "orpi 1.4.2", [129])
        self.broker.inject("orpi/v1/mt-a64-02/status",
                           json.dumps({"online": True, "fw": "orpi 1.5.0",
                                       "queue_depth": 7, "modules": [129, 131]}).encode())
        for _ in range(40):
            d = store.device("mt-a64-02")
            if d["modules"] == [129, 131] and d.get("queue_depth") == 7:
                break
            time.sleep(0.05)
        d = store.device("mt-a64-02")
        self.assertEqual(d["modules"], [129, 131])
        self.assertEqual(d["fw"], "orpi 1.5.0")
        self.assertEqual(d["queue_depth"], 7)

    def test_cmd_publish(self):
        ok = mqtt.mqtt_ingest.publish_cmd("mt-3b-01", {"cmd": "report_now"})
        self.assertTrue(ok)
        for _ in range(40):
            if any(t == "orpi/v1/mt-3b-01/cmd" for t, _ in self.broker.published):
                break
            time.sleep(0.05)
        self.assertTrue(any(t == "orpi/v1/mt-3b-01/cmd" for t, _ in self.broker.published))


if __name__ == "__main__":
    unittest.main()
