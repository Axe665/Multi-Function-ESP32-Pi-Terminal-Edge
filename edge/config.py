"""运行时配置。全部来自环境变量，默认值只适合单机演示。"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 前端构建产物；生产由 Caddy 直接服务，单进程调试时挂这里
STATIC = Path(__file__).resolve().parent.parent / "web" / "dist"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


DATA_DIR = Path(_env("EDGE_DATA_DIR", str(ROOT / "data")))
DB_PATH = Path(_env("EDGE_DB", str(DATA_DIR / "edge.db")))
# CRL 与 broker 证书同目录：mosquitto 的 crl_file 指向这里
BROKER_CRL = Path(_env("EDGE_MQTT_CERT",
                       str(ROOT / "docker" / "mosquitto" / "certs" / "edge.crt"))).parent / "crl.pem"

EDGE_ID = _env("EDGE_ID", "edge-lab-01")
EDGE_NAME = _env("EDGE_NAME", "实验室边节点")
PUBLIC_URL = _env("EDGE_PUBLIC_URL", "http://127.0.0.1:8001")

def _cloud_url() -> str:
    """文档 §5.9：静态地址兜底。环境变量优先，其次 /etc/orange-pi-terminal/cloud.json。"""
    url = _env("EDGE_CLOUD_URL")
    if url:
        return url.rstrip("/")
    path = Path(_env("EDGE_STATIC_CONFIG", "/etc/orange-pi-terminal/cloud.json"))
    try:
        data = json.loads(path.read_text())
        return str(data.get("url") or data.get("cloud_url") or "").rstrip("/")
    except (OSError, ValueError, AttributeError):
        return ""


CLOUD_URL = _cloud_url()
CLOUD_TOKEN = _env("EDGE_CLOUD_TOKEN")

# 空的 ingest token 表示只接受本机写入，见 README「安全边界」。
def _ingest_token() -> str:
    """设备写入口的令牌：环境变量优先，否则首次启动生成并落盘。

    文档 §5.7 要求接入有身份；HTTP 兜底通道不能裸奔，所以默认就要令牌。
    """
    token = _env("EDGE_INGEST_TOKEN")
    if token:
        return token
    path = DATA_DIR / "ingest_token"
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        token = secrets.token_hex(16)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")
        path.chmod(0o600)
        return token
    except OSError:
        return ""


INGEST_TOKEN = _ingest_token()
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
# L2 聚合保留 180 天，L3 文本保留 365 天（文档 §8.1）
KEEP_DAYS = int(_env("EDGE_KEEP_DAYS", "180"))
TEXT_KEEP_DAYS = int(_env("EDGE_TEXT_KEEP_DAYS", "365"))
# 每日快照 + 7 天保留（文档 §5.1）
SNAPSHOT_KEEP = int(_env("EDGE_SNAPSHOT_KEEP", "7"))
# 演示模式：compose 默认开，UI 挂「演示模式」横幅（文档 §8.5）
DEMO = _env("EDGE_DEMO", "1") != "0"
BUILD = _env("EDGE_BUILD", "dev")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
