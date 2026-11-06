"""Advanced debug helpers: schema, ports, OTel, WASM, Jupyter, templates, symbols."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

_LAUNCH_TYPES = {
    "python",
    "node",
    "debugpy",
    "chrome",
    "cppdbg",
    "lldb",
    "gdb",
    "custom",
    "jupyter",
    "wasm",
    "go",
    "rust",
    "lldb-dap",
    "java",
    "coreclr",
    "cppdbg",
    "android",
    "ios",
    "cuda",
}
_REQUESTS = {"launch", "attach"}


def validate_launch_document(document: dict[str, Any]) -> dict[str, Any]:
    """Validate launch.json; returns {ok, errors:[{path,message,severity}], warnings}."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return {
            "ok": False,
            "errors": [{"path": "", "message": "document must be an object", "severity": "error"}],
            "warnings": [],
        }
    ver = document.get("version")
    if ver is not None and str(ver) not in {"0.2.0", "0.2"}:
        warnings.append({"path": "version", "message": f"unusual version {ver!r}", "severity": "warning"})
    configs = document.get("configurations")
    if not isinstance(configs, list):
        errors.append({"path": "configurations", "message": "must be a list", "severity": "error"})
        configs = []
    names: set[str] = set()
    for i, cfg in enumerate(configs):
        prefix = f"configurations[{i}]"
        if not isinstance(cfg, dict):
            errors.append({"path": prefix, "message": "must be an object", "severity": "error"})
            continue
        name = str(cfg.get("name") or "").strip()
        if not name:
            errors.append({"path": f"{prefix}.name", "message": "name required", "severity": "error"})
        elif name in names:
            errors.append({"path": f"{prefix}.name", "message": f"duplicate name {name!r}", "severity": "error"})
        else:
            names.add(name)
        typ = str(cfg.get("type") or "").strip().lower()
        if not typ:
            errors.append({"path": f"{prefix}.type", "message": "type required", "severity": "error"})
        elif typ not in _LAUNCH_TYPES:
            warnings.append(
                {
                    "path": f"{prefix}.type",
                    "message": f"unknown type {typ!r} (custom adapters still allowed)",
                    "severity": "warning",
                }
            )
        req = str(cfg.get("request") or "").strip().lower()
        if req not in _REQUESTS:
            errors.append({"path": f"{prefix}.request", "message": "request must be launch|attach", "severity": "error"})
        if req == "attach":
            port = cfg.get("port")
            if port is None:
                errors.append({"path": f"{prefix}.port", "message": "attach requires port", "severity": "error"})
            else:
                try:
                    p = int(port)
                    if p < 1 or p > 65535:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append({"path": f"{prefix}.port", "message": "invalid port", "severity": "error"})
        if req == "launch" and typ in {"python", "debugpy", "node"}:
            if not cfg.get("program") and not cfg.get("module") and not cfg.get("debugAdapter"):
                warnings.append(
                    {
                        "path": prefix,
                        "message": "launch usually needs program or module",
                        "severity": "warning",
                    }
                )
        if cfg.get("debugAdapter") and not isinstance(cfg.get("debugAdapter"), (str, list, dict)):
            errors.append(
                {"path": f"{prefix}.debugAdapter", "message": "must be string|list|object", "severity": "error"}
            )
        maps = cfg.get("pathMappings")
        if maps is not None:
            if not isinstance(maps, list):
                errors.append({"path": f"{prefix}.pathMappings", "message": "must be list", "severity": "error"})
            else:
                for j, m in enumerate(maps):
                    if not isinstance(m, dict) or not (m.get("localRoot") and m.get("remoteRoot")):
                        errors.append(
                            {
                                "path": f"{prefix}.pathMappings[{j}]",
                                "message": "need localRoot + remoteRoot",
                                "severity": "error",
                            }
                        )
        skip = cfg.get("skipFiles")
        if skip is not None and not isinstance(skip, list):
            errors.append({"path": f"{prefix}.skipFiles", "message": "must be list of globs", "severity": "error"})
    compounds = document.get("compounds") or []
    if compounds and not isinstance(compounds, list):
        errors.append({"path": "compounds", "message": "must be a list", "severity": "error"})
        compounds = []
    for i, c in enumerate(compounds if isinstance(compounds, list) else []):
        prefix = f"compounds[{i}]"
        if not isinstance(c, dict) or not str(c.get("name") or "").strip():
            errors.append({"path": prefix, "message": "compound needs name", "severity": "error"})
            continue
        for j, ref in enumerate(c.get("configurations") or []):
            if str(ref) not in names:
                errors.append(
                    {
                        "path": f"{prefix}.configurations[{j}]",
                        "message": f"unknown configuration {ref!r}",
                        "severity": "error",
                    }
                )
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def scan_attach_ports(
    host: str = "127.0.0.1",
    *,
    start: int = 5678,
    end: int = 5688,
    extra: list[int] | None = None,
    timeout: float = 0.15,
) -> dict[str, Any]:
    """Probe TCP ports commonly used by debugpy / Node inspector."""
    h = (host or "127.0.0.1").strip() or "127.0.0.1"
    ports: list[int] = []
    lo, hi = int(start), int(end)
    if lo > hi:
        lo, hi = hi, lo
    hi = min(hi, lo + 64)  # cap range
    for p in range(lo, hi + 1):
        ports.append(p)
    for p in extra or [9229, 9230, 9222, 5858, 8888, 8889]:
        if p not in ports and 1 <= int(p) <= 65535:
            ports.append(int(p))
    open_ports: list[dict[str, Any]] = []
    for p in ports:
        t0 = time.time()
        try:
            with socket.create_connection((h, p), timeout=timeout):
                ms = int((time.time() - t0) * 1000)
                kind = _guess_debug_port(h, p, timeout=timeout)
                open_ports.append({"host": h, "port": p, "ms": ms, "kind": kind, "healthy": True})
        except OSError:
            continue
    return {"ok": True, "host": h, "scanned": len(ports), "open": open_ports}


