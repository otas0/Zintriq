"""LSP façade: real JSON-RPC servers when present, else lightweight fallback."""

from __future__ import annotations

import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from editor import lsp_client


def language_for(path: str) -> str:
    ext = Path(path).suffix.lower()
    name = Path(path).name.lower()
    if name in {"makefile", "gnumakefile"}:
        return "plaintext"
    if name.endswith(".html") or name.endswith(".htm"):
        return "html"
    return {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".jsx": "javascriptreact",
        ".json": "json",
        ".jsonc": "json",
        ".md": "markdown",
        ".markdown": "markdown",
        ".css": "css",
        ".scss": "css",
        ".less": "css",
        ".html": "html",
        ".htm": "html",
        ".rs": "rust",
        ".go": "go",
        ".c": "c",
        ".h": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".m": "objc",
        ".mm": "objc",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".lua": "lua",
        ".rb": "ruby",
        ".php": "php",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
    }.get(ext, "plaintext")


def status() -> dict[str, Any]:
    servers = lsp_client.available_servers()
    return {
        "ok": True,
        "mode": "lsp" if any(servers.values()) else "fallback",
        "servers": servers,
        "tools": {"py_compile": True},
    }


def diagnose(workspace: Path, rel: str, text: str | None = None) -> dict[str, Any]:
    lang = language_for(rel)
    source = text if text is not None else _read(workspace, rel)
    sess = lsp_client.get_session(workspace, lang)
    if sess:
        try:
            uri = sess.ensure_open(rel, source, lsp_client.language_id(lang))
            # nudge change so server re-analyzes
            sess.ensure_open(rel, source, lsp_client.language_id(lang))
            diags = sess.diagnostics_for(uri)
            return {
                "ok": True,
                "path": rel,
                "language": lang,
                "diagnostics": diags,
                "engine": "lsp",
                "server": " ".join(sess.cmd),
            }
        except Exception as exc:  # noqa: BLE001
            fallback = _fallback_diags(lang, workspace, rel, source)
            return {
                "ok": True,
                "path": rel,
                "language": lang,
                "diagnostics": fallback,
                "engine": "fallback",
                "error": str(exc),
            }
    return {
        "ok": True,
        "path": rel,
        "language": lang,
        "diagnostics": _fallback_diags(lang, workspace, rel, source),
        "engine": "fallback",
    }


def complete(
    workspace: Path,
    rel: str,
    text: str,
    line: int,
    character: int,
) -> dict[str, Any]:
    """line/character are 0-based (LSP)."""
    lang = language_for(rel)
    sess = lsp_client.get_session(workspace, lang)
    if not sess:
        return {"ok": True, "items": [], "engine": "none", "language": lang}
    try:
        uri = sess.ensure_open(rel, text, lsp_client.language_id(lang))
        result = sess.request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": int(line), "character": int(character)},
            },
            timeout=8.0,
        )
        items_raw = result.get("items") if isinstance(result, dict) else result
        items = []
        for item in items_raw or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "")
            if not label:
                continue
            items.append(
                {
                    "label": label,
                    "kind": item.get("kind"),
                    "detail": item.get("detail") or "",
                    "insertText": item.get("insertText") or label,
                    "documentation": _doc_text(item.get("documentation")),
                }
            )
        return {"ok": True, "items": items[:80], "engine": "lsp", "language": lang}
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "items": [], "engine": "error", "error": str(exc), "language": lang}


def _doc_text(doc: Any) -> str:
    if isinstance(doc, str):
        return doc[:500]
    if isinstance(doc, dict):
        return str(doc.get("value") or "")[:500]
    return ""


def _uri_to_rel(workspace: Path, uri: str) -> str | None:
    if not uri:
        return None
    try:
        import os
        from urllib.parse import unquote, urlparse

        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        path_str = unquote(parsed.path)
        if os.name == "nt" and path_str.startswith("/") and len(path_str) >= 3 and path_str[2] == ":":
            path_str = path_str[1:]
        path = Path(path_str)
        return str(path.resolve().relative_to(workspace.resolve())).replace("\\", "/")
    except Exception:
        return None


def _locations(workspace: Path, result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    items = result if isinstance(result, list) else [result]
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # LocationLink
        target_uri = item.get("targetUri") or item.get("uri")
        rng = item.get("targetSelectionRange") or item.get("targetRange") or item.get("range") or {}
        start = rng.get("start") or {}
        rel = _uri_to_rel(workspace, str(target_uri or ""))
        if not rel:
            continue
        out.append(
            {
                "path": rel,
                "line": int(start.get("line") or 0),
                "character": int(start.get("character") or 0),
            }
        )
    return out


def definition(
    workspace: Path,
    rel: str,
    text: str,
    line: int,
    character: int,
) -> dict[str, Any]:
    lang = language_for(rel)
    sess = lsp_client.get_session(workspace, lang)
    if not sess:
        return {"ok": True, "locations": [], "engine": "none", "language": lang}
    try:
        uri = sess.ensure_open(rel, text, lsp_client.language_id(lang))
        result = sess.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": int(line), "character": int(character)},
            },
            timeout=8.0,
        )
        return {
            "ok": True,
            "locations": _locations(workspace, result),
            "engine": "lsp",
            "language": lang,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "locations": [], "error": str(exc), "language": lang}


