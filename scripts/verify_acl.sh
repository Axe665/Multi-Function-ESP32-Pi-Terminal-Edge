#!/usr/bin/env bash
# 文档 §8.4：设备证书只能读写自己的 orpi/v1/<CN>/*。
# 用边 CA 现签一张临时设备证书，连真 broker 实测：自己的前缀通，别人的前缀被拒。
# 用法：./scripts/verify_acl.sh [device_id]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CID=${1:-acl-check}
OTHER=${OTHER:-mt-3b-01}
API=${API:-mt-edge-api}
MQTT=${MQTT:-mt-mqtt}
docker="${DOCKER:-docker}"

CERTS=$ROOT/docker/mosquitto/certs

# 前提：broker 的 ca.crt 必须就是边正在用的那张 CA，否则新签的设备证书一律被拒
ca_broker=$(cut -d' ' -f1 <<<"$(sha256sum "$CERTS/ca.crt")")
ca_edge=$($docker exec "$API" python -c "import hashlib,pathlib;from edge import config;print(hashlib.sha256((pathlib.Path(config.DATA_DIR)/'ca'/'edge-ca.crt').read_bytes()).hexdigest())")
if [ "$ca_broker" != "$ca_edge" ]; then
  echo "[FAIL] broker CA 与边 CA 不是同一套，签出来的设备证书连不上"
  echo "       修：$docker cp $API:/app/data/ca/. data/ca/ && python3 scripts/make_broker_cert.py mqtt.edge.local && $docker restart $MQTT"
  exit 1
fi

# 前提：证书目录要对 api 容器（uid 10001）可写，否则临时证书放不进去、吊销也写不了 CRL
if ! $docker exec "$API" sh -c ': >> /app/certs/crl.pem' 2>/dev/null; then
  echo "[FAIL] api 容器写不了证书目录/吊销列表"
  echo "       修：chmod 777 docker/mosquitto/certs && chmod 666 docker/mosquitto/certs/crl.pem"
  exit 1
fi

cleanup() {
  $docker exec "$API" python -c "
from edge import store
with store.connect() as c:
    c.execute('DELETE FROM device_certs WHERE device_id=?', ('$CID',))
" >/dev/null 2>&1 || true
  rm -f "$CERTS/$CID.crt" "$CERTS/$CID.key"
}
trap cleanup EXIT

# 用 edge.security.issue 签（和真实配对走同一条路径），CN=device_id
$docker exec -i "$API" python - "$CID" <<'PY'
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from edge import security
cid = sys.argv[1]
key = ec.generate_private_key(ec.SECP256R1())
csr = (x509.CertificateSigningRequestBuilder()
       .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cid)]))
       .sign(key, hashes.SHA256()))
b = security.issue(cid, csr.public_bytes(serialization.Encoding.PEM).decode())
open(f"/app/certs/{cid}.crt", "w").write(b["cert_pem"])
open(f"/app/certs/{cid}.key", "w").write(key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()).decode())
PY

$docker exec -i "$MQTT" sh -s -- "$CID" "$OTHER" <<'SH'
CID=$1; OTHER=$2
A="--insecure -h 127.0.0.1 -p 8883 --cafile /mosquitto/certs/ca.crt --cert /mosquitto/certs/$CID.crt --key /mosquitto/certs/$CID.key"
E="--insecure -h 127.0.0.1 -p 8883 --cafile /mosquitto/certs/ca.crt --cert /mosquitto/certs/edge.crt --key /mosquitto/certs/edge.key"
bad=0
ok() { echo "[PASS] $1"; }
no() { echo "[FAIL] $1"; bad=1; }

mosquitto_pub $A -V mqttv5 -t "orpi/v1/$CID/telemetry" -m '{"probe":1}' -q 1 >/tmp/acl1 2>&1 || true
grep -q "Not authorized" /tmp/acl1 && no "自己的遥测发不出去" || ok "自己的遥测能发"

mosquitto_sub $A -V mqttv5 -t "orpi/v1/$CID/cmd" -C 1 -W 5 >/tmp/acl2 2>&1 &
sub=$!
sleep 1
mosquitto_pub $E -V mqttv5 -t "orpi/v1/$CID/cmd" -m '{"probe":1}' -q 1 >/dev/null 2>&1 || true
wait $sub || true
grep -q probe /tmp/acl2 && ok "自己的 cmd 能收（边可下发）" || no "自己的 cmd 收不到"

mosquitto_pub $A -V mqttv5 -t "orpi/v1/$OTHER/telemetry" -m '{"probe":1}' -q 1 >/tmp/acl3 2>&1 || true
grep -q "Not authorized" /tmp/acl3 && ok "别人的遥测被拒" || no "别人的遥测没被拒"

timeout 4 mosquitto_sub $A -V mqttv5 -t "orpi/v1/$OTHER/telemetry" -C 1 >/tmp/acl4 2>&1 || true
[ -s /tmp/acl4 ] && no "能读别人的遥测" || ok "读不到别人的遥测"

timeout 4 mosquitto_sub $A -V mqttv5 -t 'orpi/v1/#' -C 1 >/tmp/acl5 2>&1 || true
[ -s /tmp/acl5 ] && no "通配订阅能读全量" || ok "通配订阅读不到东西"

exit $bad
SH
