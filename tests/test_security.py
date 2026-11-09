"""CA / 配对码 / 证书吊销。全部离线，不碰网络。"""
from __future__ import annotations

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