def hover(
    workspace: Path,
    rel: str,
    text: str,
    line: int,
    character: int,
) -> dict[str, Any]:
    lang = language_for(rel)
    sess = lsp_client.get_session(workspace, lang)
    if not sess:
        return {"ok": True, "contents": "", "engine": "none", "language": lang}
    try:
        uri = sess.ensure_open(rel, text, lsp_client.language_id(lang))
        result = sess.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": int(line), "character": int(character)},
            },
            timeout=8.0,
        )
        contents = ""
        if isinstance(result, dict):
            raw = result.get("contents")
            if isinstance(raw, str):
                contents = raw
            elif isinstance(raw, dict):
                contents = str(raw.get("value") or "")
            elif isinstance(raw, list):
                parts = []
                for part in raw:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict):
                        parts.append(str(part.get("value") or ""))
                contents = "\n".join(parts)
        return {"ok": True, "contents": contents[:4000], "engine": "lsp", "language": lang}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "contents": "", "error": str(exc), "language": lang}


def references(
    workspace: Path,
    rel: str,
    text: str,
    line: int,
    character: int,
) -> dict[str, Any]:
    lang = language_for(rel)
    sess = lsp_client.get_session(workspace, lang)
    if not sess:
        return {"ok": True, "locations": [], "engine": "none", "language": lang}
    try:
        uri = sess.ensure_open(rel, text, lsp_client.language_id(lang))
        result = sess.request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": int(line), "character": int(character)},
                "context": {"includeDeclaration": True},
            },
            timeout=10.0,
        )
        return {
            "ok": True,
            "locations": _locations(workspace, result),
            "engine": "lsp",
            "language": lang,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "locations": [], "error": str(exc), "language": lang}


def code_actions(
    workspace: Path,
    rel: str,
    text: str,
    line: int,
    character: int,
    end_line: int | None = None,
    end_character: int | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    lang = language_for(rel)
    sess = lsp_client.get_session(workspace, lang)
    if not sess:
        return {"ok": True, "actions": [], "engine": "none", "language": lang}
    try:
        uri = sess.ensure_open(rel, text, lsp_client.language_id(lang))
        el = int(end_line if end_line is not None else line)
        ec = int(end_character if end_character is not None else character)
        lsp_diags = []
        for d in diagnostics or []:
            lsp_diags.append(
                {
                    "range": {
                        "start": {
                            "line": max(0, int(d.get("line") or 1) - 1),
                            "character": max(0, int(d.get("col") or 1) - 1),
                        },
                        "end": {
                            "line": max(0, int(d.get("line") or 1) - 1),
                            "character": max(0, int(d.get("col") or 1)),
                        },
                    },
                    "message": str(d.get("message") or ""),
                    "severity": {"error": 1, "warning": 2, "info": 3, "hint": 4}.get(
                        str(d.get("severity") or "warning"), 2
                    ),
                }
            )
        result = sess.request(
            "textDocument/codeAction",
            {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": int(line), "character": int(character)},
                    "end": {"line": el, "character": ec},
                },
                "context": {"diagnostics": lsp_diags, "triggerKind": 1},
            },
            timeout=10.0,
        )
        actions = []
        for item in result or []:
            if not isinstance(item, dict):
                continue
            actions.append(
                {
                    "title": str(item.get("title") or "action"),
                    "kind": item.get("kind") or "",
                    "isPreferred": bool(item.get("isPreferred")),
                    "edit": item.get("edit"),
                    "command": item.get("command"),
                    "disabled": item.get("disabled"),
                }
            )
        return {"ok": True, "actions": actions[:40], "engine": "lsp", "language": lang}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "actions": [], "error": str(exc), "language": lang}