def _guess_debug_port(host: str, port: int, *, timeout: float = 0.2) -> str:
    """Best-effort: Node inspector JSON vs opaque DAP/debugpy."""
    try:
        import urllib.request

        url = f"http://{host}:{port}/json/version"
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read(512)
            if b"Browser" in raw or b"webSocketDebuggerUrl" in raw or b"V8" in raw:
                return "node-cdp"
    except Exception:
        pass
    if port in {5678, 5679, 5680}:
        return "debugpy?"
    if port in {9229, 9230, 9222}:
        return "node?"
    if port in {8888, 8889}:
        return "jupyter?"
    return "tcp-open"


def logpoint_templates_path(workspace: Path) -> Path:
    return workspace.resolve() / ".zintriq" / "logpoint-templates.json"


def default_logpoint_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": "enter",
            "label": "Function enter",
            "logMessage": "→ {name} args={arguments}",
            "tags": ["trace"],
        },
        {
            "id": "exit",
            "label": "Function exit",
            "logMessage": "← return={returnValue}",
            "tags": ["trace"],
        },
        {
            "id": "value",
            "label": "Value dump",
            "logMessage": "{expression} = {value}",
            "tags": ["watch"],
        },
        {
            "id": "hit",
            "label": "Hit counter",
            "logMessage": "hit @ {file}:{line}",
            "tags": ["hit"],
        },
    ]


def load_logpoint_templates(workspace: Path) -> dict[str, Any]:
    path = logpoint_templates_path(workspace)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("templates") if isinstance(raw, dict) else raw
            if isinstance(items, list):
                return {"ok": True, "path": ".zintriq/logpoint-templates.json", "templates": items, "shared": True}
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "ok": True,
        "path": ".zintriq/logpoint-templates.json",
        "templates": default_logpoint_templates(),
        "shared": False,
    }


def save_logpoint_templates(workspace: Path, templates: list[Any]) -> dict[str, Any]:
    clean = []
    for t in templates or []:
        if not isinstance(t, dict):
            continue
        msg = str(t.get("logMessage") or t.get("message") or "").strip()
        if not msg:
            continue
        clean.append(
            {
                "id": str(t.get("id") or uuid.uuid4().hex[:8]),
                "label": str(t.get("label") or msg[:40]),
                "logMessage": msg,
                "condition": str(t.get("condition") or ""),
                "tags": [str(x) for x in (t.get("tags") or []) if str(x).strip()],
            }
        )
    path = logpoint_templates_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "templates": clean}, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "path": ".zintriq/logpoint-templates.json", "templates": clean, "shared": True}


def otel_dir(workspace: Path) -> Path:
    d = workspace.resolve() / ".zintriq" / "otel"
    d.mkdir(parents=True, exist_ok=True)
    return d


def otel_record_span(
    workspace: Path,
    *,
    name: str,
    session_id: str = "",
    attributes: dict[str, Any] | None = None,
    status: str = "OK",
) -> dict[str, Any]:
    """Append a lightweight OTel-like JSON span for debug event correlation."""
    now = time.time()
    span = {
        "traceId": uuid.uuid4().hex,
        "spanId": uuid.uuid4().hex[:16],
        "name": name,
        "startTimeUnixNano": int(now * 1e9),
        "endTimeUnixNano": int(now * 1e9),
        "status": {"code": status},
        "attributes": {
            "debug.session_id": session_id,
            **{str(k): v for k, v in (attributes or {}).items()},
        },
    }
    path = otel_dir(workspace) / "debug-spans.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(span, ensure_ascii=False) + "\n")
    return {"ok": True, "span": span, "path": ".zintriq/otel/debug-spans.jsonl"}


