"""Persistent GDB / LLDB Machine Interface (MI2) client with async *stopped."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any


class GdbMiError(RuntimeError):
    pass


def resolve_mi_backend(prefer: str | None = None) -> tuple[str, str]:
    """Return (backend, executable) for gdb or lldb-mi."""
    want = (prefer or "").strip().lower()
    if want in {"lldb", "lldb-mi"}:
        path = shutil.which("lldb-mi") or shutil.which("lldb")
        if path:
            return "lldb", path
    gdb = shutil.which("gdb")
    if gdb and want not in {"lldb", "lldb-mi"}:
        return "gdb", gdb
    lldb_mi = shutil.which("lldb-mi")
    if lldb_mi:
        return "lldb", lldb_mi
    if gdb:
        return "gdb", gdb
    raise GdbMiError("neither gdb nor lldb-mi found")


class GdbMi:
    """Long-lived MI2 process (gdb --interpreter=mi2 or lldb-mi)."""

    def __init__(
        self,
        gdb_path: str | None = None,
        *,
        backend: str | None = None,
        on_stopped: Callable[[dict[str, Any]], None] | None = None,
        on_running: Callable[[], None] | None = None,
    ) -> None:
        if gdb_path:
            self.backend = (backend or "gdb").lower()
            self.gdb_path = gdb_path
        else:
            self.backend, self.gdb_path = resolve_mi_backend(backend)
        self.proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._token = 0
        self._reader: threading.Thread | None = None
        self._alive = False
        self._events: list[str] = []
        self._pending: dict[int, dict[str, Any]] = {}
        self._cv = threading.Condition(self._lock)
        self._on_stopped = on_stopped
        self._on_running = on_running
        self._stop_event = threading.Event()
        self._running = False
        self.last_stop: dict[str, Any] | None = None

    def start(self, *, extra_args: list[str] | None = None) -> None:
        if self.backend == "lldb":
            base = os.path.basename(self.gdb_path)
            if base == "lldb":
                mi = shutil.which("lldb-mi")
                if not mi:
                    raise GdbMiError("lldb-mi required for MI mode (brew install llvm)")
                self.gdb_path = mi
            cmd = [self.gdb_path, *(extra_args or [])]
        else:
            cmd = [self.gdb_path, "--interpreter=mi2", "-q", *(extra_args or [])]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "TERM": "dumb"},
        )
        self._alive = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="mi-reader")
        self._reader.start()
        time.sleep(0.15)
        try:
            self.cmd("-gdb-set", "pagination", "off", timeout=5.0)
        except GdbMiError:
            pass

    def close(self) -> None:
        self._alive = False
        try:
            if self.proc and self.proc.poll() is None:
                try:
                    self.cmd("-gdb-exit", timeout=2.0)
                except Exception:
                    pass
                self.proc.terminate()
        except OSError:
            pass
        self.proc = None

    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        while self._alive and self.proc.poll() is None:
            line = self.proc.stdout.readline()
            if not line:
                break
            self._handle_line(line.rstrip("\n"))

    def _handle_line(self, line: str) -> None:
        m = re.match(r"^(\d*)\^(\w+)(?:,(.*))?$", line)
        with self._cv:
            if m:
                tok = int(m.group(1) or 0)
                cls = m.group(2)
                rest = m.group(3) or ""
                self._pending[tok] = {"class": cls, "raw": rest, "line": line}
                # exec running/stopped sometimes as ^running
                if cls == "running":
                    self._running = True
                    self._stop_event.clear()
                    cb = self._on_running
                    if cb:
                        threading.Thread(target=cb, daemon=True).start()
                self._cv.notify_all()
                return
            if line.startswith("*stopped"):
                info = self._parse_stopped(line)
                self.last_stop = info
                self._running = False
                self._stop_event.set()
                self._events.append(line)
                cb = self._on_stopped
                self._cv.notify_all()
                if cb:
                    threading.Thread(target=cb, args=(info,), daemon=True).start()
                return
            if line.startswith("*running"):
                self._running = True
                self._stop_event.clear()
                self._events.append(line)
                cb = self._on_running
                self._cv.notify_all()
                if cb:
                    threading.Thread(target=cb, daemon=True).start()
                return
            if line.startswith(("*", "=", "~", "&", "@")):
                self._events.append(line)
                if len(self._events) > 200:
                    self._events = self._events[-200:]
                self._cv.notify_all()

    def _parse_stopped(self, line: str) -> dict[str, Any]:
        reason = ""
        m = re.search(r'reason="([^"]+)"', line)
        if m:
            reason = m.group(1)
        frame: dict[str, Any] = {}
        fm = re.search(
            r'frame=\{[^}]*func="([^"]*)"[^}]*(?:file="([^"]*)")?[^}]*(?:line="(\d+)")?',
            line,
        )
        if fm:
            frame = {"func": fm.group(1), "file": fm.group(2) or "", "line": int(fm.group(3) or 0)}
        return {"reason": reason or "stopped", "frame": frame, "raw": line}

    def wait_for_stop(self, timeout: float = 60.0) -> dict[str, Any] | None:
        if self._stop_event.wait(timeout):
            return self.last_stop
        return None

    def cmd(self, *parts: str, timeout: float = 15.0) -> dict[str, Any]:
        if not self.proc or not self.proc.stdin:
            raise GdbMiError("MI not running")
        with self._cv:
            self._token += 1
            tok = self._token
        line = f"{tok}{' '.join(parts)}\n"
        with self._lock:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        deadline = time.time() + timeout
        with self._cv:
            while time.time() < deadline:
                if tok in self._pending:
                    res = self._pending.pop(tok)
                    if res.get("class") == "error":
                        raise GdbMiError(res.get("raw") or res.get("line") or "MI error")
                    return res
                self._cv.wait(0.05)
        raise GdbMiError(f"timeout: {' '.join(parts)}")

    def cli(self, command: str, timeout: float = 15.0) -> str:
        esc = command.replace("\\", "\\\\").replace('"', '\\"')
        res = self.cmd("-interpreter-exec", "console", f'"{esc}"', timeout=timeout)
        with self._cv:
            out = [e[1:] for e in self._events if e.startswith("~")]
            self._events = [e for e in self._events if not e.startswith("~")]
        text = "".join(out)
        cleaned = []
        for chunk in re.findall(r'"((?:\\.|[^"\\])*)"', text) or [text]:
            cleaned.append(
                chunk.encode("utf-8", "backslashreplace").decode("unicode_escape", errors="replace")
                if "\\" in chunk
                else chunk
            )
        return "\n".join(cleaned) if cleaned else (res.get("raw") or "")

    def target_remote(self, host: str, port: int) -> None:
        self.cmd("-target-select", "extended-remote", f"{host}:{int(port)}", timeout=20.0)

    def stack_list_frames(self) -> list[dict[str, Any]]:
        res = self.cmd("-stack-list-frames", timeout=10.0)
        raw = res.get("raw") or ""
        frames = []
        for m in re.finditer(
            r'frame=\{level="(\d+)",addr="([^"]*)",func="([^"]*)",'
            r'(?:file="([^"]*)",)?(?:fullname="([^"]*)",)?(?:line="(\d+)",)?',
            raw,
        ):
            frames.append(
                {
                    "level": int(m.group(1)),
                    "addr": m.group(2),
                    "func": m.group(3),
                    "file": m.group(5) or m.group(4) or "",
                    "line": int(m.group(6) or 0),
                }
            )
        if not frames:
            for m in re.finditer(r'level="(\d+)".*?func="([^"]*)"', raw):
                frames.append(
                    {"level": int(m.group(1)), "addr": "", "func": m.group(2), "file": "", "line": 0}
                )
        return frames

    def stack_list_locals(self, frame_level: int = 0) -> list[dict[str, Any]]:
        try:
            self.cmd("-stack-select-frame", str(int(frame_level)), timeout=5.0)
        except GdbMiError:
            pass
        res = self.cmd("-stack-list-locals", "1", timeout=10.0)
        raw = res.get("raw") or ""
        out = []
        for m in re.finditer(r'name="([^"]+)".*?value="((?:\\.|[^"\\])*)"', raw):
            val = m.group(2).encode().decode("unicode_escape", errors="replace")
            out.append({"name": m.group(1), "value": val, "type": "", "scope": "Locals"})
        if not out:
            for m in re.finditer(r'name="([^"]+)"', raw):
                out.append({"name": m.group(1), "value": "?", "type": "", "scope": "Locals"})
        return out[:80]

    def _exec_async(self, *parts: str, wait: bool = True, timeout: float = 60.0) -> dict[str, Any] | None:
        self._stop_event.clear()
        self._running = True
        self.cmd(*parts, timeout=5.0)
        if not wait:
            return None
        return self.wait_for_stop(timeout)

    def exec_step(self, *, reverse: bool = False) -> dict[str, Any] | None:
        if reverse:
            self.cli("reverse-step")
            return self.wait_for_stop(30.0) or self.last_stop
        return self._exec_async("-exec-step", wait=True, timeout=30.0)

    def exec_next(self, *, reverse: bool = False) -> dict[str, Any] | None:
        if reverse:
            self.cli("reverse-next")
            return self.wait_for_stop(30.0) or self.last_stop
        return self._exec_async("-exec-next", wait=True, timeout=30.0)

    def exec_finish(self) -> dict[str, Any] | None:
        return self._exec_async("-exec-finish", wait=True, timeout=30.0)

    def exec_continue(self, *, reverse: bool = False) -> dict[str, Any] | None:
        if reverse:
            self.cli("reverse-continue")
            return self.wait_for_stop(120.0) or self.last_stop
        return self._exec_async("-exec-continue", wait=True, timeout=120.0)

    def data_evaluate(self, expression: str) -> str:
        esc = expression.replace("\\", "\\\\").replace('"', '\\"')
        res = self.cmd("-data-evaluate-expression", f'"{esc}"', timeout=10.0)
        raw = res.get("raw") or ""
        m = re.search(r'value="((?:\\.|[^"\\])*)"', raw)
        if m:
            return m.group(1).encode().decode("unicode_escape", errors="replace")
        return raw


# Back-compat alias
LldbMi = GdbMi
