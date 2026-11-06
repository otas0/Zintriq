"""Minimal WebSocket client for Node CDP (stdlib only)."""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
from typing import Any
from urllib.parse import urlparse


class WebSocket:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._buf = b""

    def send(self, text: str) -> None:
        data = text.encode("utf-8")
        header = bytearray([0x81])  # text, fin
        n = len(data)
        mask_bit = 0x80
        if n < 126:
            header.append(mask_bit | n)
        elif n < 65536:
            header.append(mask_bit | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack("!Q", n))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(header + masked)

    def recv(self) -> str:
        while True:
            frame = self._read_frame()
            if frame is None:
                return ""
            opcode, payload = frame
            if opcode == 0x8:  # close
                return ""
            if opcode == 0x9:  # ping
                self._pong(payload)
                continue
            if opcode == 0x1:
                return payload.decode("utf-8", errors="replace")
            if opcode == 0x2:
                return payload.decode("utf-8", errors="replace")

    def _pong(self, payload: bytes) -> None:
        header = bytearray([0x8A, 0x80 | len(payload)])
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        try:
            self.sock.sendall(header + masked)
        except OSError:
            pass

    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_frame(self) -> tuple[int, bytes] | None:
        try:
            b1, b2 = self._read_exact(2)
        except ConnectionError:
            return None
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def close(self) -> None:
        try:
            self.sock.sendall(bytes([0x88, 0x80]) + os.urandom(4))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def connect(ws_url: str, timeout: float = 5.0) -> WebSocket:
    parsed = urlparse(ws_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    sock = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(req.encode("ascii"))
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("no websocket handshake")
        data += chunk
    header = data.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    if "101" not in header.split("\r\n", 1)[0]:
        raise ConnectionError(f"websocket upgrade failed: {header[:200]}")
    expect = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    if expect not in header:
        # some servers still work; keep connection
        pass
    rest = data.split(b"\r\n\r\n", 1)[1]
    ws = WebSocket(sock)
    ws._buf = rest
    return ws
