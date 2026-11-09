"""运行时配置。全部来自环境变量，默认值只适合单机演示。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 前端构建产物；生产由 Caddy 直接服务，单进程调试时挂这里
STATIC = Path(__file__).resolve().parent.parent / "web" / "dist"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


DATA_DIR = Path(_env("EDGE_DATA_DIR", str(ROOT / "data")))
DB_PATH = Path(_env("EDGE_DB", str(DATA_DIR / "edge.db")))

EDGE_ID = _env("EDGE_ID", "edge-lab-01")
EDGE_NAME = _env("EDGE_NAME", "实验室边节点")
PUBLIC_URL = _env("EDGE_PUBLIC_URL", "http://127.0.0.1:8001")

CLOUD_URL = _env("EDGE_CLOUD_URL").rstrip("/")
CLOUD_TOKEN = _env("EDGE_CLOUD_TOKEN")

# 空的 ingest token 表示只接受本机写入，见 README「安全边界」。
INGEST_TOKEN = _env("EDGE_INGEST_TOKEN")
ADMIN_TOKEN = _env("EDGE_ADMIN_TOKEN")

K_MIN = int(_env("EDGE_K_MIN", "5"))

# ---- MQTT（端 → 边 的主通道）----
MQTT_HOST = _env("EDGE_MQTT_HOST")
MQTT_PORT = int(_env("EDGE_MQTT_PORT", "8883"))
MQTT_CA = _env("EDGE_MQTT_CA")
MQTT_CERT = _env("EDGE_MQTT_CERT")
MQTT_KEY = _env("EDGE_MQTT_KEY")
MQTT_USER = _env("EDGE_MQTT_USER")
MQTT_PASS = _env("EDGE_MQTT_PASS")
MQTT_TLS = _env("EDGE_MQTT_TLS", "1") != "0"

# ---- 边 → 云 的 mTLS ----
CLOUD_CA = _env("EDGE_CLOUD_CA")
CLOUD_CERT = _env("EDGE_CLOUD_CERT")
CLOUD_KEY = _env("EDGE_CLOUD_KEY")

# ---- mDNS 与定时任务 ----
MDNS_ENABLED = _env("EDGE_MDNS", "1") != "0"
PUSH_INTERVAL_MS = int(_env("EDGE_PUSH_INTERVAL_MS", str(60 * 60 * 1000)))
JANITOR_INTERVAL_MS = int(_env("EDGE_JANITOR_INTERVAL_MS", str(6 * 60 * 60 * 1000)))

# 设了就要求 SQLCipher；没有驱动就拒绝启动，不静默降级成明文
DB_KEY = _env("EDGE_DB_KEY")
WINDOW_MS = int(_env("EDGE_WINDOW_MS", str(5 * 60 * 1000)))
KEEP_DAYS = int(_env("EDGE_KEEP_DAYS", "180"))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
