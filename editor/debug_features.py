"""Batch features: modules, replay, OTLP, compounds graph, notebook, AI cond hints, DWARF inject."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

# path -> line -> hit count
_BP_HITS: dict[str, dict[int, int]] = {}
# sessionId -> [{ts, vars: {name: value}}]
_VAR_HISTORY: dict[str, list[dict[str, Any]]] = {}
_VAR_HISTORY_MAX = 64
# instruction breakpoints: [{id, instructionReference, offset, condition}]
_INSTRUCTION_BPS: list[dict[str, Any]] = []
# recent failure snippets for condition suggestions
_RECENT_FAILURES: list[dict[str, Any]] = []
_RECENT_FAILURES_MAX = 40


def record_bp_hit(path: str, line: int) -> None:
    p = (path or "").replace("\\", "/")
    if not p or int(line) < 1:
        return
    bucket = _BP_HITS.setdefault(p, {})
    ln = int(line)
    bucket[ln] = int(bucket.get(ln) or 0) + 1


def bp_hit_stats() -> dict[str, Any]:
    return {
        "ok": True,
        "hits": {p: dict(v) for p, v in _BP_HITS.items()},
        "heat": _heat_levels(_BP_HITS),
    }


def _heat_levels(hits: dict[str, dict[int, int]]) -> dict[str, dict[str, int]]:
    """Normalize hit counts to 0–4 heat levels per file."""
    out: dict[str, dict[str, int]] = {}
    for p, lines in hits.items():
        if not lines:
            continue
        mx = max(lines.values()) or 1
        out[p] = {str(ln): min(4, int(round(4 * c / mx))) for ln, c in lines.items()}
    return out


def clear_bp_hits() -> dict[str, Any]:
    _BP_HITS.clear()
    return {"ok": True, "hits": {}}


def push_var_history(session_id: str, variables: list[dict[str, Any]]) -> None:
    sid = session_id or "_"
    snap = {
        "ts": time.time(),
        "vars": {
            str(v.get("name") or ""): str(v.get("value") or "")
            for v in (variables or [])[:60]
            if v.get("name")
        },
    }
    hist = _VAR_HISTORY.setdefault(sid, [])
    hist.append(snap)
    if len(hist) > _VAR_HISTORY_MAX:
        del hist[: len(hist) - _VAR_HISTORY_MAX]


def var_history(session_id: str | None = None, *, limit: int = 40) -> dict[str, Any]:
    if session_id:
        items = list(_VAR_HISTORY.get(session_id) or [])
    else:
        items = []
        for sid, hist in _VAR_HISTORY.items():
            for h in hist:
                items.append({**h, "sessionId": sid})
        items.sort(key=lambda x: float(x.get("ts") or 0))
    items = items[-max(1, min(int(limit), 100)) :]
    diffs = []
    for i in range(1, len(items)):
        prev = items[i - 1].get("vars") or {}
        cur = items[i].get("vars") or {}
        changed = []
        for k in sorted(set(prev) | set(cur)):
            if prev.get(k) != cur.get(k):
                changed.append({"name": k, "from": prev.get(k, ""), "to": cur.get(k, "")})
        diffs.append(
            {
                "i": i,
                "ts": items[i].get("ts"),
                "changed": changed[:40],
                "sessionId": items[i].get("sessionId"),
            }
        )
    return {"ok": True, "history": items, "diffs": diffs}


def list_instruction_breakpoints() -> list[dict[str, Any]]:
    return [dict(x) for x in _INSTRUCTION_BPS]


def set_instruction_breakpoints(items: list[Any]) -> dict[str, Any]:
    clean = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        ref = str(raw.get("instructionReference") or raw.get("address") or "").strip()
        if not ref:
            continue
        clean.append(
            {
                "id": str(raw.get("id") or uuid.uuid4().hex[:8]),
                "instructionReference": ref,
                "offset": int(raw.get("offset") or 0),
                "condition": str(raw.get("condition") or "").strip(),
            }
        )
    _INSTRUCTION_BPS[:] = clean
    return {"ok": True, "instructionBreakpoints": list_instruction_breakpoints()}


def add_instruction_breakpoint(
    instruction_reference: str,
    *,
    offset: int = 0,
    condition: str = "",
) -> dict[str, Any]:
    ref = (instruction_reference or "").strip()
    if not ref:
        raise ValueError("instructionReference required")
    item = {
        "id": uuid.uuid4().hex[:8],
        "instructionReference": ref,
        "offset": int(offset or 0),
        "condition": str(condition or "").strip(),
    }
    _INSTRUCTION_BPS.append(item)
    return {"ok": True, "instructionBreakpoint": item, "instructionBreakpoints": list_instruction_breakpoints()}


def remove_instruction_breakpoint(id_or_ref: str) -> dict[str, Any]:
    key = (id_or_ref or "").strip()
    _INSTRUCTION_BPS[:] = [
        x for x in _INSTRUCTION_BPS if x.get("id") != key and x.get("instructionReference") != key
    ]
    return {"ok": True, "instructionBreakpoints": list_instruction_breakpoints()}


def record_failure(text: str, *, path: str = "", line: int = 0) -> None:
    t = (text or "").strip()
    if not t:
        return
    _RECENT_FAILURES.insert(
        0, {"ts": time.time(), "text": t[:500], "path": path, "line": int(line or 0)}
    )
    del _RECENT_FAILURES[_RECENT_FAILURES_MAX:]


def suggest_conditions(*, path: str = "", line: int = 0, variables: list[str] | None = None) -> dict[str, Any]:
    """Heuristic 'AI' suggestions from recent failures + common patterns."""
    suggestions: list[dict[str, Any]] = []
    vars_ = [str(v) for v in (variables or []) if str(v).strip()][:20]
    for fail in _RECENT_FAILURES[:12]:
        text = fail.get("text") or ""
        # NameError / KeyError / AttributeError patterns
        m = re.search(r"NameError: name '(\w+)'", text)
        if m:
            suggestions.append(
                {
                    "condition": f"{m.group(1)} is not None",
                    "reason": f"from recent NameError for {m.group(1)}",
                    "score": 0.9,
                }
            )
        m = re.search(r"KeyError: ['\"]?([^'\"]+)['\"]?", text)
        if m:
            key = m.group(1)
            suggestions.append(
                {
                    "condition": f"{key!r} in locals() or {key!r} in globals()",
                    "reason": f"from recent KeyError {key!r}",
                    "score": 0.85,
                }
            )
        m = re.search(r"(\w+) is None", text)
        if m:
            suggestions.append(
                {
                    "condition": f"{m.group(1)} is not None",
                    "reason": "from recent NoneType failure",
                    "score": 0.8,
                }
            )
        m = re.search(r"IndexError", text)
        if m and vars_:
            suggestions.append(
                {
                    "condition": f"len({vars_[0]}) > 0",
                    "reason": "from recent IndexError",
                    "score": 0.7,
                }
            )
        m = re.search(r"AssertionError:?\s*(.*)", text)
        if m and m.group(1).strip():
            suggestions.append(
                {
                    "condition": m.group(1).strip()[:120],
                    "reason": "from recent AssertionError",
                    "score": 0.65,
                }
            )
    for v in vars_[:6]:
        suggestions.append(
            {
                "condition": f"{v} is not None",
                "reason": f"guard variable {v}",
                "score": 0.4,
            }
        )
        suggestions.append(
            {
                "condition": f"{v}",
                "reason": f"truthy {v}",
                "score": 0.35,
            }
        )
    # dedupe by condition
    seen = set()
    uniq = []
    for s in sorted(suggestions, key=lambda x: -float(x.get("score") or 0)):
        c = s["condition"]
        if c in seen:
            continue
        seen.add(c)
        uniq.append(s)
    return {
        "ok": True,
        "path": path,
        "line": line,
        "suggestions": uniq[:12],
        "fromFailures": len(_RECENT_FAILURES),
    }


def otlp_export(
    workspace: Path,
    *,
    endpoint: str = "",
    spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Export debug spans as OTLP/JSON (HTTP). Also writes local export file."""
    from editor import debug_advanced

    if spans is None:
        spans = debug_advanced.otel_list_spans(workspace, limit=200).get("spans") or []
    # Convert to OTLP-ish resourceSpans
    otlp = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "zintriq-debug"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "zintriq.debug"},
                        "spans": [
                            {
                                "traceId": s.get("traceId") or uuid.uuid4().hex,
                                "spanId": s.get("spanId") or uuid.uuid4().hex[:16],
                                "name": s.get("name") or "debug",
                                "kind": 1,
                                "startTimeUnixNano": str(s.get("startTimeUnixNano") or 0),
                                "endTimeUnixNano": str(s.get("endTimeUnixNano") or 0),
                                "attributes": [
                                    {
                                        "key": str(k),
                                        "value": {"stringValue": str(v)},
                                    }
                                    for k, v in (s.get("attributes") or {}).items()
                                ],
                                "status": s.get("status") or {"code": 1},
                            }
                            for s in spans
                        ],
                    }
                ],
            }
        ]
    }
    out_dir = workspace.resolve() / ".zintriq" / "otel"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "otlp-export.json"
    path.write_text(json.dumps(otlp, indent=2) + "\n", encoding="utf-8")
    posted = False
    status = ""
    url = (endpoint or "").strip()
    if url:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(otlp).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                status = f"HTTP {resp.status}"
                posted = True
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            status = str(exc)[:200]
    return {
        "ok": True,
        "path": ".zintriq/otel/otlp-export.json",
        "spanCount": len(spans),
        "posted": posted,
        "endpoint": url,
        "status": status,
    }