def otel_list_spans(workspace: Path, *, limit: int = 80) -> dict[str, Any]:
    path = otel_dir(workspace) / "debug-spans.jsonl"
    if not path.is_file():
        return {"ok": True, "spans": [], "path": ".zintriq/otel/debug-spans.jsonl"}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    spans = []
    for line in lines[-max(1, min(int(limit), 500)) :]:
        try:
            spans.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"ok": True, "spans": spans, "path": ".zintriq/otel/debug-spans.jsonl"}


def enhance_core_symbols(
    workspace: Path,
    frames: list[dict[str, Any]],
    *,
    binary: str = "",
    addresses: list[str] | None = None,
) -> dict[str, Any]:
    """Enrich core frames with addr2line / llvm-symbolizer inline source locations."""
    tool = shutil.which("llvm-symbolizer") or shutil.which("addr2line")
    bin_path = None
    if binary:
        cand = Path(binary) if Path(binary).is_absolute() else (workspace / binary)
        if cand.is_file():
            bin_path = cand
    if not bin_path:
        for name in ("a.out", "main", "app", "program"):
            p = workspace / name
            if p.is_file():
                bin_path = p
                break
    enriched = [dict(f) for f in frames]
    symbols: list[dict[str, Any]] = []
    addrs = list(addresses or [])
    if not addrs:
        for fr in frames:
            for key in ("pc", "address", "instructionPointerReference"):
                v = fr.get(key)
                if v:
                    addrs.append(str(v))
                    break
    if tool and bin_path and addrs:
        for addr in addrs[:40]:
            try:
                if "llvm-symbolizer" in tool:
                    cmd = [tool, "-e", str(bin_path), "-f", "-inlining", "-pretty-print", str(addr)]
                else:
                    cmd = [tool, "-e", str(bin_path), "-f", "-C", "-i", str(addr)]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                text = (proc.stdout or "").strip()
                if not text:
                    continue
                lines = text.splitlines()
                func = lines[0] if lines else "?"
                loc = lines[1] if len(lines) > 1 else ""
                file_line = ""
                line_no = 0
                m = re.search(r"([^:]+):(\d+)", loc)
                if m:
                    file_line = m.group(1)
                    line_no = int(m.group(2))
                symbols.append(
                    {
                        "address": addr,
                        "function": func,
                        "file": file_line,
                        "line": line_no,
                        "raw": text[:500],
                        "inlined": "llvm" in tool and len(lines) > 2,
                    }
                )
                # Match into frames by empty path or native
                for fr in enriched:
                    if fr.get("path") in {"(native)", "", None} or not fr.get("line"):
                        if func and (fr.get("name") in {"?", ""} or fr.get("name") == func.split("(")[0]):
                            if file_line:
                                try:
                                    pref = str(
                                        Path(file_line).resolve().relative_to(workspace.resolve())
                                    ).replace("\\", "/")
                                except Exception:
                                    pref = file_line
                                fr["path"] = pref
                                fr["line"] = line_no or fr.get("line") or 0
                                fr["name"] = func.split("(")[0] or fr.get("name")
                                fr["symbolized"] = True
                            break
            except (OSError, subprocess.TimeoutExpired):
                continue
    return {
        "ok": True,
        "tool": tool or "",
        "binary": str(bin_path.relative_to(workspace.resolve())).replace("\\", "/") if bin_path else "",
        "frames": enriched,
        "symbols": symbols,
    }


