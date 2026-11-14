"""演示补数的开关语义：只有 EDGE_SIM=1 才补。

这一条写反过一次（`!= "1"`），生产环境 EDGE_SIM=0 却在启动时灌了 288 个
mock 窗口，还和真机数据混在同一张表里。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-roles-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from edge import roles  # noqa: E402


class SimSwitchTest(unittest.TestCase):
    def test_default_is_off(self):
        old = os.environ.pop("EDGE_SIM", None)
        try:
            self.assertFalse(roles._sim_enabled())
        finally:
            if old is not None:
                os.environ["EDGE_SIM"] = old

    def test_explicit_zero_is_off(self):
        old = os.environ.get("EDGE_SIM")
        os.environ["EDGE_SIM"] = "0"
        try:
            self.assertFalse(roles._sim_enabled())
        finally:
            os.environ.pop("EDGE_SIM", None)
            if old is not None:
                os.environ["EDGE_SIM"] = old

    def test_explicit_one_is_on(self):
        old = os.environ.get("EDGE_SIM")
        os.environ["EDGE_SIM"] = "1"
        try:
            self.assertTrue(roles._sim_enabled())
        finally:
            os.environ.pop("EDGE_SIM", None)
            if old is not None:
                os.environ["EDGE_SIM"] = old


if __name__ == "__main__":
    unittest.main()