def chrome_dwarf_inject_snippet(workspace: Path) -> dict[str, Any]:
    """Generate a userscript / DevTools snippet hint for Chrome DWARF extension auto-inject."""
    snippet = """// Zintriq WASM DWARF helper — paste in DevTools Snippets or extension content script
(async () => {
  const wasmUrls = performance.getEntriesByType('resource')
    .filter(e => e.name.endsWith('.wasm'))
    .map(e => e.name);
  console.info('[zintriq] wasm resources', wasmUrls);
  // If chrome.debugger / C/C++ DevTools Support (DWARF) is installed,
  // enable "Extension Options → Enable DWARF debugging" then reload.
  if (!wasmUrls.length) {
    console.warn('[zintriq] no .wasm loaded yet — navigate to the page that loads WASM');
  }
  for (const url of wasmUrls.slice(0, 5)) {
    try {
      const buf = await fetch(url).then(r => r.arrayBuffer());
      const u8 = new Uint8Array(buf);
      const hasDwarf = new TextDecoder().decode(u8.slice(0, Math.min(u8.length, 1<<20)))
        .includes('.debug_');
      console.info('[zintriq]', url, 'dwarf?', hasDwarf, 'bytes', u8.length);
    } catch (e) { console.warn(url, e); }
  }
})();
"""
    path = workspace.resolve() / ".zintriq" / "chrome-dwarf-inject.js"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snippet, encoding="utf-8")
    return {
        "ok": True,
        "path": ".zintriq/chrome-dwarf-inject.js",
        "snippet": snippet,
        "hint": "Install 'C/C++ DevTools Support (DWARF)' then run this snippet after WASM load",
        "extensionIdHint": "pdcpmagklfoinpibluoophmbnypaiopj",
    }


