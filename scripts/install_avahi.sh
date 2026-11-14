#!/usr/bin/env bash
# 把 _orpi-edge._tcp 的广播交给宿主 Avahi。
# 容器没有 host 网络，python-zeroconf 广播的是容器 IP，端拿不到。
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
EDGE_ID=${EDGE_ID:-$(grep -h '^EDGE_ID=' deploy/edge.env 2>/dev/null | cut -d= -f2- || true)}
EDGE_ID=${EDGE_ID:-edge-lab-01}
PORT=${EDGE_PORT:-8001}
CA=${EDGE_CA_CERT:-docker/mosquitto/certs/ca.crt}

if [ ! -f "$CA" ]; then
  echo "找不到 CA 证书：$CA；先跑 scripts/make_broker_cert.py" >&2
  exit 1
fi
FP=$(openssl x509 -in "$CA" -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f' | cut -c1-16)

OUT=/etc/avahi/services/orpi-edge.service
sed -e "s|@EDGE_ID@|$EDGE_ID|" -e "s|@PORT@|$PORT|" -e "s|@CA_FP@|$FP|" \
  "$ROOT/deploy/avahi/orpi-edge.service.tmpl" | sudo tee "$OUT" >/dev/null
sudo systemctl restart avahi-daemon
echo "已发布 _orpi-edge._tcp（id=$EDGE_ID, port=$PORT, ca_fp=$FP）"
echo "端侧可以这样验证：avahi-browse -rt _orpi-edge._tcp"
