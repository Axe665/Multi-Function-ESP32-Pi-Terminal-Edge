#!/usr/bin/env bash
# 吊销后让 broker 立刻重读 CRL（文档 §5.7.6）。
# 由 systemd timer 每 5 s 调一次；只有 crl.pem 内容变了才发 SIGHUP。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRL="${EDGE_CRL_PATH:-$ROOT/docker/mosquitto/certs/crl.pem}"
CONTAINER="${EDGE_MQTT_CONTAINER:-mt-mqtt}"
STAMP="${XDG_RUNTIME_DIR:-/tmp}/mt-edge-crl.sha"

[ -f "$CRL" ] || exit 0
SUM="$(sha256sum "$CRL" | cut -d' ' -f1)"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$SUM" ]; then
  exit 0
fi
docker kill -s HUP "$CONTAINER" >/dev/null
printf '%s\n' "$SUM" > "$STAMP"
