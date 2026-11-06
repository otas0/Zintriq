"""Minimal DAP client — Content-Length framing over stdio or TCP."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, IO


class _Transport:
    def write(self, data: bytes) -> None: ...
    def read(self, n: int) -> bytes: ...
    def close(self) -> None: ...


class _StdioTransport(_Transport):
    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self.proc = proc

    def write(self, data: bytes) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def read(self, n: int) -> bytes:
        assert self.proc.stdout
        return self.proc.stdout.read(n)

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass


class _TcpTransport(_Transport):
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._buf = b""

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)

    def read(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(n - len(self._buf), 4096))
            if not chunk:
                return b""
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


@dataclass
class DapClient:
    transport: _Transport
    _next_id: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pending: dict[int, threading.Event] = field(default_factory=dict)
    _results: dict[int, Any] = field(default_factory=dict)
    _events: list[dict[str, Any]] = field(default_factory=list)
    _event_handlers: list[Callable[[str, dict[str, Any]], None]] = field(default_factory=list)
    _request_handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = field(default_factory=dict)
    _reader: threading.Thread | None = None
    _alive: bool = False
    proc: subprocess.Popen[bytes] | None = None

    @classmethod
    def connect_tcp(cls, host: str, port: int, timeout: float = 10.0) -> "DapClient":
        deadline = time.time() + timeout
        last: Exception | None = None
        while time.time() < deadline:
            try:
                sock = socket.create_connection((host, port), timeout=1.0)
                sock.settimeout(None)
                client = cls(transport=_TcpTransport(sock))
                client.start_reader()
                return client
            except OSError as exc:
                last = exc
                time.sleep(0.05)
        raise RuntimeError(f"DAP connect failed: {last}")

    @classmethod
    def spawn_stdio(cls, cmd: list[str], cwd: Path) -> "DapClient":
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        client = cls(transport=_StdioTransport(proc), proc=proc)
        client.start_reader()
        return client

    def start_reader(self) -> None:
        self._alive = True
        self._reader = threading.Thread(target=self._read_loop, name="dap-reader", daemon=True)
        self._reader.start()

    def stop(self) -> None:
        self._alive = False
        # Prefer hard close — disconnect handshake often hangs under load.
        try:
            self.transport.close()
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def on_event(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._event_handlers.append(handler)

    def on_reverse_request(self, command: str, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        """Handle DAP reverse requests from the adapter (e.g. runInTerminal)."""
        self._request_handlers[command] = handler

    def drain_events(self) -> list[dict[str, Any]]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out

    def _read_loop(self) -> None:
        buf = b""
        while self._alive:
            chunk = self.transport.read(1)
            if not chunk:
                break
            buf += chunk
            while b"\r\n\r\n" in buf:
                header, rest = buf.split(b"\r\n\r\n", 1)
                length = 0
                for line in header.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1].strip())
                while len(rest) < length:
                    more = self.transport.read(length - len(rest))
                    if not more:
                        break
                    rest += more
                body, buf = rest[:length], rest[length:]
                try:
                    msg = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._dispatch(msg)
        self._alive = False

    def _dispatch(self, msg: dict[str, Any]) -> None:
        # Reverse request from adapter → client
        if msg.get("type") == "request" and msg.get("command") in self._request_handlers:
            cmd = str(msg.get("command") or "")
            seq = int(msg.get("seq") or 0)
            args = msg.get("arguments") if isinstance(msg.get("arguments"), dict) else {}
            try:
                body = self._request_handlers[cmd](args) or {}
                self._write(
                    {
                        "seq": self._next_id,
                        "type": "response",
                        "request_seq": seq,
                        "command": cmd,
                        "success": True,
                        "body": body,
                    }
                )
                with self._lock:
                    self._next_id += 1
            except Exception as exc:  # noqa: BLE001
                self._write(
                    {
                        "seq": self._next_id,
                        "type": "response",
                        "request_seq": seq,
                        "command": cmd,
                        "success": False,
                        "message": str(exc),
                    }
                )
                with self._lock:
                    self._next_id += 1
            return
        if msg.get("type") == "response" or ("request_seq" in msg and "command" in msg and "event" not in msg):
            mid = int(msg.get("request_seq") or msg.get("id") or 0)
            with self._lock:
                self._results[mid] = msg
                ev = self._pending.get(mid)
            if ev:
                ev.set()
            return
        if msg.get("type") == "event" or msg.get("event"):
            event = str(msg.get("event") or "")
            body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
            with self._lock:
                self._events.append({"event": event, "body": body})
            for h in list(self._event_handlers):
                try:
                    h(event, body)
                except Exception:
                    pass

    def _write(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        with self._lock:
            self.transport.write(header + data)

    def send_request(self, command: str, arguments: dict[str, Any] | None = None) -> int:
        """Fire a request; returns seq. Use wait_response() to collect the result."""
        with self._lock:
            mid = self._next_id
            self._next_id += 1
            ev = threading.Event()
            self._pending[mid] = ev
        msg: dict[str, Any] = {"seq": mid, "type": "request", "command": command}
        if arguments is not None:
            msg["arguments"] = arguments
        self._write(msg)
        return mid

    def wait_response(self, mid: int, timeout: float = 15.0) -> Any:
        with self._lock:
            ev = self._pending.get(mid)
        if not ev:
            with self._lock:
                raw = self._results.pop(mid, None)
            return None if not raw else self._unwrap(raw)
        if not ev.wait(timeout):
            with self._lock:
                self._pending.pop(mid, None)
            raise TimeoutError(f"DAP timeout waiting seq={mid}")
        with self._lock:
            self._pending.pop(mid, None)
            raw = self._results.pop(mid, None)
        return self._unwrap(raw)

    def _unwrap(self, raw: dict[str, Any] | None) -> Any:
        if not raw:
            return None
        if raw.get("success") is False:
            message = raw.get("message") or "DAP error"
            body = raw.get("body")
            raise RuntimeError(f"{message}: {body}" if body else str(message))
        return raw.get("body")

    def request(self, command: str, arguments: dict[str, Any] | None = None, timeout: float = 15.0) -> Any:
        mid = self.send_request(command, arguments)
        return self.wait_response(mid, timeout=timeout)

    def wait_event(self, name: str, timeout: float = 10.0) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for ev in self.drain_events():
                if ev.get("event") == name:
                    return ev
            time.sleep(0.02)
        return None

    def initialize(self, adapter_id: str = "debugpy") -> Any:
        return self.request(
            "initialize",
            {
                "clientID": "zintriq",
                "clientName": "Zintriq Editor",
                "adapterID": adapter_id,
                "pathFormat": "path",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "supportsVariableType": True,
                "supportsRunInTerminalRequest": True,
            },
        )
