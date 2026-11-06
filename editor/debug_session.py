"""Debugger: Python (debugpy DAP) + Node (CDP). Multi-session, conditions, watches, eval."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from editor import debug_launch
from editor.dap_client import DapClient

_TIMELINE_MAX = 48

_LOCK = threading.RLock()  # re-entrant: status() snapshots may call list_breakpoints()
_SESSIONS: dict[str, "DebugSession"] = {}
_COMPOUNDS: dict[str, list[str]] = {}  # compound name → session ids
_CONDITION_HISTORY: list[str] = []
_BP_SYNC_WORKSPACE: Path | None = None
_BP_FILE_MTIME: float = 0.0
_BP_WATCH_THREAD: threading.Thread | None = None
_BP_WATCH_STOP = threading.Event()
_BP_SYNCING = False
_ACTIVE_ID: str | None = None

# path -> [{line, condition, hitCondition, logMessage, enabled, group}]
_BREAKPOINTS: dict[str, list[dict[str, Any]]] = {}
_BP_GROUPS: dict[str, bool] = {"default": True}  # group -> enabled
_WATCHES: list[str] = []
# [{id, name, accessType, condition}]
_DATA_BREAKPOINTS: list[dict[str, Any]] = []
_EXCEPTION_BREAKPOINTS: dict[str, bool] = {
    "raised": False,
    "uncaught": True,
}
# Extra DAP exceptionBreakpointFilters filter ids → enabled
_EXCEPTION_FILTERS: dict[str, bool] = {}
_PATH_MAPPINGS: list[dict[str, str]] = []
# CDP / Node skipFiles globs → Debugger.setBlackboxPatterns
_SKIP_FILES: list[str] = ["**/node_modules/**", "**/venv/**", "**/.venv/**", "**/site-packages/**"]
# Watch expression groups: {groupName: [expressions]}
_WATCH_GROUPS: dict[str, list[str]] = {"default": []}
_DATA_DIR: Path | None = None
_POSTMORTEM: dict[str, Any] | None = None
_LAYOUT: dict[str, Any] = {
    "showStack": True,
    "showVars": True,
    "showWatches": True,
    "showConsole": True,
}
_EVENT_LOG_MAX = 200
# Active session recording id → workspace path tracking
_REPLAY_ACTIVE: dict[str, str] = {}  # sessionId -> replayId
_READONLY_ATTACH = False  # global: force read-only for attach sessions


def _which(name: str) -> str | None:
    return shutil.which(name)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _valid_rel(rel: str) -> str:
    path = (rel or "").replace("\\", "/").strip()
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise ValueError("invalid path")
    return path


def adapters() -> dict[str, Any]:
    from editor import debug_extras

    py = False
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import debugpy; print(debugpy.__version__)"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        py = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        py = False
    return {
        "ok": True,
        "python": py,
        "node": bool(_which("node")),
        "debugpy": py,
        "rr": debug_extras.rr_available(),
        "reverse": debug_extras.reverse_capabilities(),
        "hint": None if py else "pip install debugpy  # required for Python DAP",
    }


def list_breakpoints() -> dict[str, list[dict[str, Any]]]:
    with _LOCK:
        return {k: [dict(x) for x in v] for k, v in _BREAKPOINTS.items()}


def list_breakpoint_lines() -> dict[str, list[int]]:
    with _LOCK:
        return {k: [int(x["line"]) for x in v] for k, v in _BREAKPOINTS.items()}


def list_watches() -> list[str]:
    with _LOCK:
        return list(_WATCHES)


def list_data_breakpoints() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(x) for x in _DATA_BREAKPOINTS]


def add_data_breakpoint(
    name: str,
    *,
    access_type: str = "write",
    condition: str = "",
) -> dict[str, Any]:
    nm = (name or "").strip()
    if not nm:
        raise ValueError("empty data breakpoint name")
    at = (access_type or "write").strip()
    if at not in {"read", "write", "readWrite"}:
        at = "write"
    with _LOCK:
        existing = next((x for x in _DATA_BREAKPOINTS if x["name"] == nm), None)
        if existing:
            existing["accessType"] = at
            existing["condition"] = str(condition or "").strip()
            item = dict(existing)
        else:
            item = {
                "id": uuid.uuid4().hex[:8],
                "name": nm,
                "accessType": at,
                "condition": str(condition or "").strip(),
            }
            _DATA_BREAKPOINTS.append(item)
        out = [dict(x) for x in _DATA_BREAKPOINTS]
    _persist()
    _apply_data_bps_active()
    return {"ok": True, "dataBreakpoint": item, "dataBreakpoints": out}


def remove_data_breakpoint(id_or_name: str) -> dict[str, Any]:
    key = (id_or_name or "").strip()
    with _LOCK:
        _DATA_BREAKPOINTS[:] = [
            x for x in _DATA_BREAKPOINTS if x.get("id") != key and x.get("name") != key
        ]
        out = [dict(x) for x in _DATA_BREAKPOINTS]
    _persist()
    _apply_data_bps_active()
    return {"ok": True, "dataBreakpoints": out}


def _apply_data_bps_active() -> None:
    sess = _get(_ACTIVE_ID, require_alive=False)
    if sess and sess.alive and sess.stopped:
        try:
            sess.apply_data_breakpoints()
        except Exception:
            pass


def _normalize_bp(item: dict[str, Any]) -> dict[str, Any]:
    group = str(item.get("group") or "default").strip() or "default"
    enabled = item.get("enabled")
    col = item.get("column")
    try:
        column = int(col) if col is not None and int(col) > 0 else None
    except (TypeError, ValueError):
        column = None
    return {
        "line": int(item["line"]),
        "column": column,
        "condition": str(item.get("condition") or "").strip(),
        "hitCondition": str(item.get("hitCondition") or "").strip(),
        "logMessage": str(item.get("logMessage") or "").strip(),
        "enabled": True if enabled is None else bool(enabled),
        "group": group,
    }


def _empty_bp(line: int, column: int | None = None) -> dict[str, Any]:
    return {
        "line": int(line),
        "column": int(column) if column and int(column) > 0 else None,
        "condition": "",
        "hitCondition": "",
        "logMessage": "",
        "enabled": True,
        "group": "default",
    }


def list_breakpoint_groups() -> dict[str, bool]:
    with _LOCK:
        groups = dict(_BP_GROUPS)
        for bps in _BREAKPOINTS.values():
            for bp in bps:
                g = str(bp.get("group") or "default")
                groups.setdefault(g, True)
        return groups


def set_breakpoint_group_enabled(group: str, enabled: bool) -> dict[str, Any]:
    g = (group or "default").strip() or "default"
    with _LOCK:
        _BP_GROUPS[g] = bool(enabled)
        out = dict(_BP_GROUPS)
        sessions = list(_SESSIONS.values())
    _persist()
    for sess in sessions:
        if sess.alive:
            for p in _all_bp_paths():
                try:
                    sess.apply_breakpoints(p)
                except Exception:
                    pass
    return {"ok": True, "groups": out}


def batch_breakpoints(
    *,
    enable: list[dict[str, Any]] | None = None,
    disable: list[dict[str, Any]] | None = None,
    group: str | None = None,
    set_group: str | None = None,
) -> dict[str, Any]:
    """Batch enable/disable breakpoints, optionally assign group."""
    with _LOCK:
        if enable:
            for item in enable:
                path = str(item.get("path") or "").replace("\\", "/")
                ln = int(item.get("line") or 0)
                for bp in _BREAKPOINTS.get(path) or []:
                    if bp["line"] == ln:
                        bp["enabled"] = True
                        if set_group:
                            bp["group"] = set_group
        if disable:
            for item in disable:
                path = str(item.get("path") or "").replace("\\", "/")
                ln = int(item.get("line") or 0)
                for bp in _BREAKPOINTS.get(path) or []:
                    if bp["line"] == ln:
                        bp["enabled"] = False
        if group is not None and set_group:
            # rename all in group → set_group? skip
            pass
        if group is not None and enable is None and disable is None and set_group is None:
            # enable/disable whole group via groups map
            pass
        bps = {k: [dict(x) for x in v] for k, v in _BREAKPOINTS.items()}
        sessions = list(_SESSIONS.values())
    _persist()
    for sess in sessions:
        if sess.alive:
            for p in list(bps.keys()):
                try:
                    sess.apply_breakpoints(p)
                except Exception:
                    pass
    return {"ok": True, "breakpoints": bps, "groups": list_breakpoint_groups()}


def set_breakpoint_meta(
    rel: str,
    line: int,
    *,
    enabled: bool | None = None,
    group: str | None = None,
) -> dict[str, Any]:
    path = _valid_rel(rel)
    ln = int(line)
    with _LOCK:
        cur = [dict(x) for x in (_BREAKPOINTS.get(path) or [])]
        existing = next((x for x in cur if x["line"] == ln), None)
        if not existing:
            existing = _empty_bp(ln)
            cur.append(existing)
            cur.sort(key=lambda x: x["line"])
        if enabled is not None:
            existing["enabled"] = bool(enabled)
        if group is not None:
            existing["group"] = str(group).strip() or "default"
            _BP_GROUPS.setdefault(existing["group"], True)
        _BREAKPOINTS[path] = cur
        bps = [dict(x) for x in cur]
        sessions = list(_SESSIONS.values())
    for sess in sessions:
        if sess.alive:
            sess.apply_breakpoints(path)
    _persist()
    return {"ok": True, "path": path, "breakpoints": bps, "groups": list_breakpoint_groups()}


def list_exception_breakpoints() -> dict[str, bool]:
    with _LOCK:
        out = dict(_EXCEPTION_BREAKPOINTS)
        out.update(_EXCEPTION_FILTERS)
        return out


def set_exception_breakpoints(
    *,
    raised: bool | None = None,
    uncaught: bool | None = None,
    filters: dict[str, bool] | None = None,
) -> dict[str, Any]:
    with _LOCK:
        if raised is not None:
            _EXCEPTION_BREAKPOINTS["raised"] = bool(raised)
        if uncaught is not None:
            _EXCEPTION_BREAKPOINTS["uncaught"] = bool(uncaught)
        if filters:
            for k, v in filters.items():
                key = str(k).strip()
                if not key or key in {"raised", "uncaught"}:
                    if key in {"raised", "uncaught"}:
                        _EXCEPTION_BREAKPOINTS[key] = bool(v)
                    continue
                _EXCEPTION_FILTERS[key] = bool(v)
        out = dict(_EXCEPTION_BREAKPOINTS)
        out.update(_EXCEPTION_FILTERS)
        sessions = list(_SESSIONS.values())
    _persist()
    for sess in sessions:
        if sess.alive:
            try:
                sess.apply_exception_breakpoints()
            except Exception:
                pass
    return {"ok": True, "exceptionBreakpoints": out, "filters": out}


def list_skip_files() -> list[str]:
    with _LOCK:
        return list(_SKIP_FILES)


def set_skip_files(patterns: list[Any]) -> dict[str, Any]:
    clean = [str(x).strip() for x in (patterns or []) if str(x).strip()]
    with _LOCK:
        _SKIP_FILES[:] = clean
        out = list(_SKIP_FILES)
        sessions = list(_SESSIONS.values())
    _persist()
    for sess in sessions:
        if sess.alive and hasattr(sess, "apply_skip_files"):
            try:
                sess.apply_skip_files()  # type: ignore[attr-defined]
            except Exception:
                pass
    return {"ok": True, "skipFiles": out}


def list_watch_groups() -> dict[str, list[str]]:
    with _LOCK:
        groups = {k: list(v) for k, v in _WATCH_GROUPS.items()}
        # Ensure flat watches appear in default
        groups.setdefault("default", [])
        for w in _WATCHES:
            if w not in groups["default"] and not any(w in vs for k, vs in groups.items() if k != "default"):
                groups["default"].append(w)
        return groups


def set_watch_groups(groups: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, list[str]] = {}
    flat: list[str] = []
    for name, exprs in (groups or {}).items():
        g = str(name or "default").strip() or "default"
        if not isinstance(exprs, list):
            continue
        items = []
        for e in exprs:
            s = str(e).strip()
            if s and s not in items:
                items.append(s)
                if s not in flat:
                    flat.append(s)
        clean[g] = items
    if "default" not in clean:
        clean["default"] = []
    with _LOCK:
        _WATCH_GROUPS.clear()
        _WATCH_GROUPS.update(clean)
        _WATCHES[:] = flat
        out = {k: list(v) for k, v in _WATCH_GROUPS.items()}
    _persist()
    _refresh_active_watches()
    return {"ok": True, "watchGroups": out, "watches": list(flat)}


def add_watch_to_group(expression: str, group: str = "default") -> dict[str, Any]:
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("empty watch")
    g = (group or "default").strip() or "default"
    with _LOCK:
        _WATCH_GROUPS.setdefault(g, [])
        if expr not in _WATCH_GROUPS[g]:
            _WATCH_GROUPS[g].append(expr)
        if expr not in _WATCHES:
            _WATCHES.append(expr)
        out = {k: list(v) for k, v in _WATCH_GROUPS.items()}
    _persist()
    _refresh_active_watches()
    return {"ok": True, "watchGroups": out, "watches": list_watches()}


def list_path_mappings() -> list[dict[str, str]]:
    with _LOCK:
        return [dict(x) for x in _PATH_MAPPINGS]


def set_path_mappings(mappings: list[Any]) -> dict[str, Any]:
    clean: list[dict[str, str]] = []
    for item in mappings or []:
        if not isinstance(item, dict):
            continue
        local = str(item.get("localRoot") or item.get("local") or item.get("path") or "").strip()
        remote = str(item.get("remoteRoot") or item.get("remote") or local).strip()
        if local and remote:
            entry = {"localRoot": local.replace("\\", "/"), "remoteRoot": remote.replace("\\", "/")}
            if item.get("name"):
                entry["name"] = str(item["name"]).strip()
            clean.append(entry)
    with _LOCK:
        _PATH_MAPPINGS[:] = clean
        out = [dict(x) for x in _PATH_MAPPINGS]
    _persist()
    return {"ok": True, "pathMappings": out}


def sync_multi_root_mappings(workspace: Path, roots: list[Any] | None = None) -> dict[str, Any]:
    from editor import debug_advanced

    maps = debug_advanced.multi_root_path_mappings(workspace, roots=roots)  # type: ignore[arg-type]
    return set_path_mappings(maps)


def _map_remote_to_local(path: str) -> str:
    p = (path or "").replace("\\", "/")
    with _LOCK:
        mappings = [dict(x) for x in _PATH_MAPPINGS]
    for m in mappings:
        remote = m["remoteRoot"].rstrip("/")
        local = m["localRoot"].rstrip("/")
        if p == remote or p.startswith(remote + "/"):
            return local + p[len(remote) :]
    return p


def remember_condition(expr: str) -> None:
    text = (expr or "").strip()
    if not text:
        return
    with _LOCK:
        if text in _CONDITION_HISTORY:
            _CONDITION_HISTORY.remove(text)
        _CONDITION_HISTORY.insert(0, text)
        del _CONDITION_HISTORY[40:]
    _persist()


def list_condition_history() -> list[str]:
    with _LOCK:
        return list(_CONDITION_HISTORY)


def _vscode_breakpoints_path(workspace: Path) -> Path:
    return workspace.resolve() / ".vscode" / "breakpoints.json"


def sync_breakpoints_to_vscode(workspace: Path | None = None) -> None:
    global _BP_SYNCING, _BP_FILE_MTIME
    ws = workspace or _BP_SYNC_WORKSPACE
    if ws is None:
        return
    from editor import debug_extras

    path = _vscode_breakpoints_path(ws)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = debug_extras.breakpoints_to_vscode(list_breakpoints())
        _BP_SYNCING = True
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        _BP_FILE_MTIME = path.stat().st_mtime
    except OSError:
        pass
    finally:
        _BP_SYNCING = False


def _watch_breakpoints_file() -> None:
    global _BP_FILE_MTIME
    while not _BP_WATCH_STOP.wait(1.0):
        ws = _BP_SYNC_WORKSPACE
        if ws is None or _BP_SYNCING:
            continue
        path = _vscode_breakpoints_path(ws)
        if not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime <= _BP_FILE_MTIME:
            continue
        _BP_FILE_MTIME = mtime
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            import_breakpoints_vscode(raw, merge=False)
        except Exception:
            pass


def enable_breakpoint_file_sync(workspace: Path) -> None:
    global _BP_SYNC_WORKSPACE, _BP_WATCH_THREAD, _BP_FILE_MTIME
    _BP_SYNC_WORKSPACE = workspace.resolve()
    path = _vscode_breakpoints_path(_BP_SYNC_WORKSPACE)
    if path.is_file():
        try:
            _BP_FILE_MTIME = path.stat().st_mtime
        except OSError:
            _BP_FILE_MTIME = 0.0
    if _BP_WATCH_THREAD is None or not _BP_WATCH_THREAD.is_alive():
        _BP_WATCH_STOP.clear()
        _BP_WATCH_THREAD = threading.Thread(
            target=_watch_breakpoints_file, name="bp-file-watch", daemon=True
        )
        _BP_WATCH_THREAD.start()
    sync_breakpoints_to_vscode(_BP_SYNC_WORKSPACE)


def _persist() -> None:
    if not _DATA_DIR:
        return
    path = Path(_DATA_DIR) / "debug_state.json"
    with _LOCK:
        payload = {
            "breakpoints": {k: [dict(x) for x in v] for k, v in _BREAKPOINTS.items()},
            "watches": list(_WATCHES),
            "watchGroups": {k: list(v) for k, v in _WATCH_GROUPS.items()},
            "dataBreakpoints": [dict(x) for x in _DATA_BREAKPOINTS],
            "exceptionBreakpoints": dict(_EXCEPTION_BREAKPOINTS),
            "exceptionFilters": dict(_EXCEPTION_FILTERS),
            "pathMappings": [dict(x) for x in _PATH_MAPPINGS],
            "skipFiles": list(_SKIP_FILES),
            "breakpointGroups": dict(_BP_GROUPS),
            "layout": dict(_LAYOUT),
            "conditionHistory": list(_CONDITION_HISTORY),
        }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    if _BP_SYNC_WORKSPACE is not None:
        sync_breakpoints_to_vscode(_BP_SYNC_WORKSPACE)


def load_persisted(data_dir: Path) -> None:
    global _DATA_DIR
    _DATA_DIR = Path(data_dir)
    path = _DATA_DIR / "debug_state.json"
    if not path.is_file():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    with _LOCK:
        bps = raw.get("breakpoints") or {}
        if isinstance(bps, dict):
            _BREAKPOINTS.clear()
            for k, v in bps.items():
                if not isinstance(v, list):
                    continue
                clean = []
                for item in v:
                    if isinstance(item, dict) and int(item.get("line") or 0) >= 1:
                        clean.append(_normalize_bp(item))
                    elif isinstance(item, int) and item >= 1:
                        clean.append(_empty_bp(item))
                if clean:
                    _BREAKPOINTS[str(k).replace("\\", "/")] = clean
        watches = raw.get("watches") or []
        if isinstance(watches, list):
            _WATCHES[:] = [str(x).strip() for x in watches if str(x).strip()]
        data_bps = raw.get("dataBreakpoints") or []
        if isinstance(data_bps, list):
            _DATA_BREAKPOINTS.clear()
            for item in data_bps:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                _DATA_BREAKPOINTS.append(
                    {
                        "id": str(item.get("id") or uuid.uuid4().hex[:8]),
                        "name": name,
                        "accessType": str(item.get("accessType") or "write"),
                        "condition": str(item.get("condition") or "").strip(),
                    }
                )
        exc = raw.get("exceptionBreakpoints") or {}
        if isinstance(exc, dict):
            if "raised" in exc:
                _EXCEPTION_BREAKPOINTS["raised"] = bool(exc["raised"])
            if "uncaught" in exc:
                _EXCEPTION_BREAKPOINTS["uncaught"] = bool(exc["uncaught"])
        ef = raw.get("exceptionFilters") or {}
        if isinstance(ef, dict):
            _EXCEPTION_FILTERS.clear()
            for k, v in ef.items():
                _EXCEPTION_FILTERS[str(k)] = bool(v)
        maps = raw.get("pathMappings") or []
        if isinstance(maps, list):
            _PATH_MAPPINGS.clear()
            for item in maps:
                if isinstance(item, dict):
                    local = str(item.get("localRoot") or "").strip()
                    remote = str(item.get("remoteRoot") or "").strip()
                    if local and remote:
                        entry = {
                            "localRoot": local.replace("\\", "/"),
                            "remoteRoot": remote.replace("\\", "/"),
                        }
                        if item.get("name"):
                            entry["name"] = str(item["name"])
                        _PATH_MAPPINGS.append(entry)
        skip = raw.get("skipFiles") or []
        if isinstance(skip, list) and skip:
            _SKIP_FILES[:] = [str(x).strip() for x in skip if str(x).strip()]
        wg = raw.get("watchGroups") or {}
        if isinstance(wg, dict) and wg:
            _WATCH_GROUPS.clear()
            for k, v in wg.items():
                if isinstance(v, list):
                    _WATCH_GROUPS[str(k)] = [str(x).strip() for x in v if str(x).strip()]
            _WATCH_GROUPS.setdefault("default", [])
        groups = raw.get("breakpointGroups") or {}
        if isinstance(groups, dict):
            _BP_GROUPS.clear()
            for k, v in groups.items():
                _BP_GROUPS[str(k)] = bool(v)
            _BP_GROUPS.setdefault("default", True)
        layout = raw.get("layout") or {}
        if isinstance(layout, dict):
            for key in _LAYOUT:
                if key in layout:
                    _LAYOUT[key] = bool(layout[key])
        hist = raw.get("conditionHistory") or []
        if isinstance(hist, list):
            _CONDITION_HISTORY.clear()
            _CONDITION_HISTORY.extend(str(x) for x in hist if str(x).strip())


def get_layout() -> dict[str, Any]:
    with _LOCK:
        return dict(_LAYOUT)


def set_layout(layout: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        for key in _LAYOUT:
            if key in (layout or {}):
                _LAYOUT[key] = bool(layout[key])
        out = dict(_LAYOUT)
    _persist()
    return {"ok": True, "layout": out}


def set_breakpoints(rel: str, items: list[Any]) -> dict[str, Any]:
    path = _valid_rel(rel)
    parsed: list[dict[str, Any]] = []
    for item in items or []:
        if isinstance(item, int):
            parsed.append(_empty_bp(item))
        elif isinstance(item, dict):
            ln = int(item.get("line") or 0)
            if ln < 1:
                continue
            parsed.append(_normalize_bp({**item, "line": ln}))
    # Allow multiple breakpoints per line when columns differ
    by_key: dict[tuple[int, int | None], dict[str, Any]] = {}
    for p in parsed:
        by_key[(int(p["line"]), p.get("column"))] = p
    clean = [by_key[k] for k in sorted(by_key, key=lambda x: (x[0], x[1] or 0))]
    with _LOCK:
        if clean:
            _BREAKPOINTS[path] = clean
        else:
            _BREAKPOINTS.pop(path, None)
        sessions = list(_SESSIONS.values())
    for sess in sessions:
        if sess.alive:
            sess.apply_breakpoints(path)
    _persist()
    return {"ok": True, "path": path, "breakpoints": clean, "lines": [b["line"] for b in clean]}


def set_breakpoint_column(rel: str, line: int, column: int | None) -> dict[str, Any]:
    """Set/clear column for a line breakpoint (column selector)."""
    path = _valid_rel(rel)
    ln = int(line)
    col = int(column) if column is not None and int(column) > 0 else None
    with _LOCK:
        cur = [dict(x) for x in (_BREAKPOINTS.get(path) or [])]
        existing = next((x for x in cur if x["line"] == ln and (x.get("column") in {None, col} or col is None)), None)
        if not existing:
            existing = _empty_bp(ln, col)
            cur.append(existing)
            cur.sort(key=lambda x: (x["line"], x.get("column") or 0))
        else:
            existing["column"] = col
        _BREAKPOINTS[path] = cur
        bps = [dict(x) for x in cur]
        sessions = list(_SESSIONS.values())
    for sess in sessions:
        if sess.alive:
            sess.apply_breakpoints(path)
    _persist()
    return {"ok": True, "path": path, "breakpoints": bps}


def toggle_breakpoint(
    rel: str,
    line: int,
    condition: str | None = None,
    hit_condition: str | None = None,
    log_message: str | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    path = _valid_rel(rel)
    ln = int(line)
    col = int(column) if column is not None and int(column) > 0 else None
    with _LOCK:
        cur = [dict(x) for x in (_BREAKPOINTS.get(path) or [])]
        if col is not None:
            existing = next((x for x in cur if x["line"] == ln and x.get("column") == col), None)
        else:
            existing = next((x for x in cur if x["line"] == ln and not x.get("column")), None)
            if not existing:
                existing = next((x for x in cur if x["line"] == ln), None)
        touching = condition is not None or hit_condition is not None or log_message is not None
        if existing and not touching:
            if col is not None:
                cur = [x for x in cur if not (x["line"] == ln and x.get("column") == col)]
            else:
                cur = [x for x in cur if x["line"] != ln]
            enabled = False
        elif existing and touching:
            if condition is not None:
                existing["condition"] = str(condition).strip()
            if hit_condition is not None:
                existing["hitCondition"] = str(hit_condition).strip()
            if log_message is not None:
                existing["logMessage"] = str(log_message).strip()
            if col is not None:
                existing["column"] = col
            enabled = True
        else:
            bp = _empty_bp(ln, col)
            if condition is not None:
                bp["condition"] = str(condition).strip()
            if hit_condition is not None:
                bp["hitCondition"] = str(hit_condition).strip()
            if log_message is not None:
                bp["logMessage"] = str(log_message).strip()
            cur.append(bp)
            cur.sort(key=lambda x: (x["line"], x.get("column") or 0))
            enabled = True
        if cur:
            _BREAKPOINTS[path] = cur
        else:
            _BREAKPOINTS.pop(path, None)
        lines = [x["line"] for x in cur]
        bps = [dict(x) for x in cur]
        sessions = list(_SESSIONS.values())
    for sess in sessions:
        if sess.alive:
            sess.apply_breakpoints(path)
    _persist()
    return {
        "ok": True,
        "path": path,
        "lines": lines,
        "breakpoints": bps,
        "enabled": enabled,
    }


def set_breakpoint_condition(rel: str, line: int, condition: str) -> dict[str, Any]:
    cond = str(condition or "")
    if cond.strip():
        remember_condition(cond)
    return toggle_breakpoint(rel, line, condition=cond)


def set_breakpoint_hit_condition(rel: str, line: int, hit_condition: str) -> dict[str, Any]:
    """Set DAP hitCondition (e.g. '5', '>=3'). Empty clears."""
    path = _valid_rel(rel)
    ln = int(line)
    with _LOCK:
        cur = [dict(x) for x in (_BREAKPOINTS.get(path) or [])]
        existing = next((x for x in cur if x["line"] == ln), None)
        if not existing:
            bp = _empty_bp(ln)
            bp["hitCondition"] = str(hit_condition or "").strip()
            cur.append(bp)
            cur.sort(key=lambda x: x["line"])
        else:
            existing["hitCondition"] = str(hit_condition or "").strip()
        _BREAKPOINTS[path] = cur
        bps = [dict(x) for x in cur]
        sessions = list(_SESSIONS.values())
    for sess in sessions:
        if sess.alive:
            sess.apply_breakpoints(path)
    _persist()
    return {"ok": True, "path": path, "breakpoints": bps, "lines": [b["line"] for b in bps]}


def set_breakpoint_log_message(rel: str, line: int, log_message: str) -> dict[str, Any]:
    """Set DAP logMessage (logpoint). Empty clears."""
    path = _valid_rel(rel)
    ln = int(line)
    with _LOCK:
        cur = [dict(x) for x in (_BREAKPOINTS.get(path) or [])]
        existing = next((x for x in cur if x["line"] == ln), None)
        if not existing:
            bp = _empty_bp(ln)
            bp["logMessage"] = str(log_message or "").strip()
            cur.append(bp)
            cur.sort(key=lambda x: x["line"])
        else:
            existing["logMessage"] = str(log_message or "").strip()
        _BREAKPOINTS[path] = cur
        bps = [dict(x) for x in cur]
        sessions = list(_SESSIONS.values())
    for sess in sessions:
        if sess.alive:
            sess.apply_breakpoints(path)
    _persist()
    return {"ok": True, "path": path, "breakpoints": bps, "lines": [b["line"] for b in bps]}


def add_watch(expression: str) -> dict[str, Any]:
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("empty watch")
    with _LOCK:
        if expr not in _WATCHES:
            _WATCHES.append(expr)
        watches = list(_WATCHES)
    _persist()
    _refresh_active_watches()
    return {"ok": True, "watches": watches}


def remove_watch(expression: str) -> dict[str, Any]:
    expr = (expression or "").strip()
    with _LOCK:
        _WATCHES[:] = [w for w in _WATCHES if w != expr]
        watches = list(_WATCHES)
    _persist()
    return {"ok": True, "watches": watches}


def set_watches(expressions: list[str]) -> dict[str, Any]:
    clean = []
    seen: set[str] = set()
    for e in expressions or []:
        s = str(e).strip()
        if s and s not in seen:
            seen.add(s)
            clean.append(s)
    with _LOCK:
        _WATCHES[:] = clean
    _persist()
    _refresh_active_watches()
    return {"ok": True, "watches": list(clean)}


def _refresh_active_watches() -> None:
    sess = _get(_ACTIVE_ID, require_alive=False)
    if sess and sess.alive and sess.stopped:
        try:
            sess.refresh_watches()
        except Exception:
            pass


def status(session_id: str | None = None, *, workspace: Path | None = None) -> dict[str, Any]:
    with _LOCK:
        active = _ACTIVE_ID
        sessions = [s.snapshot() for s in _SESSIONS.values()]
        sess_ws = None
        for s in _SESSIONS.values():
            if hasattr(s, "workspace"):
                sess_ws = s.workspace
                break
    ws = workspace or sess_ws
    launch_info = None
    if ws is not None:
        doc = debug_launch.load(ws)
        launch_info = {
            "path": doc.get("path") or ".zintriq/launch.json",
            "configurations": doc.get("configurations") or [],
            "compounds": doc.get("compounds") or [],
        }
    base = {
        "ok": True,
        "adapters": adapters(),
        "breakpoints": list_breakpoints(),
        "breakpointLines": list_breakpoint_lines(),
        "watches": list_watches(),
        "dataBreakpoints": list_data_breakpoints(),
        "exceptionBreakpoints": list_exception_breakpoints(),
        "pathMappings": list_path_mappings(),
        "skipFiles": list_skip_files(),
        "watchGroups": list_watch_groups(),
        "breakpointGroups": list_breakpoint_groups(),
        "conditionHistory": list_condition_history(),
        "compounds": {k: list(v) for k, v in _COMPOUNDS.items()},
        "layout": get_layout(),
        "activeSessionId": active,
        "sessions": sessions,
        "launch": launch_info,
        "postmortem": _POSTMORTEM,
        "readonlyAttach": _READONLY_ATTACH,
        "coverage": None,
        "reverse": None,
        "bpHits": None,
        "pinned": [],
        "functionBreakpoints": [],
        "catchpoints": None,
    }
    try:
        from editor import debug_extras, debug_features

        base["coverage"] = debug_extras.get_coverage()
        base["reverse"] = debug_extras.reverse_capabilities()
        base["profiles"] = debug_extras.list_profiles()
        base["bpHits"] = debug_features.bp_hit_stats()
        base["instructionBreakpoints"] = debug_features.list_instruction_breakpoints()
        base["pinned"] = debug_features.list_pinned_vars()
        base["functionBreakpoints"] = debug_features.list_function_breakpoints()
        base["catchpoints"] = debug_features.get_catchpoints().get("catchpoints")
    except Exception:
        pass
    if session_id:
        sess = _get(session_id, require_alive=False)
        if sess:
            return {**base, **sess.snapshot()}
    if active and _SESSIONS.get(active):
        return {**base, **_SESSIONS[active].snapshot()}
    return {**base, "running": bool(sessions), "stopped": False}


def start_compound(
    workspace: Path,
    compound_name: str,
    *,
    current_file: str = "",
) -> dict[str, Any]:
    """Launch all configurations in a compound; tracks ids for stopAll."""
    enable_breakpoint_file_sync(workspace)
    compound = debug_launch.resolve_compound(workspace, compound_name)
    started: list[str] = []
    stop_all = bool(compound.get("stopAll", True)) if isinstance(compound, dict) else True
    # resolve_compound returns name+configurations; stopAll may be on raw doc
    doc = debug_launch.load(workspace)
    for c in doc.get("compounds") or []:
        if str(c.get("name")) == compound_name:
            stop_all = bool(c.get("stopAll", True))
            break
    for name in compound.get("configurations") or []:
        last = start(workspace, current_file or None, config_name=str(name))
        sid = last.get("sessionId") or last.get("activeSessionId")
        if sid:
            started.append(str(sid))
    with _LOCK:
        _COMPOUNDS[compound_name] = list(started)
    out = status(workspace=workspace)
    out["compound"] = {
        "name": compound_name,
        "sessionIds": started,
        "stopAll": stop_all,
    }
    return out


def stop_compound(compound_name: str) -> dict[str, Any]:
    with _LOCK:
        ids = list(_COMPOUNDS.pop(compound_name, []))
    for sid in ids:
        stop(sid)
    return status()


def start(
    workspace: Path,
    rel: str | None = None,
    *,
    config_name: str | None = None,
    config: dict[str, Any] | None = None,
    compound_name: str | None = None,
) -> dict[str, Any]:
    global _ACTIVE_ID
    enable_breakpoint_file_sync(workspace)
    if compound_name:
        return start_compound(workspace, compound_name, current_file=rel or "")
    # Allow compound via config_name match
    if config_name and not config:
        try:
            debug_launch.resolve_compound(workspace, config_name)
            return start_compound(workspace, config_name, current_file=rel or "")
        except KeyError:
            pass
    current = (rel or "").replace("\\", "/").strip()
    if current:
        current = _valid_rel(current)
    cfg = None
    if config_name or config:
        cfg = debug_launch.resolve(
            workspace, name=config_name, config=config, current_file=current
        )
        if cfg.get("preLaunchTask"):
            from editor import debug_tasks

            try:
                debug_tasks.run_pre_launch_task(workspace, str(cfg["preLaunchTask"]))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"preLaunchTask failed: {exc}") from exc
        if cfg.get("reverse") == "rr":
            return start_rr(workspace, current or cfg.get("program") or "", cfg=cfg)
        if cfg.get("skipFiles"):
            set_skip_files(list(cfg["skipFiles"]))
        typ_early = str(cfg.get("type") or "").lower()
        if typ_early in {"custom", "cppdbg", "lldb", "gdb"} or cfg.get("debugAdapter"):
            return start_custom_adapter(workspace, cfg, current_file=current)
        if typ_early == "jupyter":
            # Jupyter uses debugpy attach under the hood
            if cfg.get("pathMappings"):
                set_path_mappings(cfg["pathMappings"])
            return attach(
                workspace,
                engine="python",
                host=str(cfg.get("host") or "127.0.0.1"),
                port=int(cfg.get("port") or 5678),
                path=current or "(jupyter)",
                path_mappings=cfg.get("pathMappings"),
                remote_meta={"jupyter": cfg.get("jupyter") or {}},
            )
        if typ_early == "wasm":
            # Attach Chrome/Node CDP for WASM + DWARF tooling hints
            if cfg.get("pathMappings"):
                set_path_mappings(cfg["pathMappings"])
            return attach(
                workspace,
                engine="node",
                host=str(cfg.get("host") or "127.0.0.1"),
                port=int(cfg.get("port") or 9222),
                path=current or "(wasm)",
                path_mappings=cfg.get("pathMappings"),
                remote_meta={"wasm": True},
            )
        if cfg["request"] == "attach":
            if cfg.get("pathMappings"):
                set_path_mappings(cfg["pathMappings"])
            # Optional: ensure SSH/docker tunnel hint recorded on session via env
            return attach(
                workspace,
                engine=cfg["type"],
                host=cfg["host"],
                port=int(cfg["port"]),
                path=current or "(remote)",
                path_mappings=cfg.get("pathMappings"),
                remote_meta={"ssh": cfg.get("ssh") or {}, "docker": cfg.get("docker") or {}},
            )
        module = str(cfg.get("module") or "").strip()
        program = cfg["program"] or current
        if not program and not module:
            raise ValueError("launch configuration missing program/module")
        if module:
            if current:
                path = current
                target = (workspace / current).resolve()
            elif program and not str(program).startswith("(") and not Path(str(program)).name == module:
                try:
                    if Path(program).is_absolute():
                        target = Path(program).resolve()
                        path = str(target)
                    else:
                        path = _valid_rel(program)
                        target = (workspace / path).resolve()
                except Exception:
                    path = f"(module:{module})"
                    target = workspace / ".zintriq" / "_module_launch.py"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.is_file():
                        target.write_text("# zintriq module launch\n", encoding="utf-8")
            else:
                path = f"(module:{module})"
                target = workspace / ".zintriq" / "_module_launch.py"
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.is_file():
                    target.write_text("# zintriq module launch\n", encoding="utf-8")
        elif Path(program).is_absolute():
            target = Path(program).resolve()
            try:
                path = str(target.relative_to(workspace.resolve())).replace("\\", "/")
            except ValueError:
                path = str(target)
        else:
            path = _valid_rel(program)
            target = (workspace / path).resolve()
            target.relative_to(workspace.resolve())
    else:
        if not current:
            raise ValueError("path or launch configuration required")
        path = current
        target = (workspace / path).resolve()
        target.relative_to(workspace.resolve())
        module = ""
    if not module and not target.is_file():
        raise FileNotFoundError(path)
    ext = target.suffix.lower() if target.is_file() else ".py"
    sid = uuid.uuid4().hex[:10]
    launch_kwargs: dict[str, Any] = {}
    if cfg:
        from editor import debug_features

        env_raw = dict(cfg.get("env") or {})
        env_resolved = debug_features.vault_resolve_env(workspace, env_raw)
        launch_kwargs = {
            "program_args": list(cfg.get("args") or []),
            "env": env_resolved,
            "cwd": Path(cfg["cwd"]) if cfg.get("cwd") else workspace,
            "stop_on_entry": bool(cfg.get("stopOnEntry", True)),
            "just_my_code": bool(cfg.get("justMyCode", True)),
            "config_name": str(cfg.get("name") or ""),
            "module": str(cfg.get("module") or ""),
            "sub_process": bool(cfg.get("subProcess", True)),
        }
        if cfg.get("pathMappings"):
            set_path_mappings(cfg["pathMappings"])
            launch_kwargs["path_mappings"] = list(cfg["pathMappings"])
        typ = cfg["type"]
        # Extension-contributed adapter types → custom DAP
        if typ not in {"python", "node", "debugpy", "jupyter", "wasm"} and (
            cfg.get("debugAdapter") or cfg.get("hardware") or cfg.get("extensionId")
        ):
            return start_custom_adapter(workspace, {**cfg, "env": env_resolved}, current_file=path)
    else:
        from editor import debug_platform

        lang = debug_platform.detect_language(path)
        if lang and lang.get("type") == "custom":
            return start_custom_adapter(
                workspace,
                {
                    "name": f"{lang['label']}: {path}",
                    "type": "custom",
                    "request": "launch",
                    "program": path,
                    "cwd": str(workspace),
                    "debugAdapter": lang.get("adapter"),
                },
                current_file=path,
            )
        typ = "python" if ext == ".py" else "node" if ext in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".wasm"} else ""
        module = ""
    if typ == "python" or (not typ and ext == ".py"):
        sess: DebugSession = PythonDapSession(sid, workspace, path, target, **launch_kwargs)
    elif typ == "node" or (not typ and ext in {".js", ".mjs", ".cjs", ".wasm"}):
        sess = NodeCdpSession(sid, workspace, path, target, **launch_kwargs)
    else:
        raise RuntimeError("debugger supports .py/.js and custom/hardware adapters via launch.json")
    sess.start()
    if hasattr(sess, "_event_push"):
        try:
            sess._event_push("launch", path=path, config=str(getattr(sess, "config_name", "") or ""))  # type: ignore[attr-defined]
        except Exception:
            pass
    with _LOCK:
        _SESSIONS[sid] = sess
        _ACTIVE_ID = sid
    return status(sid, workspace=workspace)


def start_custom_adapter(
    workspace: Path,
    cfg: dict[str, Any],
    *,
    current_file: str = "",
) -> dict[str, Any]:
    """Launch a user-provided DAP adapter (debugAdapter command) over stdio."""
    global _ACTIVE_ID
    from editor import debug_advanced

    enable_breakpoint_file_sync(workspace)
    cmd = debug_advanced.resolve_debug_adapter_cmd(cfg)
    # Fix empty python placeholder
    if cmd and not cmd[0]:
        cmd[0] = sys.executable
    sid = uuid.uuid4().hex[:10]
    program = str(cfg.get("program") or current_file or "").strip()
    if program in {"${file}", "${fileBasename}"}:
        program = current_file
    rel = program.replace("\\", "/") if program else "(custom)"
    if rel and not rel.startswith("(") and not Path(rel).is_absolute():
        try:
            rel = _valid_rel(rel)
        except ValueError:
            rel = "(custom)"
    target = (workspace / rel).resolve() if not rel.startswith("(") else workspace / ".zintriq" / "_custom"
    sess = CustomDapSession(
        sid,
        workspace,
        rel,
        target,
        adapter_cmd=cmd,
        launch_args=dict(cfg),
        config_name=str(cfg.get("name") or "custom"),
    )
    sess.start()
    sess._event_push("launch", path=rel, adapter=" ".join(cmd[:3]))
    with _LOCK:
        _SESSIONS[sid] = sess
        _ACTIVE_ID = sid
    return status(sid, workspace=workspace)


def attach(
    workspace: Path,
    *,
    engine: str,
    host: str = "127.0.0.1",
    port: int,
    path: str = "(remote)",
    path_mappings: list[Any] | None = None,
    remote_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach to a remote debugpy listener or Node inspector port."""
    global _ACTIVE_ID
    eng = (engine or "").strip().lower()
    h = (host or "127.0.0.1").strip() or "127.0.0.1"
    p = int(port)
    if p < 1 or p > 65535:
        raise ValueError("invalid port")
    meta = remote_meta or {}
    hint = ""
    if meta.get("ssh") and isinstance(meta.get("ssh"), dict):
        ssh_cfg = dict(meta["ssh"])
        # Auto-tunnel unless explicitly disabled
        if ssh_cfg.get("autoTunnel", True) is not False and ssh_cfg.get("host"):
            from editor import debug_extras

            try:
                tun = debug_extras.ssh_start_tunnel(ssh_cfg)
                hint = f"ssh tunnel pid={tun.get('pid')} local={tun.get('localPort')}"
                if tun.get("localPort"):
                    p = int(tun["localPort"])
            except Exception as exc:  # noqa: BLE001
                hint = f"ssh tunnel failed: {exc}"
    if meta.get("docker") and (not path_mappings or meta.get("dockerInspect")):
        from editor import debug_extras

        dock = meta["docker"] if isinstance(meta.get("docker"), dict) else {}
        container = str(dock.get("container") or "")
        if container:
            try:
                inspected = debug_extras.docker_path_mappings(container, workspace)
                if inspected.get("pathMappings") and not path_mappings:
                    path_mappings = inspected["pathMappings"]
                if inspected.get("hostPort") and (not port or port == int(dock.get("port") or 0)):
                    p = int(inspected["hostPort"])
                hint = f"docker inspect {container}: {len(inspected.get('pathMappings') or [])} mounts"
            except Exception as exc:  # noqa: BLE001
                hint = f"docker inspect failed: {exc}"
    if path_mappings is not None:
        set_path_mappings(path_mappings)
    label = (path or "(remote)").replace("\\", "/").strip() or "(remote)"
    sid = uuid.uuid4().hex[:10]
    mappings = list_path_mappings()
    if meta.get("ssh"):
        ssh = meta["ssh"]
        hint = (
            f"Ensure SSH tunnel: ssh -L {ssh.get('localPort') or p}:127.0.0.1:"
            f"{ssh.get('remotePort') or p} {ssh.get('host') or 'user@host'}"
        )
    elif meta.get("docker") and not hint:
        dock = meta["docker"]
        hint = (
            f"Ensure docker port publish/forward for container "
            f"{dock.get('container') or '?'} :{dock.get('port') or p}"
        )
    readonly = bool(_READONLY_ATTACH) or bool((meta or {}).get("readonly"))
    if eng in {"python", "debugpy", "dap"}:
        if not adapters()["python"]:
            raise RuntimeError("debugpy not installed (pip install debugpy)")
        sess: DebugSession = PythonDapSession(
            sid,
            workspace,
            label,
            workspace / ".zintriq" / "_attach.py",
            attach_host=h,
            attach_port=p,
            path_mappings=mappings,
        )
        sess.readonly = readonly  # type: ignore[attr-defined]
    elif eng in {"node", "js", "cdp"}:
        if not adapters()["node"]:
            raise RuntimeError("node not found on PATH")
        sess = NodeCdpSession(
            sid,
            workspace,
            label,
            workspace / ".zintriq" / "_attach.js",
            attach_host=h,
            attach_port=p,
            path_mappings=mappings,
        )
        sess.readonly = readonly  # type: ignore[attr-defined]
    else:
        raise RuntimeError("engine must be python or node")
    if hint:
        sess.error = hint
    sess.start()
    with _LOCK:
        _SESSIONS[sid] = sess
        _ACTIVE_ID = sid
    return status(sid, workspace=workspace)


