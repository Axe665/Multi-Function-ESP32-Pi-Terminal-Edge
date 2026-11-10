"""分析层：趋势、热力图、报表口径。用 1 天演示数据跑，不依赖外部服务。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-analysis-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from edge import analysis, config, store  # noqa: E402


class AnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()
        # 全新建库，避免复用到别的测试留下的数据
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(config.DB_PATH) + suffix)
            if p.exists():
                p.unlink()
        store.init_db()
        from edge import sim
        cls.stats = sim.generate(1, seed=20261109)

    def test_seed_wrote_batches(self):
        self.assertGreater(self.stats["batches"], 0)
        self.assertGreaterEqual(len(store.devices()), 3)

    def test_trend_uses_aggregates(self):
        from edge import catalog
        dev = store.devices()[0]["device_id"]
        metric = catalog.metrics_of(dev)[0]
        t = analysis.trend(dev, metric, 24)
        self.assertGreater(len(t["points"]), 10)
        self.assertGreater(t["baseline"], 0)
        self.assertGreater(t["k"], 0)

    def test_heatmap_buckets(self):
        from edge import catalog
        dev = store.devices()[0]["device_id"]
        metric = catalog.metrics_of(dev)[0]
        cells = store.heatmap(dev, metric, store.now_ms() - 2 * 86_400_000)
        keys = {(c["dow"], c["hour"]) for c in cells}
        self.assertEqual(len(keys), len(cells), "同一时段不应重复成格")

    def test_report_matches_daily_totals(self):
        rep = analysis.build_report()
        daily = analysis.daily_aggregates(store.now_ms() - 86_400_000)
        self.assertEqual(len(rep["telemetry_daily"]), len(daily))
        # 报表里的样本数必须等于日聚合之和
        self.assertEqual(
            sum(r["n_samples"] for r in rep["telemetry_daily"]),
            sum(r["n_samples"] for r in daily))

    def test_anomalies_need_consecutive_windows(self):
        dev = store.devices()[0]["device_id"]
        base = store.now_ms() - 2 * 3600_000
        step = config.WINDOW_MS
        rows = [
            ("consecutive", base, 3.1), ("consecutive", base + step, 2.8),
            ("isolated", base + 2 * step, 4.2),
        ]
        with store.connect() as conn:
            for metric, ts, z in rows:
                conn.execute(
                    """INSERT OR REPLACE INTO aggregates
                       (device_id, metric, module_id, ts_from, ts_to, n_subjects,
                        n_samples, mean, slope, z, k)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (dev, metric, 1, ts, ts + step, 9, 360, 20.0, 0.1, z, 9))
        found = {r["metric"] for r in store.anomalies(base - 1)}
        self.assertIn("consecutive", found)
        self.assertNotIn("isolated", found)

    def test_overview_counts_agree(self):
        o = analysis.overview()
        self.assertEqual(o["devices_total"], len(o["lanes"]))
        self.assertEqual(o["devices_online"],
                         sum(1 for lane in o["lanes"] if lane["online"]))
        for lane in o["lanes"]:
            self.assertEqual(len(lane["ticks"]), 24)

    def test_consent_switch_gates_group_analysis(self):
        """文档 §8.5：关掉群体分析只剩在线/健康计数，分析页显示「样本不足」。"""
        store.set_settings({"group_analysis": False})
        try:
            o = analysis.overview()
            self.assertTrue(o["insufficient"])
            self.assertEqual(o["lanes"], [])
            self.assertEqual(o["findings"], [])
            # 匿名计数照旧给
            self.assertEqual(o["devices_total"], len(store.devices()))
        finally:
            store.set_settings({"group_analysis": True})
        self.assertFalse(analysis.overview().get("insufficient", False))

    def test_consent_switch_gates_personalization(self):
        """文档 §8.5：关掉个性化后建议只留本地，报表里不带 advice/词频。"""
        store.set_settings({"personalization": False})
        try:
            report = analysis.build_report()
            self.assertEqual(report["advice"], [])
            self.assertEqual(report["word_freq"], [])
            self.assertFalse(report["privacy"]["personalization"])
        finally:
            store.set_settings({"personalization": True})
        self.assertTrue(analysis.build_report()["advice"])


if __name__ == "__main__":
    unittest.main()
