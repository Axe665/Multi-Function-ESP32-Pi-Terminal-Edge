"""调度：退避序列、保留期清理、到点才生成报表。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-sched-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from edge import cloudpush, config, scheduler, store  # noqa: E402


class BackoffTest(unittest.TestCase):
    def test_backoff_sequence(self):
        store.init_db()
        store.enqueue_report("r-backoff", {"schema": "x"})
        seen = []
        for _ in range(5):
            seen.append(store.schedule_retry("r-backoff", "boom") - store.now_ms())
        # 1 min / 5 min / 30 min / 2 h / 2 h
        self.assertAlmostEqual(seen[0] / 60000, 1, delta=0.2)
        self.assertAlmostEqual(seen[1] / 60000, 5, delta=0.2)
        self.assertAlmostEqual(seen[2] / 60000, 30, delta=0.2)
        self.assertAlmostEqual(seen[3] / 3600000, 2, delta=0.02)
        self.assertAlmostEqual(seen[4] / 3600000, 2, delta=0.02)

    def test_due_respects_next_at(self):
        store.init_db()
        store.enqueue_report("r-due", {"schema": "x"})
        with store.connect() as conn:
            conn.execute("UPDATE outbox SET next_at=? WHERE report_id='r-due'",
                         (store.now_ms() + 3600_000,))
        self.assertFalse(any(r["report_id"] == "r-due" for r in store.due_reports()))
        with store.connect() as conn:
            conn.execute("UPDATE outbox SET next_at=? WHERE report_id='r-due'",
                         (store.now_ms() - 1000,))
        self.assertTrue(any(r["report_id"] == "r-due" for r in store.due_reports()))

    def test_outbox_gives_up_after_7_days(self):
        store.init_db()
        store.enqueue_report("r-old", {"schema": "x"})
        with store.connect() as conn:
            conn.execute("UPDATE outbox SET created_at=? WHERE report_id='r-old'",
                         (store.now_ms() - store.OUTBOX_MAX_AGE_MS - 1000,))
        self.assertFalse(any(r["report_id"] == "r-old" for r in store.due_reports()))
        self.assertEqual(scheduler.prune(180)["outbox_expired"], 1)
        with store.connect() as conn:
            left = conn.execute("SELECT COUNT(*) FROM outbox WHERE report_id='r-old'").fetchone()[0]
        self.assertEqual(left, 0)


class SnapshotTest(unittest.TestCase):
    def test_snapshot_written_once_per_day(self):
        store.init_db()
        out = scheduler.snapshot()
        name = out["snapshot"]
        self.assertTrue(name)
        path = config.DATA_DIR / "snapshots" / name
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 0)
        # 同一天再跑一次不会重复写
        self.assertEqual(scheduler.snapshot()["snapshot"], name)


class PruneTest(unittest.TestCase):
    def test_prune_removes_only_old_rows(self):
        store.init_db()
        now = store.now_ms()
        old = now - 400 * 86_400_000
        with store.connect() as conn:
            conn.execute("DELETE FROM aggregates")
            conn.execute("DELETE FROM telemetry")
            conn.execute("DELETE FROM advice")
            conn.execute(
                """INSERT INTO aggregates VALUES('mt-3b-01','systolic',83,?,?,8,320,128,0,0,8)""",
                (old, old))
            conn.execute(
                """INSERT INTO aggregates VALUES('mt-3b-01','systolic',83,?,?,8,320,128,0,0,8)""",
                (now, now))
            conn.execute("INSERT INTO advice(device_id,text,risk,confidence,source,created_at) "
                         "VALUES('mt-3b-01','旧建议','info',0.5,'local',?)", (old,))
        out = scheduler.prune(180)
        self.assertEqual(out["aggregates"], 1)
        self.assertEqual(out["advice"], 1)
        with store.connect() as conn:
            left = conn.execute("SELECT COUNT(*) FROM aggregates").fetchone()[0]
        self.assertEqual(left, 1)


class TickTest(unittest.TestCase):
    def test_tick_without_cloud_does_nothing(self):
        store.init_db()
        config.CLOUD_URL = ""
        out = scheduler.tick()
        self.assertIsNone(out["report"])
        self.assertIsNone(out["drain"])

    def test_cloudpush_reports_not_configured(self):
        store.init_db()
        config.CLOUD_URL = ""
        result = cloudpush.send({"schema": "orpi.edge.report.v1"})
        self.assertEqual(result["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
