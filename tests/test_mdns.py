"""mDNS 发现：只收 TXT CA 指纹对得上的云（文档 §8.4 假边/假云）。

不启真实组播，直接喂伪造的 service info。
"""
from __future__ import annotations

import datetime as dt
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-mdns-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from edge import config, mdns, store  # noqa: E402


class Info:
    """够 _CloudListener 用的最小 service info。"""

    def __init__(self, ca_fp: str):
        self.properties = {b"v": b"1", b"id": b"cloud-home-01", b"port": b"8443"}
        if ca_fp:
            self.properties[b"ca_fp"] = ca_fp.encode()
        self.addresses = [socket.inet_aton("127.0.0.1")]
        self.port = 8443


class Zc:
    def __init__(self, info):
        self.info = info

    def get_service_info(self, type_, name, timeout=0):
        return self.info


class CloudPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cloud-test-ca")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(dt.datetime(2020, 1, 1))
            .not_valid_after(dt.datetime(2040, 1, 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        cls.ca = Path(_TMP) / "cloud-ca.crt"
        cls.ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        cls.pin = mdns.pinned_cloud_fp(str(cls.ca))
        cls._orig = config.CLOUD_CA

    @classmethod
    def tearDownClass(cls):
        config.CLOUD_CA = cls._orig

    def setUp(self):
        config.CLOUD_CA = str(self.ca)
        mdns._rejected.update(ca_fp="", reason="")

    def test_pin_matches_cloud_txt_format(self):
        """口径和云仓 mdns.ca_fingerprint 一样：DER 的 SHA256 前 16 hex。"""
        self.assertEqual(len(self.pin), 16)
        self.assertRegex(self.pin, r"^[0-9a-f]{16}$")

    def test_matching_fingerprint_accepted(self):
        lis = mdns._CloudListener()
        lis.add_service(Zc(Info(self.pin)), mdns.CLOUD_TYPE, "cloud-home-01._orpi-cloud._tcp.local.")
        self.assertEqual(lis.url, "https://127.0.0.1:8443")
        self.assertIsNone(mdns.cloud_reject_reason())

    def test_fake_cloud_rejected_and_audited(self):
        lis = mdns._CloudListener()
        lis.add_service(Zc(Info("deadbeefdeadbeef")), mdns.CLOUD_TYPE, "evil._orpi-cloud._tcp.local.")
        self.assertIsNone(lis.url)
        self.assertIn("ca_fp 不符", mdns.cloud_reject_reason())
        actions = [a["action"] for a in store.audit(limit=10)]
        self.assertIn("mdns.cloud_rejected", actions)

    def test_missing_fingerprint_rejected(self):
        lis = mdns._CloudListener()
        lis.add_service(Zc(Info("")), mdns.CLOUD_TYPE, "old._orpi-cloud._tcp.local.")
        self.assertIsNone(lis.url)

    def test_no_pin_falls_back_to_accept(self):
        """没预置 cloud-ca 时无法比对，只能接受（mTLS 仍会挡住连不上的假云）。"""
        config.CLOUD_CA = ""
        lis = mdns._CloudListener()
        lis.add_service(Zc(Info("deadbeefdeadbeef")), mdns.CLOUD_TYPE, "x._orpi-cloud._tcp.local.")
        self.assertEqual(lis.url, "https://127.0.0.1:8443")


if __name__ == "__main__":
    unittest.main()
