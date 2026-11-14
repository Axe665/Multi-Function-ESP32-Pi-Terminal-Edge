#!/usr/bin/env python3
"""给 mosquitto 签一张 broker 证书，写进 docker/mosquitto/certs/。

用法：python3 scripts/make_broker_cert.py [broker 主机名]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge import security  # noqa: E402


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "mqtt.edge.local"
    out = ROOT / "docker" / "mosquitto" / "certs"
    out.mkdir(parents=True, exist_ok=True)
    bundle = security.issue_server(name, extra_sans=["mosquitto", "mt-mqtt"])
    (out / "ca.crt").write_text(bundle["ca_pem"])
    (out / "broker.crt").write_text(bundle["cert_pem"])
    (out / "broker.key").write_text(bundle["key_pem"])
    (out / "broker.key").chmod(0o600)

    # 边自己也要能连 broker：CN 必须与 ACL 里的用户名一致
    edge_id = os.environ.get("EDGE_ID", "edge-lab-01")
    client = security.issue_edge_client(edge_id)
    (out / "edge.crt").write_text(client["cert_pem"])
    (out / "edge.key").write_text(client["key_pem"])
    (out / "crl.pem").write_bytes(security.crl_pem())
    # 目录 0777 + 私钥 0644 等于把 key 发给同机任何用户。收紧到：目录 0755，
    # 公钥/证书/CRL 0644，边自己的私钥 0600（只有边进程读）。
    for f in ("ca.crt", "broker.crt", "edge.crt", "crl.pem"):
        (out / f).chmod(0o644)
    (out / "edge.key").chmod(0o600)
    # broker.key 例外：mosquitto 以非属主的 uid 运行，0600 会让它读不到私钥。
    # 真要收，就把整个 certs 目录交给 broker 用户（或换 systemd 部署，两边同一用户）。
    (out / "broker.key").chmod(0o644)
    out.chmod(0o755)
    print(f"已签发 {name} 的 broker 证书与 {edge_id} 的客户端证书 → {out}")
    print("    broker.key 保持 0644 供 mosquitto 读；edge.key 已收紧到 0600")


if __name__ == "__main__":
    main()
