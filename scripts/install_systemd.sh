#!/usr/bin/env bash
# 非容器部署：把边节点三件套装成 systemd user 服务并开机自启。
# 容器部署（文档 §5.1 的 Compose 四服务）不需要这个脚本。
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
UNIT_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
NPM=$(command -v npm || true)
if [ -z "$NPM" ]; then
  echo "找不到 npm；网页服务会装不上。先装 Node 或改用容器部署。" >&2
fi
mkdir -p "$UNIT_DIR"
# 首次安装：从示例生成 deploy/edge.env（已存在则不覆盖，避免冲掉云/MQTT 配置）
if [ ! -f "$ROOT/deploy/edge.env" ]; then
  sed "s|@ROOT@|$ROOT|g" "$ROOT/deploy/edge.env.example" > "$ROOT/deploy/edge.env"
  echo "已生成 $ROOT/deploy/edge.env（按需修改）"
fi
for unit in edge-node edge-web edge-mqtt; do
  sed "s|@ROOT@|$ROOT|g; s|@NPM@|$NPM|g; s|@NPMDIR@|$(dirname "${NPM:-/usr/bin/npm}")|g" \
    "$ROOT/deploy/systemd/$unit.service.in" > "$UNIT_DIR/$unit.service"
done
systemctl --user daemon-reload
systemctl --user enable --now edge-node.service edge-web.service edge-mqtt.service
systemctl --user --no-pager status edge-node.service edge-web.service edge-mqtt.service | grep -E "^●|Active:"

# 应用菜单图标：名字就叫「边」
APP_DIR=${XDG_DATA_HOME:-$HOME/.local/share}/applications
ICON_DIR=${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps
mkdir -p "$APP_DIR" "$ICON_DIR"
cp "$ROOT/deploy/icons/edge.svg" "$ICON_DIR/edge.svg"
sed "s|@ROOT@|$ROOT|g" "$ROOT/deploy/edge.desktop.in" > "$APP_DIR/edge.desktop"
chmod 644 "$APP_DIR/edge.desktop"
# 桌面快捷方式（存在桌面目录时也放一份，方便直接双击）
for desk in "$HOME/Desktop" "$HOME/桌面"; do
  if [ -d "$desk" ]; then
    cp "$APP_DIR/edge.desktop" "$desk/edge.desktop"
    chmod +x "$desk/edge.desktop"
    echo "桌面快捷方式：$desk/edge.desktop"
  fi
done
echo "应用菜单图标：$APP_DIR/edge.desktop（名称为「边」）"
echo "已安装：$UNIT_DIR/{edge-node,edge-web,edge-mqtt}.service"
