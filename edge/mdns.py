"""mDNS：边广播自己（_orpi-edge._tcp），并发现待接入的终端（_orpi-device._tcp）。

TXT 只放发现所需的 ID / 型号 / 版本 / 端口 / CA 指纹——
按方案 5.9，用户与健康数据一概不进广播。
没装 zeroconf 或网络不允许组播时，退化为静态清单，不影响主流程。
"""
from __future__ import annotations

import hashlib
import socket
from pathlib import Path
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


def pinned_cloud_fp(path: str | None = None) -> str:
    """预置 cloud-ca 的指纹，口径与云广播的 ca_fp 一致：DER 的 SHA256 前 16 hex。"""
    ca = path if path is not None else config.CLOUD_CA
    if not ca:
        return ""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        cert = x509.load_pem_x509_certificate(Path(ca).read_bytes())
        return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()[:16]
    except Exception:  # noqa: BLE001 —— 预置证书读不了就退回只看静态地址
        return ""


# 最近一次被拒的假云：给 /discovery 和审计看，不是状态机
_rejected: dict[str, str] = {"ca_fp": "", "reason": ""}


def cloud_reject_reason() -> str | None:
    return _rejected["reason"] or None


class _CloudListener(ServiceListener):
    """发现云节点：拿到地址后拼 https://host:port，静态配置仍然优先。"""

    def __init__(self) -> None:
        self.url: str | None = None

    def add_service(self, zc, type_, name) -> None:
        info = zc.get_service_info(type_, name, timeout=800)
        if not info:
            return
        props = {k.decode(): v.decode() for k, v in info.properties.items() if v is not None}
        fp = props.get("ca_fp", "")
        pin = pinned_cloud_fp()
        # 文档 §8.4：mDNS 只解决地址，信任靠 CA 指纹。广播的指纹和预置的
        # cloud-ca 对不上就是假云，不能拿它替换上报地址（报表会被骗走）
        if pin and fp != pin:
            reason = f"ca_fp 不符：广播 {fp or '(空)'}，预置 {pin}"
            if _rejected["ca_fp"] != fp:
                _rejected.update(ca_fp=fp, reason=reason)
                from . import store

                store.audit_action("system", "mdns.cloud_rejected", name,
                                   {"ca_fp": fp, "pinned": pin})
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
        self.cloud = _CloudListener()

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
            ServiceBrowser(self.zc, CLOUD_TYPE, self.cloud)
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
        """优先用后台已经发现的地址；没有就同步找一次。"""
        if self.cloud.url:
            self.cloud_url = self.cloud.url
            return self.cloud_url
        if not self.zc:
            return None
        browser = ServiceBrowser(self.zc, CLOUD_TYPE, self.cloud)
        import time
        time.sleep(timeout)
        browser.cancel()
        self.cloud_url = self.cloud.url
        return self.cloud_url

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.zc),
            "service": EDGE_TYPE,
            "ca_fp": edge_txt()[b"ca_fp"].decode(),
            "error": self.error,
            # 云侧：地址优先 mDNS，静态兜底；以及最近一次被拒的假云
            "cloud": {
                "url": self.cloud_url or self.cloud.url or config.CLOUD_URL,
                "source": "mdns" if (self.cloud_url or self.cloud.url)
                          else ("static" if config.CLOUD_URL else None),
                "pinned_fp": pinned_cloud_fp(),
                "rejected": cloud_reject_reason(),
            },
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
