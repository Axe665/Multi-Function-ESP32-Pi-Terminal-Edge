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
        cls.stats = sim.generate(1)

    def test_seed_wrote_batches(self):
        self.assertGreater(self.stats["batches"], 0)
        self.assertGreaterEqual(len(store.devices()), 3)

    def test_trend_uses_aggregates(self):
        t = analysis.trend("mt-3b-01", "bp.systolic", 24)
        self.assertGreater(len(t["points"]), 10)
        self.assertGreater(t["baseline"], 0)
        self.assertGreater(t["k"], 0)

    def test_heatmap_buckets(self):
        cells = store.heatmap("mt-3b-01", "bp.systolic",
                              store.now_ms() - 2 * 86_400_000)
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

    def test_overview_counts_agree(self):
        o = analysis.overview()
        self.assertEqual(o["devices_total"], len(o["lanes"]))
        self.assertEqual(o["devices_online"],
                         sum(1 for lane in o["lanes"] if lane["online"]))
        for lane in o["lanes"]:
            self.assertEqual(len(lane["ticks"]), 24)


if __name__ == "__main__":
    unittest.main()
