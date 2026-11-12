#!/usr/bin/env bash
# 启动边节点管理台（Qt 6.5.3 QML）。
#   EDGE_API=http://127.0.0.1:8001 ./run.sh
set -euo pipefail
cd "$(dirname "$0")/../.."          # 边仓库根目录
export QML_XHR_ALLOW_FILE_READ=1    # QML 从本地文件加载时允许 XHR 访问边 API
exec /opt/Qt/6.5.3/gcc_64/bin/qml tools/edge-manager/EdgeManager.qml -- --api "${EDGE_API:-http://127.0.0.1:8001}"
