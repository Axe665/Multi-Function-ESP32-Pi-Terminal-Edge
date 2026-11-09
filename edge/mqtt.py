"""MQTT 接入：orpi/v1/{deviceId}/{telemetry|status|advice|ack|cmd}。

与 HTTP 摄取共用 ingest.process，主题 ACL 由 broker 侧限制为「只能读写自己的前缀」。
传输默认 TLS + 双向证书；不带证书时只允许连本机 broker。
"""
from __future__ import annotations

import json
import ssl
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - 精简部署里可以不装
    mqtt = None  # type: ignore[assignment]

from . import catalog, config, ingest, store

TELEMETRY = "orpi/v1/{dev}/telemetry"
STATUS = "orpi/v1/{dev}/status"
ACK = "orpi/v1/{dev}/ack"
CMD = "orpi/v1/{dev}/cmd"


class MqttIngest:
    def __init__(self) -> None:
        self.client: Any = None
        self.connected = False
        self.last_error: str | None = None
        self.received = 0
        self.rejected = 0

    # ---------------------------------------------------------------- 生命周期

    def start(self) -> bool:
        if mqtt is None or not config.MQTT_HOST:
            return False
        self.client = mqtt.Client(
            client_id=f"edge-{config.EDGE_ID}", clean_session=False,
            protocol=mqtt.MQTTv311, transport="tcp")
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        if config.MQTT_TLS:
            ctx = ssl.create_default_context(cafile=config.MQTT_CA or None)
            if config.MQTT_CERT and config.MQTT_KEY:
                ctx.load_cert_chain(config.MQTT_CERT, config.MQTT_KEY)
            # 设备证书是自签 CA 签的，主机名通常就是 edge id
            ctx.check_hostname = bool(config.MQTT_CA)
            self.client.tls_set_context(ctx)

        if config.MQTT_USER:
            self.client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)

        try:
            self.client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
            self.client.loop_start()
            return True
        except Exception as e:  # noqa: BLE001 —— 连不上不能拖垮管理面
            self.last_error = str(e)[:200]
            return False

    def stop(self) -> None:
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False

    # ---------------------------------------------------------------- 回调

    def _on_connect(self, client, userdata, flags, rc):
        self.connected = rc == 0
        self.last_error = None if rc == 0 else f"rc={rc}"
        if rc == 0:
            client.subscribe([(TELEMETRY.replace("{dev}", "+"), 1),
                              (STATUS.replace("{dev}", "+"), 1)])
            store.bump("mqtt_connects")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            self.last_error = f"disconnected rc={rc}"

    def _on_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split("/")
            if len(parts) != 4 or parts[0] != "orpi" or parts[1] != "v1":
                return
            device_id, kind = parts[2], parts[3]
            body = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.rejected += 1
            return

        if kind == "status":
            self._status(device_id, body)
            return
        if kind != "telemetry":
            return

        try:
            result = ingest.process(body)
        except ingest.IngestError as e:
            self.rejected += 1
            client.publish(ACK.format(dev=device_id),
                           json.dumps({"batch_id": None, "accepted": False, "code": e.code}),
                           qos=1)
            return

        self.received += 1
        client.publish(ACK.format(dev=device_id),
                       json.dumps(ingest.ack_payload(result)), qos=1)

    def _status(self, device_id: str, body: dict[str, Any]) -> None:
        """status 里带模块清单：可以是 [83, 80]，也可以是带 capabilities 的对象。"""
        store.ensure_device(device_id)
        store.touch_device(device_id, store.now_ms())
        modules = body.get("modules")
        if not isinstance(modules, list):
            return
        ids: list[int] = []
        for m in modules:
            if isinstance(m, dict):
                mid = int(m.get("module_id", 0))
                ids.append(mid)
                for metric in m.get("metrics") or []:
                    catalog.upsert(device_id, str(metric["metric"]), mid,
                                   str(m.get("package_id", "")),
                                   str(metric.get("label", "")),
                                   str(metric.get("unit", "")),
                                   str(metric.get("table", "samples")),
                                   int(metric.get("decimals", 1)))
            elif isinstance(m, int):
                ids.append(m)
        with store.connect() as conn:
            conn.execute("UPDATE devices SET modules_json=? WHERE device_id=?",
                         (json.dumps(sorted(set(ids))), device_id))

    # ---------------------------------------------------------------- 下行

    def publish_cmd(self, device_id: str, payload: dict[str, Any]) -> bool:
        if not (self.client and self.connected):
            return False
        info = self.client.publish(CMD.format(dev=device_id),
                                   json.dumps(payload, ensure_ascii=False), qos=1)
        return info.rc == 0

    def status(self) -> dict[str, Any]:
        return {
            "enabled": mqtt is not None and bool(config.MQTT_HOST),
            "host": config.MQTT_HOST or None,
            "port": config.MQTT_PORT,
            "tls": config.MQTT_TLS,
            "connected": self.connected,
            "received": self.received,
            "rejected": self.rejected,
            "last_error": self.last_error,
        }


mqtt_ingest = MqttIngest()
