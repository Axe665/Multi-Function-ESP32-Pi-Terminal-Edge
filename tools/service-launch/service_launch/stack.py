"""两套后端（docker compose 与原生进程）统一成同一份状态和同一组动作。

只做管道：不判断业务，不缓存状态（除了 compose 服务名，它随文件变）。
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from .config import Config

RUN_DIR = Path(__file__).resolve().parents[3] / ".run"
COMPOSE_TIMEOUT = 120


def _run(args: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, f"找不到命令：{args[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"命令超时（{timeout}s）：{' '.join(args[:3])}"
    return p.returncode, (p.stdout + p.stderr).strip()


def _compose(cfg: Config, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(cfg.compose_file), *args]


def docker_ready(cfg: Config) -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "没装 docker"
    if not cfg.compose_file.exists():
        return False, f"没找到 compose 文件：{cfg.compose_file.name}"
    code, out = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
    if code:
        return False, "docker daemon 没在跑（试试 systemctl start docker）"
    return True, ""


def compose_services(cfg: Config) -> list[str]:
    """compose 文件里声明的服务名，顺序即声明顺序。"""
    code, out = _run(_compose(cfg, "config", "--services"), timeout=40)
    if code:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def compose_ps(cfg: Config) -> dict[str, dict]:
    code, out = _run(_compose(cfg, "ps", "--all", "--format", "json"), timeout=40)
    if code:
        return {}
    rows: dict[str, dict] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows[str(rec.get("Service", ""))] = rec
    return rows


def ports_of(rec: dict) -> str:
    pubs = [
        f"{p['PublishedPort']}" if p["PublishedPort"] == p["TargetPort"]
        else f"{p['PublishedPort']} → {p['TargetPort']}"
        for p in (rec.get("Publishers") or [])
        if p.get("PublishedPort")
    ]
    if pubs:
        return " / ".join(dict.fromkeys(pubs))
    raw = str(rec.get("Ports") or "").split(",")[0].strip()
    return f"内部 {raw}" if raw else ""


def http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


# ---------------------------------------------------------------- 原生进程

def _pid_file(cfg: Config) -> Path:
    return RUN_DIR / f"{cfg.native_service}.pid"


# 自己拉起的子进程要留着句柄，否则退出后会变僵尸、poll 不到
_children: dict[str, subprocess.Popen] = {}


def _alive(pid: int) -> bool:
    """僵尸也算死的。控制台重启后接管旧 PID 时只能查进程表，这里认状态位。"""
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            return fh.read().rsplit(b") ", 1)[-1].split()[0] != b"Z"
    except OSError:
        return False


def native_pid(cfg: Config) -> int:
    child = _children.get(cfg.native_service)
    if child is not None:
        if child.poll() is not None:  # 顺手回收僵尸
            _children.pop(cfg.native_service, None)
            return 0
        return child.pid
    try:
        pid = int(_pid_file(cfg).read_text().strip())
    except (OSError, ValueError):
        return 0
    try:
        os.kill(pid, 0)
    except OSError:
        return 0
    return pid if _alive(pid) else 0


def native_env(cfg: Config, base: dict[str, str] | None = None) -> dict[str, str]:
    """控制台进程的环境 + launcher.toml 里的覆盖，脚本里没写死的默认值才管用。"""
    env = dict(os.environ if base is None else base)
    env.update(cfg.native_env)
    return env


def native_start(cfg: Config) -> tuple[bool, str]:
    if native_pid(cfg):
        return True, "原生进程已经在跑"
    busy = [p for p in cfg.native_ports if port_open(p)]
    if busy:
        return False, f"端口 {busy[0]} 已被占用，先把 Docker 那套停掉"
    RUN_DIR.mkdir(exist_ok=True)
    log = (RUN_DIR / f"{cfg.native_service}.log").open("ab")
    log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} start {cfg.native_script.name}\n".encode())
    log.flush()
    proc = subprocess.Popen(
        ["bash", str(cfg.native_script)],
        cwd=str(cfg.native_script.parent),
        env=native_env(cfg),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _pid_file(cfg).write_text(str(proc.pid))
    _children[cfg.native_service] = proc
    log.close()
    # 边节点要建 jieba 词典、开加密库，起得慢；先等一会儿再给结论
    for _ in range(30):
        if not native_pid(cfg):
            return False, f"原生进程刚起就退了：{_native_log_tail(cfg)}"
        if not cfg.native_ports or any(port_open(p) for p in cfg.native_ports):
            return True, f"原生进程已启动（pid {proc.pid}）"
        time.sleep(0.5)
    return True, f"原生进程已拉起（pid {proc.pid}），还在初始化，日志见 .run/"


def _native_log_tail(cfg: Config, lines: int = 3) -> str:
    path = RUN_DIR / f"{cfg.native_service}.log"
    if not path.exists():
        return "没有日志"
    rows = [ln for ln in path.read_text(errors="replace").splitlines() if ln.strip()]
    return " / ".join(rows[-lines:])[:200] or "日志是空的"


def native_stop(cfg: Config) -> tuple[bool, str]:
    pid = native_pid(cfg)
    if not pid:
        _pid_file(cfg).unlink(missing_ok=True)
        return True, "原生进程没在跑"
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        return False, "停不掉：进程已经不在"
    for _ in range(40):
        if not native_pid(cfg):
            break
        time.sleep(0.2)
    else:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    _pid_file(cfg).unlink(missing_ok=True)
    return True, "原生进程已停止"


# ---------------------------------------------------------------- 状态

def detect_mode(cfg: Config) -> str:
    ok, _ = docker_ready(cfg)
    if ok:
        rows = compose_ps(cfg)
        if any(str(r.get("State")) == "running" for r in rows.values()):
            return "docker"
    if native_pid(cfg):
        return "native"
    return "docker" if ok else "native"


def snapshot(cfg: Config, mode: str) -> dict:
    out: dict = {"mode": mode, "services": [], "error": "", "hint": "", "deps": []}
    if mode == "docker":
        ok, why = docker_ready(cfg)
        if not ok:
            out["error"] = why
            out["hint"] = "cd docker && docker compose up -d"
            return out
        rows = compose_ps(cfg)
        declared = compose_services(cfg)
        names = list(dict.fromkeys([*cfg.services.keys(), *declared]))
        for name in names:
            rec = rows.get(name, {})
            meta = cfg.services.get(name)
            state = str(rec.get("State") or "absent")
            health = str(rec.get("Health") or "")
            out["services"].append(
                {
                    "name": name,
                    "label": meta.label if meta and meta.label else name,
                    "note": meta.note if meta else "",
                    "group": meta.group if meta else "",
                    "state": state,
                    "health": health,
                    "running": state == "running",
                    "healthy": health in ("", "healthy") and state == "running",
                    "ports": ports_of(rec),
                    "status": str(rec.get("Status") or ""),
                }
            )
    else:
        pid = native_pid(cfg)
        ports = [p for p in cfg.native_ports if port_open(p)]
        serving = bool(pid) and (not cfg.native_ports or bool(ports))
        deps = compose_ps(cfg) if cfg.deps else {}
        out["services"].append(
            {
                "name": cfg.native_service,
                "label": cfg.native_label,
                "note": " / ".join(str(p) for p in cfg.native_ports),
                "group": "",
                "state": "running" if serving else "starting" if pid else "stopped",
                "health": "starting" if pid and not serving else "",
                "running": bool(pid),
                "healthy": serving,
                "ports": " / ".join(str(p) for p in ports),
                "status": f"pid {pid}" if pid else "",
            }
        )
        out["deps"] = [
            {"name": d, "running": str((deps.get(d) or {}).get("State")) == "running"}
            for d in cfg.deps
        ]
    out["health_ok"] = http_ok(cfg.native_health_url if mode == "native" else cfg.health_url)
    # starting 是 healthcheck 的宽限期（容器刚起，间隔 60 秒、要连过 3 次），
    # 算成异常会让刚重启完的页面一片红
    out["summary"] = {
        "total": len(out["services"]),
        "running": sum(1 for s in out["services"] if s["running"]),
        "bad": sum(
            1 for s in out["services"] if s["running"] and not s["healthy"] and s["health"] != "starting"
        ),
    }
    return out


# ---------------------------------------------------------------- 动作

VERB = {"start": "启动", "stop": "停止", "restart": "重启"}


def _done(ok: bool, what: str, out: str) -> tuple[bool, str]:
    # compose 成功时只说结论，失败才把最后一行带出来
    if ok:
        return True, f"{what}完成"
    return False, f"{what}失败：{_tail(out, what)}"


def act(cfg: Config, mode: str, action: str, service: str = "") -> tuple[bool, str]:
    if action in VERB:
        if mode == "native":
            if action == "start":
                return native_start(cfg)
            if action == "stop":
                return native_stop(cfg)
            native_stop(cfg)
            return native_start(cfg)
        if service not in compose_services(cfg):
            return False, f"没有这个服务：{service}"
        if action == "start":
            args = _compose(cfg, "up", "-d", service)
        else:
            args = _compose(cfg, action, service)
        code, out = _run(args, timeout=COMPOSE_TIMEOUT)
        return _done(code == 0, f"{service} {VERB[action]}", out)

    if mode == "native":
        if action == "start_all":
            return native_start(cfg)
        if action == "stop_all":
            return native_stop(cfg)
        if action == "restart_all":
            native_stop(cfg)
            return native_start(cfg)
        if action == "start_deps":
            return _start_deps(cfg)
        return False, f"不认识的动作：{action}"

    args = {
        "start_all": (_compose(cfg, "up", "-d"), "全部启动"),
        "stop_all": (_compose(cfg, "stop"), "全部停止"),
        "restart_all": (_compose(cfg, "restart"), "全部重启"),
        "start_deps": (_compose(cfg, "up", "-d", *cfg.deps), "补依赖容器"),
    }.get(action)
    if args is None:
        return False, f"不认识的动作：{action}"
    code, out = _run(args[0], timeout=COMPOSE_TIMEOUT)
    return _done(code == 0, args[1], out)


def _start_deps(cfg: Config) -> tuple[bool, str]:
    if not cfg.deps:
        return False, "没有要补的依赖"
    code, out = _run(_compose(cfg, "up", "-d", *cfg.deps), timeout=COMPOSE_TIMEOUT)
    return _done(code == 0, "补依赖容器", out)


def logs(cfg: Config, mode: str, service: str, lines: int = 200) -> str:
    if mode == "native":
        path = RUN_DIR / f"{cfg.native_service}.log"
        if not path.exists():
            return "还没有日志：原生进程没启动过"
        text = path.read_text(errors="replace").splitlines()
        return "\n".join(text[-lines:])
    code, out = _run(_compose(cfg, "logs", "--tail", str(lines), "--no-color", service), timeout=25)
    return out or "（这个服务还没有输出）"


def _tail(text: str, what: str) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return f"{what} 已执行"
    return lines[-1][:200]
