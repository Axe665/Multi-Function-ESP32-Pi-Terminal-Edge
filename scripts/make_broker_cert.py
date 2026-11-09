#!/usr/bin/env python3
"""给 mosquitto 签一张 broker 证书，写进 docker/mosquitto/certs/。

用法：python3 scripts/make_broker_cert.py [broker 主机名]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge import security  # noqa: E402


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "mqtt.edge.local"
    out = ROOT / "docker" / "mosquitto" / "certs"
    out.mkdir(parents=True, exist_ok=True)
    bundle = security.issue_server(name)
    (out / "ca.crt").write_text(bundle["ca_pem"])
    (out / "broker.crt").write_text(bundle["cert_pem"])
    (out / "broker.key").write_text(bundle["key_pem"])
    (out / "broker.key").chmod(0o600)
    print(f"已签发 {name} 的 broker 证书 → {out}")


if __name__ == "__main__":
    main()
