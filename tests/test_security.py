"""CA / 配对码 / 证书吊销。全部离线，不碰网络。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="edge-security-")
os.environ.setdefault("EDGE_DB", os.path.join(_TMP, "edge.db"))
os.environ.setdefault("EDGE_DATA_DIR", _TMP)
os.environ.setdefault("EDGE_CLIENT_CERT", "")

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from edge import security, store  # noqa: E402


def make_csr(device_id: str) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, device_id)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


class PairingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()
        with store.connect() as conn:
            conn.execute("DELETE FROM pair_codes")
            conn.execute("DELETE FROM device_certs")
            conn.execute("DELETE FROM revoked")
        store.upsert_device("mt-3b-01", "诊室屏 · Pi 3B", "health", "orpi 1.4.2", [83, 80])

    def test_ca_is_created_once(self):
        security.ensure_ca()
        self.assertTrue(security.CA_CRT.exists())
        self.assertEqual(security.CA_KEY.stat().st_mode & 0o777, 0o600)
        first = security.CA_CRT.read_bytes()
        security.ensure_ca()
        self.assertEqual(first, security.CA_CRT.read_bytes())

    def test_redeem_issues_verifiable_cert(self):
        code = security.new_pair_code("mt-3b-01")
        out = security.redeem(code, make_csr("mt-3b-01"))
        self.assertIn("BEGIN CERTIFICATE", out["cert_pem"])

        verified = security.verify(out["cert_pem"])
        self.assertEqual(verified["device_id"], "mt-3b-01")
        self.assertEqual(verified["serial"], out["serial"])

        # 证书字段：CN=device_id、OU=mt-device、365 天
        cert = x509.load_pem_x509_certificate(out["cert_pem"].encode())
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        ou = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value
        days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        self.assertEqual(cn, "mt-3b-01")
        self.assertEqual(ou, "mt-device")
        self.assertGreaterEqual(days, 364)

    def test_code_is_single_use(self):
        code = security.new_pair_code("mt-3b-01")
        security.redeem(code, make_csr("mt-3b-01"))
        with self.assertRaises(ValueError):
            security.redeem(code, make_csr("mt-3b-01"))

    def test_code_binds_public_key(self):
        code = security.new_pair_code("mt-3b-01")
        csr_a = make_csr("mt-3b-01")
        csr_b = make_csr("mt-3b-01")   # 同一台设备、另一把钥匙
        # 第一次尝试失败了也不要紧：把公钥钉住的是兑换本身
        security.redeem(code, csr_a)
        with self.assertRaises(ValueError):
            security.redeem(code, csr_b)

    def test_five_failures_lock(self):
        code = security.new_pair_code("mt-3b-01")
        for _ in range(security.PAIR_MAX_ATTEMPTS):
            store.pair_failure(code, security.PAIR_MAX_ATTEMPTS, security.PAIR_LOCK_MS)
        with self.assertRaises(ValueError) as ctx:
            security.redeem(code, make_csr("mt-3b-01"))
        self.assertIn("10 分钟", str(ctx.exception))

    def test_lock_is_per_device(self):
        """锁的是这台设备的码：以前全局计数，一个人猜错码就锁死全场配对。"""
        code_a = security.new_pair_code("mt-3b-01")
        code_b = security.new_pair_code("mt-3b-02")
        for _ in range(security.PAIR_MAX_ATTEMPTS):
            store.pair_failure(code_a, security.PAIR_MAX_ATTEMPTS, security.PAIR_LOCK_MS)
        with self.assertRaises(ValueError):
            security.redeem(code_a, make_csr("mt-3b-01"))
        out = security.redeem(code_b, make_csr("mt-3b-02"))
        self.assertIn("BEGIN CERTIFICATE", out["cert_pem"])

    def test_unknown_code_does_not_lock_everything(self):
        """未知码只交给 /pair/redeem 的接口限速，不写全局锁。"""
        with store.connect() as conn:
            conn.execute("DELETE FROM pair_codes WHERE code='999999'")
        with self.assertRaises(ValueError):
            security.redeem("999999", make_csr("mt-3b-01"))
        code = security.new_pair_code("mt-3b-01")
        self.assertIn("BEGIN CERTIFICATE", security.redeem(code, make_csr("mt-3b-01"))["cert_pem"])

    def test_redeem_writes_audit(self):
        code = security.new_pair_code("mt-3b-01")
        out = security.redeem(code, make_csr("mt-3b-01"))
        rows = [a for a in store.audit(200) if a["action"] == "pair.issued"]
        self.assertTrue(rows, "签发证书没留审计")
        self.assertEqual(json.loads(rows[0]["detail"])["serial"], out["serial"])

    def test_revoke_without_cert_is_not_silent(self):
        """没有证书可吊销也是结论，别把「什么都没发生」报成成功。"""
        self.assertEqual(security.revoke("mt-no-certs", "admin"), 0)
        rows = [a for a in store.audit(200) if a["action"] == "cert.revoke_noop"]
        self.assertTrue(rows)
        detail = json.loads(rows[0]["detail"])
        self.assertEqual(detail["device_id"], "mt-no-certs")
        self.assertEqual(detail["matched"], 0)

    def test_revoke_blocks_verify_and_fills_crl(self):
        code = security.new_pair_code("mt-3b-01")
        out = security.redeem(code, make_csr("mt-3b-01"))
        security.revoke("mt-3b-01", "admin")
        with self.assertRaises(ValueError) as ctx:
            security.verify(out["cert_pem"])
        self.assertIn("吊销", str(ctx.exception))
        crl = security.crl_pem()
        self.assertIn(b"BEGIN X509 CRL", crl)


class CertShapeTest(unittest.TestCase):
    def test_foreign_cert_is_rejected(self):
        store.init_db()
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "rogue")])
        rogue = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(security._now()).not_valid_after(security._now())
            .sign(key, hashes.SHA256())
        )
        with self.assertRaises(Exception):
            security.verify(rogue.public_bytes(serialization.Encoding.PEM).decode())


if __name__ == "__main__":
    unittest.main()


class RenewAuthorizationTest(unittest.TestCase):
    """续签以前只校验共享摄取令牌，device_id 由调用方给 —— 等于发证书给任意人。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from edge.main import app

        store.init_db()
        store.upsert_device("mt-renew-target", "续签目标", "health", "orpi 1.4.2", [83])
        cls.client = TestClient(app)

    def test_device_token_alone_cannot_renew(self):
        from unittest import mock

        from edge import config

        with mock.patch.object(config, "ADMIN_TOKEN", "admin-for-test"):
            r = self.client.post("/api/v1/devices/mt-renew-target/renew",
                                 json={"csr": make_csr("mt-renew-target")},
                                 headers={"Authorization": "Bearer device-token"})
        self.assertEqual(r.status_code, 401, r.text)

    def test_admin_token_can_renew(self):
        from unittest import mock

        from edge import config

        with mock.patch.object(config, "ADMIN_TOKEN", "admin-for-test"):
            r = self.client.post("/api/v1/devices/mt-renew-target/renew",
                                 json={"csr": make_csr("mt-renew-target")},
                                 headers={"Authorization": "Bearer admin-for-test"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("cert_pem", r.json())


if __name__ == "__main__":
    unittest.main()