def compounds_graph(document: dict[str, Any]) -> dict[str, Any]:
    """Build nodes/edges + mermaid for launch compounds visualization."""
    configs = {str(c.get("name")): c for c in (document.get("configurations") or []) if isinstance(c, dict)}
    compounds = [c for c in (document.get("compounds") or []) if isinstance(c, dict)]
    nodes = []
    edges = []
    for name, cfg in configs.items():
        nodes.append(
            {
                "id": f"cfg:{name}",
                "label": name,
                "kind": "config",
                "type": cfg.get("type"),
                "request": cfg.get("request"),
            }
        )
    for c in compounds:
        cname = str(c.get("name") or "")
        nodes.append(
            {
                "id": f"cmp:{cname}",
                "label": cname,
                "kind": "compound",
                "stopAll": bool(c.get("stopAll", True)),
            }
        )
        for ref in c.get("configurations") or []:
            edges.append({"from": f"cmp:{cname}", "to": f"cfg:{ref}", "kind": "includes"})
    lines = ["flowchart LR"]
    for n in nodes:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", n["id"])
        shape = "{{" + n["label"] + "}}" if n["kind"] == "compound" else ("[" + n["label"] + "]")
        lines.append(f"  {safe}{shape}")
    for e in edges:
        a = re.sub(r"[^A-Za-z0-9_]", "_", e["from"])
        b = re.sub(r"[^A-Za-z0-9_]", "_", e["to"])
        lines.append(f"  {a} --> {b}")
    return {"ok": True, "nodes": nodes, "edges": edges, "mermaid": "\n".join(lines)}


def notebook_cells(workspace: Path, path: str) -> dict[str, Any]:
    """Parse .ipynb for cell-level DAP targeting."""
    rel = (path or "").replace("\\", "/").strip()
    if not rel.endswith(".ipynb") or ".." in Path(rel).parts:
        raise ValueError("not a notebook path")
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())
    raw = json.loads(target.read_text(encoding="utf-8"))
    cells = []
    for i, cell in enumerate(raw.get("cells") or []):
        if not isinstance(cell, dict):
            continue
        src = cell.get("source") or ""
        if isinstance(src, list):
            src = "".join(src)
        cells.append(
            {
                "index": i,
                "id": cell.get("id") or f"cell-{i}",
                "cell_type": cell.get("cell_type") or "code",
                "lines": len(str(src).splitlines()) or 1,
                "preview": str(src)[:120].replace("\n", " "),
            }
        )
    return {
        "ok": True,
        "path": rel,
        "cells": cells,
        "launchHint": {
            "name": f"Notebook: {Path(rel).name}",
            "type": "jupyter",
            "request": "attach",
            "host": "127.0.0.1",
            "port": 5678,
            "notebook": {"path": rel, "cellIndex": 0},
        },
    }


def notebook_cell_source(workspace: Path, path: str, cell_index: int) -> dict[str, Any]:
    rel = (path or "").replace("\\", "/").strip()
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())
    raw = json.loads(target.read_text(encoding="utf-8"))
    cells = raw.get("cells") or []
    if cell_index < 0 or cell_index >= len(cells):
        raise IndexError("cell index out of range")
    cell = cells[cell_index]
    src = cell.get("source") or ""
    if isinstance(src, list):
        src = "".join(src)
    # Write temp .py for DAP launch of a single cell
    out = workspace.resolve() / ".zintriq" / "notebook_cells" / f"{Path(rel).stem}_c{cell_index}.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(str(src), encoding="utf-8")
    return {
        "ok": True,
        "path": rel,
        "cellIndex": cell_index,
        "program": str(out.relative_to(workspace.resolve())).replace("\\", "/"),
        "source": str(src),
    }


