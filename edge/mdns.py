"""mDNS：边广播自己（_orpi-edge._tcp），并发现待接入的终端（_orpi-device._tcp）。

TXT 只放发现所需的 ID / 型号 / 版本 / 端口 / CA 指纹——
按方案 5.9，用户与健康数据一概不进广播。
没装 zeroconf 或网络不允许组播时，退化为静态清单，不影响主流程。
"""
from __future__ import annotations

import socket
from typing import Any

try:
    from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf
except ImportError:  # pragma: no cover
    Zeroconf = None  # type: ignore[assignment]

from . import config, security

EDGE_TYPE = "_orpi-edge._tcp.local."
DEVICE_TYPE = "_orpi-device._tcp.local."
CLOUD_TYPE = "_orpi-cloud._tcp.local."


def edge_txt(port: int = 8001) -> dict[bytes, bytes]:
    return {
        b"v": b"1",
        b"id": config.EDGE_ID.encode(),
        b"port": str(port).encode(),
        b"ca_fp": security.ca_fingerprint().split(":")[-1][:16].encode(),
    }


def device_txt(device_id: str, model: str, fw: str, port: int = 4580) -> dict[bytes, bytes]:
    return {
        b"v": b"1",
        b"id": device_id.encode(),
        b"model": model.encode(),
        b"fw": fw.encode(),
        b"port": str(port).encode(),
    }


class _DeviceListener(ServiceListener):
    def __init__(self, found: dict[str, dict[str, Any]]):
        self.found = found

    def _take(self, zc, type_, name) -> None:
        info = zc.get_service_info(type_, name, timeout=800)
        if not info:
            return
        props = {k.decode(): v.decode() for k, v in info.properties.items() if v is not None}
        dev = props.get("id") or name.split(".")[0]
        addresses = [socket.inet_ntoa(a) for a in info.addresses]
        self.found[dev] = {
            "device_id": dev, "model": props.get("model"), "fw": props.get("fw"),
            "port": int(props.get("port", 0) or info.port or 0),
            "address": addresses[0] if addresses else None,
            "source": "mdns",
        }

    def add_service(self, zc, type_, name):
        self._take(zc, type_, name)

    def update_service(self, zc, type_, name):
        self._take(zc, type_, name)

    def remove_service(self, zc, type_, name):
        dev = name.split(".")[0]
        self.found.pop(dev, None)


class _CloudListener(ServiceListener):
    """发现云节点：拿到地址后拼 https://host:port，静态配置仍然优先。"""

    def __init__(self) -> None:
        self.url: str | None = None

    def add_service(self, zc, type_, name) -> None:
        info = zc.get_service_info(type_, name, timeout=800)
        if not info:
            return
        addresses = [socket.inet_ntoa(a) for a in info.addresses]
        if not addresses:
            return
        self.url = f"https://{addresses[0]}:{info.port or 8443}"

    def update_service(self, *args) -> None:
        pass

    def remove_service(self, *args) -> None:
        pass


class Mdns:
    def __init__(self) -> None:
        self.zc: Any = None
        self.info: Any = None
        self.error: str | None = None
        self.cloud_url: str | None = None

    def start(self) -> bool:
        if Zeroconf is None or not config.MDNS_ENABLED:
            self.error = "zeroconf 未安装或已关闭"
            return False
        try:
            self.zc = Zeroconf()
            self.info = ServiceInfo(
                EDGE_TYPE,
                f"{config.EDGE_ID}.{EDGE_TYPE}",
                addresses=[socket.inet_aton(_lan_ip())],
                port=8001,
                properties=edge_txt(8001),
                server=f"{config.EDGE_ID}.local.",
            )
            self.zc.register_service(self.info)
            # 文档 §5.8：云地址优先 mDNS 发现，静态地址兜底
            ServiceBrowser(self.zc, CLOUD_TYPE, _CloudListener())
            self.error = None
            return True
        except Exception as e:  # noqa: BLE001 —— 组播被禁用时不能拖垮服务
            self.error = str(e)[:200]
            return False

    def stop(self) -> None:
        if self.zc:
            if self.info:
                self.zc.unregister_service(self.info)
            self.zc.close()
            self.zc = None

    def browse(self, timeout: float = 1.0) -> list[dict[str, Any]]:
        """同步发现，最多等 timeout 秒。给 /discovery 用。"""
        if not self.zc:
            return []
        found: dict[str, dict[str, Any]] = {}
        browser = ServiceBrowser(self.zc, DEVICE_TYPE, _DeviceListener(found))
        import time
        time.sleep(timeout)
        browser.cancel()
        return list(found.values())

    def discover_cloud(self, timeout: float = 1.0) -> str | None:
        """同步找一次云；找不到返回 None（调用方继续用静态地址）。"""
        if not self.zc:
            return None
        listener = _CloudListener()
        browser = ServiceBrowser(self.zc, CLOUD_TYPE, listener)
        import time
        time.sleep(timeout)
        browser.cancel()
        self.cloud_url = listener.url
        return listener.url

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.zc),
            "service": EDGE_TYPE,
            "ca_fp": edge_txt()[b"ca_fp"].decode(),
            "error": self.error,
        }


def _lan_ip() -> str:
    """取默认路由的出口地址；取不到就退回回环。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


mdns = Mdns()
