#!/usr/bin/env bash
# 安装 / 卸载“CRL 变更后重载 broker”的 systemd user timer。
# 用法：./scripts/install_crl_reload.sh [--uninstall]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="$UNIT_DIR/mt-edge-crl-reload.service"
TIMER="$UNIT_DIR/mt-edge-crl-reload.timer"

if [ "${1:-}" = "--uninstall" ]; then
  systemctl --user disable --now mt-edge-crl-reload.timer 2>/dev/null || true
  rm -f "$SERVICE" "$TIMER"
  systemctl --user daemon-reload
  echo "已卸载 mt-edge-crl-reload.timer"
  exit 0
fi

mkdir -p "$UNIT_DIR"
cat > "$SERVICE" <<EOF
[Unit]
Description=Reload mosquitto CRL after edge revoke

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=$ROOT/scripts/reload_crl.sh
EOF

cat > "$TIMER" <<'EOF'
[Unit]
Description=Check edge CRL every 5s

[Timer]
OnBootSec=10s
OnUnitActiveSec=5s
Unit=mt-edge-crl-reload.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now mt-edge-crl-reload.timer
echo "已安装 mt-edge-crl-reload.timer（每 5 s 检查 $ROOT/docker/mosquitto/certs/crl.pem）"
echo "当前用户需要在 docker 组里；否则用 sudo 安装或把脚本改成 sudo docker。"
