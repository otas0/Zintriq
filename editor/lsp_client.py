"""JSON-RPC LSP client over stdio (pyright / typescript-language-server)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _which(name: str) -> str | None:
    return shutil.which(name)


def resolve_server_cmd(language: str) -> list[str] | None:
    """Resolve an installed language server binary for the language id."""
    lang = (language or "").lower()
    # normalize react variants onto JS/TS servers
    if lang in {"javascriptreact", "jsx"}:
        lang = "javascript"
    if lang in {"typescriptreact", "tsx"}:
        lang = "typescript"

    table: dict[str, list[list[str]]] = {
        "python": [
            ["basedpyright-langserver", "--stdio"],
            ["pyright-langserver", "--stdio"],
        ],
        "javascript": [["typescript-language-server", "--stdio"]],
        "typescript": [["typescript-language-server", "--stdio"]],
        "go": [["gopls", "serve"]],
        "rust": [["rust-analyzer"]],
        "c": [["clangd", "--background-index"]],
        "cpp": [["clangd", "--background-index"]],
        "objc": [["clangd", "--background-index"]],
        "json": [
            ["vscode-json-language-server", "--stdio"],
            ["vscode-json-languageserver", "--stdio"],
        ],
        "html": [
            ["vscode-html-language-server", "--stdio"],
            ["vscode-html-languageserver", "--stdio"],
        ],
        "css": [
            ["vscode-css-language-server", "--stdio"],
            ["vscode-css-languageserver", "--stdio"],
        ],
        "yaml": [["yaml-language-server", "--stdio"]],
        "markdown": [["marksman", "server"]],
        "lua": [["lua-language-server"]],
        "ruby": [["solargraph", "stdio"]],
        "php": [["intelephense", "--stdio"]],
        "bash": [["bash-language-server", "start"]],
        "shellscript": [["bash-language-server", "start"]],
    }
    for candidate in table.get(lang) or []:
        if _which(candidate[0]):
            return candidate

    if lang == "python":
        try:
            proc = subprocess.run(
                [sys.executable, "-c", "import pyright; print('ok')"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and _which("pyright-langserver"):
                return ["pyright-langserver", "--stdio"]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


@dataclass
class LspSession:
    language: str
    workspace: Path
    cmd: list[str]
    proc: subprocess.Popen[bytes] | None = None
    _next_id: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pending: dict[int, threading.Event] = field(default_factory=dict)
    _results: dict[int, Any] = field(default_factory=dict)
    _diagnostics: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _reader: threading.Thread | None = None
    _alive: bool = False
    _initialized: bool = False
    opened: set[str] = field(default_factory=set)

    def start(self) -> None:
        if self._alive:
            return
        self.proc = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.workspace),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        self._alive = True
        self._reader = threading.Thread(target=self._read_loop, name=f"lsp-{self.language}", daemon=True)
        self._reader.start()
        root_uri = self.workspace.resolve().as_uri()
        result = self.request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": root_uri,
                "capabilities": {
                    "textDocument": {
                        "synchronization": {"didSave": True, "dynamicRegistration": False},
                        "completion": {"completionItem": {"snippetSupport": False}},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "definition": {"linkSupport": True},
                        "references": {},
                        "rename": {"prepareSupport": True},
                        "codeAction": {
                            "codeActionLiteralSupport": {
                                "codeActionKind": {
                                    "valueSet": [
                                        "",
                                        "quickfix",
                                        "refactor",
                                        "refactor.extract",
                                        "refactor.inline",
                                        "refactor.rewrite",
                                        "source",
                                        "source.organizeImports",
                                    ]
                                }
                            }
                        },
                        "publishDiagnostics": {},
                    }
                },
                "workspaceFolders": [{"uri": root_uri, "name": self.workspace.name}],
            },
            timeout=30.0,
        )
        if result is None and not self._alive:
            raise RuntimeError(f"LSP failed to start: {' '.join(self.cmd)}")
        self.notify("initialized", {})
        self._initialized = True

    def stop(self) -> None:
        self._alive = False
        try:
            if self.proc and self.proc.poll() is None:
                try:
                    self.request("shutdown", None, timeout=2.0)
                except Exception:
                    pass
                try:
                    self.notify("exit", None)
                except Exception:
                    pass
                self.proc.kill()
        except Exception:
            pass
        self.proc = None

    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        buf = b""
        while self._alive and self.proc.poll() is None:
            chunk = self.proc.stdout.read(1)
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
                    more = self.proc.stdout.read(length - len(rest))
                    if not more:
                        break
                    rest += more
                body, buf = rest[:length], rest[length:]
                try:
                    msg = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._dispatch(msg)

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            mid = int(msg["id"])
            with self._lock:
                self._results[mid] = msg
                ev = self._pending.get(mid)
            if ev:
                ev.set()
            return
        method = msg.get("method")
        if method == "textDocument/publishDiagnostics":
            params = msg.get("params") or {}
            uri = str(params.get("uri") or "")
            diags = []
            for d in params.get("diagnostics") or []:
                rng = d.get("range") or {}
                start = rng.get("start") or {}
                sev = int(d.get("severity") or 1)
                severity = {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(sev, "warning")
                diags.append(
                    {
                        "line": int(start.get("line") or 0) + 1,
                        "col": int(start.get("character") or 0) + 1,
                        "severity": severity,
                        "message": str(d.get("message") or ""),
                        "source": str(d.get("source") or self.language),
                    }
                )
            with self._lock:
                self._diagnostics[uri] = diags

    def _write(self, payload: dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("LSP not running")
        data = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        with self._lock:
            self.proc.stdin.write(header + data)
            self.proc.stdin.flush()

    def notify(self, method: str, params: Any) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    def request(self, method: str, params: Any, timeout: float = 10.0) -> Any:
        with self._lock:
            mid = self._next_id
            self._next_id += 1
            ev = threading.Event()
            self._pending[mid] = ev
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        if not ev.wait(timeout):
            with self._lock:
                self._pending.pop(mid, None)
            raise TimeoutError(f"LSP timeout: {method}")
        with self._lock:
            self._pending.pop(mid, None)
            raw = self._results.pop(mid, None)
        if not raw:
            return None
        if raw.get("error"):
            err = raw["error"]
            raise RuntimeError(err.get("message") or str(err))
        return raw.get("result")

    def uri_for(self, rel: str) -> str:
        return (self.workspace / rel).resolve().as_uri()

    def ensure_open(self, rel: str, text: str, language_id: str) -> str:
        uri = self.uri_for(rel)
        if uri not in self.opened:
            self.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": language_id,
                        "version": 1,
                        "text": text,
                    }
                },
            )
            self.opened.add(uri)
        else:
            self.notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": int(time.time() * 1000) % 1_000_000},
                    "contentChanges": [{"text": text}],
                },
            )
        return uri

    def diagnostics_for(self, uri: str) -> list[dict[str, Any]]:
        # wait briefly for publishDiagnostics
        deadline = time.time() + 1.5
        while time.time() < deadline:
            with self._lock:
                if uri in self._diagnostics:
                    return list(self._diagnostics[uri])
            time.sleep(0.05)
        with self._lock:
            return list(self._diagnostics.get(uri, []))


_SESSIONS: dict[str, LspSession] = {}
_SESS_LOCK = threading.Lock()


def language_id(language: str) -> str:
    return {
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
        "javascriptreact": "javascriptreact",
        "typescriptreact": "typescriptreact",
        "jsx": "javascriptreact",
        "tsx": "typescriptreact",
        "go": "go",
        "rust": "rust",
        "c": "c",
        "cpp": "cpp",
        "objc": "objective-c",
        "json": "json",
        "html": "html",
        "css": "css",
        "yaml": "yaml",
        "markdown": "markdown",
        "lua": "lua",
        "ruby": "ruby",
        "php": "php",
        "bash": "shellscript",
        "shellscript": "shellscript",
    }.get(language, language or "plaintext")


def _session_key_lang(language: str) -> str:
    lang = (language or "").lower()
    if lang in {"javascriptreact", "jsx", "typescriptreact", "tsx", "javascript", "typescript"}:
        # one tsserver session covers JS/TS family
        return "typescript"
    if lang in {"c", "cpp", "objc"}:
        return "cpp"
    if lang in {"bash", "shellscript"}:
        return "bash"
    return lang


def get_session(workspace: Path, language: str) -> LspSession | None:
    key_lang = _session_key_lang(language)
    key = f"{workspace.resolve()}::{key_lang}"
    with _SESS_LOCK:
        sess = _SESSIONS.get(key)
        if sess and sess._alive:
            return sess
        cmd = resolve_server_cmd(key_lang)
        if not cmd:
            return None
        sess = LspSession(language=key_lang, workspace=workspace.resolve(), cmd=cmd)
        try:
            sess.start()
        except Exception:
            return None
        _SESSIONS[key] = sess
        return sess


def shutdown_all() -> None:
    with _SESS_LOCK:
        for sess in list(_SESSIONS.values()):
            sess.stop()
        _SESSIONS.clear()


def available_servers() -> dict[str, bool]:
    langs = (
        "python",
        "typescript",
        "go",
        "rust",
        "cpp",
        "json",
        "html",
        "css",
        "yaml",
        "markdown",
        "lua",
        "ruby",
        "php",
        "bash",
    )
    return {lang: bool(resolve_server_cmd(lang)) for lang in langs}