def select_frame(frame_id: Any, *, session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    sess.select_frame(frame_id)
    return status(sess.id)


def select_thread(thread_id: Any, *, session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    sess.select_thread(thread_id)
    return status(sess.id)


def timeline_seek(index: int, *, session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    sess.timeline_seek(int(index))
    return status(sess.id)


def timeline_live(*, session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    sess.timeline_live()
    return status(sess.id)


def disassemble(*, session_id: str | None = None, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]:
    sess = _need(session_id)
    return sess.disassemble(memory_reference=memory_reference, offset=offset, count=count)


def read_memory(
    *,
    session_id: str | None = None,
    memory_reference: str = "",
    expression: str = "",
    offset: int = 0,
    count: int = 64,
) -> dict[str, Any]:
    sess = _need(session_id)
    return sess.read_memory(
        memory_reference=memory_reference,
        expression=expression,
        offset=offset,
        count=count,
    )


def write_memory(
    *,
    session_id: str | None = None,
    memory_reference: str = "",
    data: str = "",
    offset: int = 0,
    allow_partial: bool = True,
) -> dict[str, Any]:
    sess = _need(session_id)
    _require_write(sess)
    if hasattr(sess, "write_memory"):
        return sess.write_memory(  # type: ignore[attr-defined]
            memory_reference=memory_reference,
            data=data,
            offset=offset,
            allow_partial=allow_partial,
        )
    raise RuntimeError("writeMemory not supported")


def set_variable(
    *,
    variables_reference: int,
    name: str,
    value: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    sess = _need(session_id)
    _require_write(sess)
    if hasattr(sess, "set_variable"):
        return sess.set_variable(  # type: ignore[attr-defined]
            variables_reference=variables_reference, name=name, value=value
        )
    raise RuntimeError("setVariable not supported")


def set_expression(
    *,
    expression: str,
    value: str,
    frame_id: Any = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    sess = _need(session_id)
    _require_write(sess)
    if hasattr(sess, "set_expression"):
        return sess.set_expression(  # type: ignore[attr-defined]
            expression=expression, value=value, frame_id=frame_id
        )
    raise RuntimeError("setExpression not supported")


def breakpoint_locations(
    *,
    path: str,
    line: int,
    end_line: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    sess = _get(session_id, require_alive=False) if session_id else _get(_ACTIVE_ID, require_alive=False)
    if sess and sess.alive and hasattr(sess, "breakpoint_locations"):
        locs = sess.breakpoint_locations(path=path, line=line, end_line=end_line)  # type: ignore[attr-defined]
        return {"ok": True, "locations": locs}
    # Static fallback: whole line is a valid location
    return {
        "ok": True,
        "locations": [{"line": int(line), "column": 1, "endLine": int(end_line or line), "endColumn": None}],
        "source": "fallback",
    }


def data_breakpoint_info(
    name: str,
    *,
    frame_id: Any = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    sess = _need(session_id)
    if hasattr(sess, "data_breakpoint_info"):
        return sess.data_breakpoint_info(name, frame_id=frame_id)  # type: ignore[attr-defined]
    raise RuntimeError("dataBreakpointInfo not supported")


def session_events(*, session_id: str | None = None, clear: bool = False) -> dict[str, Any]:
    sess = _get(session_id, require_alive=False) if session_id else _get(_ACTIVE_ID, require_alive=False)
    if not sess:
        return {"ok": True, "events": []}
    if clear and hasattr(sess, "events"):
        with _LOCK:
            sess.events.clear()  # type: ignore[attr-defined]
    events = list(getattr(sess, "events", []) or [])
    return {"ok": True, "events": events, "sessionId": getattr(sess, "id", None)}


def set_readonly_attach(enabled: bool) -> dict[str, Any]:
    global _READONLY_ATTACH
    _READONLY_ATTACH = bool(enabled)
    return {"ok": True, "readonlyAttach": _READONLY_ATTACH}


def readonly_attach() -> bool:
    return _READONLY_ATTACH


def _require_write(sess: Any) -> None:
    if getattr(sess, "readonly", False) or (
        _READONLY_ATTACH and not getattr(sess, "owns_process", True)
    ):
        raise PermissionError("read-only attach: setVariable / writeMemory / hotReload denied")
    if _DATA_DIR is not None:
        from editor import permissions

        perms = permissions.load(_DATA_DIR)
        if not perms.get("debug.write", True):
            raise PermissionError("permission denied: debug.write")


def list_modules(*, session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    if hasattr(sess, "list_modules"):
        mods = sess.list_modules()  # type: ignore[attr-defined]
        return {"ok": True, "modules": mods, "sessionId": sess.id}
    return {"ok": True, "modules": [], "sessionId": getattr(sess, "id", None)}


def hot_reload(*, session_id: str | None = None, module: str = "") -> dict[str, Any]:
    sess = _need(session_id)
    _require_write(sess)
    if hasattr(sess, "hot_reload"):
        return sess.hot_reload(module=module)  # type: ignore[attr-defined]
    raise RuntimeError("hotReload not supported")


def apply_instruction_breakpoints(*, session_id: str | None = None) -> dict[str, Any]:
    from editor import debug_features

    sess = _need(session_id)
    if hasattr(sess, "apply_instruction_breakpoints"):
        sess.apply_instruction_breakpoints()  # type: ignore[attr-defined]
        return {"ok": True, "instructionBreakpoints": debug_features.list_instruction_breakpoints()}
    raise RuntimeError("setInstructionBreakpoints not supported")


def start_session_recording(workspace: Path, *, session_id: str | None = None) -> dict[str, Any]:
    from editor import debug_features

    sess = _need(session_id)
    meta = {
        "engine": getattr(sess, "engine", "") or "",
        "path": getattr(sess, "rel", ""),
        "configName": getattr(sess, "config_name", ""),
    }
    # engine from snapshot
    try:
        meta["engine"] = (sess.snapshot() or {}).get("engine") or meta["engine"]
    except Exception:
        pass
    out = debug_features.start_recording(workspace, sess.id, meta=meta)
    _REPLAY_ACTIVE[sess.id] = out["replayId"]
    return out


def stop_session_recording(*, session_id: str | None = None) -> dict[str, Any]:
    sid = session_id or _ACTIVE_ID
    rid = _REPLAY_ACTIVE.pop(sid or "", None)
    return {"ok": True, "replayId": rid, "stopped": bool(rid)}


def _maybe_record(sess: Any, event: dict[str, Any]) -> None:
    rid = _REPLAY_ACTIVE.get(getattr(sess, "id", "") or "")
    if not rid:
        return
    ws = getattr(sess, "workspace", None)
    if ws is None:
        return
    try:
        from editor import debug_features

        debug_features.append_recording(ws, rid, event)
    except Exception:
        pass


def stop(session_id: str | None = None) -> dict[str, Any]:
    global _ACTIVE_ID
    with _LOCK:
        if session_id:
            ids = [session_id] if session_id in _SESSIONS else []
        else:
            ids = list(_SESSIONS.keys())
    for sid in ids:
        with _LOCK:
            sess = _SESSIONS.pop(sid, None)
            if _ACTIVE_ID == sid:
                _ACTIVE_ID = next(iter(_SESSIONS), None)
        if sess:
            sess.stop()
    return status()


def set_active(session_id: str) -> dict[str, Any]:
    global _ACTIVE_ID
    with _LOCK:
        if session_id not in _SESSIONS:
            raise KeyError("unknown session")
        _ACTIVE_ID = session_id
    return status(session_id)


def cont(session_id: str | None = None) -> dict[str, Any]:
    return _need(session_id).cont()


def step_over(session_id: str | None = None) -> dict[str, Any]:
    return _need(session_id).step_over()


def step_in(session_id: str | None = None) -> dict[str, Any]:
    return _need(session_id).step_in()


def step_out(session_id: str | None = None) -> dict[str, Any]:
    return _need(session_id).step_out()


def step_in_targets(*, session_id: str | None = None, frame_id: Any = None) -> dict[str, Any]:
    sess = _need(session_id)
    if hasattr(sess, "step_in_targets"):
        targets = sess.step_in_targets(frame_id=frame_id)  # type: ignore[attr-defined]
        return {"ok": True, "targets": targets, "sessionId": sess.id}
    return {"ok": True, "targets": [], "sessionId": getattr(sess, "id", None)}


def step_in_with_target(*, target_id: Any = None, session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    if target_id is not None and hasattr(sess, "step_in_target"):
        return sess.step_in_target(target_id)  # type: ignore[attr-defined]
    return sess.step_in()


def goto_targets(
    *,
    path: str,
    line: int,
    session_id: str | None = None,
) -> dict[str, Any]:
    sess = _need(session_id)
    if hasattr(sess, "goto_targets"):
        targets = sess.goto_targets(path, line)  # type: ignore[attr-defined]
        return {"ok": True, "targets": targets, "sessionId": sess.id}
    raise RuntimeError("gotoTargets not supported")


def goto(
    *,
    target_id: Any = None,
    path: str = "",
    line: int = 0,
    session_id: str | None = None,
) -> dict[str, Any]:
    sess = _need(session_id)
    if hasattr(sess, "goto"):
        return sess.goto(target_id=target_id, path=path, line=line)  # type: ignore[attr-defined]
    raise RuntimeError("goto not supported")


def restart_frame(*, frame_id: Any = None, session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    if hasattr(sess, "restart_frame"):
        return sess.restart_frame(frame_id=frame_id)  # type: ignore[attr-defined]
    raise RuntimeError("restartFrame not supported")


def step_back(session_id: str | None = None) -> dict[str, Any]:
    return _need(session_id).step_back()


def reverse_continue(session_id: str | None = None) -> dict[str, Any]:
    return _need(session_id).reverse_continue()


def completions(
    text: str,
    column: int,
    *,
    session_id: str | None = None,
    frame_id: Any = None,
) -> dict[str, Any]:
    sess = _need(session_id)
    items = sess.completions(text, column, frame_id=frame_id)
    return {"ok": True, "items": items, "sessionId": sess.id}


def open_postmortem(workspace: Path, path: str) -> dict[str, Any]:
    global _ACTIVE_ID, _POSTMORTEM
    from editor import debug_extras

    data = debug_extras.load_postmortem(workspace, path)
    sid = uuid.uuid4().hex[:10]
    sess = PostmortemSession(sid, workspace, data)
    with _LOCK:
        _SESSIONS[sid] = sess
        _ACTIVE_ID = sid
        _POSTMORTEM = {"sessionId": sid, "path": path, "mode": data.get("mode")}
    return status(sid, workspace=workspace)


def open_postmortem_from_data(workspace: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Open a postmortem/replay session from an in-memory dump (e.g. .zintriq/replay)."""
    global _ACTIVE_ID, _POSTMORTEM
    sid = uuid.uuid4().hex[:10]
    payload = {
        "ok": True,
        "mode": data.get("mode") or "replay",
        "path": data.get("path") or "(replay)",
        "reason": data.get("reason") or "replay",
        "stack": data.get("stack") or [],
        "variables": data.get("variables") or [],
        "console": data.get("console")
        or [{"type": "output", "text": f"replay events={len(data.get('events') or [])}"}],
    }
    sess = PostmortemSession(sid, workspace, payload)
    with _LOCK:
        _SESSIONS[sid] = sess
        _ACTIVE_ID = sid
        _POSTMORTEM = {
            "sessionId": sid,
            "path": payload["path"],
            "mode": payload["mode"],
            "replayId": data.get("id"),
        }
    return status(sid, workspace=workspace)


def start_test(
    workspace: Path,
    path: str,
    *,
    xdist: bool = False,
    workers: str = "auto",
) -> dict[str, Any]:
    from editor import debug_extras

    kind = debug_extras.detect_test_kind(path, workspace)
    if xdist or (kind == "pytest" and os.environ.get("ZINTRIQ_PYTEST_XDIST") == "1"):
        return start(
            workspace,
            path,
            config=debug_extras.pytest_xdist_launch(workspace, path, workers=workers),
        )
    return start(workspace, path, config=debug_extras.test_launch_config(workspace, path))


def start_rr(
    workspace: Path,
    program: str,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record (optional) and open an rr replay debugging session."""
    global _ACTIVE_ID
    from editor import debug_extras

    if not debug_extras.rr_available():
        raise RuntimeError("rr not installed (brew/apt install rr)")
    cfg = cfg or {}
    rel = (program or "").replace("\\", "/")
    if rel and not rel.startswith("("):
        try:
            rel = _valid_rel(rel)
        except ValueError:
            pass
    trace = str(cfg.get("trace") or "").strip()
    if not trace:
        rec = debug_extras.rr_record(
            workspace,
            rel or str(cfg.get("program") or ""),
            list(cfg.get("args") or []),
        )
        if not rec.get("ok"):
            raise RuntimeError(f"rr record failed: {rec.get('stderr') or rec.get('code')}")
        trace = str(rec.get("latest") or rec.get("traceDir") or "")
    sid = uuid.uuid4().hex[:10]
    sess = RrReplaySession(sid, workspace, rel or "(rr)", trace=trace, port=int(cfg.get("port") or 1234))
    sess.start()
    with _LOCK:
        _SESSIONS[sid] = sess
        _ACTIVE_ID = sid
    return status(sid, workspace=workspace)


def sessions_var_diff(
    session_a: str,
    session_b: str,
    *,
    session_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compare top-level variables between two or more sessions (matrix when 3+)."""
    ids = [str(x) for x in (session_ids or []) if str(x).strip()]
    if len(ids) >= 2:
        sessions = [_need(i) for i in ids]
        maps = [
            {str(v.get("name")): v.get("value") for v in (getattr(s, "variables", None) or []) if v.get("name")}
            for s in sessions
        ]
        keys = sorted(set().union(*[set(m) for m in maps]) if maps else [])
        matrix = []
        for k in keys:
            vals = [m.get(k) for m in maps]
            uniq = {str(v) for v in vals}
            matrix.append(
                {
                    "name": k,
                    "values": vals,
                    "status": "same" if len(uniq) <= 1 and None not in vals else "changed",
                }
            )
        return {
            "ok": True,
            "mode": "matrix",
            "sessionIds": [s.id for s in sessions],
            "matrix": matrix,
            "changed": sum(1 for r in matrix if r["status"] != "same"),
        }
    a = _need(session_a)
    b = _need(session_b)
    va = {str(v.get("name")): v for v in (getattr(a, "variables", None) or []) if v.get("name")}
    vb = {str(v.get("name")): v for v in (getattr(b, "variables", None) or []) if v.get("name")}
    keys = sorted(set(va) | set(vb))
    rows = []
    for k in keys:
        left = va.get(k)
        right = vb.get(k)
        lv = None if left is None else left.get("value")
        rv = None if right is None else right.get("value")
        if left is None:
            status_ = "onlyB"
        elif right is None:
            status_ = "onlyA"
        elif str(lv) == str(rv):
            status_ = "same"
        else:
            status_ = "changed"
        rows.append({"name": k, "a": lv, "b": rv, "status": status_})
    return {
        "ok": True,
        "mode": "pair",
        "sessionA": a.id,
        "sessionB": b.id,
        "diff": rows,
        "changed": sum(1 for r in rows if r["status"] != "same"),
    }


def export_breakpoints_vscode() -> dict[str, Any]:
    from editor import debug_extras

    return {"ok": True, **debug_extras.breakpoints_to_vscode(list_breakpoints())}


def import_breakpoints_vscode(document: dict[str, Any], *, merge: bool = True) -> dict[str, Any]:
    from editor import debug_extras

    imported = debug_extras.breakpoints_from_vscode(document)
    with _LOCK:
        if not merge:
            _BREAKPOINTS.clear()
        for path, bps in imported.items():
            cur = {int(x["line"]): dict(x) for x in (_BREAKPOINTS.get(path) or [])}
            for bp in bps:
                cur[int(bp["line"])] = dict(bp)
            _BREAKPOINTS[path] = sorted(cur.values(), key=lambda x: x["line"])
        sessions = list(_SESSIONS.values())
    _persist()
    for sess in sessions:
        if sess.alive:
            for p in imported:
                try:
                    sess.apply_breakpoints(p)
                except Exception:
                    pass
    return {"ok": True, "breakpoints": list_breakpoints()}


def loaded_sources(session_id: str | None = None) -> dict[str, Any]:
    sess = _need(session_id)
    if hasattr(sess, "list_loaded_sources"):
        sources = sess.list_loaded_sources()  # type: ignore[attr-defined]
        return {"ok": True, "sources": sources, "sessionId": sess.id}
    raise RuntimeError("loadedSources not supported for this session")


def rename_child_session(session_id: str, name: str) -> dict[str, Any]:
    sess = _need(session_id)
    label = (name or "").strip()
    if not label:
        raise ValueError("name required")
    sess.config_name = label
    if hasattr(sess, "rel"):
        # keep path prefix style for workers
        if str(getattr(sess, "rel", "")).startswith("worker:"):
            sess.rel = f"worker:{label}"
    return status(sess.id)


def register_child_session(parent_id: str, child: "DebugSession") -> None:
    global _ACTIVE_ID
    with _LOCK:
        parent = _SESSIONS.get(parent_id)
        _SESSIONS[child.id] = child
        if parent is not None:
            kids = getattr(parent, "child_ids", None)
            if kids is None:
                parent.child_ids = []
                kids = parent.child_ids
            kids.append(child.id)
            child.parent_id = parent_id
        _ACTIVE_ID = child.id


def evaluate(
    expression: str,
    *,
    session_id: str | None = None,
    frame_id: Any = None,
    context: str = "repl",
) -> dict[str, Any]:
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("empty expression")
    sess = _need(session_id)
    result = sess.evaluate(expr, frame_id=frame_id, context=context)
    return {"ok": True, "expression": expr, "result": result, "sessionId": sess.id}


def expand_variables(
    variables_reference: int,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    ref = int(variables_reference)
    if ref <= 0:
        raise ValueError("invalid variablesReference")
    sess = _need(session_id)
    children = sess.expand_variables(ref)
    return {"ok": True, "variablesReference": ref, "variables": children, "sessionId": sess.id}


def _get(session_id: str | None, *, require_alive: bool = True) -> "DebugSession | None":
    with _LOCK:
        sid = session_id or _ACTIVE_ID
        sess = _SESSIONS.get(sid) if sid else None
    if require_alive and (not sess or not sess.alive):
        return None
    return sess


def _need(session_id: str | None = None) -> "DebugSession":
    sess = _get(session_id, require_alive=True)
    if not sess:
        raise RuntimeError("no active debug session")
    return sess


def _bps_for(rel: str) -> list[dict[str, Any]]:
    """Active breakpoints for DAP/CDP (enabled + group enabled)."""
    with _LOCK:
        groups = dict(_BP_GROUPS)
        out = []
        for x in _BREAKPOINTS.get(rel) or []:
            bp = dict(x)
            g = str(bp.get("group") or "default")
            if bp.get("enabled", True) is False:
                continue
            if groups.get(g, True) is False:
                continue
            out.append(bp)
        return out


def _all_bp_paths() -> list[str]:
    with _LOCK:
        return list(_BREAKPOINTS.keys())


class DebugSession:
    id: str = ""
    alive: bool = False
    stopped: bool = False
    watches: list[dict[str, Any]]

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def apply_breakpoints(self, rel: str) -> None: ...
    def apply_data_breakpoints(self) -> None: ...
    def apply_exception_breakpoints(self) -> None: ...
    def select_frame(self, frame_id: Any) -> None: ...
    def select_thread(self, thread_id: Any) -> None: ...
    def timeline_seek(self, index: int) -> None: ...
    def timeline_live(self) -> None: ...
    def step_back(self) -> dict[str, Any]: ...
    def reverse_continue(self) -> dict[str, Any]: ...
    def completions(self, text: str, column: int, *, frame_id: Any = None) -> list[dict[str, Any]]: ...
    def profile_start(self, kind: str = "cpu") -> dict[str, Any]: ...
    def profile_stop(self, kind: str = "cpu") -> dict[str, Any]: ...
    def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]: ...
    def read_memory(
        self,
        *,
        memory_reference: str = "",
        expression: str = "",
        offset: int = 0,
        count: int = 64,
    ) -> dict[str, Any]: ...
    def cont(self) -> dict[str, Any]: ...
    def step_over(self) -> dict[str, Any]: ...
    def step_in(self) -> dict[str, Any]: ...
    def step_out(self) -> dict[str, Any]: ...
    def evaluate(self, expression: str, *, frame_id: Any = None, context: str = "repl") -> dict[str, Any]: ...
    def expand_variables(self, variables_reference: int) -> list[dict[str, Any]]: ...
    def refresh_watches(self) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...


def _timeline_entry(sess: Any) -> dict[str, Any]:
    top = (sess.stack or [None])[0] or {}
    return {
        "id": uuid.uuid4().hex[:8],
        "ts": time.time(),
        "reason": getattr(sess, "reason", "") or "",
        "threadId": getattr(sess, "thread_id", None),
        "frameId": getattr(sess, "frame_id", None),
        "stack": [dict(x) for x in (sess.stack or [])],
        "variables": [dict(x) for x in (sess.variables or [])[:80]],
        "watches": [dict(x) for x in (sess.watches or [])],
        "inlineValues": [dict(x) for x in (getattr(sess, "inline_values", None) or [])],
        "path": top.get("path") or getattr(sess, "rel", ""),
        "line": top.get("line") or 0,
        "name": top.get("name") or "",
    }


class _TimelineMixin:
    timeline: list[dict[str, Any]]
    timeline_index: int
    timeline_viewing: bool
    events: list[dict[str, Any]]
    _live_stack: list[dict[str, Any]]
    _live_variables: list[dict[str, Any]]
    _live_watches: list[dict[str, Any]]
    _live_inline: list[dict[str, Any]]
    _live_frame_id: Any

    def _timeline_init(self) -> None:
        self.timeline = []
        self.timeline_index = -1
        self.timeline_viewing = False
        self.events = []
        self._live_stack = []
        self._live_variables = []
        self._live_watches = []
        self._live_inline = []
        self._live_frame_id = None

    def _event_push(self, kind: str, **extra: Any) -> None:
        entry = {
            "ts": time.time(),
            "kind": kind,
            "sessionId": getattr(self, "id", ""),
            "reason": getattr(self, "reason", "") or "",
            "path": "",
            "line": 0,
            **extra,
        }
        stack = getattr(self, "stack", None) or []
        if stack and not entry.get("path"):
            top = stack[0] if isinstance(stack[0], dict) else {}
            entry["path"] = top.get("path") or ""
            entry["line"] = top.get("line") or 0
        self.events.append(entry)
        if len(self.events) > _EVENT_LOG_MAX:
            self.events = self.events[-_EVENT_LOG_MAX:]
        # Correlate with OTel span file when workspace known
        ws = getattr(self, "workspace", None)
        if ws is not None:
            try:
                from editor import debug_advanced

                debug_advanced.otel_record_span(
                    ws,
                    name=f"debug.{kind}",
                    session_id=str(getattr(self, "id", "") or ""),
                    attributes={"reason": entry.get("reason"), "path": entry.get("path"), "line": entry.get("line")},
                )
            except Exception:
                pass
        if kind == "stopped":
            try:
                from editor import debug_features

                debug_features.record_bp_hit(str(entry.get("path") or ""), int(entry.get("line") or 0))
                reason = str(entry.get("reason") or "")
                if "exception" in reason.lower() or "error" in reason.lower():
                    debug_features.record_failure(
                        reason, path=str(entry.get("path") or ""), line=int(entry.get("line") or 0)
                    )
            except Exception:
                pass
        try:
            _maybe_record(
                self,
                {
                    "event": kind,
                    "reason": entry.get("reason"),
                    "path": entry.get("path"),
                    "line": entry.get("line"),
                    "stack": list(getattr(self, "stack", []) or [])[:20],
                    "variables": list(getattr(self, "variables", []) or [])[:40],
                },
            )
        except Exception:
            pass

    def _timeline_push(self) -> None:
        if not getattr(self, "stopped", False):
            return
        if self.timeline_viewing:
            self.timeline_live()
        entry = _timeline_entry(self)
        self.timeline.append(entry)
        if len(self.timeline) > _TIMELINE_MAX:
            self.timeline = self.timeline[-_TIMELINE_MAX:]
        self.timeline_index = len(self.timeline) - 1
        self._event_push("snapshot", reason=entry.get("reason") or "stopped")
        try:
            from editor import debug_features

            debug_features.push_var_history(str(getattr(self, "id", "") or ""), list(self.variables or []))
        except Exception:
            pass

    def timeline_seek(self, index: int) -> None:
        if not self.timeline:
            raise RuntimeError("no timeline snapshots")
        idx = max(0, min(int(index), len(self.timeline) - 1))
        if not self.timeline_viewing:
            self._live_stack = list(self.stack)
            self._live_variables = list(self.variables)
            self._live_watches = list(self.watches)
            self._live_inline = list(getattr(self, "inline_values", []) or [])
            self._live_frame_id = self.frame_id
        entry = self.timeline[idx]
        self.timeline_viewing = True
        self.timeline_index = idx
        self.stack = [dict(x) for x in entry.get("stack") or []]
        self.variables = [dict(x) for x in entry.get("variables") or []]
        self.watches = [dict(x) for x in entry.get("watches") or []]
        self.inline_values = [dict(x) for x in entry.get("inlineValues") or []]
        self.frame_id = entry.get("frameId")

    def timeline_live(self) -> None:
        if not self.timeline_viewing:
            self.timeline_index = len(self.timeline) - 1 if self.timeline else -1
            return
        self.timeline_viewing = False
        self.stack = list(self._live_stack)
        self.variables = list(self._live_variables)
        self.watches = list(self._live_watches)
        self.inline_values = list(self._live_inline)
        self.frame_id = self._live_frame_id
        self.timeline_index = len(self.timeline) - 1 if self.timeline else -1

    def _timeline_meta(self) -> dict[str, Any]:
        return {
            "length": len(self.timeline),
            "index": self.timeline_index,
            "viewing": self.timeline_viewing,
            "entries": [
                {
                    "i": i,
                    "ts": e.get("ts"),
                    "reason": e.get("reason"),
                    "path": e.get("path"),
                    "line": e.get("line"),
                    "name": e.get("name"),
                    "threadId": e.get("threadId"),
                }
                for i, e in enumerate(self.timeline)
            ],
            "events": list(getattr(self, "events", []) or [])[-80:],
        }


class PostmortemSession(_TimelineMixin, DebugSession):
    """Read-only session from a traceback / dump file."""

    def __init__(self, sid: str, workspace: Path, data: dict[str, Any]) -> None:
        self.id = sid
        self.workspace = workspace.resolve()
        self.rel = str(data.get("path") or "(postmortem)")
        self.alive = True
        self.stopped = True
        self.watches = []
        self.stack = list(data.get("stack") or [])
        self.variables = list(data.get("variables") or [])
        self.inline_values = []
        self.console = list(data.get("console") or [])
        self.reason = str(data.get("reason") or "postmortem")
        self.error = ""
        self.frame_id = self.stack[0]["id"] if self.stack else None
        self.thread_id = "postmortem"
        self.threads = [{"id": "postmortem", "name": "Postmortem"}]
        self.parent_id = None
        self.child_ids: list[str] = []
        self.config_name = "postmortem"
        self._timeline_init()
        self._timeline_push()

    def start(self) -> None:
        return None

    def stop(self) -> None:
        self.alive = False

    def apply_breakpoints(self, rel: str) -> None:
        return None

    def apply_data_breakpoints(self) -> None:
        return None

    def apply_exception_breakpoints(self) -> None:
        return None

    def select_frame(self, frame_id: Any) -> None:
        self.frame_id = frame_id

    def select_thread(self, thread_id: Any) -> None:
        return None

    def step_back(self) -> dict[str, Any]:
        if self.timeline and self.timeline_index > 0:
            self.timeline_seek(self.timeline_index - 1)
        return self.snapshot()

    def reverse_continue(self) -> dict[str, Any]:
        if self.timeline:
            self.timeline_seek(0)
        return self.snapshot()

    def completions(self, text: str, column: int, *, frame_id: Any = None) -> list[dict[str, Any]]:
        return []

    def profile_start(self, kind: str = "cpu") -> dict[str, Any]:
        raise RuntimeError("profiling unavailable in postmortem")

    def profile_stop(self, kind: str = "cpu") -> dict[str, Any]:
        raise RuntimeError("profiling unavailable in postmortem")

    def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]:
        return {"ok": False, "text": "", "error": "postmortem"}

    def read_memory(
        self,
        *,
        memory_reference: str = "",
        expression: str = "",
        offset: int = 0,
        count: int = 64,
    ) -> dict[str, Any]:
        raise RuntimeError("postmortem is read-only")

    def cont(self) -> dict[str, Any]:
        raise RuntimeError("postmortem is read-only")

    def step_over(self) -> dict[str, Any]:
        raise RuntimeError("postmortem is read-only")

    def step_in(self) -> dict[str, Any]:
        raise RuntimeError("postmortem is read-only")

    def step_out(self) -> dict[str, Any]:
        raise RuntimeError("postmortem is read-only")

    def evaluate(self, expression: str, *, frame_id: Any = None, context: str = "repl") -> dict[str, Any]:
        raise RuntimeError("postmortem is read-only")

    def expand_variables(self, variables_reference: int) -> list[dict[str, Any]]:
        return []

    def refresh_watches(self) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "id": self.id,
            "sessionId": self.id,
            "running": False,
            "stopped": True,
            "engine": "postmortem",
            "path": self.rel,
            "configName": "postmortem",
            "reason": self.reason,
            "error": self.error,
            "stack": list(self.stack),
            "selectedFrameId": self.frame_id,
            "threadId": self.thread_id,
            "threads": list(self.threads),
            "variables": list(self.variables)[:80],
            "watches": [],
            "inlineValues": [],
            "timeline": self._timeline_meta(),
            "console": list(self.console)[-40:],
            "breakpoints": list_breakpoints(),
            "attached": False,
            "postmortem": True,
        }


class ChildProxySession(_TimelineMixin, DebugSession):
    """Lightweight child/worker marker session (subprocess / worker target)."""

    def __init__(
        self,
        sid: str,
        workspace: Path,
        rel: str,
        *,
        parent: "DebugSession",
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.id = sid
        self.workspace = workspace.resolve()
        self.rel = rel
        self.alive = True
        self.stopped = False
        self.watches = []
        self.stack = []
        self.variables = []
        self.inline_values = []
        self.console = [{"type": "output", "text": f"Child target: {json.dumps(meta or {})}"}]
        self.reason = "subprocess"
        self.error = ""
        self.frame_id = None
        self.thread_id = None
        self.threads = []
        self.parent_id = getattr(parent, "id", None)
        self.child_ids: list[str] = []
        self.config_name = "child"
        self.meta = meta or {}
        self._timeline_init()

    def start(self) -> None:
        return None

    def stop(self) -> None:
        self.alive = False

    def apply_breakpoints(self, rel: str) -> None:
        return None

    def apply_data_breakpoints(self) -> None:
        return None

    def apply_exception_breakpoints(self) -> None:
        return None

    def select_frame(self, frame_id: Any) -> None:
        return None

    def select_thread(self, thread_id: Any) -> None:
        return None

    def step_back(self) -> dict[str, Any]:
        raise RuntimeError("switch to parent session for stepping")

    def reverse_continue(self) -> dict[str, Any]:
        raise RuntimeError("switch to parent session for stepping")

    def completions(self, text: str, column: int, *, frame_id: Any = None) -> list[dict[str, Any]]:
        return []

    def profile_start(self, kind: str = "cpu") -> dict[str, Any]:
        raise RuntimeError("profile on parent session")

    def profile_stop(self, kind: str = "cpu") -> dict[str, Any]:
        raise RuntimeError("profile on parent session")

    def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]:
        return {"ok": False, "text": "", "error": "child proxy"}

    def read_memory(
        self,
        *,
        memory_reference: str = "",
        expression: str = "",
        offset: int = 0,
        count: int = 64,
    ) -> dict[str, Any]:
        raise RuntimeError("child proxy")

    def cont(self) -> dict[str, Any]:
        raise RuntimeError("use parent session")

    def step_over(self) -> dict[str, Any]:
        raise RuntimeError("use parent session")

    def step_in(self) -> dict[str, Any]:
        raise RuntimeError("use parent session")

    def step_out(self) -> dict[str, Any]:
        raise RuntimeError("use parent session")

    def evaluate(self, expression: str, *, frame_id: Any = None, context: str = "repl") -> dict[str, Any]:
        raise RuntimeError("use parent session")

    def expand_variables(self, variables_reference: int) -> list[dict[str, Any]]:
        return []

    def refresh_watches(self) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "id": self.id,
            "sessionId": self.id,
            "running": self.alive,
            "stopped": self.stopped,
            "engine": "child",
            "path": self.rel,
            "configName": "child",
            "reason": self.reason,
            "error": self.error,
            "parentSessionId": self.parent_id,
            "stack": [],
            "variables": [],
            "watches": [],
            "console": list(self.console)[-20:],
            "threads": [],
            "timeline": self._timeline_meta(),
            "child": True,
            "meta": self.meta,
        }


class RrReplaySession(_TimelineMixin, DebugSession):
    """True reverse-execution session via Mozilla rr + persistent gdb MI."""

    def __init__(
        self,
        sid: str,
        workspace: Path,
        rel: str,
        *,
        trace: str,
        port: int = 1234,
    ) -> None:
        self.id = sid
        self.workspace = workspace.resolve()
        self.rel = rel
        self.trace = trace
        self.port = int(port)
        self.alive = False
        self.stopped = True
        self.watches: list[dict[str, Any]] = []
        self.stack: list[dict[str, Any]] = []
        self.variables: list[dict[str, Any]] = []
        self.inline_values: list[dict[str, Any]] = []
        self.console: list[dict[str, Any]] = []
        self.reason = "rr"
        self.error = ""
        self.frame_id: Any = None
        self.thread_id: Any = "rr"
        self.threads = [{"id": "rr", "name": "rr replay"}]
        self.parent_id = None
        self.child_ids: list[str] = []
        self.config_name = "rr replay"
        self._rr_proc: subprocess.Popen[str] | None = None
        self._mi: Any = None
        self._timeline_init()

    def start(self) -> None:
        from editor import debug_extras
        from editor.gdb_mi import GdbMi, resolve_mi_backend

        info = debug_extras.rr_replay_gdb_server(self.workspace, self.trace, port=self.port)
        self._rr_proc = info.get("proc")
        prefer = os.environ.get("ZINTRIQ_MI_BACKEND") or "gdb"
        try:
            backend, path = resolve_mi_backend(prefer)
        except Exception:
            backend, path = "gdb", shutil.which("gdb") or "gdb"
        self._mi = GdbMi(
            path,
            backend=backend,
            on_stopped=self._on_mi_stopped,
            on_running=self._on_mi_running,
        )
        self._mi.start()
        self._mi.target_remote("127.0.0.1", self.port)
        self.alive = True
        self.console.append(
            {
                "type": "output",
                "text": f"rr replay + {backend} MI on :{self.port} (trace={self.trace})",
            }
        )
        self._refresh_state()
        self._timeline_push()

    def _on_mi_stopped(self, info: dict[str, Any]) -> None:
        self.stopped = True
        self.reason = str(info.get("reason") or "stopped")
        try:
            self._refresh_state()
            self._timeline_push()
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)

    def _on_mi_running(self) -> None:
        self.stopped = False

    def _refresh_state(self) -> None:
        if not self._mi:
            return
        try:
            frames = self._mi.stack_list_frames()
            stack = []
            for fr in frames:
                fpath = fr.get("file") or ""
                try:
                    if fpath:
                        pref = str(Path(fpath).resolve().relative_to(self.workspace)).replace("\\", "/")
                    else:
                        pref = self.rel
                except Exception:
                    pref = fpath or self.rel
                stack.append(
                    {
                        "id": int(fr.get("level") or 0) + 1,
                        "name": fr.get("func") or "?",
                        "path": pref,
                        "line": int(fr.get("line") or 0),
                        "column": 1,
                    }
                )
            self.stack = stack or [
                {"id": 1, "name": "<rr>", "path": self.rel, "line": 0, "column": 1}
            ]
            level = 0
            if self.frame_id is not None:
                level = max(0, int(self.frame_id) - 1)
            self.frame_id = self.stack[0]["id"] if self.stack else None
            self.variables = self._mi.stack_list_locals(level)
            self.stopped = True
            self.error = ""
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)

    def stop(self) -> None:
        self.alive = False
        if self._mi:
            try:
                self._mi.close()
            except Exception:
                pass
            self._mi = None
        if self._rr_proc and self._rr_proc.poll() is None:
            try:
                self._rr_proc.terminate()
            except OSError:
                pass
        self._rr_proc = None

    def apply_breakpoints(self, rel: str) -> None:
        return None

    def apply_data_breakpoints(self) -> None:
        return None

    def apply_exception_breakpoints(self) -> None:
        return None

    def select_frame(self, frame_id: Any) -> None:
        self.frame_id = frame_id
        if self._mi:
            try:
                level = max(0, int(frame_id) - 1)
                self.variables = self._mi.stack_list_locals(level)
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)

    def select_thread(self, thread_id: Any) -> None:
        return None

    def step_back(self) -> dict[str, Any]:
        assert self._mi
        self.stopped = False
        self._mi.exec_step(reverse=True)
        # state refreshed via *stopped callback; ensure once if already stopped
        if self.stopped:
            self._refresh_state()
        return self.snapshot()

    def reverse_continue(self) -> dict[str, Any]:
        assert self._mi
        self.stopped = False
        self._mi.exec_continue(reverse=True)
        if self.stopped:
            self._refresh_state()
        return self.snapshot()

    def completions(self, text: str, column: int, *, frame_id: Any = None) -> list[dict[str, Any]]:
        prefix = (text or "")[: max(0, column)]
        token = re.split(r"[^\w\.\$]", prefix)[-1] if prefix else ""
        out = []
        for v in self.variables:
            n = str(v.get("name") or "")
            if n.startswith(token):
                out.append({"label": n, "text": n, "type": "variable"})
        return out[:40]

    def profile_start(self, kind: str = "cpu") -> dict[str, Any]:
        raise RuntimeError("profiling unavailable under rr")

    def profile_stop(self, kind: str = "cpu") -> dict[str, Any]:
        raise RuntimeError("profiling unavailable under rr")

    def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]:
        assert self._mi
        text = self._mi.cli("disassemble")
        return {"ok": True, "mode": "gdb-mi", "text": text[-8000:]}

    def read_memory(
        self,
        *,
        memory_reference: str = "",
        expression: str = "",
        offset: int = 0,
        count: int = 64,
    ) -> dict[str, Any]:
        assert self._mi
        expr = expression or memory_reference or "$pc"
        text = self._mi.cli(f"x/{max(1, count)}xb {expr}")
        return {"ok": True, "mode": "gdb-mi", "text": text[-4000:]}

    def cont(self) -> dict[str, Any]:
        assert self._mi
        self.stopped = False
        self._mi.exec_continue(reverse=False)
        return self.snapshot()

    def step_over(self) -> dict[str, Any]:
        assert self._mi
        self.stopped = False
        self._mi.exec_next(reverse=False)
        return self.snapshot()

    def step_in(self) -> dict[str, Any]:
        assert self._mi
        self.stopped = False
        self._mi.exec_step(reverse=False)
        return self.snapshot()

    def step_out(self) -> dict[str, Any]:
        assert self._mi
        self.stopped = False
        self._mi.exec_finish()
        return self.snapshot()

    def evaluate(self, expression: str, *, frame_id: Any = None, context: str = "repl") -> dict[str, Any]:
        assert self._mi
        val = self._mi.data_evaluate(expression)
        return {"value": val, "type": "gdb"}

    def expand_variables(self, variables_reference: int) -> list[dict[str, Any]]:
        return []

    def refresh_watches(self) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "id": self.id,
            "sessionId": self.id,
            "running": self.alive,
            "stopped": self.stopped,
            "engine": "rr",
            "path": self.rel,
            "configName": self.config_name,
            "reason": self.reason,
            "error": self.error,
            "stack": list(self.stack),
            "selectedFrameId": self.frame_id,
            "threadId": self.thread_id,
            "threads": list(self.threads),
            "variables": list(self.variables)[:80],
            "watches": [],
            "inlineValues": [],
            "timeline": self._timeline_meta(),
            "console": list(self.console)[-40:],
            "breakpoints": list_breakpoints(),
            "supportsStepBack": True,
            "rr": True,
            "mi": True,
            "trace": self.trace,
        }


def _cdp_logpoint_condition(log_message: str) -> str:
    """Convert DAP-style logMessage (`hello {x}`) into a non-breaking CDP condition."""
    msg = log_message or ""
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"\{([^{}]+)\}", msg):
        lit = msg[last : m.start()]
        if lit:
            parts.append(json.dumps(lit))
        parts.append(f"({m.group(1)})")
        last = m.end()
    tail = msg[last:]
    if tail:
        parts.append(json.dumps(tail))
    if not parts:
        parts.append('""')
    expr = "+".join(parts)
    return f"(()=>{{console.log({expr});return false;}})()"


def _format_hex_dump(data: bytes, *, base: int = 0) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + i:08x}  {hex_part:<47}  {ascii_part}")
    return "\n".join(lines)


def _ast_bytes_literal(text: str) -> bytes:
    import ast

    return ast.literal_eval(text)


def _compute_inline_values(
    workspace: Path,
    stack: list[dict[str, Any]],
    frame_id: Any,
    variables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    frame = next((f for f in stack if f.get("id") == frame_id), None)
    if not frame and stack:
        frame = stack[0]
    if not frame:
        return []
    path = str(frame.get("path") or "")
    line = int(frame.get("line") or 0)
    by_name: dict[str, str] = {}
    for v in variables:
        name = str(v.get("name") or "")
        if not name or name.startswith("__") or name == "this":
            continue
        scope = str(v.get("scope") or "").lower()
        if name in by_name and "local" not in scope and "arg" not in scope:
            continue
        val = str(v.get("value") or "")
        if len(val) > 60:
            val = val[:57] + "…"
        by_name[name] = val
    if not by_name:
        return []
    placements: list[dict[str, Any]] = []
    lines: list[str] = []
    if path and not path.startswith("("):
        try:
            text = (workspace / path).read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
        except OSError:
            lines = []
    if lines and line > 0:
        start = max(0, line - 10)
        end = min(len(lines), line + 16)
        line_items: dict[int, list[dict[str, str]]] = {}
        for ln in range(start, end):
            src = lines[ln]
            for name, val in by_name.items():
                if re.search(rf"\b{re.escape(name)}\b", src):
                    line_items.setdefault(ln + 1, []).append({"name": name, "value": val})
        for ln, items in sorted(line_items.items()):
            uniq: list[dict[str, str]] = []
            seen: set[str] = set()
            for it in items:
                if it["name"] in seen:
                    continue
                seen.add(it["name"])
                uniq.append(it)
                if len(uniq) >= 6:
                    break
            placements.append(
                {
                    "path": path,
                    "line": ln,
                    "text": "  ".join(f"{i['name']} = {i['value']}" for i in uniq),
                    "items": uniq,
                }
            )
    elif line > 0:
        items = [{"name": n, "value": v} for n, v in list(by_name.items())[:8]]
        placements.append(
            {
                "path": path,
                "line": line,
                "text": "  ".join(f"{i['name']} = {i['value']}" for i in items),
                "items": items,
            }
        )
    return placements


def _cdp_hit_condition_expr(hit_condition: str, bp_key: str) -> str:
    """Adapt DAP-style hitCondition into a CDP boolean expression."""
    hit = (hit_condition or "").strip()
    if not hit:
        return ""
    m = re.match(r"^(>=|<=|>|<|==|=|%)\s*(\d+)$", hit)
    if m:
        op, num = m.group(1), int(m.group(2))
        if op == "=":
            op = "=="
    else:
        m2 = re.match(r"^(\d+)$", hit)
        if not m2:
            return ""
        op, num = "==", int(m2.group(1))
    key = json.dumps(bp_key)
    if op == "%":
        cmp = f"(n%{num})===0"
    else:
        cmp = f"n{op}{num}"
    return (
        f"(()=>{{var g=globalThis;g.__zqHits=g.__zqHits||{{}};var k={key};"
        f"g.__zqHits[k]=(g.__zqHits[k]||0)+1;var n=g.__zqHits[k];return {cmp};}})()"
    )


def _merge_cdp_condition(
    condition: str,
    hit_condition: str,
    bp_key: str,
    *,
    log_message: str = "",
) -> str:
    log = (log_message or "").strip()
    if log:
        # Logpoints never stop; hit/condition still gate whether the log runs.
        log_expr = _cdp_logpoint_condition(log)
        parts: list[str] = []
        hit_expr = _cdp_hit_condition_expr(hit_condition, bp_key)
        if hit_expr:
            parts.append(hit_expr)
        cond = (condition or "").strip()
        if cond:
            parts.append(f"({cond})")
        if parts:
            return f"({'&&'.join(parts)})?({log_expr}):false"
        return log_expr
    parts = []
    hit_expr = _cdp_hit_condition_expr(hit_condition, bp_key)
    if hit_expr:
        parts.append(hit_expr)
    cond = (condition or "").strip()
    if cond:
        parts.append(f"({cond})")
    return "&&".join(parts)


def _var_row(v: dict[str, Any], *, scope: str = "") -> dict[str, Any]:
    ref = int(v.get("variablesReference") or 0)
    return {
        "name": v.get("name"),
        "value": v.get("value"),
        "type": v.get("type") or "",
        "scope": scope,
        "variablesReference": ref,
        "namedVariables": int(v.get("namedVariables") or 0),
        "indexedVariables": int(v.get("indexedVariables") or 0),
        "expandable": ref > 0,
    }


class CustomDapSession(_TimelineMixin, DebugSession):
    """Generic DAP session over a custom debugAdapter executable (stdio)."""

    def __init__(
        self,
        sid: str,
        workspace: Path,
        rel: str,
        target: Path,
        *,
        adapter_cmd: list[str],
        launch_args: dict[str, Any] | None = None,
        config_name: str = "",
    ) -> None:
        self.id = sid
        self.workspace = workspace.resolve()
        self.rel = rel
        self.target = target
        self.adapter_cmd = list(adapter_cmd)
        self.launch_args = dict(launch_args or {})
        self.config_name = config_name or "custom"
        self.client: DapClient | None = None
        self.alive = False
        self.stopped = False
        self.thread_id: int | None = None
        self.threads: list[dict[str, Any]] = []
        self.frame_id: Any = None
        self.stack: list[dict[str, Any]] = []
        self.variables: list[dict[str, Any]] = []
        self.watches: list[dict[str, Any]] = []
        self.inline_values: list[dict[str, Any]] = []
        self.console: list[dict[str, Any]] = []
        self.reason = ""
        self.error = ""
        self.port = 0
        self.capabilities: dict[str, Any] = {}
        self.parent_id: str | None = None
        self.child_ids: list[str] = []
        self._refresh_lock = threading.Lock()
        self._instruction_ref = ""
        self._timeline_init()

    def start(self) -> None:
        if not self.adapter_cmd:
            raise RuntimeError("debugAdapter command empty")
        self.client = DapClient.spawn_stdio(self.adapter_cmd, self.workspace)
        self.client.on_event(self._on_event)
        adapter_id = str(self.launch_args.get("type") or "custom")
        self.capabilities = self.client.initialize(adapter_id) or {}
        args = dict(self.launch_args)
        args.setdefault("cwd", str(self.workspace))
        if self.target.is_file() and "program" not in args:
            args["program"] = str(self.target)
        # Strip Zintriq-only keys
        for k in ("debugAdapter", "ssh", "docker", "jupyter", "reverse", "preLaunchTask"):
            args.pop(k, None)
        req = str(args.get("request") or "launch")
        seq = self.client.send_request(req, args)
        if not self.client.wait_event("initialized", timeout=20.0):
            raise RuntimeError("custom DAP initialized missing")
        for p in _all_bp_paths():
            self.apply_breakpoints(p)
        self.apply_exception_breakpoints()
        self.client.request("configurationDone", {})
        try:
            self.client.wait_response(seq, timeout=30.0)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        self.alive = True
        self._event_push("initialized")

    def stop(self) -> None:
        self.alive = False
        self._event_push("terminated")
        if self.client:
            try:
                self.client.stop()
            except Exception:
                pass
        self.client = None

    def apply_breakpoints(self, rel: str) -> None:
        if not self.client:
            return
        bps = _bps_for(rel)
        source_path = str((self.workspace / rel).resolve()) if not rel.startswith("(") else rel
        payload = []
        for bp in bps:
            item: dict[str, Any] = {"line": int(bp["line"])}
            for key in ("condition", "hitCondition", "logMessage"):
                if bp.get(key):
                    item[key] = bp[key]
            payload.append(item)
        try:
            self.client.request(
                "setBreakpoints",
                {"source": {"path": source_path}, "breakpoints": payload},
                timeout=8.0,
            )
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)

    def apply_exception_breakpoints(self) -> None:
        if not self.client:
            return
        filters = list_exception_breakpoints()
        filter_ids = [k for k, v in filters.items() if v]
        try:
            self.client.request("setExceptionBreakpoints", {"filters": filter_ids}, timeout=5.0)
        except Exception:
            pass

    def apply_data_breakpoints(self) -> None:
        pass

    def _on_event(self, event: str, body: dict[str, Any]) -> None:
        if event == "stopped":
            self.stopped = True
            self.thread_id = int(body.get("threadId") or 0) or None
            self.reason = str(body.get("reason") or "stopped")
            self._event_push("stopped", reason=self.reason)
            threading.Thread(target=self._refresh_if_stopped, name=f"custom-dap-{self.id}", daemon=True).start()
        elif event == "continued":
            self.stopped = False
            self._event_push("continued")
            self.stack = []
            self.variables = []
        elif event in {"terminated", "exited"}:
            self.alive = False
            self._event_push(event)
        elif event == "output":
            out = str(body.get("output") or "")
            if out:
                self.console.append({"type": "output", "text": out})
                self.console = self.console[-100:]

    def _refresh_if_stopped(self) -> None:
        if not self.client or not self.stopped or not self.thread_id:
            return
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            body = self.client.request(
                "stackTrace",
                {"threadId": self.thread_id, "startFrame": 0, "levels": 20},
                timeout=5.0,
            )
            frames = []
            for fr in (body or {}).get("stackFrames") or []:
                src = fr.get("source") or {}
                path = str(src.get("path") or "")
                try:
                    rel = str(Path(path).resolve().relative_to(self.workspace))
                except Exception:
                    rel = path
                frames.append(
                    {
                        "id": fr.get("id"),
                        "name": fr.get("name"),
                        "path": rel.replace("\\", "/"),
                        "line": fr.get("line"),
                        "column": fr.get("column"),
                    }
                )
            self.stack = frames
            self.frame_id = frames[0]["id"] if frames else None
            self.variables = []
            if self.frame_id is not None:
                scopes = self.client.request("scopes", {"frameId": self.frame_id}, timeout=5.0) or {}
                for sc in scopes.get("scopes") or []:
                    vb = self.client.request(
                        "variables", {"variablesReference": sc.get("variablesReference")}, timeout=5.0
                    ) or {}
                    for v in vb.get("variables") or []:
                        self.variables.append(_var_row(v, scope=str(sc.get("name") or "")))
            self.refresh_watches()
            self._timeline_push()
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        finally:
            self._refresh_lock.release()

    def refresh_watches(self) -> None:
        self.watches = []
        for expr in list_watches():
            try:
                res = self.evaluate(expr, context="watch")
                self.watches.append(
                    {"expression": expr, "value": res.get("value"), "type": res.get("type") or "", "error": ""}
                )
            except Exception as exc:  # noqa: BLE001
                self.watches.append({"expression": expr, "value": "", "type": "", "error": str(exc)})

    def evaluate(self, expression: str, *, frame_id: Any = None, context: str = "repl") -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("DAP not running")
        args: dict[str, Any] = {"expression": expression, "context": context}
        fid = frame_id if frame_id is not None else self.frame_id
        if fid is not None:
            args["frameId"] = fid
        body = self.client.request("evaluate", args, timeout=5.0) or {}
        return {"value": body.get("result") or "", "type": body.get("type") or "", "variablesReference": body.get("variablesReference") or 0}

    def cont(self) -> dict[str, Any]:
        if self.client and self.thread_id is not None:
            self.client.request("continue", {"threadId": self.thread_id}, timeout=5.0)
            self.stopped = False
            self._event_push("continued")
        return self.snapshot()

    def step_over(self) -> dict[str, Any]:
        if self.client and self.thread_id is not None:
            self.client.request("next", {"threadId": self.thread_id}, timeout=5.0)
        return self.snapshot()

    def step_in(self) -> dict[str, Any]:
        if self.client and self.thread_id is not None:
            self.client.request("stepIn", {"threadId": self.thread_id}, timeout=5.0)
        return self.snapshot()

    def step_out(self) -> dict[str, Any]:
        if self.client and self.thread_id is not None:
            self.client.request("stepOut", {"threadId": self.thread_id}, timeout=5.0)
        return self.snapshot()

    def step_back(self) -> dict[str, Any]:
        raise RuntimeError("stepBack not supported on custom adapter")

    def reverse_continue(self) -> dict[str, Any]:
        raise RuntimeError("reverseContinue not supported on custom adapter")

    def select_frame(self, frame_id: Any) -> None:
        self.frame_id = frame_id
        self._refresh_if_stopped()

    def select_thread(self, thread_id: Any) -> None:
        self.thread_id = int(thread_id)

    def expand_variables(self, variables_reference: int) -> list[dict[str, Any]]:
        if not self.client:
            return []
        body = self.client.request("variables", {"variablesReference": int(variables_reference)}, timeout=5.0) or {}
        return [_var_row(v) for v in body.get("variables") or []]

    def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]:
        return {"ok": False, "text": "", "error": "disassemble N/A"}

    def read_memory(
        self,
        *,
        memory_reference: str = "",
        expression: str = "",
        offset: int = 0,
        count: int = 64,
    ) -> dict[str, Any]:
        return {"ok": False, "text": "", "error": "readMemory N/A"}

    def snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "sessionId": self.id,
            "engine": "custom-dap",
            "running": self.alive,
            "stopped": self.stopped,
            "configName": self.config_name,
            "path": self.rel,
            "reason": self.reason,
            "error": self.error,
            "stack": list(self.stack),
            "variables": list(self.variables)[:80],
            "watches": list(self.watches),
            "console": list(self.console)[-40:],
            "threads": list(self.threads),
            "threadId": self.thread_id,
            "frameId": self.frame_id,
            "timeline": self._timeline_meta(),
            "capabilities": {
                k: self.capabilities.get(k)
                for k in (
                    "supportsDataBreakpoints",
                    "supportsSetVariable",
                    "supportsSetExpression",
                    "supportsReadMemoryRequest",
                    "supportsDisassembleRequest",
                    "exceptionBreakpointFilters",
                )
                if k in self.capabilities
            },
        }


class PythonDapSession(_TimelineMixin, DebugSession):
    def __init__(
        self,
        sid: str,
        workspace: Path,
        rel: str,
        target: Path,
        *,
        attach_host: str | None = None,
        attach_port: int | None = None,
        path_mappings: list[dict[str, str]] | None = None,
        program_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        stop_on_entry: bool = True,
        just_my_code: bool = True,
        config_name: str = "",
        module: str = "",
        sub_process: bool = True,
    ) -> None:
        self.id = sid
        self.workspace = workspace.resolve()
        self.rel = rel
        self.target = target
        self.attach_host = attach_host
        self.attach_port = attach_port
        self.path_mappings = [dict(x) for x in (path_mappings or [])]
        self.program_args = list(program_args or [])
        self.env_extra = dict(env or {})
        self.cwd = Path(cwd).resolve() if cwd else self.workspace
        self.stop_on_entry = bool(stop_on_entry)
        self.just_my_code = bool(just_my_code)
        self.config_name = config_name or ""
        self.module = (module or "").strip()
        self.sub_process = bool(sub_process)
        self.owns_process = attach_host is None
        self.client: DapClient | None = None
        self.debuggee: subprocess.Popen[bytes] | None = None
        self.alive = False
        self.stopped = False
        self.thread_id: int | None = None
        self.threads: list[dict[str, Any]] = []
        self.frame_id: Any = None
        self.stack: list[dict[str, Any]] = []
        self.variables: list[dict[str, Any]] = []
        self.watches: list[dict[str, Any]] = []
        self.inline_values: list[dict[str, Any]] = []
        self.console: list[dict[str, Any]] = []
        self.reason = ""
        self.error = ""
        self.port = 0
        self.capabilities: dict[str, Any] = {}
        self.parent_id: str | None = None
        self.child_ids: list[str] = []
        self._profiling = False
        self._refresh_lock = threading.Lock()
        self._instruction_ref: str = ""
        self.readonly = False
        self.modules: list[dict[str, Any]] = []
        self._timeline_init()

    def start(self) -> None:
        if not adapters()["python"]:
            raise RuntimeError("debugpy not installed (pip install debugpy)")
        if self.attach_host is not None and self.attach_port is not None:
            self._start_attach()
        else:
            self._start_launch()

    def _bind_run_in_terminal(self) -> None:
        if not self.client:
            return

        def _run_in_terminal(args: dict[str, Any]) -> dict[str, Any]:
            cwd = str(args.get("cwd") or self.cwd)
            cmd = args.get("args") or args.get("command") or []
            if isinstance(cmd, str):
                cmd = [cmd]
            cmd = [str(x) for x in cmd]
            kind = str(args.get("kind") or "integrated")
            # Integrated: try injecting into existing PTY shell; else spawn detached.
            if kind in {"integrated", "external"}:
                try:
                    from editor import pty_session

                    # Start a shell PTY and feed the command line
                    info = pty_session.start(self.workspace)
                    tid = str(info.get("id") or info.get("sessionId") or "")
                    if tid and cmd:
                        line = " ".join(cmd) + "\n"
                        pty_session.write(tid, f"cd {cwd!s}\n{line}")
                        self.console.append(
                            {"type": "output", "text": f"runInTerminal[{kind}] → pty {tid}: {line.strip()}"}
                        )
                        return {"processId": None, "shellProcessId": None}
                except Exception:
                    pass
            proc = subprocess.Popen(cmd, cwd=cwd, start_new_session=True)
            self.console.append(
                {"type": "output", "text": f"runInTerminal[{kind}] pid={proc.pid}: {' '.join(cmd)}"}
            )
            return {"processId": proc.pid}

        self.client.on_reverse_request("runInTerminal", _run_in_terminal)

    def _start_launch(self) -> None:
        self.port = _free_port()
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.debuggee = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "debugpy.adapter",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=str(self.workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self.client = DapClient.connect_tcp("127.0.0.1", self.port, timeout=12.0)
        self.client.on_event(self._on_event)
        self._bind_run_in_terminal()
        self.capabilities = self.client.initialize("debugpy") or {}
        env = {**os.environ, **self.env_extra, "PYTHONUNBUFFERED": "1"}
        launch_args: dict[str, Any] = {
            "name": self.config_name or f"Zintriq:{self.rel}",
            "type": "python",
            "request": "launch",
            "cwd": str(self.cwd),
            "python": sys.executable,
            "args": list(self.program_args),
            "env": env,
            "console": "internalConsole",
            "stopOnEntry": self.stop_on_entry,
            "justMyCode": self.just_my_code,
            "subProcess": self.sub_process,
        }
        if self.module:
            launch_args["module"] = self.module
        else:
            launch_args["program"] = str(self.target)
        launch_seq = self.client.send_request("launch", launch_args)
        if not self.client.wait_event("initialized", timeout=15.0):
            raise RuntimeError("DAP initialized event missing")
        for p in _all_bp_paths():
            self.apply_breakpoints(p)
        self.apply_breakpoints(self.rel)
        self.apply_exception_breakpoints()
        self.client.request("configurationDone", {})
        try:
            self.client.wait_response(launch_seq, timeout=20.0)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        self.alive = True
        deadline = time.time() + 5.0
        while time.time() < deadline and not self.stopped:
            time.sleep(0.05)
            self._refresh_if_stopped()

    def _path_mappings_payload(self) -> list[dict[str, str]]:
        maps = self.path_mappings or list_path_mappings()
        if maps:
            return [
                {"localRoot": m["localRoot"], "remoteRoot": m["remoteRoot"]}
                for m in maps
            ]
        return [{"localRoot": str(self.workspace), "remoteRoot": str(self.workspace)}]

    def _start_attach(self) -> None:
        assert self.attach_host is not None and self.attach_port is not None
        self.port = int(self.attach_port)
        self.client = DapClient.connect_tcp(self.attach_host, self.port, timeout=12.0)
        self.client.on_event(self._on_event)
        self._bind_run_in_terminal()
        self.capabilities = self.client.initialize("debugpy") or {}
        # Direct DAP attach to a debugpy.listen / --listen port (already connected).
        attach_seq = self.client.send_request(
            "attach",
            {
                "name": f"Zintriq attach {self.attach_host}:{self.port}",
                "type": "python",
                "request": "attach",
                "justMyCode": True,
                "pathMappings": self._path_mappings_payload(),
            },
        )
        if not self.client.wait_event("initialized", timeout=15.0):
            # Some debugpy listen ports accept attach without a second initialized.
            pass
        for p in _all_bp_paths():
            self.apply_breakpoints(p)
        self.apply_exception_breakpoints()
        try:
            self.client.request("configurationDone", {}, timeout=8.0)
        except Exception:
            pass
        try:
            self.client.wait_response(attach_seq, timeout=20.0)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        self.alive = True
        self.rel = f"attach:{self.attach_host}:{self.port}"
        deadline = time.time() + 3.0
        while time.time() < deadline and not self.stopped:
            time.sleep(0.05)
            self._refresh_if_stopped()

    def stop(self) -> None:
        self.alive = False
        if self.client:
            try:
                if not self.owns_process:
                    try:
                        self.client.request("disconnect", {"restart": False}, timeout=2.0)
                    except Exception:
                        pass
                self.client.stop()
            except Exception:
                pass
        self.client = None
        if self.owns_process and self.debuggee:
            if self.debuggee.poll() is None:
                try:
                    self.debuggee.kill()
                except Exception:
                    pass
            for pipe in (self.debuggee.stdout, self.debuggee.stderr):
                try:
                    if pipe:
                        pipe.close()
                except Exception:
                    pass
        self.debuggee = None

    def apply_breakpoints(self, rel: str) -> None:
        if not self.client:
            return
        bps = _bps_for(rel)
        source_path = str((self.workspace / rel).resolve())
        # Also try remote-mapped path for attach sessions.
        sources = [source_path]
        for m in self.path_mappings or list_path_mappings():
            local = m["localRoot"].rstrip("/")
            remote = m["remoteRoot"].rstrip("/")
            abs_local = str((self.workspace / rel).resolve()).replace("\\", "/")
            if abs_local.startswith(local + "/") or abs_local == local:
                sources.append(remote + abs_local[len(local) :])
            elif rel and not rel.startswith("("):
                sources.append(f"{remote}/{rel}")
        # unique preserve order
        seen: set[str] = set()
        uniq_sources = []
        for s in sources:
            if s not in seen:
                seen.add(s)
                uniq_sources.append(s)
        payload = []
        for bp in bps:
            item: dict[str, Any] = {"line": int(bp["line"])}
            if bp.get("column"):
                item["column"] = int(bp["column"])
            cond = (bp.get("condition") or "").strip()
            if cond:
                item["condition"] = cond
            hit = (bp.get("hitCondition") or "").strip()
            if hit:
                item["hitCondition"] = hit
            log = (bp.get("logMessage") or "").strip()
            if log:
                item["logMessage"] = log
                # Also index as structured tracepoint warehouse
                try:
                    from editor import debug_features

                    debug_features.record_tracepoint(log, path=rel, line=int(bp["line"]))
                except Exception:
                    pass
            payload.append(item)
        for source_path in uniq_sources:
            try:
                self.client.request(
                    "setBreakpoints",
                    {"source": {"path": source_path}, "breakpoints": payload},
                    timeout=8.0,
                )
            except Exception:
                pass
        self.apply_function_breakpoints()

    def apply_function_breakpoints(self) -> None:
        from editor import debug_features

        if not self.client:
            return
        wanted = debug_features.list_function_breakpoints()
        bps = []
        for item in wanted:
            entry: dict[str, Any] = {"name": item["name"]}
            if item.get("condition"):
                entry["condition"] = item["condition"]
            bps.append(entry)
        try:
            self.client.request("setFunctionBreakpoints", {"breakpoints": bps}, timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            self.error = f"function BP: {exc}"

    def step_in_targets(self, *, frame_id: Any = None) -> list[dict[str, Any]]:
        if not self.client or not self.stopped:
            return []
        fid = frame_id if frame_id is not None else self.frame_id
        if fid is None:
            return []
        try:
            body = self.client.request("stepInTargets", {"frameId": fid}, timeout=5.0) or {}
            return [
                {
                    "id": t.get("id"),
                    "label": t.get("label") or str(t.get("id")),
                    "line": t.get("line"),
                    "column": t.get("column"),
                    "endLine": t.get("endLine"),
                    "endColumn": t.get("endColumn"),
                }
                for t in (body.get("targets") or [])
            ]
        except Exception:
            return []

    def step_in_target(self, target_id: Any) -> dict[str, Any]:
        if not self.client or not self.thread_id:
            raise RuntimeError("not stopped")
        if self.timeline_viewing:
            self.timeline_live()
        self.stopped = False
        args: dict[str, Any] = {"threadId": self.thread_id}
        if target_id is not None:
            args["targetId"] = target_id
        self.client.request("stepIn", args, timeout=8.0)
        deadline = time.time() + 5.0
        while time.time() < deadline and self.alive and not self.stopped:
            time.sleep(0.05)
        if self.stopped:
            self._refresh_if_stopped()
        return self.snapshot()

    def apply_exception_breakpoints(self) -> None:
        if not self.client:
            return
        filters = list_exception_breakpoints()
        # Prefer adapter-advertised exceptionBreakpointFilters ids when present
        advertised = self.capabilities.get("exceptionBreakpointFilters") or []
        filter_ids: list[str] = []
        if isinstance(advertised, list) and advertised:
            id_set = {str(f.get("filter") or f.get("label") or "") for f in advertised if isinstance(f, dict)}
            for key, on in filters.items():
                if on and (key in id_set or key in {"raised", "uncaught", "userUnhandled"}):
                    # Map our keys onto common debugpy ids
                    mapped = key
                    if key == "raised" and "raised" not in id_set and "userUnhandled" in id_set:
                        mapped = "raised"
                    filter_ids.append(mapped)
            # Also enable any extra filter toggles that match advertised
            for f in advertised:
                if not isinstance(f, dict):
                    continue
                fid = str(f.get("filter") or "")
                if fid and filters.get(fid):
                    if fid not in filter_ids:
                        filter_ids.append(fid)
        else:
            if filters.get("raised"):
                filter_ids.append("raised")
            if filters.get("uncaught"):
                filter_ids.append("uncaught")
            for k, v in filters.items():
                if k not in {"raised", "uncaught"} and v and k not in filter_ids:
                    filter_ids.append(k)
        try:
            self.client.request("setExceptionBreakpoints", {"filters": filter_ids}, timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)

    def _on_event(self, event: str, body: dict[str, Any]) -> None:
        if event == "stopped":
            self.stopped = True
            self.thread_id = int(body.get("threadId") or 0) or None
            self.reason = str(body.get("reason") or "stopped")
            self._event_push("stopped", reason=self.reason)
            # Never DAP-request from the reader thread (deadlock); refresh async.
            threading.Thread(target=self._refresh_if_stopped, name=f"dap-refresh-{self.id}", daemon=True).start()
        elif event == "continued":
            self.stopped = False
            self._event_push("continued")
            self.stack = []
            self.variables = []
            self.watches = []
            self.inline_values = []
            self.frame_id = None
        elif event == "output":
            out = str(body.get("output") or "")
            if out and body.get("category") != "telemetry":
                self.console.append({"type": "output", "category": body.get("category"), "text": out})
                self.console = self.console[-100:]
        elif event == "process":
            # Subprocess / child process notification — surface as child session stub.
            name = str(body.get("name") or "subprocess")
            if self.sub_process and body.get("startMethod") in {None, "launch", "attach"}:
                child = ChildProxySession(
                    uuid.uuid4().hex[:10],
                    self.workspace,
                    f"child:{name}",
                    parent=self,
                    meta=body,
                )
                register_child_session(self.id, child)
        elif event in {"terminated", "exited"}:
            self.alive = False
            self.stopped = False
            self._event_push(event)

    def _refresh_if_stopped(self) -> None:
        if not self.client or not self.stopped or not self.thread_id:
            return
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            body = self.client.request(
                "stackTrace",
                {"threadId": self.thread_id, "startFrame": 0, "levels": 20},
                timeout=5.0,
            )
            frames = []
            self._instruction_ref = ""
            for fr in (body or {}).get("stackFrames") or []:
                src = fr.get("source") or {}
                path = str(src.get("path") or "")
                mapped = _map_remote_to_local(path)
                try:
                    rel = str(Path(mapped).resolve().relative_to(self.workspace))
                except Exception:
                    try:
                        rel = str(Path(path).resolve().relative_to(self.workspace))
                    except Exception:
                        rel = mapped or path
                frames.append(
                    {
                        "id": fr.get("id"),
                        "name": fr.get("name"),
                        "path": rel.replace("\\", "/"),
                        "line": fr.get("line"),
                        "column": fr.get("column"),
                        "instructionPointerReference": fr.get("instructionPointerReference") or "",
                    }
                )
                if not self._instruction_ref and fr.get("instructionPointerReference"):
                    self._instruction_ref = str(fr.get("instructionPointerReference") or "")
            self.stack = frames
            keep = self.frame_id
            if keep is not None and any(f["id"] == keep for f in frames):
                self.frame_id = keep
            else:
                self.frame_id = frames[0]["id"] if frames else None
            self._load_vars_for_frame(self.frame_id)
            try:
                self.apply_data_breakpoints()
            except Exception:
                pass
            self._refresh_threads()
            self.refresh_watches()
            self.inline_values = _compute_inline_values(
                self.workspace, self.stack, self.frame_id, self.variables
            )
            # Merge pinned expressions into inline values
            try:
                from editor import debug_features

                for pin in debug_features.list_pinned_vars():
                    try:
                        ev = self.evaluate(pin["expression"], frame_id=self.frame_id, context="watch")
                        self.inline_values.append(
                            {
                                "expression": pin["expression"],
                                "value": ev.get("value"),
                                "pinned": True,
                                "label": pin.get("label"),
                            }
                        )
                    except Exception:
                        pass
                # SBOM / CVE pause annotation
                sbom = debug_features.check_sbom_pause(self.modules or [], path=str((self.stack or [{}])[0].get("path") or ""))
                if sbom.get("pause"):
                    self.reason = f"{self.reason}; {sbom.get('reason')}"
            except Exception:
                pass
            self._timeline_push()
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        finally:
            self._refresh_lock.release()

    def _refresh_threads(self) -> None:
        if not self.client:
            return
        try:
            body = self.client.request("threads", {}, timeout=5.0) or {}
            out = []
            for t in body.get("threads") or []:
                out.append({"id": t.get("id"), "name": t.get("name") or f"Thread {t.get('id')}"})
            self.threads = out
            if self.thread_id is None and out:
                self.thread_id = out[0]["id"]
        except Exception:
            if self.thread_id is not None:
                self.threads = [{"id": self.thread_id, "name": f"Thread {self.thread_id}"}]

    def select_thread(self, thread_id: Any) -> None:
        if self.timeline_viewing:
            self.timeline_live()
        tid = int(thread_id)
        self.thread_id = tid
        if not self.stopped:
            raise RuntimeError("select thread requires paused session")
        self._refresh_if_stopped()

    def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("DAP not running")
        if not self.stopped:
            raise RuntimeError("disassemble requires paused session")
        if self.timeline_viewing:
            raise RuntimeError("leave timeline view first")
        ref = (memory_reference or self._instruction_ref or "").strip()
        n = max(1, min(int(count or 64), 256))
        if ref and self.capabilities.get("supportsDisassembleRequest", True):
            try:
                body = self.client.request(
                    "disassemble",
                    {
                        "memoryReference": ref,
                        "offset": int(offset or 0),
                        "instructionOffset": 0,
                        "instructionCount": n,
                        "resolveSymbols": True,
                    },
                    timeout=8.0,
                ) or {}
                instrs = body.get("instructions") or []
                lines = []
                for ins in instrs:
                    addr = ins.get("address") or ""
                    text = ins.get("instruction") or ""
                    sym = ins.get("symbol") or ""
                    lines.append(f"{addr}  {text}" + (f"  ; {sym}" if sym else ""))
                if lines:
                    return {
                        "ok": True,
                        "engine": "dap-debugpy",
                        "mode": "disassemble",
                        "text": "\n".join(lines),
                        "instructions": instrs,
                    }
            except Exception:
                pass
        # Fallback: CPython bytecode via evaluate
        try:
            res = self.evaluate(
                "__import__('dis').Bytecode(__import__('sys')._getframe().f_code).dis()",
                frame_id=self.frame_id,
                context="watch",
            )
            text = str(res.get("value") or "")
            if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
                try:
                    text = _ast_bytes_literal(text) if text.startswith("b") else __import__("ast").literal_eval(text)
                    text = str(text)
                except Exception:
                    pass
            return {"ok": True, "engine": "dap-debugpy", "mode": "bytecode", "text": text}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "text": ""}

    def read_memory(
        self,
        *,
        memory_reference: str = "",
        expression: str = "",
        offset: int = 0,
        count: int = 64,
    ) -> dict[str, Any]:
        import base64

        if not self.client:
            raise RuntimeError("DAP not running")
        if not self.stopped:
            raise RuntimeError("readMemory requires paused session")
        n = max(1, min(int(count or 64), 512))
        ref = (memory_reference or "").strip()
        if not ref and expression.strip():
            try:
                ev = self.evaluate(
                    f"(lambda o: (hex(id(o)), o))({expression.strip()})",
                    frame_id=self.frame_id,
                    context="repl",
                )
            except Exception:
                ev = {}
            # Prefer DAP memoryReference from evaluate if present — rare for Python.
            ref = str((ev or {}).get("memoryReference") or "")
        if ref and self.capabilities.get("supportsReadMemoryRequest", True):
            try:
                body = self.client.request(
                    "readMemory",
                    {"memoryReference": ref, "offset": int(offset or 0), "count": n},
                    timeout=8.0,
                ) or {}
                raw_b64 = body.get("data") or ""
                data = base64.b64decode(raw_b64) if raw_b64 else b""
                return {
                    "ok": True,
                    "engine": "dap-debugpy",
                    "mode": "readMemory",
                    "address": body.get("address") or ref,
                    "bytesRead": len(data),
                    "text": _format_hex_dump(data, base=int(offset or 0)),
                    "data": raw_b64,
                }
            except Exception:
                pass
        # Fallback: dump object repr / bytes via evaluate
        expr = (expression or memory_reference or "").strip()
        if not expr:
            raise ValueError("expression or memoryReference required")
        dump_expr = (
            f"(lambda o: (bytes(o)[:{n}] if isinstance(o,(bytes,bytearray,memoryview)) "
            f"else repr(o)[:{n*4}]))({expr})"
        )
        res = self.evaluate(dump_expr, frame_id=self.frame_id, context="repl")
        val = res.get("value")
        if isinstance(val, (bytes, bytearray)):
            data = bytes(val)
            return {
                "ok": True,
                "engine": "dap-debugpy",
                "mode": "evaluate",
                "text": _format_hex_dump(data),
                "bytesRead": len(data),
            }
        text = str(val or "")
        # try to parse b'...' style
        if text.startswith("b'") or text.startswith('b"'):
            try:
                data = _ast_bytes_literal(text)
                return {
                    "ok": True,
                    "engine": "dap-debugpy",
                    "mode": "evaluate",
                    "text": _format_hex_dump(data[:n]),
                    "bytesRead": min(len(data), n),
                }
            except Exception:
                pass
        return {"ok": True, "engine": "dap-debugpy", "mode": "repr", "text": text, "bytesRead": 0}

    def _load_vars_for_frame(self, frame_id: Any) -> None:
        self.variables = []
        if not self.client or frame_id is None:
            return
        scopes = self.client.request("scopes", {"frameId": frame_id}, timeout=8.0)
        for sc in (scopes or {}).get("scopes") or []:
            if sc.get("expensive"):
                continue
            vars_body = self.client.request(
                "variables",
                {"variablesReference": sc.get("variablesReference")},
                timeout=8.0,
            )
            for v in (vars_body or {}).get("variables") or []:
                self.variables.append(_var_row(v, scope=str(sc.get("name") or "")))
            if len(self.variables) > 80:
                break

    def select_frame(self, frame_id: Any) -> None:
        if self.timeline_viewing:
            raise RuntimeError("leave timeline view first")
        if not self.stopped:
            raise RuntimeError("select frame requires paused session")
        fid = frame_id
        if not any(f.get("id") == fid for f in self.stack):
            # allow numeric string ids
            for f in self.stack:
                if str(f.get("id")) == str(frame_id):
                    fid = f.get("id")
                    break
            else:
                raise ValueError("unknown frame")
        self.frame_id = fid
        self._load_vars_for_frame(fid)
        self.refresh_watches()
        self.inline_values = _compute_inline_values(
            self.workspace, self.stack, self.frame_id, self.variables
        )

    def apply_data_breakpoints(self) -> None:
        if not self.client or not self.stopped:
            return
        wanted = list_data_breakpoints()
        if not wanted:
            try:
                self.client.request("setDataBreakpoints", {"breakpoints": []}, timeout=5.0)
            except Exception:
                pass
            return
        if not self.capabilities.get("supportsDataBreakpoints", True):
            return
        bps: list[dict[str, Any]] = []
        for item in wanted:
            name = item["name"]
            args: dict[str, Any] = {"name": name}
            if self.frame_id is not None:
                args["frameId"] = self.frame_id
            try:
                info = self.client.request("dataBreakpointInfo", args, timeout=5.0) or {}
            except Exception:
                try:
                    info = self.client.request("dataBreakpointInfo", {"name": name}, timeout=5.0) or {}
                except Exception as exc:  # noqa: BLE001
                    self.error = f"data BP {name}: {exc}"
                    continue
            data_id = info.get("dataId")
            if not data_id:
                continue
            access = item.get("accessType") or "write"
            allowed = info.get("accessTypes") or ["write"]
            if access not in allowed:
                access = allowed[0] if allowed else "write"
            entry: dict[str, Any] = {"dataId": data_id, "accessType": access}
            cond = (item.get("condition") or "").strip()
            if cond:
                entry["condition"] = cond
            bps.append(entry)
        try:
            self.client.request("setDataBreakpoints", {"breakpoints": bps}, timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)

    def data_breakpoint_info(self, name: str, *, frame_id: Any = None) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("DAP not running")
        args: dict[str, Any] = {"name": (name or "").strip()}
        fid = frame_id if frame_id is not None else self.frame_id
        if fid is not None:
            args["frameId"] = fid
        info = self.client.request("dataBreakpointInfo", args, timeout=5.0) or {}
        return {
            "ok": True,
            "name": name,
            "dataId": info.get("dataId"),
            "description": info.get("description") or "",
            "accessTypes": info.get("accessTypes") or ["write"],
            "canPersist": bool(info.get("canPersist")),
        }

    def list_modules(self) -> list[dict[str, Any]]:
        if not self.client:
            return list(self.modules)
        try:
            body = self.client.request("modules", {}, timeout=5.0) or {}
            mods = []
            for m in body.get("modules") or []:
                mods.append(
                    {
                        "id": m.get("id"),
                        "name": m.get("name") or "",
                        "path": m.get("path") or "",
                        "version": m.get("version") or "",
                        "symbolStatus": m.get("symbolStatus") or "",
                    }
                )
            self.modules = mods
            return mods
        except Exception:
            # Fallback: sys.modules via evaluate
            try:
                res = self.evaluate(
                    "[(n, getattr(m,'__file__',None)) for n,m in list(__import__('sys').modules.items())[:80]]",
                    context="watch",
                )
                text = str(res.get("value") or "")
                return [{"name": "sys.modules", "path": text[:500], "id": 0}]
            except Exception:
                return list(self.modules)

    def apply_instruction_breakpoints(self) -> None:
        from editor import debug_features

        if not self.client:
            return
        wanted = debug_features.list_instruction_breakpoints()
        bps = []
        for item in wanted:
            entry: dict[str, Any] = {
                "instructionReference": item["instructionReference"],
                "offset": int(item.get("offset") or 0),
            }
            if item.get("condition"):
                entry["condition"] = item["condition"]
            bps.append(entry)
        try:
            self.client.request("setInstructionBreakpoints", {"breakpoints": bps}, timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            self.error = f"instruction BP: {exc}"

    def hot_reload(self, *, module: str = "") -> dict[str, Any]:
        if not self.stopped:
            raise RuntimeError("hotReload requires paused session")
        mod = (module or "").strip()
        if mod:
            expr = (
                f"(lambda m: (__import__('importlib').reload(__import__('sys').modules[m]) "
                f"and f'reloaded {{m}}') if m in __import__('sys').modules else "
                f"(__import__(m) and f'imported {{m}}'))({mod!r})"
            )
        else:
            # Reload current frame module
            expr = (
                "(lambda p: (__import__('importlib').reload(__import__(p)) and f'reloaded {p}') "
                "if p else 'no module')( (__import__('sys').modules.get('__main__') and '__main__') )"
            )
            # Better: use stack top path
            top = (self.stack or [{}])[0]
            path = str(top.get("path") or self.rel or "")
            if path.endswith(".py") and not path.startswith("("):
                # Convert path to module-ish reload via importlib.util
                expr = (
                    f"(lambda path: (lambda s: (__import__('importlib').util.spec_from_file_location('zintriq_hot', path) "
                    f"and __import__('importlib').reload(__import__('importlib').util.module_from_spec("
                    f"__import__('importlib').util.spec_from_file_location('zintriq_hot', path))) "
                    f") or path) )({str((self.workspace / path).resolve())!r})"
                )
                # Simpler reliable path:
                expr = (
                    "(__import__('importlib').reload(__import__('sys').modules['__main__']) "
                    "and 'reloaded __main__') if '__main__' in __import__('sys').modules else 'skip'"
                )
        res = self.evaluate(expr, context="repl")
        return {"ok": True, "engine": "python", "result": res.get("value"), "module": mod or "__main__"}

    def set_variable(self, *, variables_reference: int, name: str, value: str) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("DAP not running")
        if not self.stopped:
            raise RuntimeError("setVariable requires paused session")
        body = self.client.request(
            "setVariable",
            {
                "variablesReference": int(variables_reference),
                "name": str(name),
                "value": str(value),
            },
            timeout=8.0,
        ) or {}
        self._load_vars_for_frame(self.frame_id)
        self.refresh_watches()
        return {
            "ok": True,
            "name": body.get("name") or name,
            "value": body.get("value") or value,
            "type": body.get("type") or "",
            "variablesReference": body.get("variablesReference") or 0,
        }

    def set_expression(self, *, expression: str, value: str, frame_id: Any = None) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("DAP not running")
        if not self.stopped:
            raise RuntimeError("setExpression requires paused session")
        args: dict[str, Any] = {"expression": str(expression), "value": str(value)}
        fid = frame_id if frame_id is not None else self.frame_id
        if fid is not None:
            args["frameId"] = fid
        if self.capabilities.get("supportsSetExpression", True):
            try:
                body = self.client.request("setExpression", args, timeout=8.0) or {}
                self._load_vars_for_frame(self.frame_id)
                self.refresh_watches()
                return {
                    "ok": True,
                    "value": body.get("value") or value,
                    "type": body.get("type") or "",
                    "variablesReference": body.get("variablesReference") or 0,
                }
            except Exception:
                pass
        # Fallback: assign via evaluate
        assign = f"{expression} = {value}"
        res = self.evaluate(assign, frame_id=fid, context="repl")
        self._load_vars_for_frame(self.frame_id)
        return {"ok": True, "value": res.get("value"), "type": res.get("type") or "", "mode": "evaluate"}

    def write_memory(
        self,
        *,
        memory_reference: str = "",
        data: str = "",
        offset: int = 0,
        allow_partial: bool = True,
    ) -> dict[str, Any]:
        import base64

        if not self.client:
            raise RuntimeError("DAP not running")
        if not self.stopped:
            raise RuntimeError("writeMemory requires paused session")
        ref = (memory_reference or "").strip()
        if not ref:
            raise ValueError("memoryReference required")
        raw = data.strip()
        try:
            blob = base64.b64decode(raw) if re.fullmatch(r"[A-Za-z0-9+/=\s]+", raw) and len(raw) % 4 == 0 else bytes.fromhex(raw.replace(" ", ""))
        except Exception as exc:
            raise ValueError(f"data must be base64 or hex: {exc}") from exc
        body = self.client.request(
            "writeMemory",
            {
                "memoryReference": ref,
                "offset": int(offset or 0),
                "allowPartial": bool(allow_partial),
                "data": base64.b64encode(blob).decode("ascii"),
            },
            timeout=8.0,
        ) or {}
        return {
            "ok": True,
            "bytesWritten": body.get("bytesWritten") or len(blob),
            "offset": body.get("offset") or offset,
        }

    def breakpoint_locations(
        self, *, path: str, line: int, end_line: int | None = None
    ) -> list[dict[str, Any]]:
        if not self.client:
            return [{"line": int(line), "column": 1}]
        source_path = str((self.workspace / path).resolve()) if path and not path.startswith("(") else path
        args: dict[str, Any] = {
            "source": {"path": source_path},
            "line": int(line),
        }
        if end_line is not None:
            args["endLine"] = int(end_line)
        try:
            body = self.client.request("breakpointLocations", args, timeout=5.0) or {}
            return [
                {
                    "line": loc.get("line"),
                    "column": loc.get("column"),
                    "endLine": loc.get("endLine"),
                    "endColumn": loc.get("endColumn"),
                }
                for loc in (body.get("breakpoints") or [])
            ]
        except Exception:
            return [{"line": int(line), "column": 1}]

    def expand_variables(self, variables_reference: int) -> list[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("DAP not running")
        if not self.stopped:
            raise RuntimeError("expand requires paused session")
        if self.timeline_viewing:
            raise RuntimeError("timeline view is read-only")
        body = self.client.request(
            "variables",
            {"variablesReference": int(variables_reference)},
            timeout=8.0,
        )
        return [_var_row(v) for v in (body or {}).get("variables") or []]

    def refresh_watches(self) -> None:
        exprs = list_watches()
        out: list[dict[str, Any]] = []
        for expr in exprs:
            try:
                res = self.evaluate(expr, frame_id=self.frame_id, context="watch")
                out.append(
                    {
                        "expression": expr,
                        "value": res.get("value"),
                        "type": res.get("type") or "",
                        "error": "",
                        "variablesReference": int(res.get("variablesReference") or 0),
                        "expandable": int(res.get("variablesReference") or 0) > 0,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                out.append(
                    {
                        "expression": expr,
                        "value": "",
                        "type": "",
                        "error": str(exc),
                        "variablesReference": 0,
                        "expandable": False,
                    }
                )
        self.watches = out

    def evaluate(self, expression: str, *, frame_id: Any = None, context: str = "repl") -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("DAP not running")
        if not self.stopped:
            raise RuntimeError("evaluate requires paused session")
        if self.timeline_viewing and context == "repl":
            raise RuntimeError("leave timeline view first")
        fid = frame_id if frame_id is not None else self.frame_id
        args: dict[str, Any] = {
            "expression": expression,
            "context": context if context in {"repl", "watch", "hover", "clipboard"} else "repl",
        }
        if fid is not None:
            args["frameId"] = fid
        body = self.client.request("evaluate", args, timeout=5.0) or {}
        result = {
            "value": body.get("result") or body.get("value") or "",
            "type": body.get("type") or "",
            "variablesReference": body.get("variablesReference") or 0,
        }
        if context == "repl":
            self.console.append({"type": "in", "text": expression})
            self.console.append({"type": "out", "text": str(result["value"]), "valueType": result["type"]})
            self.console = self.console[-100:]
        return result

    def cont(self) -> dict[str, Any]:
        return self._run_cmd("continue")

    def step_over(self) -> dict[str, Any]:
        return self._run_cmd("next")

    def step_in(self) -> dict[str, Any]:
        return self._run_cmd("stepIn")

    def step_out(self) -> dict[str, Any]:
        return self._run_cmd("stepOut")

    def step_back(self) -> dict[str, Any]:
        """True DAP stepBack when supported; else seek previous timeline snapshot."""
        if self.timeline_viewing:
            if self.timeline_index > 0:
                self.timeline_seek(self.timeline_index - 1)
            return self.snapshot()
        if self.capabilities.get("supportsStepBackRequest") and self.client and self.thread_id:
            try:
                return self._run_cmd("stepBack")
            except Exception:
                pass
        if self.timeline and self.timeline_index > 0:
            self.timeline_seek(self.timeline_index - 1)
            return self.snapshot()
        raise RuntimeError("stepBack unavailable (no DAP support / timeline empty)")

    def reverse_continue(self) -> dict[str, Any]:
        if self.capabilities.get("supportsStepBackRequest") and self.client and self.thread_id:
            try:
                return self._run_cmd("reverseContinue")
            except Exception:
                pass
        if self.timeline:
            self.timeline_seek(0)
            return self.snapshot()
        raise RuntimeError("reverseContinue unavailable")

    def completions(self, text: str, column: int, *, frame_id: Any = None) -> list[dict[str, Any]]:
        if not self.client or not self.stopped:
            return []
        fid = frame_id if frame_id is not None else self.frame_id
        try:
            body = self.client.request(
                "completions",
                {
                    "text": text,
                    "column": max(1, int(column)),
                    **({"frameId": fid} if fid is not None else {}),
                },
                timeout=5.0,
            ) or {}
            out = []
            for it in body.get("targets") or []:
                out.append(
                    {
                        "label": it.get("label") or it.get("text") or "",
                        "text": it.get("text") or it.get("label") or "",
                        "type": it.get("type") or "",
                        "start": it.get("start"),
                        "length": it.get("length"),
                    }
                )
            return out
        except Exception:
            # fallback: variable names
            prefix = text[: max(0, column)].split()[-1] if text else ""
            prefix = re.split(r"[^\w\.]", prefix)[-1]
            names = []
            for v in self.variables:
                n = str(v.get("name") or "")
                if n.startswith(prefix):
                    names.append({"label": n, "text": n, "type": v.get("type") or "variable"})
            return names[:40]

    def list_loaded_sources(self) -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            body = self.client.request("loadedSources", {}, timeout=5.0) or {}
        except Exception:
            return []
        out = []
        for s in body.get("sources") or []:
            path = str(s.get("path") or s.get("name") or "")
            try:
                if path and Path(path).is_absolute():
                    path = str(Path(path).resolve().relative_to(self.workspace)).replace("\\", "/")
            except Exception:
                pass
            out.append(
                {
                    "path": path,
                    "name": s.get("name") or path,
                    "origin": s.get("origin") or "",
                    "sourceReference": s.get("sourceReference") or 0,
                }
            )
        return out[:200]

    def goto_targets(self, path: str, line: int) -> list[dict[str, Any]]:
        if not self.client:
            return []
        src = {"path": str((self.workspace / path).resolve()) if path and not path.startswith("/") else path}
        try:
            body = self.client.request(
                "gotoTargets",
                {"source": src, "line": int(line)},
                timeout=5.0,
            ) or {}
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            return []
        return list(body.get("targets") or [])

    def goto(self, *, target_id: Any = None, path: str = "", line: int = 0) -> dict[str, Any]:
        if not self.client or not self.thread_id:
            raise RuntimeError("DAP not running")
        tid = target_id
        if tid is None:
            targets = self.goto_targets(path, line)
            if not targets:
                raise RuntimeError("no goto targets")
            tid = targets[0].get("id")
        self.client.request(
            "goto",
            {"threadId": self.thread_id, "targetId": tid},
            timeout=10.0,
        )
        time.sleep(0.3)
        self._refresh_if_stopped()
        return self.snapshot()

    def restart_frame(self, *, frame_id: Any = None) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("DAP not running")
        fid = frame_id if frame_id is not None else self.frame_id
        if fid is None:
            raise RuntimeError("no frame")
        self.client.request("restartFrame", {"frameId": fid}, timeout=10.0)
        time.sleep(0.3)
        self._refresh_if_stopped()
        return self.snapshot()

    def profile_start(self, kind: str = "cpu") -> dict[str, Any]:
        self._profiling = True
        if kind == "heap":
            return {"ok": False, "error": "Python heap snapshot not supported; use CPU profile", "kind": kind}
        try:
            self.evaluate(
                "(__import__('sys').modules.__setitem__('_zintriq_prof', __import__('cProfile').Profile()) "
                "or __import__('sys').modules['_zintriq_prof'].enable() or 'started')",
                context="repl",
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "kind": kind}
        return {"ok": True, "kind": kind, "sessionId": self.id}

    def profile_stop(self, kind: str = "cpu") -> dict[str, Any]:
        from editor import debug_extras

        self._profiling = False
        expr = (
            "(lambda p, b: (p.disable(), __import__('pstats').Stats(p, stream=b).sort_stats('cumulative')"
            ".print_stats(40), b.getvalue())[-1])("
            "__import__('sys').modules.get('_zintriq_prof'), __import__('io').StringIO())"
        )
        try:
            res = self.evaluate(expr, context="repl")
            text = str(res.get("value") or "")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "kind": kind}
        return debug_extras.store_profile(self.id, kind, {"text": text[:20000]})

    def _run_cmd(self, command: str) -> dict[str, Any]:
        if not self.client or not self.thread_id:
            raise RuntimeError("not stopped")
        if self.timeline_viewing:
            self.timeline_live()
        self.stopped = False
        self.client.request(command, {"threadId": self.thread_id}, timeout=8.0)
        deadline = time.time() + 5.0
        while time.time() < deadline and self.alive and not self.stopped:
            time.sleep(0.05)
        if self.stopped:
            self._refresh_if_stopped()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "id": self.id,
            "sessionId": self.id,
            "running": self.alive,
            "stopped": self.stopped,
            "engine": "dap-debugpy",
            "path": self.rel,
            "configName": self.config_name,
            "reason": self.reason,
            "error": self.error,
            "stack": list(self.stack),
            "selectedFrameId": self.frame_id,
            "threadId": self.thread_id,
            "threads": list(self.threads),
            "parentSessionId": self.parent_id,
            "childSessionIds": list(self.child_ids),
            "variables": list(self.variables)[:80],
            "watches": list(self.watches),
            "inlineValues": list(self.inline_values),
            "timeline": self._timeline_meta(),
            "readonly": bool(self.readonly),
            "modules": list(self.modules)[:40],
            "dataBreakpoints": list_data_breakpoints(),
            "exceptionBreakpoints": list_exception_breakpoints(),
            "pathMappings": list_path_mappings(),
            "breakpointGroups": list_breakpoint_groups(),
            "console": list(self.console)[-40:],
            "breakpoints": list_breakpoints(),
            "breakpointLines": list_breakpoint_lines(),
            "attached": not self.owns_process,
            "supportsStepBack": bool(self.capabilities.get("supportsStepBackRequest")),
        }


class NodeCdpSession(_TimelineMixin, DebugSession):
    def __init__(
        self,
        sid: str,
        workspace: Path,
        rel: str,
        target: Path,
        *,
        attach_host: str | None = None,
        attach_port: int | None = None,
        path_mappings: list[dict[str, str]] | None = None,
        program_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        stop_on_entry: bool = True,
        just_my_code: bool = True,
        config_name: str = "",
        module: str = "",
        sub_process: bool = True,
    ) -> None:
        self.id = sid
        self.workspace = workspace.resolve()
        self.rel = rel
        self.target = target
        self.attach_host = attach_host
        self.attach_port = attach_port
        self.path_mappings = [dict(x) for x in (path_mappings or [])]
        self.program_args = list(program_args or [])
        self.env_extra = dict(env or {})
        self.cwd = Path(cwd).resolve() if cwd else self.workspace
        self.stop_on_entry = bool(stop_on_entry)
        self.config_name = config_name or ""
        self.module = module or ""
        self.sub_process = bool(sub_process)
        self.owns_process = attach_host is None
        self.proc: subprocess.Popen[str] | None = None
        self.ws: Any = None
        self.alive = False
        self.stopped = False
        self.thread_id: Any = "main"
        self.threads: list[dict[str, Any]] = [{"id": "main", "name": "Main"}]
        self.stack: list[dict[str, Any]] = []
        self.variables: list[dict[str, Any]] = []
        self.watches: list[dict[str, Any]] = []
        self.inline_values: list[dict[str, Any]] = []
        self.console: list[dict[str, Any]] = []
        self.reason = ""
        self.error = ""
        self.frame_id: Any = None
        self.parent_id: str | None = None
        self.child_ids: list[str] = []
        self._call_frames: list[dict[str, Any]] = []
        self._bp_ids: dict[str, list[str]] = {}
        self._var_refs: dict[int, str] = {}
        self._var_ref_seq = 0
        self._soft_data_prev: dict[str, str] = {}
        self._script_id: str = ""
        self._profile_active = False
        self._alloc_sampling = False
        self.readonly = False
        self.modules: list[dict[str, Any]] = []
        self._id = 0
        self._lock = threading.Lock()
        self._pending: dict[int, dict[str, Any]] = {}
        self._pending_by_session: dict[str, dict[int, dict[str, Any]]] = {}
        self._cdp_children: dict[str, "NodeCdpSession"] = {}
        self._cdp_session_id: str | None = None
        self._parent_cdp: "NodeCdpSession | None" = None
        self._reader: threading.Thread | None = None
        self._pause_event = threading.Event()
        self._timeline_init()

    def _ref_for(self, object_id: str | None) -> int:
        if not object_id:
            return 0
        self._var_ref_seq += 1
        rid = self._var_ref_seq
        self._var_refs[rid] = str(object_id)
        return rid

    def _props_as_vars(self, object_id: str, *, scope: str = "") -> list[dict[str, Any]]:
        props = self._send(
            "Runtime.getProperties",
            {"objectId": object_id, "ownProperties": True, "generatePreview": True},
        )
        out: list[dict[str, Any]] = []
        for p in (props or {}).get("result") or []:
            val = p.get("value") or {}
            child_id = val.get("objectId") if val.get("type") in {"object", "function"} else None
            ref = self._ref_for(child_id)
            out.append(
                {
                    "name": p.get("name"),
                    "value": val.get("description") or val.get("value") or val.get("type"),
                    "type": val.get("type") or "",
                    "scope": scope,
                    "variablesReference": ref,
                    "namedVariables": 0,
                    "indexedVariables": 0,
                    "expandable": ref > 0,
                }
            )
        return out

    def start(self) -> None:
        from editor import cdp_ws

        if self.attach_host is not None and self.attach_port is not None:
            ws_url = self._discover_ws_url(self.attach_host, int(self.attach_port))
            self.rel = f"attach:{self.attach_host}:{self.attach_port}"
        else:
            node = _which("node")
            if not node:
                raise RuntimeError("node not found on PATH")
            cmd = [node]
            if self.stop_on_entry:
                cmd.append("--inspect-brk=127.0.0.1:0")
            else:
                cmd.append("--inspect=127.0.0.1:0")
            cmd.append(str(self.target))
            cmd.extend(self.program_args)
            env = {**os.environ, **self.env_extra}
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(self.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            ws_url = self._wait_ws_url()
        self.ws = cdp_ws.connect(ws_url)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._send("Runtime.enable")
        self._send("Debugger.enable")
        try:
            self._send("Target.setAutoAttach", {
                "autoAttach": True,
                "waitForDebuggerOnStart": True,
                "flatten": True,
            })
        except Exception:
            pass
        self.apply_skip_files()
        self.apply_exception_breakpoints()
        for p in _all_bp_paths():
            self.apply_breakpoints(p)
        self.alive = True
        self._event_push("launch", path=self.rel)
        try:
            self._send("Runtime.runIfWaitingForDebugger", timeout=2.0)
        except Exception:
            pass
        self._pause_event.wait(3.0)
        if self.stopped:
            self._refresh()

    def apply_skip_files(self) -> None:
        """Map skipFiles globs → CDP Debugger.setBlackboxPatterns."""
        if not self.ws and not self._parent_cdp:
            return
        patterns = list_skip_files()
        regexes = []
        for pat in patterns:
            r = (
                pat.replace(".", r"\.")
                .replace("**/", "(.*/)?")
                .replace("**", ".*")
                .replace("*", "[^/]*")
            )
            regexes.append(r)
        try:
            self._send("Debugger.setBlackboxPatterns", {"patterns": regexes}, timeout=3.0)
        except Exception as exc:  # noqa: BLE001
            self.error = f"blackbox: {exc}"

    def start_as_cdp_child(self, parent: "NodeCdpSession", cdp_session_id: str, label: str) -> None:
        """Attach as a flattened CDP child session (worker / nested target)."""
        self._parent_cdp = parent
        self._cdp_session_id = cdp_session_id
        self.ws = parent.ws
        self.owns_process = False
        self.rel = label
        self.config_name = "worker"
        self.alive = True
        try:
            self._send("Runtime.enable")
            self._send("Debugger.enable")
            self.apply_skip_files()
            self.apply_exception_breakpoints()
            for p in _all_bp_paths():
                self.apply_breakpoints(p)
            self._send("Runtime.runIfWaitingForDebugger", timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        self._pause_event.wait(1.5)
        if self.stopped:
            self._refresh()

    def _discover_ws_url(self, host: str, port: int) -> str:
        import urllib.error
        import urllib.request

        url = f"http://{host}:{port}/json"
        try:
            with urllib.request.urlopen(url, timeout=5.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Node inspector discovery failed at {url}: {exc}") from exc
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list) or not payload:
            raise RuntimeError(f"no inspector targets at {url}")
        for target in payload:
            if not isinstance(target, dict):
                continue
            ws = target.get("webSocketDebuggerUrl")
            if ws:
                return str(ws)
        raise RuntimeError(f"no webSocketDebuggerUrl at {url}")

    def _wait_ws_url(self) -> str:
        assert self.proc and self.proc.stderr
        deadline = time.time() + 5.0
        buf = ""
        while time.time() < deadline:
            line = self.proc.stderr.readline()
            if not line:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.02)
                continue
            buf += line
            m = re.search(r"(ws://127\.0\.0\.1:\d+/[^\s]+)", line)
            if m:
                return m.group(1)
        raise RuntimeError(f"could not find inspector websocket\n{buf}")

    def _read_loop(self) -> None:
        assert self.ws
        while self.alive or self._cdp_children:
            try:
                raw = self.ws.recv()
            except Exception:
                break
            if not raw:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            sess_id = msg.get("sessionId")
            if "id" in msg:
                mid = int(msg["id"])
                with self._lock:
                    if sess_id and sess_id in self._pending_by_session:
                        self._pending_by_session[sess_id][mid] = msg
                    elif sess_id and sess_id in self._cdp_children:
                        child = self._cdp_children[sess_id]
                        with child._lock:
                            child._pending[mid] = msg
                    else:
                        self._pending[mid] = msg
            method = msg.get("method")
            target = self
            if sess_id and sess_id in self._cdp_children:
                target = self._cdp_children[sess_id]
            if method == "Target.attachedToTarget" and not sess_id:
                self._on_attached_to_target(msg.get("params") or {})
            elif method == "Target.detachedFromTarget" and not sess_id:
                det = (msg.get("params") or {}).get("sessionId")
                if det and det in self._cdp_children:
                    child = self._cdp_children.pop(det)
                    child.alive = False
            elif method == "Debugger.paused":
                params = msg.get("params") or {}
                target.stopped = True
                target.reason = str(params.get("reason") or "paused")
                target._last_pause = params
                target._pause_event.set()
                if hasattr(target, "_event_push"):
                    try:
                        target._event_push("stopped", reason=target.reason)
                    except Exception:
                        pass
                if target is not self:
                    threading.Thread(
                        target=target._refresh, name=f"cdp-child-refresh-{target.id}", daemon=True
                    ).start()
            elif method == "Debugger.resumed":
                target.stopped = False
                target._pause_event.clear()
                if hasattr(target, "_event_push"):
                    try:
                        target._event_push("continued")
                    except Exception:
                        pass
            elif method == "Runtime.consoleAPICalled":
                args = (msg.get("params") or {}).get("args") or []
                text = " ".join(str((a or {}).get("value") or (a or {}).get("description") or "") for a in args)
                if text:
                    target.console.append({"type": "output", "text": text})
                    target.console = target.console[-100:]
            elif method in {"Runtime.executionContextDestroyed", "Inspector.detached"}:
                if target is self and not self._cdp_children:
                    self.alive = False

    def _on_attached_to_target(self, params: dict[str, Any]) -> None:
        info = params.get("targetInfo") or {}
        cdp_sid = str(params.get("sessionId") or "")
        if not cdp_sid or cdp_sid in self._cdp_children:
            return
        ttype = str(info.get("type") or "").lower()
        url = str(info.get("url") or "")
        title = str(info.get("title") or url or ttype or "worker")
        # Filter nested targets: skip browser pages / iframes / unknown noise
        skip_types = {"page", "iframe", "other", "webview", "browser"}
        allow_types = {
            "worker",
            "service_worker",
            "shared_worker",
            "node",
            "node_worker",
            "worker_thread",
        }
        if ttype in skip_types:
            self.console.append({"type": "output", "text": f"Skipped nested target ({ttype}): {title[:60]}"})
            try:
                self._send("Runtime.runIfWaitingForDebugger", timeout=1.0)
            except Exception:
                pass
            return
        if ttype and ttype not in allow_types and not params.get("waitingForDebugger"):
            return
        # Friendly rename
        if ttype == "service_worker":
            label = f"sw:{title[:60]}"
        elif ttype == "shared_worker":
            label = f"shared:{title[:60]}"
        elif "worker" in ttype or ttype in {"node", "node_worker"}:
            label = f"worker:{title[:60]}"
        else:
            label = f"nested:{title[:60]}"
        child_id = uuid.uuid4().hex[:10]
        child = NodeCdpSession(
            child_id,
            self.workspace,
            label,
            self.target,
            cwd=self.cwd,
            stop_on_entry=True,
            sub_process=False,
        )
        child.config_name = label
        self._cdp_children[cdp_sid] = child
        self._pending_by_session.setdefault(cdp_sid, {})
        try:
            child.start_as_cdp_child(self, cdp_sid, label)
            register_child_session(self.id, child)
            self.console.append({"type": "output", "text": f"Attached {ttype or 'target'}: {label}"})
        except Exception as exc:  # noqa: BLE001
            self.console.append({"type": "output", "text": f"Worker attach failed: {exc}"})
            self._cdp_children.pop(cdp_sid, None)

    def _send(self, method: str, params: dict[str, Any] | None = None, timeout: float = 5.0) -> Any:
        root = self._parent_cdp or self
        assert root.ws
        with root._lock:
            root._id += 1
            mid = root._id
        payload: dict[str, Any] = {"id": mid, "method": method}
        if params is not None:
            payload["params"] = params
        if self._cdp_session_id:
            payload["sessionId"] = self._cdp_session_id
        root.ws.send(json.dumps(payload))
        deadline = time.time() + timeout
        pending = self._pending
        while time.time() < deadline:
            with self._lock:
                if mid in pending:
                    msg = pending.pop(mid)
                    if "error" in msg:
                        raise RuntimeError(str(msg["error"]))
                    return msg.get("result")
            # Also check parent session bucket
            if self._cdp_session_id and self._parent_cdp:
                with self._parent_cdp._lock:
                    bucket = self._parent_cdp._pending_by_session.get(self._cdp_session_id) or {}
                    if mid in bucket:
                        msg = bucket.pop(mid)
                        if "error" in msg:
                            raise RuntimeError(str(msg["error"]))
                        return msg.get("result")
            time.sleep(0.01)
        raise TimeoutError(method)

    def apply_breakpoints(self, rel: str) -> None:
        if not self.ws:
            return
        # remove previous for this file
        for bid in self._bp_ids.get(rel) or []:
            try:
                self._send("Debugger.removeBreakpoint", {"breakpointId": bid}, timeout=2.0)
            except Exception:
                pass
        self._bp_ids[rel] = []
        bps = _bps_for(rel)
        url = (self.workspace / rel).resolve().as_uri()
        path = str((self.workspace / rel).resolve())
        for bp in bps:
            line = int(bp["line"])
            merged = _merge_cdp_condition(
                str(bp.get("condition") or ""),
                str(bp.get("hitCondition") or ""),
                f"{rel}:{line}",
                log_message=str(bp.get("logMessage") or ""),
            )
            col = int(bp.get("column") or 1)
            params: dict[str, Any] = {
                "url": url,
                "lineNumber": line - 1,
                "columnNumber": max(0, col - 1),
            }
            if merged:
                params["condition"] = merged
            if bp.get("logMessage"):
                try:
                    from editor import debug_features

                    debug_features.record_tracepoint(str(bp["logMessage"]), path=rel, line=line)
                except Exception:
                    pass
            try:
                res = self._send("Debugger.setBreakpointByUrl", params, timeout=3.0)
            except Exception:
                try:
                    params = {
                        "urlRegex": re.escape(path) + "$",
                        "lineNumber": line - 1,
                    }
                    if merged:
                        params["condition"] = merged
                    res = self._send("Debugger.setBreakpointByUrl", params, timeout=3.0)
                except Exception as exc:  # noqa: BLE001
                    self.error = str(exc)
                    continue
            bid = (res or {}).get("breakpointId")
            if bid:
                self._bp_ids.setdefault(rel, []).append(str(bid))

    def apply_exception_breakpoints(self) -> None:
        if not self.ws:
            return
        filters = list_exception_breakpoints()
        if filters.get("raised") or filters.get("all"):
            state = "all"
        elif filters.get("uncaught"):
            state = "uncaught"
        else:
            state = "none"
        try:
            self._send("Debugger.setPauseOnExceptions", {"state": state}, timeout=3.0)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)

    def set_variable(self, *, variables_reference: int, name: str, value: str) -> dict[str, Any]:
        if not self.stopped:
            raise RuntimeError("setVariable requires paused session")
        # CDP: assign via evaluate on call frame
        assign = f"({name}) = ({value})"
        res = self.evaluate(assign, frame_id=self.frame_id, context="repl")
        self._load_vars_for_frame(self.frame_id)
        return {"ok": True, "name": name, "value": res.get("value"), "type": res.get("type") or "", "mode": "evaluate"}

    def set_expression(self, *, expression: str, value: str, frame_id: Any = None) -> dict[str, Any]:
        if not self.stopped:
            raise RuntimeError("setExpression requires paused session")
        assign = f"({expression}) = ({value})"
        res = self.evaluate(assign, frame_id=frame_id or self.frame_id, context="repl")
        self._load_vars_for_frame(self.frame_id)
        return {"ok": True, "value": res.get("value"), "type": res.get("type") or "", "mode": "evaluate"}

    def list_modules(self) -> list[dict[str, Any]]:
        if not self.stopped:
            return []
        try:
            res = self.evaluate(
                "Object.keys(require.cache||{}).slice(0,80).map(k=>({name:k,path:k}))",
                context="watch",
            )
            # Also include scripts from stack
            mods = []
            seen = set()
            for fr in self.stack or []:
                p = str(fr.get("path") or "")
                if p and p not in seen:
                    seen.add(p)
                    mods.append({"id": len(mods), "name": Path(p).name, "path": p})
            text = str(res.get("value") or "")
            if text and text not in {"undefined", ""}:
                mods.append({"id": "require.cache", "name": "require.cache", "path": text[:800]})
            return mods
        except Exception:
            return [
                {"id": i, "name": Path(str(fr.get("path") or "")).name, "path": fr.get("path")}
                for i, fr in enumerate(self.stack or [])
            ]

    def apply_instruction_breakpoints(self) -> None:
        # CDP has no setInstructionBreakpoints; store as soft markers only
        pass

    def hot_reload(self, *, module: str = "") -> dict[str, Any]:
        if not self.stopped:
            raise RuntimeError("hotReload requires paused session")
        mod = (module or "").strip()
        if mod:
            expr = (
                f"(function(m){{ try {{ delete require.cache[require.resolve(m)]; "
                f"return 'reloaded '+require.resolve(m); }} catch(e) {{ return String(e); }} }})({mod!r})"
            )
        else:
            top = str(((self.stack or [{}])[0]).get("path") or self.rel or "")
            expr = (
                f"(function(p){{ try {{ const k=Object.keys(require.cache||{{}}).find(x=>x.includes(p)||x.endsWith(p)); "
                f"if(!k) return 'not in cache'; delete require.cache[k]; require(k); return 'reloaded '+k; "
                f"}} catch(e) {{ return String(e); }} }})({top!r})"
            )
        res = self.evaluate(expr, context="repl")
        return {"ok": True, "engine": "node", "result": res.get("value"), "module": mod or "(current)"}

    def breakpoint_locations(
        self, *, path: str, line: int, end_line: int | None = None
    ) -> list[dict[str, Any]]:
        if not self.ws or not self._script_id:
            return [{"line": int(line), "column": 1}]
        try:
            body = self._send(
                "Debugger.getPossibleBreakpoints",
                {
                    "start": {"scriptId": self._script_id, "lineNumber": max(0, int(line) - 1), "columnNumber": 0},
                    "end": {
                        "scriptId": self._script_id,
                        "lineNumber": max(0, int(end_line or line) - 1),
                        "columnNumber": 0,
                    },
                },
                timeout=3.0,
            ) or {}
            locs = []
            for loc in body.get("locations") or []:
                locs.append(
                    {
                        "line": int(loc.get("lineNumber") or 0) + 1,
                        "column": int(loc.get("columnNumber") or 0) + 1,
                    }
                )
            return locs or [{"line": int(line), "column": 1}]
        except Exception:
            return [{"line": int(line), "column": 1}]

    def _refresh(self) -> None:
        params = getattr(self, "_last_pause", {}) or {}
        call_frames = params.get("callFrames") or []
        self._call_frames = call_frames
        self._var_refs.clear()
        frames = []
        self._script_id = ""
        for fr in call_frames[:20]:
            loc = fr.get("location") or {}
            line = int(loc.get("lineNumber") or 0) + 1
            url = fr.get("url") or ""
            rel = url
            if url.startswith("file://"):
                try:
                    p = Path(urlparse(url).path)
                    mapped = _map_remote_to_local(str(p))
                    try:
                        rel = str(Path(mapped).resolve().relative_to(self.workspace)).replace("\\", "/")
                    except Exception:
                        rel = str(p.resolve().relative_to(self.workspace)).replace("\\", "/")
                except Exception:
                    rel = _map_remote_to_local(url)
            else:
                rel = _map_remote_to_local(url)
            if not self._script_id and loc.get("scriptId"):
                self._script_id = str(loc.get("scriptId"))
            frames.append(
                {
                    "id": fr.get("callFrameId"),
                    "name": fr.get("functionName") or "(anonymous)",
                    "path": rel,
                    "line": line,
                    "column": int(loc.get("columnNumber") or 0) + 1,
                }
            )
        self.stack = frames
        keep = self.frame_id
        if keep is not None and any(f["id"] == keep for f in frames):
            self.frame_id = keep
        else:
            self.frame_id = frames[0]["id"] if frames else None
        self.threads = [{"id": "main", "name": "Main"}]
        self.thread_id = "main"
        self._load_vars_for_frame(self.frame_id)
        self.apply_data_breakpoints()
        self.refresh_watches()
        self.inline_values = _compute_inline_values(
            self.workspace, self.stack, self.frame_id, self.variables
        )
        self._timeline_push()

    def select_thread(self, thread_id: Any) -> None:
        # Node inspector is single-threaded for the main target.
        self.thread_id = thread_id or "main"
        if not self.threads:
            self.threads = [{"id": "main", "name": "Main"}]

    def step_back(self) -> dict[str, Any]:
        if self.timeline and (self.timeline_viewing and self.timeline_index > 0 or not self.timeline_viewing):
            idx = (self.timeline_index if self.timeline_viewing else len(self.timeline) - 1) - 1
            if idx >= 0:
                self.timeline_seek(idx)
                return self.snapshot()
        raise RuntimeError("Node CDP has no native stepBack — timeline empty")

    def reverse_continue(self) -> dict[str, Any]:
        if self.timeline:
            self.timeline_seek(0)
            return self.snapshot()
        raise RuntimeError("timeline empty")

    def completions(self, text: str, column: int, *, frame_id: Any = None) -> list[dict[str, Any]]:
        prefix = text[: max(0, column)]
        token = re.split(r"[^\w\.\$]", prefix)[-1] if prefix else ""
        out = []
        for v in self.variables:
            n = str(v.get("name") or "")
            if n.startswith(token):
                out.append({"label": n, "text": n, "type": v.get("type") or "variable"})
        return out[:40]

    def list_loaded_sources(self) -> list[dict[str, Any]]:
        if not self.ws:
            return []
        try:
            # Prefer Debugger.getScriptSource inventory via possibleCollected / scripts
            # CDP doesn't have loadedSources; use Runtime / tracked scripts from pauses.
            out = []
            seen = set()
            for fr in self.stack or []:
                p = str(fr.get("path") or "")
                if p and p not in seen:
                    seen.add(p)
                    out.append({"path": p, "name": Path(p).name, "origin": "stack"})
            # Also ask for possible script list via HeapProfiler / Profiler not available —
            # use Page.getResourceTree when present (noop for node)
            return out[:200]
        except Exception:
            return []

    def profile_start(self, kind: str = "cpu") -> dict[str, Any]:
        if not self.ws:
            raise RuntimeError("CDP not connected")
        if kind in {"heap", "alloc", "allocation"}:
            self._send("HeapProfiler.enable")
            try:
                self._send("HeapProfiler.startSampling", {"samplingInterval": 32768})
                self._profile_active = True
                self._alloc_sampling = True
                return {"ok": True, "kind": "allocation"}
            except Exception:
                self._alloc_sampling = False
                self._profile_active = True
                return {"ok": True, "kind": "heap"}
        self._send("Profiler.enable")
        self._send("Profiler.setSamplingInterval", {"interval": 100})
        self._send("Profiler.start")
        self._profile_active = True
        self._alloc_sampling = False
        return {"ok": True, "kind": "cpu", "sessionId": self.id}

    def profile_stop(self, kind: str = "cpu") -> dict[str, Any]:
        from editor import debug_extras

        if kind in {"heap", "alloc", "allocation"} or getattr(self, "_alloc_sampling", False):
            try:
                if getattr(self, "_alloc_sampling", False):
                    body = self._send("HeapProfiler.stopSampling", timeout=30.0) or {}
                    self._profile_active = False
                    self._alloc_sampling = False
                    profile = body.get("profile") or body
                    # Convert allocation sample profile into flame-ish tree
                    flame = {"name": "root", "value": 0, "self": 0, "children": []}
                    samples = profile.get("samples") or []
                    sizes = {}
                    for s in samples:
                        nid = int(s.get("nodeId") or s.get("ordinal") or 0)
                        sizes[nid] = sizes.get(nid, 0) + int(s.get("size") or 1)
                    nodes = {int(n["id"]): n for n in (profile.get("head") and [profile["head"]] or profile.get("nodes") or []) if isinstance(n, dict) and "id" in n}

                    def walk(n: dict[str, Any]) -> dict[str, Any]:
                        nid = int(n.get("id") or 0)
                        kids = [walk(c) for c in (n.get("children") or []) if isinstance(c, dict)]
                        self_sz = sizes.get(nid, 0)
                        val = self_sz + sum(int(k.get("value") or 0) for k in kids)
                        call = n.get("callFrame") or {}
                        name = call.get("functionName") or call.get("url") or f"node-{nid}"
                        return {"name": str(name), "value": val, "self": self_sz, "children": kids}

                    if profile.get("head"):
                        flame = walk(profile["head"])
                        flame = {"name": "root", "value": flame.get("value") or 0, "self": 0, "children": [flame]}
                    elif nodes:
                        # flat
                        kids = [
                            {
                                "name": str((n.get("callFrame") or {}).get("functionName") or nid),
                                "value": sizes.get(nid, 1),
                                "self": sizes.get(nid, 1),
                                "children": [],
                            }
                            for nid, n in list(nodes.items())[:80]
                        ]
                        flame = {
                            "name": "root",
                            "value": sum(k["value"] for k in kids),
                            "self": 0,
                            "children": kids,
                        }
                    return debug_extras.store_profile(
                        self.id,
                        "allocation",
                        {"profile": profile, "flame": flame, "timeline": True},
                    )
            except Exception:
                pass
            body = self._send("HeapProfiler.takeHeapSnapshot", timeout=30.0) or {}
            self._profile_active = False
            return debug_extras.store_profile(self.id, "heap", {"result": body})
        body = self._send("Profiler.stop", timeout=30.0) or {}
        self._profile_active = False
        profile = body.get("profile") or body
        nodes = (profile.get("nodes") or [])[:200]
        summary = [
            {
                "id": n.get("id"),
                "function": ((n.get("callFrame") or {}).get("functionName") or "(anonymous)"),
                "url": ((n.get("callFrame") or {}).get("url") or ""),
                "line": ((n.get("callFrame") or {}).get("lineNumber") or 0),
                "hitCount": n.get("hitCount"),
            }
            for n in nodes
        ]
        return debug_extras.store_profile(
            self.id,
            "cpu",
            {"nodes": summary, "profile": profile, "rawKeys": list(profile.keys())},
        )

    def _frame_index(self, frame_id: Any) -> int:
        for i, fr in enumerate(self.stack):
            if fr.get("id") == frame_id or str(fr.get("id")) == str(frame_id):
                return i
        return 0

    def _load_vars_for_frame(self, frame_id: Any) -> None:
        self.variables = []
        idx = self._frame_index(frame_id)
        if idx >= len(self._call_frames):
            return
        call_frame = self._call_frames[idx]
        for scope in (call_frame.get("scopeChain") or [])[:3]:
            obj = scope.get("object") or {}
            oid = obj.get("objectId")
            if not oid:
                continue
            try:
                self.variables.extend(self._props_as_vars(str(oid), scope=str(scope.get("type") or "")))
            except Exception:
                pass
            if len(self.variables) > 80:
                break

    def select_frame(self, frame_id: Any) -> None:
        if self.timeline_viewing:
            raise RuntimeError("leave timeline view first")
        if not self.stopped:
            raise RuntimeError("select frame requires paused session")
        idx = self._frame_index(frame_id)
        if not self.stack:
            raise ValueError("unknown frame")
        self.frame_id = self.stack[idx]["id"]
        self._load_vars_for_frame(self.frame_id)
        self.refresh_watches()
        self.inline_values = _compute_inline_values(
            self.workspace, self.stack, self.frame_id, self.variables
        )

    def apply_data_breakpoints(self) -> None:
        """Soft data breakpoints for Node: flag when watched expressions change across pauses."""
        wanted = list_data_breakpoints()
        if not wanted or not self.stopped:
            return
        changed: list[str] = []
        for item in wanted:
            name = item["name"]
            try:
                res = self.evaluate(name, frame_id=self.frame_id, context="watch")
                cur = str(res.get("value") or "")
            except Exception:
                cur = "<err>"
            prev = self._soft_data_prev.get(name)
            self._soft_data_prev[name] = cur
            if prev is not None and prev != cur:
                changed.append(f"{name}: {prev} → {cur}")
        if changed and self.reason not in {"data breakpoint", "breakpoint", "step"}:
            self.reason = "data breakpoint"
        elif changed:
            self.reason = f"{self.reason}; data: {', '.join(changed[:3])}"

    def expand_variables(self, variables_reference: int) -> list[dict[str, Any]]:
        if not self.stopped:
            raise RuntimeError("expand requires paused session")
        oid = self._var_refs.get(int(variables_reference))
        if not oid:
            raise ValueError("unknown variablesReference")
        return self._props_as_vars(oid)

    def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict[str, Any]:
        if not self.stopped:
            raise RuntimeError("disassemble requires paused session")
        n = max(1, min(int(count or 64), 200))
        script_id = (memory_reference or self._script_id or "").strip()
        if script_id:
            try:
                body = self._send("Debugger.getScriptSource", {"scriptId": script_id}, timeout=5.0) or {}
                src = str(body.get("scriptSource") or "")
                frame = next((f for f in self.stack if f.get("id") == self.frame_id), None)
                line = int((frame or {}).get("line") or 1)
                lines = src.splitlines()
                start = max(0, line - 8 + int(offset or 0))
                end = min(len(lines), start + n)
                chunk = []
                for i in range(start, end):
                    mark = ">>" if i + 1 == line else "  "
                    chunk.append(f"{mark}{i+1:5d}  {lines[i]}")
                return {
                    "ok": True,
                    "engine": "cdp-node",
                    "mode": "source",
                    "text": "\n".join(chunk) or "(empty script)",
                    "scriptId": script_id,
                }
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc), "text": ""}
        return {"ok": False, "error": "no scriptId", "text": ""}

    def read_memory(
        self,
        *,
        memory_reference: str = "",
        expression: str = "",
        offset: int = 0,
        count: int = 64,
    ) -> dict[str, Any]:
        if not self.stopped:
            raise RuntimeError("readMemory requires paused session")
        n = max(1, min(int(count or 64), 512))
        expr = (expression or memory_reference or "").strip()
        if not expr:
            raise ValueError("expression required")
        dump = (
            f"(function(o){{const off={int(offset or 0)};const n={n};"
            f"if(o instanceof ArrayBuffer)o=new Uint8Array(o);"
            f"if(ArrayBuffer.isView(o)){{const u=new Uint8Array(o.buffer,o.byteOffset+off,Math.min(n,o.byteLength-off));"
            f"return Array.from(u);}}"
            f"if(typeof o==='string'){{const u=[];for(let i=off;i<Math.min(o.length,off+n);i++)u.push(o.charCodeAt(i)&255);return u;}}"
            f"return null;}})({expr})"
        )
        fid = self.frame_id
        if fid:
            body = self._send(
                "Debugger.evaluateOnCallFrame",
                {"callFrameId": fid, "expression": dump, "returnByValue": True},
                timeout=5.0,
            )
        else:
            body = self._send("Runtime.evaluate", {"expression": dump, "returnByValue": True}, timeout=5.0)
        if (body or {}).get("exceptionDetails"):
            detail = (body or {}).get("exceptionDetails") or {}
            raise RuntimeError(detail.get("text") or "evaluation error")
        val = ((body or {}).get("result") or {}).get("value")
        if isinstance(val, list):
            data = bytes(int(x) & 255 for x in val[:n])
            return {
                "ok": True,
                "engine": "cdp-node",
                "mode": "evaluate",
                "text": _format_hex_dump(data, base=int(offset or 0)),
                "bytesRead": len(data),
            }
        return {"ok": True, "engine": "cdp-node", "mode": "repr", "text": str(val), "bytesRead": 0}

    def refresh_watches(self) -> None:
        out: list[dict[str, Any]] = []
        for expr in list_watches():
            try:
                res = self.evaluate(expr, frame_id=self.frame_id, context="watch")
                out.append(
                    {
                        "expression": expr,
                        "value": res.get("value"),
                        "type": res.get("type") or "",
                        "error": "",
                        "variablesReference": int(res.get("variablesReference") or 0),
                        "expandable": int(res.get("variablesReference") or 0) > 0,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                out.append(
                    {
                        "expression": expr,
                        "value": "",
                        "type": "",
                        "error": str(exc),
                        "variablesReference": 0,
                        "expandable": False,
                    }
                )
        self.watches = out

    def evaluate(self, expression: str, *, frame_id: Any = None, context: str = "repl") -> dict[str, Any]:
        if not self.stopped:
            raise RuntimeError("evaluate requires paused session")
        fid = frame_id if frame_id is not None else self.frame_id
        if fid:
            body = self._send(
                "Debugger.evaluateOnCallFrame",
                {
                    "callFrameId": fid,
                    "expression": expression,
                    "returnByValue": False,
                    "generatePreview": True,
                },
            )
        else:
            body = self._send(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": False, "generatePreview": True},
            )
        if (body or {}).get("exceptionDetails"):
            detail = (body or {}).get("exceptionDetails") or {}
            raise RuntimeError(detail.get("text") or "evaluation error")
        val = (body or {}).get("result") or {}
        ref = self._ref_for(val.get("objectId") if val.get("type") in {"object", "function"} else None)
        result = {
            "value": val.get("value") if "value" in val else val.get("description") or val.get("type") or "",
            "type": val.get("type") or "",
            "variablesReference": ref,
        }
        if context == "repl":
            self.console.append({"type": "in", "text": expression})
            self.console.append({"type": "out", "text": str(result["value"]), "valueType": result["type"]})
            self.console = self.console[-100:]
        return result

    def cont(self) -> dict[str, Any]:
        return self._step("Debugger.resume")

    def step_over(self) -> dict[str, Any]:
        return self._step("Debugger.stepOver")

    def step_in(self) -> dict[str, Any]:
        return self._step("Debugger.stepInto")

    def step_out(self) -> dict[str, Any]:
        return self._step("Debugger.stepOut")

    def _step(self, method: str) -> dict[str, Any]:
        if self.timeline_viewing:
            self.timeline_live()
        self._pause_event.clear()
        self.stopped = False
        self._send(method)
        self._pause_event.wait(5.0)
        if self.stopped:
            self._refresh()
        elif self.proc and self.proc.poll() is not None:
            self.alive = False
        return self.snapshot()

    def stop(self) -> None:
        self.alive = False
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self.ws = None
        if self.owns_process and self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "id": self.id,
            "sessionId": self.id,
            "running": self.alive,
            "stopped": self.stopped,
            "engine": "cdp-node",
            "path": self.rel,
            "configName": self.config_name,
            "reason": self.reason,
            "error": self.error,
            "stack": list(self.stack),
            "selectedFrameId": self.frame_id,
            "threadId": self.thread_id,
            "threads": list(self.threads),
            "parentSessionId": self.parent_id,
            "childSessionIds": list(self.child_ids),
            "variables": list(self.variables)[:80],
            "watches": list(self.watches),
            "inlineValues": list(self.inline_values),
            "timeline": self._timeline_meta(),
            "readonly": bool(self.readonly),
            "modules": list(self.modules)[:40],
            "dataBreakpoints": list_data_breakpoints(),
            "exceptionBreakpoints": list_exception_breakpoints(),
            "pathMappings": list_path_mappings(),
            "breakpointGroups": list_breakpoint_groups(),
            "console": list(self.console)[-40:],
            "breakpoints": list_breakpoints(),
            "breakpointLines": list_breakpoint_lines(),
            "attached": not self.owns_process,
            "supportsStepBack": False,
        }


def shutdown() -> None:
    stop()
