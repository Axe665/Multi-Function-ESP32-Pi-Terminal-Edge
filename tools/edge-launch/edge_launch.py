#!/usr/bin/env python3
"""边节点启动提示：小弹窗列出网页入口（本机 + 局域网），点击直接打开。

部署后由 autostart 拉起；只依赖标准库 tkinter，不引入 Qt。
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

BG = "#0B141C"
CARD = "#16242F"
INK = "#E1ECF2"
DIM = "#A9BCC8"
ACCENT = "#8CD8F5"
ON_ACCENT = "#003544"
OUTLINE = "#3A4F5E"


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
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


def main() -> int:
    web_up = port_open(WEB_PORT)
    api_up = port_open(API_PORT)

    root = tk.Tk()
    root.title("边节点")
    root.configure(bg=BG)
    root.resizable(False, False)
    width, height = 660, 430

    card = tk.Frame(root, bg=CARD, highlightbackground=OUTLINE, highlightthickness=1)
    card.place(x=16, y=16, width=width - 32, height=height - 32)

    tk.Label(card, text="边节点已启动", bg=CARD, fg=INK,
             font=("Noto Sans CJK SC", 20, "bold")).place(x=24, y=20)
    status = "网页服务运行中" if web_up else "网页服务未运行（edge-web.service）"
    tk.Label(card, text=status, bg=CARD, fg=(DIM if web_up else "#FFB4AB"),
             font=("Noto Sans CJK SC", 12)).place(x=24, y=62)

    entries: list[tuple[str, str]] = []
    if web_up:
        entries.append(("本机", f"http://localhost:{WEB_PORT}"))
        for ip in lan_ips():
            entries.append(("局域网", f"http://{ip}:{WEB_PORT}"))

    y = 104
    for label, url in entries[:3]:
        row = tk.Frame(card, bg=CARD)
        row.place(x=20, y=y, width=width - 72)
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
        tk.Label(card, text="先启动 edge-web.service 再打开网页",
                 bg=CARD, fg="#FFB4AB", font=("Noto Sans CJK SC", 12)).place(x=24, y=112)

    tk.Label(card, text="边 API：127.0.0.1:%d" % API_PORT, bg=CARD, fg=DIM,
             font=("Noto Sans CJK SC", 11)).place(x=24, y=height - 108)
    tk.Button(card, text="关闭", command=root.destroy,
              bg=CARD, fg=ACCENT, activebackground=CARD, relief="flat", bd=0,
              font=("Noto Sans CJK SC", 11, "bold"), cursor="hand2").place(
                  x=width - 140, y=height - 112, width=100, height=34)

    center(root, width, height)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
