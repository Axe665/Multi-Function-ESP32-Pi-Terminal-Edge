#!/usr/bin/env bash
# 宿主侧依赖自检：Avahi（mDNS）与 chrony（NTP），部署后跑（文档 §5.1 / §13.2）。
# 容器里的 mDNS 由 compose 负责，这里查的是宿主机；不在容器里跑。
set -uo pipefail

fail=0
ok() { printf '  [OK]   %s\n' "$1"; }
bad() { printf '  [FAIL] %s\n' "$1"; fail=1; }

for svc in avahi-daemon chrony; do
  if systemctl is-active --quiet "$svc"; then
    ok "$svc active"
  else
    bad "$svc 未运行（systemctl enable --now $svc）"
  fi
done

if command -v chronyc >/dev/null; then
  if chronyc tracking >/dev/null 2>&1; then
    ok "chronyc tracking 可用"
  else
    bad "chronyc tracking 失败；检查 /etc/chrony/chrony.conf"
  fi
fi

[ "$fail" = 0 ] && echo "宿主侧依赖齐全" || echo "宿主侧依赖不完整，先装 Avahi 与 chrony"
exit "$fail"