def replay_dir(workspace: Path) -> Path:
    d = workspace.resolve() / ".zintriq" / "replay"
    d.mkdir(parents=True, exist_ok=True)
    return d


def start_recording(workspace: Path, session_id: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    rid = uuid.uuid4().hex[:10]
    path = replay_dir(workspace) / f"{rid}.jsonl"
    header = {
        "kind": "header",
        "id": rid,
        "sessionId": session_id,
        "ts": time.time(),
        "meta": meta or {},
    }
    path.write_text(json.dumps(header) + "\n", encoding="utf-8")
    return {"ok": True, "replayId": rid, "path": f".zintriq/replay/{rid}.jsonl"}


def append_recording(workspace: Path, replay_id: str, event: dict[str, Any]) -> None:
    path = replay_dir(workspace) / f"{replay_id}.jsonl"
    if not path.is_file():
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "event", "ts": time.time(), **event}, ensure_ascii=False) + "\n")


def list_recordings(workspace: Path) -> dict[str, Any]:
    items = []
    for p in sorted(replay_dir(workspace).glob("*.jsonl"), key=lambda x: -x.stat().st_mtime):
        try:
            first = p.read_text(encoding="utf-8").splitlines()[0]
            header = json.loads(first)
        except Exception:
            header = {}
        items.append(
            {
                "id": p.stem,
                "path": f".zintriq/replay/{p.name}",
                "sessionId": header.get("sessionId"),
                "ts": header.get("ts"),
                "meta": header.get("meta") or {},
                "bytes": p.stat().st_size,
            }
        )
    return {"ok": True, "recordings": items}


def load_recording(workspace: Path, replay_id: str) -> dict[str, Any]:
    path = replay_dir(workspace) / f"{replay_id}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(replay_id)
    events = []
    header = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("kind") == "header":
            header = obj
        else:
            events.append(obj)
    # Build postmortem-like view from last stopped snapshot
    stack = []
    variables = []
    for ev in reversed(events):
        if ev.get("event") == "stopped" or ev.get("kind") == "snapshot":
            stack = ev.get("stack") or stack
            variables = ev.get("variables") or variables
            if stack:
                break
    return {
        "ok": True,
        "id": replay_id,
        "header": header,
        "events": events,
        "stack": stack,
        "variables": variables,
        "reason": f"replay:{replay_id}",
        "path": f".zintriq/replay/{replay_id}.jsonl",
        "mode": "replay",
    }


def rust_go_presets() -> list[dict[str, Any]]:
    return [
        {
            "name": "Rust: lldb (custom adapter)",
            "type": "custom",
            "request": "launch",
            "program": "${workspaceFolder}/target/debug/${workspaceFolderBasename}",
            "cwd": "${workspaceFolder}",
            "debugAdapter": ["codelldb"],
            "sourceLanguages": ["rust"],
        },
        {
            "name": "Rust: gdb (custom adapter)",
            "type": "custom",
            "request": "launch",
            "program": "${workspaceFolder}/target/debug/${workspaceFolderBasename}",
            "cwd": "${workspaceFolder}",
            "debugAdapter": ["gdb", "--interpreter=mi"],
        },
        {
            "name": "Go: delve (dlv dap)",
            "type": "custom",
            "request": "launch",
            "program": "${workspaceFolder}",
            "cwd": "${workspaceFolder}",
            "debugAdapter": ["dlv", "dap"],
            "mode": "debug",
        },
        {
            "name": "Go: attach delve",
            "type": "custom",
            "request": "attach",
            "host": "127.0.0.1",
            "port": 2345,
            "debugAdapter": ["dlv", "dap"],
        },
    ]


