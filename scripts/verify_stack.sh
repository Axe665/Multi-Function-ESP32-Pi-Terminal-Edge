#!/usr/bin/env bash
# 验收脚本：跑在 docker/compose.yml 起来之后。
# 检查四服务是否都在、Caddy 的三个入口是否各归其位。
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
ok()   { printf '  [OK]   %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=1; }

echo "== 服务状态 =="
for s in mosquitto ingest api web; do
  state="$(docker compose -f docker/compose.yml ps --format '{{.Service}} {{.State}}' | awk -v s="$s" '$1==s{print $2}')"
  [ "$state" = "running" ] && ok "$s running" || bad "$s ${state:-未启动}"
done

echo "== 入口归属 =="
code() { curl -s -o /dev/null -w '%{http_code}' -m 8 "$@"; }

[ "$(code http://127.0.0.1:8001/api/v1/health)" = "200" ] \
  && ok "web(8001) → api 健康检查" || bad "web(8001) 健康检查不通"

[ "$(code -X POST -H 'content-type: application/json' -d '{}' http://127.0.0.1:8001/api/v1/ingest/telemetry)" = "422" ] \
  && ok "web(8001) → ingest 摄取入口（空载荷应 422）" || bad "摄取入口没转到 ingest"

[ "$(code http://127.0.0.1:8001/api/v1/devices)" = "200" ] \
  && ok "web(8001) → api 设备列表" || bad "设备列表不通"

[ "$(code http://127.0.0.1:8885/api/v1/devices)" = "404" ] \
  && ok "ingest(8885) 不提供查询接口" || bad "ingest 上出现了查询接口"

[ "$(code http://127.0.0.1:8885/api/v1/health)" = "200" ] \
  && ok "ingest(8885) 健康检查" || bad "ingest 健康检查不通"

echo "== 静态前端 =="
curl -s -m 8 http://127.0.0.1:8001/ | grep -qi '<html' \
  && ok "首页 HTML" || bad "首页不是 HTML"

echo "== k 门槛 =="
curl -s -m 8 "http://127.0.0.1:8001/api/v1/overview" | grep -q '"k"' \
  && ok "总览有 k 字段" || bad "总览读不到 k"

echo
[ "$fail" = "0" ] && echo "VERIFY: 全部通过" || { echo "VERIFY: 有失败项"; exit 1; }
