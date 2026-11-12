#!/usr/bin/env python3
"""边节点启动提示：小弹窗列出网页入口（本机 + 局域网），并管理边服务。

- 点击网址行「打开」直接跳浏览器
- 「开机自启」切换三个 systemd user 服务的 enable 状态
- 「关闭所有边服务」停掉 edge-node / edge-web / edge-mqtt
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

BG = "#0B141C"
CARD = "#16242F"
INK = "#E1ECF2"
DIM = "#A9BCC8"
ACCENT = "#8CD8F5"
ON_ACCENT = "#003544"
DANGER = "#FFB4AB"
OUTLINE = "#3A4F5E"


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
    root.resizable(False, False)
    width, height = 660, 500

    card = tk.Frame(root, bg=CARD, highlightbackground=OUTLINE, highlightthickness=1)
    card.place(x=16, y=16, width=width - 32, height=height - 32)

    title = tk.Label(card, text="边节点已启动", bg=CARD, fg=INK,
                     font=("Noto Sans CJK SC", 20, "bold"))
    title.place(x=24, y=20)

    status = tk.Label(card, text="", bg=CARD, fg=DIM, anchor="w",
                      font=("Noto Sans CJK SC", 11), width=52)
    status.place(x=24, y=64)

    entries_frame = tk.Frame(card, bg=CARD)
    entries_frame.place(x=24, y=104, width=width - 80, height=190)

    def rebuild_entries() -> None:
        for child in entries_frame.winfo_children():
            child.destroy()
        web_up = port_open(WEB_PORT)
        entries: list[tuple[str, str]] = []
        if web_up:
            entries.append(("本机", f"http://localhost:{WEB_PORT}"))
            for ip in lan_ips():
                entries.append(("局域网", f"http://{ip}:{WEB_PORT}"))
        y = 0
        for label, url in entries[:3]:
            row = tk.Frame(entries_frame, bg=CARD)
            row.place(x=0, y=y, width=width - 80)
            tk.Label(row, text=label, bg=CARD, fg=DIM, width=7, anchor="w",
                     font=("Noto Sans CJK SC", 11)).pack(side="left")
            tk.Label(row, text=url, bg=CARD, fg=ACCENT,
                     font=("Noto Sans CJK SC", 12)).pack(side="left", padx=(6, 12))
            tk.Button(row, text="打开", command=lambda u=url: open_url(u),
                      bg=ACCENT, fg=ON_ACCENT, activebackground="#6FC3DE",
                      relief="flat", bd=0, padx=16, pady=4,
                      font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2").pack(side="right")
            y += 56
        if not entries:
            tk.Label(entries_frame, text="网页服务未运行（edge-web.service）",
                     bg=CARD, fg=DANGER, font=("Noto Sans CJK SC", 12)).place(x=0, y=8)

    def refresh() -> None:
        active = [s for s in SERVICES if service_active(s)]
        if active:
            status.config(text=f"服务：" + " / ".join(active), fg=DIM)
        else:
            status.config(text="服务未运行（点「启动边服务」）", fg=DANGER)
        auto_btn.config(text=f"开机自启：{'开' if autostart_enabled() else '关'}",
                        fg=(ACCENT if autostart_enabled() else DIM))
        web_up = port_open(WEB_PORT)
        rebuild_entries()
        return web_up

    def stop_all() -> None:
        systemctl("stop", *[f"{s}.service" for s in SERVICES])
        refresh()

    def start_all() -> None:
        systemctl("start", *[f"{s}.service" for s in SERVICES])
        refresh()

    def toggle_autostart() -> None:
        args = [f"{s}.service" for s in SERVICES]
        if autostart_enabled():
            systemctl("disable", *args)
        else:
            systemctl("enable", *args)
        refresh()

    actions = tk.Frame(card, bg=CARD)
    actions.place(x=24, y=height - 150, width=width - 80)

    start_btn = tk.Button(actions, text="启动边服务", command=start_all,
                          bg=ACCENT, fg=ON_ACCENT, activebackground="#6FC3DE",
                          relief="flat", bd=0, padx=14, pady=6,
                          font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2")
    start_btn.pack(side="left")

    stop_btn = tk.Button(actions, text="关闭所有边服务", command=stop_all,
                         bg=DANGER, fg="#3A1414", activebackground="#E29A92",
                         relief="flat", bd=0, padx=14, pady=6,
                         font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2")
    stop_btn.pack(side="left", padx=(10, 0))

    auto_btn = tk.Button(actions, text="开机自启：开", command=toggle_autostart,
                         bg=CARD, fg=ACCENT, activebackground=CARD,
                         relief="flat", bd=0, padx=10, pady=6,
                         font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2")
    auto_btn.pack(side="left", padx=(10, 0))

    close_btn = tk.Button(actions, text="关闭", command=root.destroy,
                          bg=CARD, fg=DIM, activebackground=CARD,
                          relief="flat", bd=0, padx=12, pady=6,
                          font=("Noto Sans CJK SC", 11), cursor="hand2")
    close_btn.pack(side="right")

    tk.Label(card, text=f"边 API：127.0.0.1:{API_PORT} · 服务自启由 systemd user 管理",
             bg=CARD, fg=DIM, font=("Noto Sans CJK SC", 10)).place(x=24, y=height - 74)

    refresh()
    center(root, width, height)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
