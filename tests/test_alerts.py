"""告警：连续窗口判定、确认、静音、审计。用临时库，不依赖服务。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-alerts-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from edge import config, store  # noqa: E402


class AlertTest(unittest.TestCase):
    def setUp(self):
        store.init_db()
        with store.connect() as conn:
            conn.execute("DELETE FROM alert_state")
            conn.execute("DELETE FROM audit")
            conn.execute("DELETE FROM aggregates")
            conn.execute("DELETE FROM devices")
            conn.execute("DELETE FROM telemetry")
        store.ensure_device("dev-a")
        self.base = store.now_ms() - 2 * 3600_000
        self.step = config.WINDOW_MS

    def _win(self, metric, idx, z):
        ts = self.base + idx * self.step
        with store.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO aggregates
                   (device_id, metric, module_id, ts_from, ts_to, n_subjects,
                    n_samples, mean, slope, z, k)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                ("dev-a", metric, 1, ts, ts + self.step, 9, 360, 20.0, 0.1, z, 9))

    def feed(self):
        return store.alert_feed(self.base - 1, stale_ms=3 * config.WINDOW_MS)

    def test_two_windows_is_critical(self):
        self._win("voltage", 0, 3.1)
        self._win("voltage", 1, 2.8)
        rows = [a for a in self.feed() if a["metric"] == "voltage"]
        self.assertEqual(len(rows), 1, "一段连续的越界应合并成一条")
        self.assertEqual(rows[0]["severity"], "critical")
        self.assertEqual(rows[0]["windows"], 2)
        self.assertEqual(rows[0]["state"], "pending")

    def test_single_window_is_notice(self):
        self._win("temp", 0, 2.2)
        rows = [a for a in self.feed() if a["metric"] == "temp"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "notice")

    def test_recovery_is_computed(self):
        self._win("hum", 0, 2.6)
        self._win("hum", 1, 2.6)
        self._win("hum", 2, 0.3)
        rows = [a for a in self.feed() if a["metric"] == "hum"]
        self.assertEqual(rows[0]["state"], "resolved")

    def test_ack_and_mute_write_audit(self):
        self._win("co2", 0, 3.0)
        self._win("co2", 1, 3.0)
        a = [x for x in self.feed() if x["metric"] == "co2"][0]
        store.ack_alert("dev-a", "co2", a["ts_from"], "admin")
        self.assertEqual([x for x in self.feed() if x["metric"] == "co2"][0]["state"], "acked")

        store.mute_alert("dev-a", "co2", a["ts_from"],
                         store.now_ms() + 3600_000, "等换传感器", "admin")
        self.assertEqual([x for x in self.feed() if x["metric"] == "co2"][0]["state"], "muted")

        actions = {r["action"] for r in store.audit(20)}
        self.assertIn("alert.ack", actions)
        self.assertIn("alert.mute", actions)

        store.unmute_alert("dev-a", "co2", a["ts_from"])
        self.assertEqual([x for x in self.feed() if x["metric"] == "co2"][0]["state"], "acked")

    def test_stale_device_is_critical(self):
        with store.connect() as conn:
            conn.execute("UPDATE devices SET last_seen=? WHERE device_id='dev-a'",
                         (store.now_ms() - 3600_000,))
        stale = [a for a in self.feed() if a["kind"] == "stale"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["severity"], "critical")
        self.assertEqual(stale[0]["metric"], "__stale__")


if __name__ == "__main__":
    unittest.main()
