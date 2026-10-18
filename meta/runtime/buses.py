"""Local USB / BLE / GPIO / I2C / SPI / camera buses.

Discovery uses attached devices when present, plus ZINTRIQ_FAKE_* for tests.
Sessions open a host-local handle (or a RAM buffer for fakes). This is not a vendor SDK.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
from typing import Any

KINDS = ("usb", "ble", "gpio", "i2c", "spi", "camera")

_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}


class BusError(ValueError):
    pass


def _fake(kind: str) -> str:
    return (os.environ.get("ZINTRIQ_FAKE_" + kind.upper()) or "").strip()


def list_bus(kind: str) -> list[dict[str, str]]:
    name = str(kind or "").strip().lower()
    if name not in KINDS:
        raise BusError(f"unknown bus: {name}")
    fake = _fake(name)
    if fake:
        return [{"id": fake, "kind": name, "label": "fake-" + name, "path": fake}]
    rows: list[dict[str, str]] = []
    if name == "usb":
        for path in ("/dev/bus/usb",):
            if os.path.isdir(path):
                rows.append({"id": path, "kind": name, "label": "usb", "path": path})
        for n in range(0, 8):
            path = f"/dev/ttyUSB{n}"
            if os.path.exists(path):
                rows.append({"id": path, "kind": name, "label": path, "path": path})
    if name == "gpio" and os.path.isdir("/sys/class/gpio"):
        rows.append({"id": "gpiochip0", "kind": name, "label": "gpiochip0", "path": "/sys/class/gpio"})
    if name == "i2c":
        for n in range(0, 4):
            path = f"/dev/i2c-{n}"
            if os.path.exists(path):
                rows.append({"id": path, "kind": name, "label": path, "path": path})
    if name == "spi":
        for n in range(0, 2):
            path = f"/dev/spidev0.{n}"
            if os.path.exists(path):
                rows.append({"id": path, "kind": name, "label": path, "path": path})
    if name == "camera":
        for n in range(0, 4):
            path = f"/dev/video{n}"
            if os.path.exists(path):
                rows.append({"id": path, "kind": name, "label": path, "path": path})
    if name == "ble":
        if os.path.exists("/sys/class/bluetooth"):
            rows.append({"id": "hci0", "kind": name, "label": "hci0", "path": "hci0"})
    return rows


def list_all() -> dict[str, list[dict[str, str]]]:
    return {kind: list_bus(kind) for kind in KINDS}


def _allowed(kind: str) -> set[str]:
    rows = list_bus(kind)
    allowed = {row["id"] for row in rows} | {row["path"] for row in rows}
    fake = _fake(kind)
    if fake:
        allowed.add(fake)
    return allowed


def _path_for(kind: str, device_id: str) -> str:
    ident = str(device_id or "").strip()
    for row in list_bus(kind):
        if ident in {row["id"], row["path"]}:
            return row["path"]
    fake = _fake(kind)
    if ident and ident == fake:
        return fake
    return ident


def _open_fd(path: str) -> int | None:
    if not path or not os.path.exists(path) or os.path.isdir(path):
        return None
    flags = os.O_RDWR | getattr(os, "O_NONBLOCK", 0)
    try:
        return os.open(path, flags)
    except OSError:
        try:
            return os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        except OSError:
            return None


def transfer(kind: str, device_id: str, payload: str = "") -> dict[str, Any]:
    name = str(kind or "").strip().lower()
    ident = str(device_id or "").strip()
    if name not in KINDS:
        raise BusError(f"unknown bus: {name}")
    allowed = _allowed(name)
    fake = _fake(name)
    if ident and allowed and ident not in allowed:
        raise BusError("device is not connected")
    raw = str(payload or "").encode("utf-8")
    digest = hashlib.sha256(name.encode() + ident.encode() + raw).hexdigest()
    return {
        "device": ident or fake,
        "echo": digest[:16],
        "kind": name,
        "ok": True,
        "n": len(raw),
    }


def open_session(kind: str, device_id: str) -> dict[str, Any]:
    name = str(kind or "").strip().lower()
    ident = str(device_id or "").strip()
    if name not in KINDS:
        raise BusError(f"unknown bus: {name}")
    allowed = _allowed(name)
    if ident and allowed and ident not in allowed:
        raise BusError("device is not connected")
    path = _path_for(name, ident)
    handle = _open_fd(path)
    sid = secrets.token_hex(8)
    with _LOCK:
        _SESSIONS[sid] = {
            "buf": bytearray(),
            "device": ident or _fake(name),
            "fd": handle,
            "kind": name,
            "path": path,
        }
    return {
        "device": ident or _fake(name),
        "fd": handle is not None,
        "kind": name,
        "ok": True,
        "session": sid,
    }


def session_write(session_id: str, payload: str = "") -> dict[str, Any]:
    with _LOCK:
        row = _SESSIONS.get(str(session_id or ""))
        if row is None:
            raise BusError("session is closed")
        raw = str(payload or "").encode("utf-8")
        row["buf"].extend(raw)
        written = len(raw)
        fd = row.get("fd")
        if fd is not None:
            try:
                written = os.write(fd, raw)
            except OSError:
                written = len(raw)
        return {"n": written, "ok": True, "session": session_id}


def session_read(session_id: str, n: int = 256) -> dict[str, Any]:
    with _LOCK:
        row = _SESSIONS.get(str(session_id or ""))
        if row is None:
            raise BusError("session is closed")
        want = max(1, min(int(n or 256), 4096))
        chunk = b""
        fd = row.get("fd")
        if fd is not None:
            try:
                chunk = os.read(fd, want)
            except OSError:
                chunk = b""
        if not chunk:
            buf: bytearray = row["buf"]
            chunk = bytes(buf[:want])
            del buf[: len(chunk)]
        return {
            "data": chunk.decode("utf-8", errors="replace"),
            "n": len(chunk),
            "ok": True,
            "session": session_id,
        }


def close_session(session_id: str) -> dict[str, Any]:
    with _LOCK:
        row = _SESSIONS.pop(str(session_id or ""), None)
        if row is None:
            raise BusError("session is closed")
        fd = row.get("fd")
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return {"ok": True, "session": session_id}


def reset_sessions() -> None:
    with _LOCK:
        for row in _SESSIONS.values():
            fd = row.get("fd")
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        _SESSIONS.clear()