def subprocess_attach_matrix(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Build parent/child attach matrix from session snapshots."""
    by_id = {str(s.get("sessionId") or s.get("id")): s for s in sessions}
    rows = []
    for sid, s in by_id.items():
        parent = s.get("parentSessionId")
        children = s.get("childSessionIds") or s.get("childIds") or []
        rows.append(
            {
                "sessionId": sid,
                "label": s.get("configName") or s.get("path") or sid,
                "engine": s.get("engine"),
                "alive": s.get("running") or s.get("alive"),
                "stopped": s.get("stopped"),
                "parentSessionId": parent,
                "childSessionIds": list(children),
                "role": "child" if parent else ("parent" if children else "solo"),
            }
        )
    return {"ok": True, "matrix": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Function breakpoints, pins, live share, vault, merge, triage, LLM, SBOM, …
# ---------------------------------------------------------------------------

_FUNCTION_BPS: list[dict[str, Any]] = []
_PINNED_VARS: list[dict[str, Any]] = []  # {expression, label}
_LIVE_SHARE: dict[str, Any] = {}  # roomId -> {snapshot, spectators, readonly}
_TRACE_LOG: list[dict[str, Any]] = []  # structured logpoints
_CATCHPOINTS: dict[str, Any] = {"throw": False, "signals": []}  # gdb catch
_SBOM_CVES: list[dict[str, Any]] = []  # loaded vulnerability rules


def list_function_breakpoints() -> list[dict[str, Any]]:
    return [dict(x) for x in _FUNCTION_BPS]


def set_function_breakpoints(names: list[Any]) -> dict[str, Any]:
    clean = []
    for n in names or []:
        if isinstance(n, dict):
            name = str(n.get("name") or n.get("function") or "").strip()
            if not name:
                continue
            clean.append(
                {
                    "id": str(n.get("id") or uuid.uuid4().hex[:8]),
                    "name": name,
                    "condition": str(n.get("condition") or ""),
                }
            )
        else:
            name = str(n).strip()
            if name:
                clean.append({"id": uuid.uuid4().hex[:8], "name": name, "condition": ""})
    _FUNCTION_BPS[:] = clean
    return {"ok": True, "functionBreakpoints": list_function_breakpoints()}


def list_pinned_vars() -> list[dict[str, Any]]:
    return [dict(x) for x in _PINNED_VARS]


def pin_variable(expression: str, *, label: str = "") -> dict[str, Any]:
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("empty expression")
    existing = next((x for x in _PINNED_VARS if x["expression"] == expr), None)
    if existing:
        if label:
            existing["label"] = label
        return {"ok": True, "pinned": list_pinned_vars(), "item": dict(existing)}
    item = {"expression": expr, "label": (label or expr).strip(), "id": uuid.uuid4().hex[:8]}
    _PINNED_VARS.append(item)
    return {"ok": True, "pinned": list_pinned_vars(), "item": item}


def unpin_variable(id_or_expr: str) -> dict[str, Any]:
    key = (id_or_expr or "").strip()
    _PINNED_VARS[:] = [x for x in _PINNED_VARS if x.get("id") != key and x.get("expression") != key]
    return {"ok": True, "pinned": list_pinned_vars()}


def live_share_publish(session_snapshot: dict[str, Any], *, room: str = "") -> dict[str, Any]:
    """Host publishes a read-only debug snapshot for spectators."""
    rid = (room or "").strip() or uuid.uuid4().hex[:8]
    _LIVE_SHARE[rid] = {
        "room": rid,
        "ts": time.time(),
        "readonly": True,
        "snapshot": {
            k: session_snapshot.get(k)
            for k in (
                "sessionId",
                "engine",
                "stopped",
                "stack",
                "variables",
                "watches",
                "reason",
                "path",
                "line",
                "console",
                "timeline",
            )
        },
        "spectators": (_LIVE_SHARE.get(rid) or {}).get("spectators") or 0,
    }
    return {"ok": True, "room": rid, "urlHint": f"/api/debug/liveShare/{rid}", "readonly": True}


def live_share_join(room: str) -> dict[str, Any]:
    rid = (room or "").strip()
    data = _LIVE_SHARE.get(rid)
    if not data:
        raise KeyError("unknown live share room")
    data["spectators"] = int(data.get("spectators") or 0) + 1
    return {"ok": True, "room": rid, "readonly": True, "snapshot": data.get("snapshot") or {}, "ts": data.get("ts")}


def live_share_list() -> dict[str, Any]:
    rooms = [
        {"room": r, "ts": v.get("ts"), "spectators": v.get("spectators") or 0, "path": (v.get("snapshot") or {}).get("path")}
        for r, v in _LIVE_SHARE.items()
    ]
    return {"ok": True, "rooms": rooms}


def vault_path(workspace: Path) -> Path:
    return workspace.resolve() / ".zintriq" / "secrets.vault.json"


def vault_load(workspace: Path) -> dict[str, str]:
    path = vault_path(workspace)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    secrets = raw.get("secrets") if isinstance(raw, dict) else {}
    if not isinstance(secrets, dict):
        return {}
    return {str(k): str(v) for k, v in secrets.items()}


def vault_set(workspace: Path, key: str, value: str) -> dict[str, Any]:
    k = (key or "").strip()
    if not k or k.startswith("_"):
        raise ValueError("invalid key")
    secrets = vault_load(workspace)
    secrets[k] = str(value)
    path = vault_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "secrets": secrets}, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "keys": sorted(secrets.keys())}


def vault_resolve_env(workspace: Path, env: dict[str, Any] | None) -> dict[str, str]:
    """Resolve ${vault:KEY} placeholders in launch env."""
    secrets = vault_load(workspace)
    out: dict[str, str] = {}
    for k, v in (env or {}).items():
        s = str(v)
        m = re.fullmatch(r"\$\{vault:([^}]+)\}", s.strip())
        if m:
            key = m.group(1).strip()
            out[str(k)] = secrets.get(key, "")
        else:
            out[str(k)] = s
    return out


def merge_breakpoints(
    local: dict[str, list[dict[str, Any]]],
    remote: dict[str, list[dict[str, Any]]],
    *,
    strategy: str = "union",
) -> dict[str, Any]:
    """Merge multi-user breakpoint maps. strategy: union|local|remote|conflict."""
    strat = (strategy or "union").lower()
    conflicts: list[dict[str, Any]] = []
    merged: dict[str, list[dict[str, Any]]] = {}
    paths = set(local or {}) | set(remote or {})
    for path in paths:
        la = {int(b.get("line") or 0): dict(b) for b in (local or {}).get(path) or [] if int(b.get("line") or 0) >= 1}
        ra = {int(b.get("line") or 0): dict(b) for b in (remote or {}).get(path) or [] if int(b.get("line") or 0) >= 1}
        lines = set(la) | set(ra)
        out_list = []
        for ln in sorted(lines):
            L, R = la.get(ln), ra.get(ln)
            if L and R:
                if (
                    L.get("condition") != R.get("condition")
                    or L.get("logMessage") != R.get("logMessage")
                    or L.get("hitCondition") != R.get("hitCondition")
                    or L.get("column") != R.get("column")
                ):
                    conflicts.append({"path": path, "line": ln, "local": L, "remote": R})
                    if strat == "remote":
                        out_list.append(R)
                    elif strat == "conflict":
                        # keep both as annotated
                        out_list.append({**L, "conflict": "local"})
                        out_list.append({**R, "conflict": "remote", "line": ln})
                    else:
                        out_list.append(L)  # union defaults to local wins on conflict
                else:
                    out_list.append(L)
            elif L and strat != "remote":
                out_list.append(L)
            elif R and strat != "local":
                out_list.append(R)
        if out_list:
            merged[path] = out_list
    return {"ok": True, "breakpoints": merged, "conflicts": conflicts, "strategy": strat}


def triage_report(
    workspace: Path,
    *,
    session: dict[str, Any] | None = None,
    postmortem: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One-click crash triage markdown + JSON under .zintriq/triage/."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    d = workspace.resolve() / ".zintriq" / "triage"
    d.mkdir(parents=True, exist_ok=True)
    sess = session or {}
    pm = postmortem or {}
    stack = sess.get("stack") or pm.get("stack") or []
    reason = sess.get("reason") or pm.get("reason") or "crash"
    report = {
        "id": f"triage-{ts}",
        "ts": time.time(),
        "reason": reason,
        "engine": sess.get("engine") or pm.get("mode"),
        "path": sess.get("path") or pm.get("path"),
        "stack": stack[:40],
        "variables": (sess.get("variables") or pm.get("variables") or [])[:40],
        "console": (sess.get("console") or pm.get("console") or [])[-30:],
        "modules": sess.get("modules") or [],
    }
    md_lines = [
        f"# Triage {report['id']}",
        "",
        f"**Reason:** {reason}",
        f"**Engine:** {report.get('engine')}",
        f"**Path:** {report.get('path')}",
        "",
        "## Stack",
    ]
    for fr in stack[:25]:
        md_lines.append(f"- `{fr.get('name')}` @ `{fr.get('path')}:{fr.get('line')}`")
    md_lines += ["", "## Variables"]
    for v in report["variables"][:30]:
        md_lines.append(f"- `{v.get('name')}` = `{v.get('value')}` ({v.get('type')})")
    md = "\n".join(md_lines) + "\n"
    json_path = d / f"{report['id']}.json"
    md_path = d / f"{report['id']}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    return {
        "ok": True,
        "id": report["id"],
        "json": f".zintriq/triage/{json_path.name}",
        "markdown": f".zintriq/triage/{md_path.name}",
        "report": report,
    }


def suggest_conditions_llm(
    *,
    path: str = "",
    line: int = 0,
    code_context: str = "",
    failure: str = "",
    variables: list[str] | None = None,
    allow_network: bool = False,
) -> dict[str, Any]:
    """True model path via ai_worker when API key + ai.run; else heuristic fallback."""
    heuristic = suggest_conditions(path=path, line=line, variables=variables)
    prompt = (
        "Suggest 3-5 debug breakpoint conditions (boolean expressions) for this stop.\n"
        f"File: {path}:{line}\n"
        f"Recent failure: {failure or (_RECENT_FAILURES[0]['text'] if _RECENT_FAILURES else 'n/a')}\n"
        f"Variables: {', '.join(variables or [])}\n"
        f"Code:\n{code_context[:2000]}\n"
        "Return ONLY a JSON array of objects {condition, reason}. No markdown."
    )
    try:
        from editor import ai_worker

        result = ai_worker.run(
            {
                "prompt": prompt,
                "path": path or "breakpoint.py",
                "text": code_context or "",
                "allow_network": allow_network,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return {**heuristic, "provider": "heuristic", "llmError": str(exc)}
    if not result.get("ok"):
        return {**heuristic, "provider": "heuristic", "llmError": result.get("error")}
    if result.get("provider") == "stub":
        return {**heuristic, "provider": "heuristic+stub", "note": result.get("note")}
    # Parse model JSON from after text
    text = str(result.get("after") or "")
    suggestions = []
    try:
        # find JSON array
        m = re.search(r"\[[\s\S]*\]", text)
        raw = json.loads(m.group(0) if m else text)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("condition"):
                    suggestions.append(
                        {
                            "condition": str(item["condition"]),
                            "reason": str(item.get("reason") or "llm"),
                            "score": 0.95,
                        }
                    )
    except Exception:
        suggestions = heuristic.get("suggestions") or []
    if not suggestions:
        suggestions = heuristic.get("suggestions") or []
    return {
        "ok": True,
        "suggestions": suggestions[:12],
        "provider": result.get("provider") or "llm",
        "fromFailures": heuristic.get("fromFailures"),
    }


def record_tracepoint(message: str, *, path: str = "", line: int = 0, fields: dict[str, Any] | None = None) -> None:
    _TRACE_LOG.append(
        {
            "ts": time.time(),
            "message": (message or "")[:500],
            "path": path,
            "line": int(line or 0),
            "fields": fields or {},
        }
    )
    if len(_TRACE_LOG) > 2000:
        del _TRACE_LOG[: len(_TRACE_LOG) - 2000]


def query_tracepoints(
    *,
    q: str = "",
    path: str = "",
    limit: int = 80,
) -> dict[str, Any]:
    """Structured log warehouse query over recorded logpoints/tracepoints."""
    query = (q or "").strip().lower()
    pref = (path or "").replace("\\", "/")
    hits = []
    for row in reversed(_TRACE_LOG):
        if pref and not str(row.get("path") or "").startswith(pref):
            continue
        blob = json.dumps(row, ensure_ascii=False).lower()
        if query and query not in blob:
            continue
        hits.append(row)
        if len(hits) >= max(1, min(int(limit), 500)):
            break
    return {"ok": True, "results": list(reversed(hits)), "totalIndexed": len(_TRACE_LOG), "q": q}


def profile_budget_check(
    workspace: Path,
    profile: dict[str, Any],
    *,
    budget_ms: float = 100.0,
    budget_self_pct: float = 40.0,
) -> dict[str, Any]:
    """CI-style performance budget gate against a flame/profile summary."""
    flame = profile.get("flame") or profile
    violations = []

    def walk(node: dict[str, Any], depth: int = 0) -> None:
        name = str(node.get("name") or "?")
        val = float(node.get("value") or 0)
        self_v = float(node.get("self") or 0)
        # Treat value as relative cost units; if ms keys exist use them
        ms = float(node.get("ms") or node.get("time") or 0)
        if ms and ms > budget_ms and depth > 0:
            violations.append({"name": name, "ms": ms, "rule": "budget_ms"})
        total = float(flame.get("value") or 1) or 1
        if self_v / total * 100 >= budget_self_pct and depth > 0:
            violations.append({"name": name, "selfPct": round(self_v / total * 100, 1), "rule": "budget_self_pct"})
        for c in node.get("children") or []:
            if isinstance(c, dict):
                walk(c, depth + 1)

    if isinstance(flame, dict):
        walk(flame)
    ok = not violations
    out_dir = workspace.resolve() / ".zintriq" / "ci"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"ok": ok, "violations": violations[:40], "budgetMs": budget_ms, "budgetSelfPct": budget_self_pct}
    path = out_dir / "profile-budget.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {**report, "path": ".zintriq/ci/profile-budget.json"}


def set_catchpoints(*, throw: bool | None = None, signals: list[str] | None = None) -> dict[str, Any]:
    if throw is not None:
        _CATCHPOINTS["throw"] = bool(throw)
    if signals is not None:
        _CATCHPOINTS["signals"] = [str(s).strip() for s in signals if str(s).strip()]
    return {"ok": True, "catchpoints": dict(_CATCHPOINTS)}


def get_catchpoints() -> dict[str, Any]:
    return {"ok": True, "catchpoints": dict(_CATCHPOINTS)}


def apply_gdb_catchpoints(mi: Any) -> dict[str, Any]:
    """Apply catch throw / catch signal via gdb MI/CLI."""
    results = []
    cp = dict(_CATCHPOINTS)
    try:
        if cp.get("throw"):
            results.append({"cmd": "catch throw", "out": mi.cli("catch throw")[:500]})
        for sig in cp.get("signals") or []:
            results.append({"cmd": f"catch signal {sig}", "out": mi.cli(f"catch signal {sig}")[:500]})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "results": results}
    return {"ok": True, "results": results, "catchpoints": cp}


def diff_replays(workspace: Path, a_id: str, b_id: str) -> dict[str, Any]:
    a = load_recording(workspace, a_id)
    b = load_recording(workspace, b_id)
    a_stack = [(f.get("path"), f.get("line"), f.get("name")) for f in (a.get("stack") or [])]
    b_stack = [(f.get("path"), f.get("line"), f.get("name")) for f in (b.get("stack") or [])]
    a_vars = {str(v.get("name")): str(v.get("value")) for v in (a.get("variables") or [])}
    b_vars = {str(v.get("name")): str(v.get("value")) for v in (b.get("variables") or [])}
    var_diff = []
    for k in sorted(set(a_vars) | set(b_vars)):
        if a_vars.get(k) != b_vars.get(k):
            var_diff.append({"name": k, "a": a_vars.get(k, ""), "b": b_vars.get(k, "")})
    a_ev = [e.get("event") or e.get("kind") for e in (a.get("events") or [])]
    b_ev = [e.get("event") or e.get("kind") for e in (b.get("events") or [])]
    return {
        "ok": True,
        "a": a_id,
        "b": b_id,
        "stackEqual": a_stack == b_stack,
        "stackA": a_stack[:30],
        "stackB": b_stack[:30],
        "varDiff": var_diff[:60],
        "eventCount": {"a": len(a_ev), "b": len(b_ev)},
        "reason": {"a": a.get("reason"), "b": b.get("reason")},
    }


def load_sbom(workspace: Path, path: str = "") -> dict[str, Any]:
    """Load CycloneDX / simple JSON SBOM + optional CVE list for pause-on-vuln."""
    global _SBOM_CVES
    rel = (path or ".zintriq/sbom.json").replace("\\", "/")
    target = (workspace / rel).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError("sbom outside workspace") from exc
    if not target.is_file():
        # seed empty
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "components": [],
                    "vulnerabilities": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    raw = json.loads(target.read_text(encoding="utf-8"))
    vulns = []
    for v in raw.get("vulnerabilities") or []:
        if isinstance(v, dict):
            vulns.append(
                {
                    "id": v.get("id") or v.get("cve") or "",
                    "severity": v.get("severity") or "high",
                    "affects": [a.get("ref") if isinstance(a, dict) else str(a) for a in (v.get("affects") or [])],
                    "packages": v.get("packages") or [],
                }
            )
    # Also accept simple {cves:[{id,package}]}
    for v in raw.get("cves") or []:
        if isinstance(v, dict):
            vulns.append(
                {
                    "id": v.get("id") or "",
                    "severity": v.get("severity") or "high",
                    "packages": [v.get("package")] if v.get("package") else [],
                    "affects": [],
                }
            )
    _SBOM_CVES = [x for x in vulns if x.get("id")]
    return {"ok": True, "path": rel, "vulnerabilities": _SBOM_CVES, "count": len(_SBOM_CVES)}


def check_sbom_pause(modules: list[dict[str, Any]] | None = None, path: str = "") -> dict[str, Any]:
    """If loaded modules / frame path match SBOM CVE packages → recommend pause."""
    if not _SBOM_CVES:
        return {"ok": True, "pause": False, "hits": []}
    blob_parts = [path or ""]
    for m in modules or []:
        blob_parts.append(str(m.get("name") or ""))
        blob_parts.append(str(m.get("path") or ""))
    blob = " ".join(blob_parts).lower()
    hits = []
    for v in _SBOM_CVES:
        pkgs = [str(p).lower() for p in (v.get("packages") or []) if p]
        affects = [str(a).lower() for a in (v.get("affects") or []) if a]
        keys = pkgs + affects + [str(v.get("id") or "").lower()]
        if any(k and k in blob for k in keys):
            hits.append(v)
    return {
        "ok": True,
        "pause": bool(hits),
        "hits": hits,
        "reason": f"SBOM vulnerability: {', '.join(h['id'] for h in hits[:5])}" if hits else "",
    }


def shared_array_buffer_hint() -> dict[str, Any]:
    return {
        "ok": True,
        "headers": {
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Embedder-Policy": "require-corp",
        },
        "cdp": {
            "enable": ["Debugger", "Runtime"],
            "note": "Workers with SharedArrayBuffer appear as nested CDP targets; use Target.setAutoAttach",
        },
        "launchHint": {
            "name": "Node: worker + SAB",
            "type": "node",
            "request": "launch",
            "program": "${file}",
            "runtimeArgs": ["--experimental-worker"],
            "subProcess": True,
        },
    }


def rr_scrub_state(session_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize rr / timeline scrub UI state (frame index sync)."""
    tl = session_snapshot.get("timeline") or {}
    engine = str(session_snapshot.get("engine") or "")
    return {
        "ok": True,
        "engine": engine,
        "isRr": "rr" in engine or bool(session_snapshot.get("rr")),
        "index": tl.get("index"),
        "length": tl.get("length"),
        "viewing": tl.get("viewing"),
        "entries": tl.get("entries") or [],
        "events": tl.get("events") or [],
        "canScrub": bool(tl.get("length")),
    }

