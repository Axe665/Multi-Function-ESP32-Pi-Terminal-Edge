#!/usr/bin/env bash
# 起服务控制台。已经在跑就只把浏览器叫出来。
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
PORT="$(python3 -c 'from service_launch import config; print(config.load().port)')"
URL="http://127.0.0.1:${PORT}/"

up() { curl -sf -o /dev/null --max-time 1 "$URL" ; }

if ! up; then
  mkdir -p "$ROOT/.run"
  nohup python3 -m service_launch >>"$ROOT/.run/console.log" 2>&1 &
  for _ in $(seq 1 40); do
    up && break
    sleep 0.25
  done
fi

if ! up; then
  echo "控制台没起来，看日志：$ROOT/.run/console.log" >&2
  tail -n 20 "$ROOT/.run/console.log" >&2 || true
  exit 1
fi

echo "$URL"
if [ -n "${DISPLAY:-}" ] && command -v xdg-open >/dev/null; then
  xdg-open "$URL" >/dev/null 2>&1 &
fi
