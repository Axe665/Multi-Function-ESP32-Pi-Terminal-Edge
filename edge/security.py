"""边 CA：签发设备证书、吊销、配对码。

只有边持有 CA 私钥（data/ca/edge-ca.key，0600）。设备拿到的是链路证书，
不是 CA；云端另有一套 CA，两边互不签发。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from . import config, store

CA_DIR = Path(config.DATA_DIR) / "ca"
CA_KEY = CA_DIR / "edge-ca.key"
CA_CRT = CA_DIR / "edge-ca.crt"
DEVICE_DAYS = 365
PAIR_TTL_MS = 10 * 60 * 1000
PAIR_MAX_ATTEMPTS = 5
PAIR_LOCK_MS = 10 * 60 * 1000


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def ensure_ca() -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    CA_DIR.mkdir(parents=True, exist_ok=True)
    if CA_KEY.exists() and CA_CRT.exists():
        key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
        crt = x509.load_pem_x509_certificate(CA_CRT.read_bytes())
        return crt, key  # type: ignore[return-value]

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"{config.EDGE_ID} edge-ca"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Modular Terminal"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "mt-edge"),
    ])
    crt = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - dt.timedelta(minutes=5))
        .not_valid_after(_now() + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                          content_commitment=False, key_encipherment=False,
                          data_encipherment=False, key_agreement=False,
                          encipher_only=False, decipher_only=False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    CA_KEY.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    CA_KEY.chmod(0o600)
    CA_CRT.write_bytes(crt.public_bytes(serialization.Encoding.PEM))
    return crt, key


def ca_fingerprint() -> str:
    crt, _ = ensure_ca()
    return "sha256:" + hashlib.sha256(
        crt.public_bytes(serialization.Encoding.DER)).hexdigest()[:32]


def _load_csr(pem: str) -> x509.CertificateSigningRequest:
    csr = x509.load_pem_x509_csr(pem.encode())
    if not csr.is_signature_valid:
        raise ValueError("CSR 签名无效")
    return csr


def issue(device_id: str, csr_pem: str) -> dict[str, Any]:
    """给某台设备签发 365 天证书。CN=device_id，OU=mt-device。"""
    ca_crt, ca_key = ensure_ca()
    csr = _load_csr(csr_pem)
    pubkey_fp = hashlib.sha256(
        csr.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()[:16]

    now = _now()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, device_id),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "mt-device"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Modular Terminal"),
        ]))
        .issuer_name(ca_crt.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=DEVICE_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(digital_signature=True, key_encipherment=True,
                          content_commitment=False, data_encipherment=False,
                          key_agreement=False, key_cert_sign=False, crl_sign=False,
                          encipher_only=False, decipher_only=False),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    serial = f"{cert.serial_number:x}"
    with store.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO device_certs(serial, device_id, pubkey_fp, issued_at, expires_at)
               VALUES(?,?,?,?,?)""",
            (serial, device_id, pubkey_fp, store.now_ms(),
             int(cert.not_valid_after_utc.timestamp() * 1000)))
        conn.execute("UPDATE devices SET cert_fp=? WHERE device_id=?", (pubkey_fp, device_id))
    return {"cert_pem": pem, "serial": serial, "device_id": device_id,
            "expires_at": int(cert.not_valid_after_utc.timestamp() * 1000),
            "pubkey_fp": pubkey_fp}


def issue_server(name: str) -> dict[str, Any]:
    """给 broker 签一张 serverAuth 证书（mosquitto 的 certfile）。"""
    ca_crt, ca_key = ensure_ca()
    key = ec.generate_private_key(ec.SECP256R1())
    now = _now()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, name),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "mt-broker"),
        ]))
        .issuer_name(ca_crt.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
                       critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name), x509.DNSName("localhost")]),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return {
        "cert_pem": cert.public_bytes(serialization.Encoding.PEM).decode(),
        "key_pem": key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode(),
        "ca_pem": ca_crt.public_bytes(serialization.Encoding.PEM).decode(),
    }


