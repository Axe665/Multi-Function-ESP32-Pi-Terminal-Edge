"""读仓库根的 launcher.toml。

服务清单不写在这里：它来自 `docker compose config --services`，本文件只补
界面要用的中文名、端口说明和分组，免得 compose 改了还要同步两处。
"""
from __future__ import annotations

try:  # Python 3.11+ 自带；3.10 要 pip install tomli
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path

# tools/service-launch/service_launch/config.py → 仓库根
ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ServiceMeta:
    label: str = ""
    note: str = ""
    group: str = ""


@dataclass(frozen=True)
class Config:
    title: str
    port: int
    web_url: str
    health_url: str
    compose_file: Path
    native_service: str
    native_label: str
    native_script: Path
    native_ports: tuple[int, ...]
    deps: tuple[str, ...]
    services: dict[str, ServiceMeta] = field(default_factory=dict)


def load(path: Path | None = None) -> Config:
    raw = (path or ROOT / "launcher.toml").read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    c = data["console"]
    n = data.get("native", {})
    return Config(
        title=str(c["title"]),
        port=int(c["port"]),
        web_url=str(c["web_url"]),
        health_url=str(c["health_url"]),
        compose_file=ROOT / str(c["compose_file"]),
        native_service=str(n.get("service", "native")),
        native_label=str(n.get("label", n.get("service", "原生进程"))),
        native_script=ROOT / str(n.get("script", "run.sh")),
        native_ports=tuple(int(p) for p in n.get("ports", [])),
        deps=tuple(str(d) for d in n.get("deps", [])),
        services={
            name: ServiceMeta(
                label=str(meta.get("label", "")),
                note=str(meta.get("note", "")),
                group=str(meta.get("group", "")),
            )
            for name, meta in data.get("services", {}).items()
        },
    )