def wasm_dwarf_info(workspace: Path, path: str) -> dict[str, Any]:
    """Inspect a .wasm for DWARF sections (custom sections / name)."""
    rel = (path or "").replace("\\", "/").strip()
    if not rel or ".." in Path(rel).parts:
        raise ValueError("invalid path")
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())
    if not target.is_file():
        raise FileNotFoundError(rel)
    data = target.read_bytes()
    if data[:4] != b"\x00asm":
        raise ValueError("not a WebAssembly module")
    version = struct.unpack_from("<I", data, 4)[0] if len(data) >= 8 else 0
    sections = []
    i = 8
    dwarf_names = {
        ".debug_info",
        ".debug_line",
        ".debug_abbrev",
        ".debug_str",
        ".debug_ranges",
        ".debug_loc",
        "name",
    }
    while i < len(data):
        try:
            sec_id = data[i]
            i += 1
            size, i = _read_leb128(data, i)
            payload = data[i : i + size]
            i += size
        except Exception:
            break
        name = f"id:{sec_id}"
        if sec_id == 0 and payload:
            # custom section: name leb + bytes
            try:
                nlen, j = _read_leb128(payload, 0)
                name = payload[j : j + nlen].decode("utf-8", errors="replace")
            except Exception:
                name = "custom"
        sections.append({"id": sec_id, "name": name, "size": size})
    dwarf = [s for s in sections if s["name"] in dwarf_names or str(s["name"]).startswith(".debug_")]
    return {
        "ok": True,
        "path": rel,
        "version": version,
        "sections": sections[:80],
        "dwarfSections": dwarf,
        "hasDwarf": bool(dwarf),
        "hint": (
            "Chrome DevTools / DWARF extension can map WASM→source when .debug_* sections present"
            if dwarf
            else "No DWARF custom sections — rebuild with -g / wasm-ld --debug"
        ),
        "launchHint": {
            "type": "wasm",
            "request": "attach",
            "host": "127.0.0.1",
            "port": 9222,
            "webRoot": "${workspaceFolder}",
            "skipFiles": ["**/node_modules/**"],
        },
    }


def _read_leb128(data: bytes, i: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while i < len(data):
        b = data[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, i


def jupyter_launch_config(workspace: Path, *, port: int = 8888, kernel: str = "python3") -> dict[str, Any]:
    """Suggested launch/attach config for Jupyter / IPython debugpy."""
    return {
        "name": f"Jupyter/IPython attach :{port}",
        "type": "jupyter",
        "request": "attach",
        "host": "127.0.0.1",
        "port": int(port),
        "justMyCode": False,
        "pathMappings": [{"localRoot": "${workspaceFolder}", "remoteRoot": "${workspaceFolder}"}],
        "jupyter": {"kernel": kernel, "hint": "Enable debugger in JupyterLab or %debug / debugpy.listen"},
        "env": {"PYDEVD_DISABLE_FILE_VALIDATION": "1"},
    }


def resolve_debug_adapter_cmd(cfg: dict[str, Any]) -> list[str]:
    """Resolve launch.json debugAdapter field to argv."""
    da = cfg.get("debugAdapter")
    if isinstance(da, list):
        return [str(x) for x in da if str(x).strip()]
    if isinstance(da, str) and da.strip():
        return [da.strip()]
    if isinstance(da, dict):
        cmd = da.get("command") or da.get("program")
        args = da.get("args") or []
        if cmd:
            return [str(cmd), *[str(a) for a in args]]
    # type-based defaults
    typ = str(cfg.get("type") or "").lower()
    if typ in {"python", "debugpy", "jupyter"}:
        return [os.environ.get("PYTHON", ""), "-m", "debugpy.adapter"]
    raise ValueError("debugAdapter command required for custom adapter")


def multi_root_path_mappings(
    workspace: Path,
    roots: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build pathMappings for multi-root workspaces (name→path folders)."""
    out: list[dict[str, str]] = []
    if roots:
        for r in roots:
            if not isinstance(r, dict):
                continue
            local = str(r.get("path") or r.get("localRoot") or "").strip()
            remote = str(r.get("remoteRoot") or r.get("remote") or local).strip()
            name = str(r.get("name") or "").strip()
            if local and remote:
                item = {"localRoot": local.replace("\\", "/"), "remoteRoot": remote.replace("\\", "/")}
                if name:
                    item["name"] = name
                out.append(item)
    # Always include primary workspace
    ws = str(workspace.resolve()).replace("\\", "/")
    if not any(m.get("localRoot") == ws for m in out):
        out.insert(0, {"localRoot": ws, "remoteRoot": ws, "name": "workspace"})
    # Discover sibling folders from .zintriq/workspace.json or .code-workspace
    for cand in (
        workspace / ".zintriq" / "workspace.json",
        workspace / "zintriq.code-workspace",
        workspace / f"{workspace.name}.code-workspace",
    ):
        if not cand.is_file():
            continue
        try:
            raw = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        folders = raw.get("folders") if isinstance(raw, dict) else None
        if isinstance(folders, list):
            for f in folders:
                if not isinstance(f, dict):
                    continue
                p = str(f.get("path") or "").strip()
                if not p:
                    continue
                abs_p = str((workspace / p).resolve() if not Path(p).is_absolute() else Path(p)).replace("\\", "/")
                if not any(m.get("localRoot") == abs_p for m in out):
                    out.append(
                        {
                            "localRoot": abs_p,
                            "remoteRoot": abs_p,
                            "name": str(f.get("name") or Path(abs_p).name),
                        }
                    )
    return out
