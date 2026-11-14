"""服务控制台的逻辑测试。不碰 docker：compose 的输出用假数据喂。

控制台是开发机上的小工具，这里只锁三件事：配置能读、状态聚合对、
危险动作不会因为名字写错就打到别的服务上。
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "tools/service-launch"
sys.path.insert(0, str(SHARED))

from service_launch import config, stack  # noqa: E402


class ConfigTest(unittest.TestCase):
    def test_repo_config_loads(self):
        cfg = config.load()
        self.assertTrue(cfg.title)
        self.assertGreater(cfg.port, 1024)
        self.assertTrue(cfg.web_url.startswith("http"))
        self.assertTrue(cfg.health_url.startswith("http"))
        self.assertTrue(cfg.compose_file.exists(), f"compose 文件不存在：{cfg.compose_file}")

    def test_services_have_labels(self):
        cfg = config.load()
        unnamed = [n for n, m in cfg.services.items() if not m.label]
        self.assertEqual(unnamed, [], "launcher.toml 里的服务都应该有中文名")


class PortsTest(unittest.TestCase):
    def test_published_ports_deduped(self):
        rec = {
            "Publishers": [
                {"PublishedPort": 8001, "TargetPort": 8001},
                {"PublishedPort": 8001, "TargetPort": 8001},
                {"PublishedPort": 8885, "TargetPort": 8001},
            ]
        }
        self.assertEqual(stack.ports_of(rec), "8001 / 8885 → 8001")

    def test_internal_port_fallback(self):
        # 没发布到宿主机的端口标成「内部」，免得跟真实入口混淆
        self.assertEqual(stack.ports_of({"Ports": "8001/tcp,443/tcp"}), "内部 8001/tcp")


class SnapshotTest(unittest.TestCase):
    def _snap(self, rows, ready=(True, ""), health=False):
        cfg = config.load()
        with (
            mock.patch.object(stack, "docker_ready", return_value=ready),
            mock.patch.object(stack, "compose_ps", return_value=rows),
            mock.patch.object(stack, "compose_services", return_value=list(rows)),
            mock.patch.object(stack, "http_ok", return_value=health),
        ):
            return stack.snapshot(cfg, "docker")

    def test_unhealthy_container_is_counted(self):
        snap = self._snap(
            {"api": {"Service": "api", "State": "running", "Health": "unhealthy", "Status": "Up 1m"}}
        )
        api = next(s for s in snap["services"] if s["name"] == "api")
        self.assertTrue(api["running"])
        self.assertFalse(api["healthy"])
        self.assertEqual(snap["summary"]["bad"], 1)
        self.assertFalse(snap["health_ok"])

    def test_missing_container_shows_as_absent(self):
        snap = self._snap({}, ready=(True, ""))
        self.assertTrue(all(s["state"] == "absent" for s in snap["services"]))
        self.assertEqual(snap["summary"]["running"], 0)

    def test_docker_down_reports_hint(self):
        cfg = config.load()
        with mock.patch.object(stack, "docker_ready", return_value=(False, "没装 docker")):
            snap = stack.snapshot(cfg, "docker")
        self.assertEqual(snap["error"], "没装 docker")
        self.assertIn("docker compose", snap["hint"])

    def test_native_mode_without_pid_is_stopped(self):
        cfg = config.load()
        with (
            mock.patch.object(stack, "native_pid", return_value=0),
            mock.patch.object(stack, "compose_ps", return_value={}),
            mock.patch.object(stack, "http_ok", return_value=False),
        ):
            snap = stack.snapshot(cfg, "native")
        self.assertEqual(len(snap["services"]), 1)
        self.assertFalse(snap["services"][0]["running"])
        self.assertEqual(snap["services"][0]["state"], "stopped")
        # 云仓原生模式要 postgres 和 redis，没起的时候要能看到
        self.assertEqual(len(snap["deps"]), len(cfg.deps))
        self.assertTrue(all(not d["running"] for d in snap["deps"]))


class ActionTest(unittest.TestCase):
    def test_unknown_service_is_refused(self):
        cfg = config.load()
        with mock.patch.object(stack, "compose_services", return_value=["api"]):
            ok, msg = stack.act(cfg, "docker", "stop", "不存在的")
        self.assertFalse(ok)
        self.assertIn("不存在的", msg)

    def test_unknown_action_is_refused(self):
        cfg = config.load()
        ok, msg = stack.act(cfg, "docker", "rm-rf")
        self.assertFalse(ok)
        self.assertIn("不认识", msg)

    def test_failure_keeps_compose_output(self):
        cfg = config.load()
        with (
            mock.patch.object(stack, "compose_services", return_value=["api"]),
            mock.patch.object(stack, "_run", return_value=(1, "Error: no such container")),
        ):
            ok, msg = stack.act(cfg, "docker", "start", "api")
        self.assertFalse(ok)
        self.assertIn("no such container", msg)


class SharedFilesTest(unittest.TestCase):
    def test_checksums_match(self):
        out = subprocess.run(
            [sys.executable, str(SHARED / "checksums.py"), "--check"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(out.returncode, 0, out.stderr or out.stdout)


if __name__ == "__main__":
    unittest.main()