def apply_code_action(
    workspace: Path,
    data_dir: Path,
    action: dict[str, Any],
    *,
    open_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply CodeAction.edit via change stack. Commands without edits are rejected."""
    from editor import changes

    edit = action.get("edit") if isinstance(action, dict) else None
    if not edit:
        raise RuntimeError("code action has no workspace edit (command-only not applied)")
    files = _workspace_edit_to_files(workspace, edit, open_overrides=open_overrides)
    if not files:
        raise RuntimeError("code action produced no file edits")
    proposed = changes.propose(
        data_dir,
        source="lsp-codeAction",
        files=files,
        note=str(action.get("title") or "code action")[:200],
    )
    return {"ok": True, "change": proposed}


def rename(
    workspace: Path,
    data_dir: Path,
    rel: str,
    text: str,
    line: int,
    character: int,
    new_name: str,
) -> dict[str, Any]:
    """Request LSP rename; propose WorkspaceEdit via change stack (no silent write)."""
    from editor import changes

    name = (new_name or "").strip()
    if not name:
        raise ValueError("empty name")
    lang = language_for(rel)
    sess = lsp_client.get_session(workspace, lang)
    if not sess:
        raise RuntimeError("no LSP server for rename")
    uri = sess.ensure_open(rel, text, lsp_client.language_id(lang))
    # sync unsaved buffer for current file
    sess.ensure_open(rel, text, lsp_client.language_id(lang))
    result = sess.request(
        "textDocument/rename",
        {
            "textDocument": {"uri": uri},
            "position": {"line": int(line), "character": int(character)},
            "newName": name,
        },
        timeout=15.0,
    )
    files = _workspace_edit_to_files(workspace, result, open_overrides={rel: text})
    if not files:
        raise RuntimeError("rename produced no edits")
    proposed = changes.propose(
        data_dir,
        source="lsp-rename",
        files=files,
        note=f"rename → {name}",
    )
    return {"ok": True, "change": proposed, "engine": "lsp", "language": lang}


def _workspace_edit_to_files(
    workspace: Path,
    edit: Any,
    *,
    open_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    if not isinstance(edit, dict):
        return []
    overrides = open_overrides or {}
    # Prefer documentChanges
    doc_changes = edit.get("documentChanges")
    path_edits: dict[str, list[tuple[dict[str, Any], str]]] = {}
    if isinstance(doc_changes, list):
        for dc in doc_changes:
            if not isinstance(dc, dict) or "textDocument" not in dc:
                continue
            uri = str((dc.get("textDocument") or {}).get("uri") or "")
            rel = _uri_to_rel(workspace, uri)
            if not rel:
                continue
            for te in dc.get("edits") or []:
                if isinstance(te, dict):
                    path_edits.setdefault(rel, []).append((te.get("range") or {}, str(te.get("newText") or "")))
    else:
        changes_map = edit.get("changes") or {}
        if isinstance(changes_map, dict):
            for uri, edits in changes_map.items():
                rel = _uri_to_rel(workspace, str(uri))
                if not rel:
                    continue
                for te in edits or []:
                    if isinstance(te, dict):
                        path_edits.setdefault(rel, []).append((te.get("range") or {}, str(te.get("newText") or "")))

    out: list[dict[str, str]] = []
    for rel, edits in path_edits.items():
        before = overrides.get(rel)
        if before is None:
            path = (workspace / rel).resolve()
            path.relative_to(workspace.resolve())
            before = path.read_text(encoding="utf-8") if path.is_file() else ""
        after = _apply_text_edits(before, edits)
        if after != before:
            out.append({"path": rel, "before": before, "after": after})
    return out


def _apply_text_edits(text: str, edits: list[tuple[dict[str, Any], str]]) -> str:
    """Apply LSP TextEdits (ranges are 0-based). Apply from end to start."""

    def offset(line: int, character: int) -> int:
        lines = text.splitlines(keepends=True)
        if line >= len(lines):
            return len(text)
        off = sum(len(lines[i]) for i in range(line))
        return off + min(character, len(lines[line]))

    ranked = []
    for rng, new in edits:
        start = rng.get("start") or {}
        end = rng.get("end") or {}
        s = offset(int(start.get("line") or 0), int(start.get("character") or 0))
        e = offset(int(end.get("line") or 0), int(end.get("character") or 0))
        ranked.append((s, e, new))
    ranked.sort(key=lambda t: t[0], reverse=True)
    out = text
    for s, e, new in ranked:
        out = out[:s] + new + out[e:]
    return out


def _read(workspace: Path, rel: str) -> str:
    path = (workspace / rel).resolve()
    path.relative_to(workspace.resolve())
    return path.read_text(encoding="utf-8")


def _fallback_diags(lang: str, workspace: Path, rel: str, source: str) -> list[dict[str, Any]]:
    if lang == "python":
        return _python_fallback(source)
    if lang == "json":
        try:
            json.loads(source)
        except json.JSONDecodeError as exc:
            return [
                {
                    "line": exc.lineno or 1,
                    "col": exc.colno or 1,
                    "severity": "error",
                    "message": exc.msg,
                    "source": "json",
                }
            ]
    return []


def _python_fallback(source: str) -> list[dict[str, Any]]:
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(source)
            tmp_path = tmp.name
        try:
            py_compile.compile(tmp_path, doraise=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except py_compile.PyCompileError as exc:
        msg = str(exc)
        line = 1
        if "line" in msg:
            try:
                line = int(msg.split("line")[-1].split()[0].strip(","))
            except ValueError:
                line = 1
        return [
            {
                "line": line,
                "col": 1,
                "severity": "error",
                "message": msg.split("\n")[0][:300],
                "source": "py_compile",
            }
        ]
    return []
