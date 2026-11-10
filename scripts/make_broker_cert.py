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
    # 容器里的 mosquitto 以 uid 1883 运行，读不到 0600 的私钥；演示证书放 0644
    (out / "crl.pem").write_bytes(security.crl_pem())
    for f in ("ca.crt", "broker.crt", "broker.key", "edge.crt", "edge.key", "crl.pem"):
        (out / f).chmod(0o644)
    # api 容器（uid 10001）要在吊销时重写 crl.pem：目录得能建文件，文件本身也得可写
    (out / "crl.pem").chmod(0o666)
    out.chmod(0o777)
    print(f"已签发 {name} 的 broker 证书与 {edge_id} 的客户端证书 → {out}")


if __name__ == "__main__":
    main()