def verify(cert_pem: str) -> dict[str, Any]:
    """校验设备证书：签名、有效期、吊销状态。失败抛 ValueError。"""
    ca_crt, _ = ensure_ca()
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    cert.verify_directly_issued_by(ca_crt)
    now = _now()
    if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
        raise ValueError("证书已过期")
    device_id = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    ou = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)
    if not ou or ou[0].value != "mt-device":
        raise ValueError("不是设备证书")
    if store.is_revoked(f"{cert.serial_number:x}"):
        raise ValueError("证书已被吊销")
    return {"device_id": device_id, "serial": f"{cert.serial_number:x}"}


def revoke(device_id: str, reason: str = "unspecified") -> int:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT serial FROM device_certs WHERE device_id=?", (device_id,)).fetchall()
    n = 0
    for r in rows:
        store.revoke_serial(r["serial"], device_id, reason)
        n += 1
    return n


def crl_pem() -> bytes:
    ca_crt, ca_key = ensure_ca()
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(ca_crt.subject)
        .last_update(_now())
        .next_update(_now() + dt.timedelta(days=7))
    )
    for row in store.revoked():
        entry = (
            x509.RevokedCertificateBuilder()
            .serial_number(int(row["serial"], 16))
            .revocation_date(_now() - dt.timedelta(days=1))
            .add_extension(x509.CRLReason(x509.ReasonFlags.unspecified), critical=False)
            .build()
        )
        builder = builder.add_revoked_certificate(entry)
    crl = builder.sign(ca_key, hashes.SHA256())
    return crl.public_bytes(serialization.Encoding.PEM)


# ---------------------------------------------------------------- 配对

def new_pair_code(device_id: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    store.create_pair_code(code, device_id, PAIR_TTL_MS)
    return code


def redeem(code: str, csr_pem: str) -> dict[str, Any]:
    row = store.pair_code(code)
    if not row:
        raise ValueError("配对码不存在")
    now = store.now_ms()
    if row["used_at"]:
        raise ValueError("配对码已使用过")
    if row["expires_at"] < now:
        raise ValueError("配对码已过期")
    if row["locked_until"] and row["locked_until"] > now:
        raise ValueError("失败次数过多，请 10 分钟后再试")

    # 配对码绑定公钥指纹：同一码换一把钥匙来兑换就会被拒
    fp = _csr_fingerprint(csr_pem)
    if row["pubkey_fp"] and row["pubkey_fp"] != fp:
        store.pair_failure(code, PAIR_MAX_ATTEMPTS, PAIR_LOCK_MS)
        raise ValueError("配对码与这把公钥不匹配")

    if not store.mark_pair_used(code):
        store.pair_failure(code, PAIR_MAX_ATTEMPTS, PAIR_LOCK_MS)
        raise ValueError("配对码已被占用")
    return issue(row["device_id"], csr_pem)


def _csr_fingerprint(csr_pem: str) -> str:
    csr = _load_csr(csr_pem)
    return hashlib.sha256(
        csr.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()[:16]


def device_certs() -> list[dict[str, Any]]:
    """证书清单，带剩余天数 —— 到期前 30 天要提醒续期。"""
    now = store.now_ms()
    out = []
    for row in store.device_certs():
        days = max(0, (row["expires_at"] - now) // 86_400_000)
        out.append({**row, "days_left": int(days), "expiring": days <= RENEW_BEFORE_DAYS})
    return out


RENEW_BEFORE_DAYS = 30


def renew(device_id: str, csr_pem: str) -> dict[str, Any]:
    """设备换新证书。旧证书不吊销：交接期两条链路都能连，到期自然失效。"""
    if not store.device(device_id):
        raise ValueError("设备不存在")
    out = issue(device_id, csr_pem)
    store.audit_action("device", "cert.renew", device_id, {"serial": out["serial"]})
    return out


def expiring(days: int = RENEW_BEFORE_DAYS) -> list[dict[str, Any]]:
    return [c for c in device_certs() if c["days_left"] <= days]
