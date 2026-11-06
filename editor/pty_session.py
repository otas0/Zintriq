"""Interactive PTY for Linux, macOS, and Windows.

Unix: os.fork + pty
Windows: pywinpty (ConPTY) when installed
"""

from __future__ import annotations

import os
import select
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

_LOCK = threading.Lock()
_SESSIONS: dict[str, "PtySession"] = {}


class _Backend(Protocol):
    def write(self, data: bytes) -> None: ...
    def read(self, n: int = 4096) -> bytes: ...
    def resize(self, rows: int, cols: int) -> None: ...
    def close(self) -> None: ...
    def alive(self) -> bool: ...


@dataclass
class PtySession:
    id: str
    workspace: Path
    backend: _Backend
    buffer: bytearray = field(default_factory=bytearray)
    _stop: bool = False
    _reader: threading.Thread | None = None
    shell: str = ""

    def start_reader(self) -> None:
        self._reader = threading.Thread(target=self._loop, name=f"pty-{self.id}", daemon=True)
        self._reader.start()

    def _loop(self) -> None:
        while not self._stop and self.backend.alive():
            try:
                chunk = self.backend.read(4096)
                if not chunk:
                    time.sleep(0.02)
                    continue
                with _LOCK:
                    self.buffer.extend(chunk)
                    if len(self.buffer) > 200_000:
                        del self.buffer[: len(self.buffer) - 200_000]
            except OSError:
                break
        self._stop = True

    def write(self, data: str | bytes) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        self.backend.write(raw)

    def read(self) -> str:
        with _LOCK:
            if not self.buffer:
                return ""
            out = bytes(self.buffer)
            self.buffer.clear()
        return out.decode("utf-8", errors="replace")

    def resize(self, rows: int, cols: int) -> None:
        self.backend.resize(int(rows), int(cols))

    def close(self) -> None:
        self._stop = True
        try:
            self.backend.close()
        except Exception:
            pass


class _UnixBackend:
    def __init__(self, workspace: Path, shell: str, cols: int, rows: int) -> None:
        import pty

        self.pid: int
        self.master_fd: int
        pid, master = pty.fork()
        if pid == 0:
            os.chdir(str(workspace))
            env = {k: v for k, v in os.environ.items() if k != "ZINTRIQ_DESKTOP_TOKEN"}
            env["TERM"] = env.get("TERM") or "xterm-256color"
            env["COLORTERM"] = env.get("COLORTERM") or "truecolor"
            os.execvpe(shell, [shell, "-l"], env)
        self.pid = pid
        self.master_fd = master
        self._alive = True
        self.resize(rows, cols)

    def write(self, data: bytes) -> None:
        os.write(self.master_fd, data)

    def read(self, n: int = 4096) -> bytes:
        r, _, _ = select.select([self.master_fd], [], [], 0.05)
        if not r:
            pid, _status = os.waitpid(self.pid, os.WNOHANG)
            if pid != 0:
                self._alive = False
            return b""
        try:
            return os.read(self.master_fd, n)
        except OSError:
            self._alive = False
            return b""

    def resize(self, rows: int, cols: int) -> None:
        try:
            import fcntl
            import termios

            winsize = struct.pack("HHHH", int(rows), int(cols), 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    def close(self) -> None:
        self._alive = False
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        try:
            os.kill(self.pid, 15)
        except OSError:
            pass

    def alive(self) -> bool:
        return self._alive


class _WinBackend:
    """ConPTY via pywinpty."""

    def __init__(self, workspace: Path, shell: str, cols: int, rows: int) -> None:
        from winpty import PtyProcess  # type: ignore

        self.proc = PtyProcess.spawn(
            shell,
            cwd=str(workspace),
            dimensions=(int(rows), int(cols)),
        )
        self._alive = True

    def write(self, data: bytes) -> None:
        self.proc.write(data.decode("utf-8", errors="replace"))

    def read(self, n: int = 4096) -> bytes:
        if not self.proc.isalive():
            self._alive = False
            return b""
        try:
            # non-blocking-ish: winpty read may block briefly
            out = self.proc.read(n)
            if isinstance(out, str):
                return out.encode("utf-8", errors="replace")
            return out or b""
        except Exception:
            if not self.proc.isalive():
                self._alive = False
            return b""

    def resize(self, rows: int, cols: int) -> None:
        try:
            self.proc.setwinsize(int(rows), int(cols))
        except Exception:
            pass

    def close(self) -> None:
        self._alive = False
        try:
            self.proc.close(force=True)
        except Exception:
            pass

    def alive(self) -> bool:
        try:
            return self._alive and bool(self.proc.isalive())
        except Exception:
            return False


def supported() -> bool:
    if os.name != "nt":
        return hasattr(os, "fork")
    try:
        import winpty  # noqa: F401

        return True
    except ImportError:
        return False


def backend_name() -> str:
    if os.name == "nt":
        return "conpty-pywinpty" if supported() else "none"
    return "unix-pty" if supported() else "none"


def _default_shell() -> str:
    if os.name == "nt":
        return os.environ.get("COMSPEC") or "powershell.exe"
    return os.environ.get("SHELL") or "/bin/bash"


def start(workspace: Path, *, cols: int = 80, rows: int = 24) -> dict[str, Any]:
    if not supported():
        raise RuntimeError(
            "interactive PTY unavailable "
            + ("(install pywinpty for Windows ConPTY)" if os.name == "nt" else "")
        )
    root = workspace.resolve()
    root.mkdir(parents=True, exist_ok=True)
    shell = _default_shell()
    if os.name == "nt":
        backend: _Backend = _WinBackend(root, shell, cols, rows)
    else:
        backend = _UnixBackend(root, shell, cols, rows)
    sid = uuid.uuid4().hex[:12]
    sess = PtySession(id=sid, workspace=root, backend=backend, shell=shell)
    sess.start_reader()
    with _LOCK:
        _SESSIONS[sid] = sess
    time.sleep(0.05)
    return {
        "ok": True,
        "id": sid,
        "shell": shell,
        "cwd": str(root),
        "backend": backend_name(),
    }


def write(session_id: str, data: str) -> dict[str, Any]:
    sess = _get(session_id)
    sess.write(data)
    return {"ok": True, "alive": sess.backend.alive()}


def read(session_id: str) -> dict[str, Any]:
    sess = _get(session_id)
    return {"ok": True, "data": sess.read(), "alive": sess.backend.alive()}


def resize(session_id: str, rows: int, cols: int) -> dict[str, Any]:
    sess = _get(session_id)
    sess.resize(rows, cols)
    return {"ok": True}


def close(session_id: str) -> dict[str, Any]:
    with _LOCK:
        sess = _SESSIONS.pop(session_id, None)
    if sess:
        sess.close()
    return {"ok": True}


def _get(session_id: str) -> PtySession:
    with _LOCK:
        sess = _SESSIONS.get(session_id)
    if not sess:
        raise KeyError("unknown pty session")
    return sess
