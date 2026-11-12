#!/usr/bin/env python3
"""边节点启动提示：小弹窗列出网页入口（本机 + 局域网），并管理边服务。

- 点击网址行「打开」直接跳浏览器
- 「开机自启」切换三个 systemd user 服务的 enable 状态
- 「关闭所有边服务」停掉 edge-node / edge-web / edge-mqtt
- 窗口可缩放/最大化，布局用 pack 自适应，全屏时内容居中铺开
只依赖标准库 tkinter，不引入 Qt。
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import webbrowser
import tkinter as tk

WEB_PORT = 5173
API_PORT = 8001
SERVICES = ("edge-node", "edge-web", "edge-mqtt")

# 与网页 web/src/styles/m3.css 的亮色 token 对齐（绿色种子）
BG = "#f5f7f3"          # surface-container-high（窗口底）
CARD = "#ffffff"        # card-bg
INK = "#1a1c18"         # on-surface
DIM = "#43483e"         # on-surface-variant
ACCENT = "#386a20"      # primary
ON_ACCENT = "#ffffff"   # on-primary
ACCENT_HOVER = "#4a7a2e"
DANGER = "#ba1a1a"      # error
ON_DANGER = "#ffffff"
DANGER_HOVER = "#9e1616"
OUTLINE = "#c3c8bb"     # outline-variant


def systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def service_active(name: str) -> bool:
    return systemctl("is-active", f"{name}.service").stdout.strip() == "active"


def autostart_enabled() -> bool:
    return systemctl("is-enabled", "edge-node.service").stdout.strip() == "enabled"


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def lan_ips() -> list[str]:
    ips: list[str] = []
    try:
        out = subprocess.check_output(["ip", "-4", "addr"], text=True)
    except Exception:  # noqa: BLE001
        return ips
    for line in out.splitlines():
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", line)
        if not m:
            continue
        ip = m.group(1)
        if ip.startswith(("127.", "198.18.", "172.17.", "172.18.")):
            continue
        ips.append(ip)
    return ips


def open_url(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        subprocess.Popen(["xdg-open", url])


def center(window: tk.Tk, width: int, height: int) -> None:
    window.update_idletasks()
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    window.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 2}")


def main() -> int:
    root = tk.Tk()
    root.title("边节点")
    root.configure(bg=BG)
    root.minsize(560, 420)
    root.geometry("720x520")
    center(root, 720, 520)

    card = tk.Frame(root, bg=CARD, highlightbackground=OUTLINE, highlightthickness=1)
    card.pack(fill="both", expand=True, padx=16, pady=16)

    header = tk.Frame(card, bg=CARD)
    header.pack(fill="x", padx=24, pady=(20, 0))
    tk.Label(header, text="边节点已启动", bg=CARD, fg=INK,
             font=("Noto Sans CJK SC", 20, "bold")).pack(side="left")
    status = tk.Label(header, text="", bg=CARD, fg=DIM, anchor="e",
                      font=("Noto Sans CJK SC", 11))
    status.pack(side="right")

    entries_frame = tk.Frame(card, bg=CARD)
    entries_frame.pack(fill="both", expand=True, padx=24, pady=(20, 0))

    busy = {"value": False}
    start_btn = tk.Button()
    stop_btn = tk.Button()
    auto_btn = tk.Button()

    def rebuild_entries() -> None:
        for child in entries_frame.winfo_children():
            child.destroy()
        web_up = port_open(WEB_PORT)
        entries: list[tuple[str, str]] = []
        if web_up:
            entries.append(("本机", f"http://localhost:{WEB_PORT}"))
            for ip in lan_ips():
                entries.append(("局域网", f"http://{ip}:{WEB_PORT}"))
        if not entries:
            tk.Label(entries_frame, text="网页服务未运行（edge-web.service）",
                     bg=CARD, fg=DANGER, font=("Noto Sans CJK SC", 12)).pack(anchor="w", pady=8)
            return
        for label, url in entries[:3]:
            row = tk.Frame(entries_frame, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=CARD, fg=DIM, width=7, anchor="w",
                     font=("Noto Sans CJK SC", 11)).pack(side="left")
            tk.Label(row, text=url, bg=CARD, fg=ACCENT,
                     font=("Noto Sans CJK SC", 12)).pack(side="left", padx=(6, 12))
            tk.Button(row, text="打开", command=lambda u=url: open_url(u),
                      bg=ACCENT, fg=ON_ACCENT, activebackground=ACCENT_HOVER,
                      relief="flat", bd=0, padx=16, pady=4,
                      font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2").pack(side="right")

    def refresh() -> None:
        active = [s for s in SERVICES if service_active(s)]
        if active:
            status.config(text="服务：" + " / ".join(active), fg=DIM)
        else:
            status.config(text="服务未运行（点「启动边服务」）", fg=DANGER)
        auto_btn.config(text=f"开机自启：{'开' if autostart_enabled() else '关'}",
                        fg=(ACCENT if autostart_enabled() else DIM))
        rebuild_entries()

    def _finish() -> None:
        busy["value"] = False
        start_btn.config(state="normal")
        stop_btn.config(state="normal")
        refresh()

    def _wait_state(expect_active: bool, deadline_ms: int) -> None:
        # --no-block 立即返回，服务真正起/停要几秒：轮询到期望状态或超时再解除。
        active = any(service_active(s) for s in SERVICES)
        if active == expect_active or deadline_ms <= 0:
            _finish()
        else:
            root.after(1200, lambda: _wait_state(expect_active, deadline_ms - 1200))

    def _set_busy(text: str) -> None:
        busy["value"] = True
        status.config(text=text, fg=ACCENT)
        start_btn.config(state="disabled")
        stop_btn.config(state="disabled")

    def stop_all() -> None:
        if busy["value"]:
            return
        _set_busy("正在关闭边服务…")
        systemctl("--no-block", "stop", *[f"{s}.service" for s in SERVICES])
        root.after(1000, lambda: _wait_state(False, 12000))

    def start_all() -> None:
        if busy["value"]:
            return
        _set_busy("正在启动边服务…（edge-node 加载模型约 5-10 秒）")
        systemctl("--no-block", "start", *[f"{s}.service" for s in SERVICES])
        root.after(1000, lambda: _wait_state(True, 20000))

    def toggle_autostart() -> None:
        args = [f"{s}.service" for s in SERVICES]
        if autostart_enabled():
            systemctl("disable", *args)
        else:
            systemctl("enable", *args)
        refresh()

    footer = tk.Label(card, text=f"边 API：127.0.0.1:{API_PORT} · 服务自启由 systemd user 管理",
                      bg=CARD, fg=DIM, font=("Noto Sans CJK SC", 10))
    footer.pack(side="bottom", anchor="w", padx=24, pady=(0, 16))

    actions = tk.Frame(card, bg=CARD)
    actions.pack(side="bottom", fill="x", padx=24, pady=(16, 10))

    start_btn = tk.Button(actions, text="启动边服务", command=start_all,
                          bg=ACCENT, fg=ON_ACCENT, activebackground=ACCENT_HOVER,
                          relief="flat", bd=0, padx=14, pady=6,
                          font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2")
    start_btn.pack(side="left")

    stop_btn = tk.Button(actions, text="关闭所有边服务", command=stop_all,
                         bg=DANGER, fg=ON_DANGER, activebackground=DANGER_HOVER,
                         relief="flat", bd=0, padx=14, pady=6,
                         font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2")
    stop_btn.pack(side="left", padx=(10, 0))

    auto_btn = tk.Button(actions, text="开机自启：开", command=toggle_autostart,
                         bg=CARD, fg=ACCENT, activebackground=CARD,
                         relief="flat", bd=0, padx=10, pady=6,
                         font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2")
    auto_btn.pack(side="left", padx=(10, 0))

    tk.Button(actions, text="关闭", command=root.destroy,
              bg=CARD, fg=DIM, activebackground=CARD,
              relief="flat", bd=0, padx=12, pady=6,
              font=("Noto Sans CJK SC", 11), cursor="hand2").pack(side="right")

    refresh()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
