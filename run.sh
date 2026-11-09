#!/usr/bin/env bash
# 本地跑起来：./run.sh  （首次会自动写 7 天演示数据）
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f data/edge.db ]; then
  echo "没有数据库，先生成 7 天演示数据…"
  python3 -m edge.seed
fi
exec python3 -m uvicorn edge.main:app --host 0.0.0.0 --port "${PORT:-8001}"
