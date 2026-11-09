"""够用的假 MQTT broker：只实现测试要用的那几种报文。

CONNECT/CONNACK、SUBSCRIBE/SUBACK、PUBLISH(QoS1)/PUBACK、PINGREQ/PINGRESP。
它不是 mosquitto 的替代品，只用来证明我们的客户端在真实报文上能收发。
"""
from __future__ import annotations

import socket
import struct
import threading


def _read_varint(sock) -> int:
    mult, value = 1, 0
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("closed")
        value += (b[0] & 0x7F) * mult
        if not b[0] & 0x80:
            return value
        mult *= 128


def _read_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def _packet(kind: int, flags: int, body: bytes) -> bytes:
    header = bytes([(kind << 4) | flags])
    length, out = len(body), b""
    while True:
        byte = length % 128
        length //= 128
        if length:
            byte |= 0x80
        out += bytes([byte])
        if not length:
            break
    return header + out + body


class FakeBroker:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.subscriptions: list[str] = []
        self.published: list[tuple[str, bytes]] = []
        self.conn: socket.socket | None = None
        self._stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        self.conn = conn
        try:
            while not self._stop:
                head = conn.recv(1)
                if not head:
                    return
                kind = head[0] >> 4
                length = _read_varint(conn)
                body = _read_exact(conn, length) if length else b""
                if kind == 1:      # CONNECT
                    conn.sendall(_packet(2, 0, b"\x00\x00"))
                elif kind == 8:    # SUBSCRIBE
                    pid = body[:2]
                    i, granted = 2, b""
                    while i < len(body):
                        n = struct.unpack(">H", body[i:i + 2])[0]
                        self.subscriptions.append(body[i + 2:i + 2 + n].decode())
                        granted += b"\x01"
                        i += 2 + n + 1
                    conn.sendall(_packet(9, 0, pid + granted))
                elif kind == 3:    # PUBLISH
                    qos = (head[0] >> 1) & 0x03
                    n = struct.unpack(">H", body[:2])[0]
                    topic = body[2:2 + n].decode()
                    rest = body[2 + n:]
                    pid, payload = b"", rest
                    if qos == 1:
                        pid, payload = rest[:2], rest[2:]
                    self.published.append((topic, payload))
                    if qos == 1:
                        conn.sendall(_packet(4, 0, pid))
                elif kind == 12:   # PINGREQ
                    conn.sendall(_packet(13, 0, b""))
                elif kind == 14:   # DISCONNECT
                    return
        except (ConnectionError, OSError):
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def inject(self, topic: str, payload: bytes) -> None:
        """从 broker 侧推一条 QoS1 PUBLISH 给客户端。"""
        body = struct.pack(">H", len(topic)) + topic.encode() + b"\x00\x01" + payload
        self.conn.sendall(_packet(3, 0x02, body))

    def close(self) -> None:
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass
