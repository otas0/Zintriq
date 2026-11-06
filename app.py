#!/usr/bin/env python3
"""Zintriq Editor — thin local Flask host for the desktop shell."""

from __future__ import annotations

import atexit
import hmac
import json
import os
import sys
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory

from editor import (
    ai_bypass,
    changes,
    debug_session,
    git_ops,
    lsp_bridge,
    lsp_client,
    permissions,
    pty_session,
    search,
    terminal,
)
from editor.permissions import PermissionDenied
from editor import workspace_bootstrap

TOKEN_HEADER = "X-Zintriq-Desktop-Token"
MIN_TOKEN_LENGTH = 32


def _env_path(name: str, default: Path) -> Path:
    raw = (os.environ.get(name) or "").strip()
    return Path(raw).expanduser().resolve() if raw else default.resolve()


ROOT = Path(__file__).resolve().parent
DATA_DIR = _env_path("ZINTRIQ_DATA_DIR", Path.home() / ".editor")
WORKSPACE = _env_path("ZINTRIQ_WORKSPACE", DATA_DIR / "workspace")
DESKTOP = (os.environ.get("ZINTRIQ_DESKTOP") or "").strip() == "1"
TOKEN = (os.environ.get("ZINTRIQ_DESKTOP_TOKEN") or "").strip()

debug_session.load_persisted(DATA_DIR)

app = Flask(
    __name__,
    static_folder=str(ROOT / "static"),
    template_folder=str(ROOT / "templates"),
)


def _token_ok() -> bool:
    if not DESKTOP:
        return False
    if len(TOKEN) < MIN_TOKEN_LENGTH:
        return False
    got = request.headers.get(TOKEN_HEADER) or request.args.get("token") or ""
    return hmac.compare_digest(got, TOKEN)


@app.before_request
def _gate_api() -> None:
    path = request.path or ""
    if path.startswith("/static/") or path in ("/healthz", "/favicon.ico"):
        return
    if path == "/editor" or path.startswith("/editor/"):
        if not DESKTOP:
            abort(404)
        return
    if path.startswith("/api/"):
        if not _token_ok():
            abort(401)
        return


@app.errorhandler(PermissionDenied)
def _perm_denied(exc: PermissionDenied) -> Response:
    return jsonify({"ok": False, "error": str(exc)}), 403


def _safe_under_workspace(rel: str) -> Path:
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        abort(400, "invalid path")
    target = (WORKSPACE / raw).resolve()
    try:
        target.relative_to(WORKSPACE.resolve())
    except ValueError:
        abort(400, "path escapes workspace")
    return target


def _err(exc: Exception, code: int = 400) -> Response:
    return jsonify({"ok": False, "error": str(exc)}), code


@app.get("/healthz")
def healthz() -> Response:
    if DESKTOP and not _token_ok():
        got = request.headers.get(TOKEN_HEADER) or ""
        if got and not hmac.compare_digest(got, TOKEN):
            abort(401)
    return jsonify(
        {
            "ok": True,
            "product": "editor",
            "desktop": DESKTOP,
            "workspace": str(WORKSPACE),
        }
    )


@app.get("/")
def root() -> Response:
    if DESKTOP:
        return Response("", status=302, headers={"Location": "/editor"})
    return jsonify({"ok": True, "product": "editor", "hint": "run with ZINTRIQ_DESKTOP=1"})


@app.get("/editor")
def editor_page() -> str:
    if not DESKTOP:
        abort(404)
    return render_template("editor.html")


@app.get("/api/fs/list")
def fs_list() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    rel = request.args.get("path") or ""
    if not rel.strip():
        workspace_bootstrap.seed_workspace(WORKSPACE)
    base = WORKSPACE.resolve() if not rel.strip() else _safe_under_workspace(rel)
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
    if not base.is_dir():
        abort(400, "not a directory")
    entries = []
    for child in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith("."):
            continue
        rel_path = str(child.relative_to(WORKSPACE.resolve())).replace("\\", "/")
        entries.append({"name": child.name, "path": rel_path, "dir": child.is_dir()})
    return jsonify(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "workspace": str(WORKSPACE.resolve()),
            "empty": workspace_bootstrap.is_empty_workspace(WORKSPACE) if not rel.strip() else False,
            "entries": entries,
        }
    )


@app.get("/api/fs/read")
def fs_read() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    target = _safe_under_workspace(request.args.get("path") or "")
    if not target.is_file():
        abort(404)
    if target.stat().st_size > 2 * 1024 * 1024:
        abort(413, "file too large")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        abort(415, "not utf-8 text")
    rel = str(target.relative_to(WORKSPACE.resolve())).replace("\\", "/")
    return jsonify({"ok": True, "path": rel, "text": text, "language": lsp_bridge.language_for(rel)})


@app.put("/api/fs/write")
def fs_write() -> Response:
    permissions.require(DATA_DIR, "fs.write")
    body = request.get_json(silent=True) or {}
    target = _safe_under_workspace(str(body.get("path") or ""))
    if "text" not in body:
        abort(400, "missing text")
    text = body["text"]
    if not isinstance(text, str):
        abort(400, "text must be string")
    if len(text.encode("utf-8")) > 2 * 1024 * 1024:
        abort(413, "file too large")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    rel = str(target.relative_to(WORKSPACE.resolve())).replace("\\", "/")
    return jsonify({"ok": True, "path": rel})


@app.post("/api/fs/mkdir")
def fs_mkdir() -> Response:
    permissions.require(DATA_DIR, "fs.write")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "").strip().replace("\\", "/")
    if not rel:
        abort(400, "missing path")
    target = _safe_under_workspace(rel)
    if target.exists():
        abort(409, "already exists")
    target.mkdir(parents=True, exist_ok=False)
    out = str(target.relative_to(WORKSPACE.resolve())).replace("\\", "/")
    return jsonify({"ok": True, "path": out, "dir": True})


@app.post("/api/fs/create")
def fs_create() -> Response:
    """Create a new empty file (fails if it already exists)."""
    permissions.require(DATA_DIR, "fs.write")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "").strip().replace("\\", "/")
    if not rel:
        abort(400, "missing path")
    text = body.get("text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        abort(400, "text must be string")
    if len(text.encode("utf-8")) > 2 * 1024 * 1024:
        abort(413, "file too large")
    target = _safe_under_workspace(rel)
    if target.exists():
        abort(409, "already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    out = str(target.relative_to(WORKSPACE.resolve())).replace("\\", "/")
    return jsonify({"ok": True, "path": out, "language": lsp_bridge.language_for(out)})


@app.post("/api/fs/delete")
def fs_delete() -> Response:
    permissions.require(DATA_DIR, "fs.write")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "").strip().replace("\\", "/")
    if not rel:
        abort(400, "missing path")
    target = _safe_under_workspace(rel)
    if not target.exists():
        abort(404)
    if target.is_dir():
        if any(target.iterdir()):
            abort(400, "directory not empty")
        target.rmdir()
    else:
        target.unlink()
    return jsonify({"ok": True, "path": rel})


@app.post("/api/fs/rename")
def fs_rename() -> Response:
    permissions.require(DATA_DIR, "fs.write")
    body = request.get_json(silent=True) or {}
    src_rel = str(body.get("from") or body.get("path") or "").strip().replace("\\", "/")
    dst_rel = str(body.get("to") or "").strip().replace("\\", "/")
    if not src_rel or not dst_rel:
        abort(400, "missing from/to")
    src = _safe_under_workspace(src_rel)
    dst = _safe_under_workspace(dst_rel)
    if not src.exists():
        abort(404)
    if dst.exists():
        abort(409, "destination exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    out = str(dst.relative_to(WORKSPACE.resolve())).replace("\\", "/")
    return jsonify({"ok": True, "path": out, "from": src_rel})


@app.get("/api/onboarding")
def onboarding_get() -> Response:
    state = workspace_bootstrap.ensure_ready(WORKSPACE, DATA_DIR)
    return jsonify({"ok": True, **state})


@app.post("/api/onboarding/complete")
def onboarding_complete() -> Response:
    body = request.get_json(silent=True) or {}
    completed = body.get("completed", True)
    state = workspace_bootstrap.save_onboarding(DATA_DIR, completed=bool(completed))
    return jsonify({"ok": True, "onboarding": state})


@app.get("/api/permissions")
def permissions_get() -> Response:
    return jsonify({"ok": True, "permissions": permissions.load(DATA_DIR)})


@app.put("/api/permissions")
def permissions_put() -> Response:
    body = request.get_json(silent=True) or {}
    saved = permissions.save(DATA_DIR, body.get("permissions") or body)
    return jsonify({"ok": True, "permissions": saved})


@app.get("/api/changes")
def changes_list() -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    status = request.args.get("status")
    return jsonify({"ok": True, "changes": changes.list_changes(DATA_DIR, status)})


@app.get("/api/changes/<change_id>")
def changes_get(change_id: str) -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    item = changes.get_change(DATA_DIR, change_id)
    if not item:
        abort(404)
    diffs = [
        {
            "path": f["path"],
            "diff": changes.unified_diff(f["before"], f["after"], f["path"]),
        }
        for f in item.get("files") or []
    ]
    return jsonify({"ok": True, "change": item, "diffs": diffs})


@app.post("/api/changes")
def changes_propose() -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    body = request.get_json(silent=True) or {}
    try:
        item = changes.propose(
            DATA_DIR,
            source=str(body.get("source") or "tool"),
            files=list(body.get("files") or []),
            note=str(body.get("note") or ""),
        )
    except ValueError as exc:
        return _err(exc)
    return jsonify({"ok": True, "change": item})


@app.post("/api/changes/<change_id>/accept")
def changes_accept(change_id: str) -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    try:
        item = changes.accept(DATA_DIR, WORKSPACE, change_id)
    except FileNotFoundError:
        abort(404)
    except (ValueError, OSError) as exc:
        return _err(exc)
    return jsonify({"ok": True, "change": item})


@app.post("/api/changes/<change_id>/reject")
def changes_reject(change_id: str) -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    try:
        item = changes.reject(DATA_DIR, change_id)
    except FileNotFoundError:
        abort(404)
    except ValueError as exc:
        return _err(exc)
    return jsonify({"ok": True, "change": item})


@app.post("/api/changes/<change_id>/rollback")
def changes_rollback(change_id: str) -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    try:
        item = changes.rollback(DATA_DIR, WORKSPACE, change_id)
    except FileNotFoundError:
        abort(404)
    except (ValueError, OSError) as exc:
        return _err(exc)
    return jsonify({"ok": True, "change": item})


@app.post("/api/changes/<change_id>/files/accept")
def changes_accept_file(change_id: str) -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        item = changes.accept_file(DATA_DIR, WORKSPACE, change_id, rel)
    except FileNotFoundError:
        abort(404)
    except (ValueError, OSError) as exc:
        return _err(exc)
    return jsonify({"ok": True, "change": item})


@app.post("/api/changes/<change_id>/files/reject")
def changes_reject_file(change_id: str) -> Response:
    permissions.require(DATA_DIR, "changes.apply")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        item = changes.reject_file(DATA_DIR, change_id, rel)
    except FileNotFoundError:
        abort(404)
    except ValueError as exc:
        return _err(exc)
    return jsonify({"ok": True, "change": item})


@app.post("/api/ai/run")
def ai_run() -> Response:
    permissions.require(DATA_DIR, "ai.run")
    body = request.get_json(silent=True) or {}
    try:
        result = ai_bypass.run_ai(
            data_dir=DATA_DIR,
            workspace=WORKSPACE,
            prompt=str(body.get("prompt") or ""),
            path=str(body.get("path") or ""),
        )
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return _err(exc, 400)
    return jsonify(result)


@app.get("/api/git/status")
def git_status() -> Response:
    permissions.require(DATA_DIR, "git.read")
    return jsonify(git_ops.status(WORKSPACE))


@app.get("/api/git/diff")
def git_diff() -> Response:
    permissions.require(DATA_DIR, "git.read")
    staged = request.args.get("staged") == "1"
    return jsonify(git_ops.diff(WORKSPACE, staged=staged))


@app.post("/api/git/init")
def git_init() -> Response:
    permissions.require(DATA_DIR, "git.write")
    return jsonify(git_ops.init(WORKSPACE))


@app.post("/api/git/commit")
def git_commit() -> Response:
    permissions.require(DATA_DIR, "git.write")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(git_ops.commit(WORKSPACE, str(body.get("message") or "")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/git/log")
def git_log() -> Response:
    permissions.require(DATA_DIR, "git.read")
    try:
        limit = int(request.args.get("limit") or 80)
    except (TypeError, ValueError):
        limit = 80
    try:
        return jsonify(git_ops.log_graph(WORKSPACE, limit=limit))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/git/branches")
def git_branches() -> Response:
    permissions.require(DATA_DIR, "git.read")
    return jsonify(git_ops.branches(WORKSPACE))


@app.post("/api/git/checkout")
def git_checkout() -> Response:
    permissions.require(DATA_DIR, "git.write")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            git_ops.checkout(
                WORKSPACE,
                str(body.get("name") or ""),
                create=bool(body.get("create")),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/lsp/status")
def lsp_status() -> Response:
    return jsonify(lsp_bridge.status())


@app.post("/api/lsp/diagnose")
def lsp_diagnose() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    text = body.get("text")
    if text is not None and not isinstance(text, str):
        abort(400, "text must be string")
    return jsonify(lsp_bridge.diagnose(WORKSPACE, rel, text if isinstance(text, str) else None))


@app.post("/api/lsp/complete")
def lsp_complete() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    text = body.get("text")
    if not isinstance(text, str):
        abort(400, "text must be string")
    try:
        line = int(body.get("line") or 0)
        character = int(body.get("character") or 0)
    except (TypeError, ValueError):
        abort(400, "bad position")
    return jsonify(lsp_bridge.complete(WORKSPACE, rel, text, line, character))


def _lsp_pos_body() -> tuple[str, str, int, int]:
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    text = body.get("text")
    if not isinstance(text, str):
        abort(400, "text must be string")
    try:
        line = int(body.get("line") or 0)
        character = int(body.get("character") or 0)
    except (TypeError, ValueError):
        abort(400, "bad position")
    return rel, text, line, character


@app.post("/api/lsp/definition")
def lsp_definition() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    rel, text, line, character = _lsp_pos_body()
    return jsonify(lsp_bridge.definition(WORKSPACE, rel, text, line, character))


@app.post("/api/lsp/hover")
def lsp_hover() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    rel, text, line, character = _lsp_pos_body()
    return jsonify(lsp_bridge.hover(WORKSPACE, rel, text, line, character))


@app.post("/api/lsp/rename")
def lsp_rename() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    permissions.require(DATA_DIR, "changes.apply")
    rel, text, line, character = _lsp_pos_body()
    body = request.get_json(silent=True) or {}
    try:
        result = lsp_bridge.rename(
            WORKSPACE,
            DATA_DIR,
            rel,
            text,
            line,
            character,
            str(body.get("newName") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)
    return jsonify(result)


@app.post("/api/lsp/references")
def lsp_references() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    rel, text, line, character = _lsp_pos_body()
    return jsonify(lsp_bridge.references(WORKSPACE, rel, text, line, character))


@app.post("/api/lsp/codeAction")
def lsp_code_action() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    rel, text, line, character = _lsp_pos_body()
    body = request.get_json(silent=True) or {}
    end_line = body.get("endLine")
    end_character = body.get("endCharacter")
    try:
        el = int(end_line) if end_line is not None else None
        ec = int(end_character) if end_character is not None else None
    except (TypeError, ValueError):
        abort(400, "bad range")
    diags = body.get("diagnostics")
    if diags is not None and not isinstance(diags, list):
        abort(400, "diagnostics must be list")
    return jsonify(
        lsp_bridge.code_actions(
            WORKSPACE,
            rel,
            text,
            line,
            character,
            end_line=el,
            end_character=ec,
            diagnostics=diags if isinstance(diags, list) else None,
        )
    )


@app.post("/api/lsp/codeAction/apply")
def lsp_code_action_apply() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    permissions.require(DATA_DIR, "changes.apply")
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    if not isinstance(action, dict):
        abort(400, "action required")
    overrides = body.get("openOverrides")
    if overrides is not None and not isinstance(overrides, dict):
        abort(400, "openOverrides must be object")
    clean: dict[str, str] | None = None
    if isinstance(overrides, dict):
        clean = {}
        for k, v in overrides.items():
            rel = str(k)
            _safe_under_workspace(rel)
            if isinstance(v, str):
                clean[rel] = v
    try:
        return jsonify(
            lsp_bridge.apply_code_action(
                WORKSPACE,
                DATA_DIR,
                action,
                open_overrides=clean,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/search")
def search_api() -> Response:
    permissions.require(DATA_DIR, "fs.read")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(search.search(WORKSPACE, str(body.get("query") or "")))
    except ValueError as exc:
        return _err(exc)


@app.post("/api/terminal/run")
def terminal_run() -> Response:
    permissions.require(DATA_DIR, "terminal")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(terminal.run(WORKSPACE, str(body.get("command") or "")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/terminal/pty/supported")
def terminal_pty_supported() -> Response:
    return jsonify(
        {
            "ok": True,
            "supported": pty_session.supported(),
            "backend": pty_session.backend_name(),
        }
    )


@app.post("/api/terminal/pty/start")
def terminal_pty_start() -> Response:
    permissions.require(DATA_DIR, "terminal")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            pty_session.start(
                WORKSPACE,
                cols=int(body.get("cols") or 80),
                rows=int(body.get("rows") or 24),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/terminal/pty/write")
def terminal_pty_write() -> Response:
    permissions.require(DATA_DIR, "terminal")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(pty_session.write(str(body.get("id") or ""), str(body.get("data") or "")))
    except KeyError:
        abort(404)
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/terminal/pty/read")
def terminal_pty_read() -> Response:
    permissions.require(DATA_DIR, "terminal")
    sid = request.args.get("id") or ""
    try:
        return jsonify(pty_session.read(sid))
    except KeyError:
        abort(404)


@app.post("/api/terminal/pty/resize")
def terminal_pty_resize() -> Response:
    permissions.require(DATA_DIR, "terminal")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            pty_session.resize(
                str(body.get("id") or ""),
                int(body.get("rows") or 24),
                int(body.get("cols") or 80),
            )
        )
    except KeyError:
        abort(404)
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/terminal/pty/close")
def terminal_pty_close() -> Response:
    permissions.require(DATA_DIR, "terminal")
    body = request.get_json(silent=True) or {}
    return jsonify(pty_session.close(str(body.get("id") or "")))


def _debug_sid() -> str | None:
    body = request.get_json(silent=True) or {}
    sid = body.get("sessionId") or request.args.get("sessionId")
    return str(sid) if sid else None


@app.get("/api/debug/status")
def debug_status() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify(
        debug_session.status(request.args.get("sessionId"), workspace=WORKSPACE)
    )


@app.get("/api/debug/adapters")
def debug_adapters() -> Response:
    # allow probing without enabling debug (so UI can show install hint)
    return jsonify(debug_session.adapters())


@app.post("/api/debug/breakpoints")
def debug_set_breakpoints() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    items = body.get("breakpoints")
    if items is None:
        items = body.get("lines") or []
    if not isinstance(items, list):
        abort(400, "breakpoints must be list")
    try:
        return jsonify(debug_session.set_breakpoints(rel, items))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpoints/toggle")
def debug_toggle_breakpoint() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    cond = body.get("condition")
    hit = body.get("hitCondition")
    log = body.get("logMessage")
    col = body.get("column")
    try:
        return jsonify(
            debug_session.toggle_breakpoint(
                rel,
                int(body.get("line") or 0),
                condition=None if cond is None else str(cond),
                hit_condition=None if hit is None else str(hit),
                log_message=None if log is None else str(log),
                column=None if col is None else int(col),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpoints/column")
def debug_breakpoint_column() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.set_breakpoint_column(
                rel,
                int(body.get("line") or 0),
                int(body["column"]) if body.get("column") is not None else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpoints/condition")
def debug_breakpoint_condition() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.set_breakpoint_condition(
                rel,
                int(body.get("line") or 0),
                str(body.get("condition") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpoints/hit")
def debug_breakpoint_hit() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.set_breakpoint_hit_condition(
                rel,
                int(body.get("line") or 0),
                str(body.get("hitCondition") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpoints/log")
def debug_breakpoint_log() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.set_breakpoint_log_message(
                rel,
                int(body.get("line") or 0),
                str(body.get("logMessage") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/exceptions")
def debug_exceptions_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify({"ok": True, "exceptionBreakpoints": debug_session.list_exception_breakpoints()})


@app.post("/api/debug/exceptions")
def debug_exceptions_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    filters = body.get("exceptionBreakpoints") or body
    extra = body.get("filters") if isinstance(body.get("filters"), dict) else None
    # Any non-raised/uncaught keys in filters become exceptionBreakpointFilters
    if extra is None and isinstance(filters, dict):
        extra = {k: v for k, v in filters.items() if k not in {"raised", "uncaught", "exceptionBreakpoints"}}
    return jsonify(
        debug_session.set_exception_breakpoints(
            raised=None if "raised" not in filters else bool(filters.get("raised")),
            uncaught=None if "uncaught" not in filters else bool(filters.get("uncaught")),
            filters=extra,
        )
    )


@app.get("/api/debug/pathMappings")
def debug_path_mappings_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify({"ok": True, "pathMappings": debug_session.list_path_mappings()})


@app.post("/api/debug/pathMappings")
def debug_path_mappings_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    mappings = body.get("pathMappings") or body.get("mappings") or []
    if not isinstance(mappings, list):
        abort(400, "pathMappings must be list")
    return jsonify(debug_session.set_path_mappings(mappings))


@app.post("/api/debug/disassemble")
def debug_disassemble() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.disassemble(
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
                memory_reference=str(body.get("memoryReference") or ""),
                offset=int(body.get("offset") or 0),
                count=int(body.get("count") or 64),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/memory")
def debug_memory() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        if body.get("write") or body.get("data"):
            return jsonify(
                debug_session.write_memory(
                    session_id=str(body["sessionId"]) if body.get("sessionId") else None,
                    memory_reference=str(body.get("memoryReference") or ""),
                    data=str(body.get("data") or ""),
                    offset=int(body.get("offset") or 0),
                    allow_partial=bool(body.get("allowPartial", True)),
                )
            )
        return jsonify(
            debug_session.read_memory(
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
                memory_reference=str(body.get("memoryReference") or ""),
                expression=str(body.get("expression") or ""),
                offset=int(body.get("offset") or 0),
                count=int(body.get("count") or 64),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/layout")
def debug_layout() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    return jsonify(debug_session.set_layout(body.get("layout") or body))


@app.post("/api/debug/variables")
def debug_variables_expand() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.expand_variables(
                int(body.get("variablesReference") or 0),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/watches")
def debug_watches_list() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify({"ok": True, "watches": debug_session.list_watches()})


@app.post("/api/debug/watches")
def debug_watches_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    if "expression" in body:
        try:
            return jsonify(debug_session.add_watch(str(body.get("expression") or "")))
        except Exception as exc:  # noqa: BLE001
            return _err(exc, 400)
    exprs = body.get("watches") or body.get("expressions") or []
    if not isinstance(exprs, list):
        abort(400, "watches must be list")
    return jsonify(debug_session.set_watches([str(x) for x in exprs]))


@app.post("/api/debug/watches/remove")
def debug_watches_remove() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    return jsonify(debug_session.remove_watch(str(body.get("expression") or "")))


@app.post("/api/debug/evaluate")
def debug_evaluate() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.evaluate(
                str(body.get("expression") or ""),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
                frame_id=body.get("frameId"),
                context=str(body.get("context") or "repl"),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/start")
def debug_start() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    if rel:
        _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.start(
                WORKSPACE,
                rel or None,
                config_name=str(body["configName"]) if body.get("configName") else None,
                config=body.get("config") if isinstance(body.get("config"), dict) else None,
                compound_name=str(body["compoundName"]) if body.get("compoundName") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/launch")
def debug_launch_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced, debug_launch as dl

    doc = dl.load(WORKSPACE)
    validation = debug_advanced.validate_launch_document(doc)
    return jsonify({"ok": True, **doc, "validation": validation})


@app.post("/api/debug/launch")
def debug_launch_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_launch as dl

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(dl.save(WORKSPACE, body))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/launch/validate")
def debug_launch_validate() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced, debug_launch as dl

    body = request.get_json(silent=True) or {}
    doc = body if body.get("configurations") is not None else dl.load(WORKSPACE)
    return jsonify(debug_advanced.validate_launch_document(doc))


@app.post("/api/debug/thread")
def debug_select_thread() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.select_thread(
                body.get("threadId"),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/timeline")
def debug_timeline() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    sid = str(body["sessionId"]) if body.get("sessionId") else None
    try:
        if body.get("live"):
            return jsonify(debug_session.timeline_live(session_id=sid))
        if "index" in body:
            return jsonify(debug_session.timeline_seek(int(body.get("index") or 0), session_id=sid))
        st = debug_session.status(sid, workspace=WORKSPACE)
        return jsonify({"ok": True, "timeline": (st.get("timeline") or {})})
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/attach")
def debug_attach() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    mappings = body.get("pathMappings")
    try:
        return jsonify(
            debug_session.attach(
                WORKSPACE,
                engine=str(body.get("engine") or body.get("type") or "python"),
                host=str(body.get("host") or "127.0.0.1"),
                port=int(body.get("port") or 0),
                path=str(body.get("path") or "(remote)"),
                path_mappings=mappings if isinstance(mappings, list) else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/frame")
def debug_select_frame() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.select_frame(
                body.get("frameId"),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/dataBreakpoints")
def debug_data_breakpoints_list() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify({"ok": True, "dataBreakpoints": debug_session.list_data_breakpoints()})


@app.post("/api/debug/dataBreakpoints")
def debug_data_breakpoints_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    if body.get("remove") or body.get("id") and body.get("action") == "remove":
        return jsonify(
            debug_session.remove_data_breakpoint(str(body.get("id") or body.get("name") or ""))
        )
    try:
        return jsonify(
            debug_session.add_data_breakpoint(
                str(body.get("name") or ""),
                access_type=str(body.get("accessType") or "write"),
                condition=str(body.get("condition") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/dataBreakpoints/remove")
def debug_data_breakpoints_remove() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    return jsonify(
        debug_session.remove_data_breakpoint(str(body.get("id") or body.get("name") or ""))
    )


@app.post("/api/debug/stop")
def debug_stop() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    sid = str(body["sessionId"]) if body.get("sessionId") else None
    return jsonify(debug_session.stop(sid))


@app.post("/api/debug/active")
def debug_set_active() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(debug_session.set_active(str(body.get("sessionId") or "")))
    except KeyError:
        abort(404)
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/continue")
def debug_continue() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(debug_session.cont(_debug_sid()))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/stepOver")
def debug_step_over() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(debug_session.step_over(_debug_sid()))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/stepIn")
def debug_step_in() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(debug_session.step_in(_debug_sid()))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/stepOut")
def debug_step_out() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(debug_session.step_out(_debug_sid()))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/stepBack")
def debug_step_back() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(debug_session.step_back(_debug_sid()))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/reverseContinue")
def debug_reverse_continue() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(debug_session.reverse_continue(_debug_sid()))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/completions")
def debug_completions() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.completions(
                str(body.get("text") or ""),
                int(body.get("column") or 1),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
                frame_id=body.get("frameId"),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpoints/meta")
def debug_breakpoint_meta() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.set_breakpoint_meta(
                rel,
                int(body.get("line") or 0),
                enabled=None if "enabled" not in body else bool(body.get("enabled")),
                group=None if body.get("group") is None else str(body.get("group")),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpoints/batch")
def debug_breakpoints_batch() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    return jsonify(
        debug_session.batch_breakpoints(
            enable=body.get("enable") if isinstance(body.get("enable"), list) else None,
            disable=body.get("disable") if isinstance(body.get("disable"), list) else None,
            set_group=str(body["setGroup"]) if body.get("setGroup") else None,
        )
    )


@app.post("/api/debug/breakpoints/groups")
def debug_breakpoint_groups() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    if "group" in body and "enabled" in body:
        return jsonify(
            debug_session.set_breakpoint_group_enabled(
                str(body.get("group") or "default"),
                bool(body.get("enabled")),
            )
        )
    return jsonify({"ok": True, "groups": debug_session.list_breakpoint_groups()})


@app.post("/api/debug/profile/start")
def debug_profile_start() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        sess = debug_session._need(  # noqa: SLF001
            str(body["sessionId"]) if body.get("sessionId") else None
        )
        return jsonify(sess.profile_start(str(body.get("kind") or "cpu")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/profile/stop")
def debug_profile_stop() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        sess = debug_session._need(  # noqa: SLF001
            str(body["sessionId"]) if body.get("sessionId") else None
        )
        return jsonify(sess.profile_stop(str(body.get("kind") or "cpu")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/profiles")
def debug_profiles_list() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    return jsonify({"ok": True, "profiles": debug_extras.list_profiles()})


@app.get("/api/debug/profiles/<pid>")
def debug_profile_get(pid: str) -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    try:
        return jsonify(debug_extras.get_profile(pid))
    except KeyError:
        abort(404)
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/diff")
def debug_sessions_diff() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        ids = body.get("sessionIds") if isinstance(body.get("sessionIds"), list) else None
        return jsonify(
            debug_session.sessions_var_diff(
                str(body.get("sessionA") or ""),
                str(body.get("sessionB") or ""),
                session_ids=[str(x) for x in ids] if ids else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/profiles/<pid>/speedscope")
def debug_profile_speedscope(pid: str) -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    try:
        return jsonify(debug_extras.export_speedscope(pid))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/coverage/summary")
def debug_coverage_summary() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    return jsonify(debug_extras.coverage_summary())


@app.post("/api/debug/coverage/tip")
def debug_coverage_tip() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    body = request.get_json(silent=True) or {}
    if body.get("diff"):
        try:
            return jsonify(debug_extras.coverage_diff_tip())
        except Exception as exc:  # noqa: BLE001
            return _err(exc, 400)
    return jsonify(debug_extras.save_coverage_tip())


@app.post("/api/debug/ssh/tunnel")
def debug_ssh_tunnel() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    body = request.get_json(silent=True) or {}
    if body.get("stop"):
        return jsonify(debug_extras.ssh_stop_tunnel(str(body["key"]) if body.get("key") else None))
    try:
        return jsonify(debug_extras.ssh_start_tunnel(body.get("ssh") if isinstance(body.get("ssh"), dict) else body))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/sources")
def debug_loaded_sources() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(
            debug_session.loaded_sources(
                str(request.args["sessionId"]) if request.args.get("sessionId") else None
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/session/rename")
def debug_session_rename() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.rename_child_session(
                str(body.get("sessionId") or ""),
                str(body.get("name") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/breakpoints/export")
def debug_breakpoints_export() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify(debug_session.export_breakpoints_vscode())


@app.post("/api/debug/breakpoints/import")
def debug_breakpoints_import() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.import_breakpoints_vscode(
                body if isinstance(body, dict) else {},
                merge=bool(body.get("merge", True)),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/docker/inspect")
def debug_docker_inspect() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    body = request.get_json(silent=True) or {}
    try:
        result = debug_extras.docker_path_mappings(str(body.get("container") or ""), WORKSPACE)
        if body.get("apply"):
            debug_session.set_path_mappings(result.get("pathMappings") or [])
            result["applied"] = True
            result["pathMappings"] = debug_session.list_path_mappings()
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/coverage")
def debug_coverage_run() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    if rel:
        _safe_under_workspace(rel)
    engine = str(body.get("engine") or "auto")
    try:
        if engine == "node" or (engine == "auto" and rel.endswith((".js", ".mjs", ".cjs"))):
            return jsonify(debug_extras.run_node_coverage(WORKSPACE, rel))
        return jsonify(
            debug_extras.run_python_coverage(WORKSPACE, rel, body.get("args") if isinstance(body.get("args"), list) else None)
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/coverage")
def debug_coverage_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    return jsonify(debug_extras.get_coverage())


@app.post("/api/debug/postmortem")
def debug_postmortem() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(debug_session.open_postmortem(WORKSPACE, rel))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/test")
def debug_test() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.start_test(
                WORKSPACE,
                rel,
                xdist=bool(body.get("xdist")),
                workers=str(body.get("workers") or "auto"),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/compound/stop")
def debug_compound_stop() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(debug_session.stop_compound(str(body.get("name") or "")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/gotoTargets")
def debug_goto_targets() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    if rel:
        _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.goto_targets(
                path=rel,
                line=int(body.get("line") or 0),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/goto")
def debug_goto() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    if rel:
        _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_session.goto(
                target_id=body.get("targetId"),
                path=rel,
                line=int(body.get("line") or 0),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/restartFrame")
def debug_restart_frame() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.restart_frame(
                frame_id=body.get("frameId"),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/sourcemap")
def debug_sourcemap() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    body = request.get_json(silent=True) or {}
    rel = str(body.get("path") or "")
    _safe_under_workspace(rel)
    try:
        return jsonify(
            debug_extras.resolve_sourcemap(
                WORKSPACE,
                rel,
                int(body.get("line") or 1),
                int(body.get("column") or 0),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/coverage/html")
def debug_coverage_html() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    try:
        return jsonify(debug_extras.coverage_html_report(WORKSPACE))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/profiles/<pid>/speedscope/raw")
def debug_profile_speedscope_raw(pid: str) -> Response:
    """Raw Speedscope JSON for iframe profileURL."""
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    try:
        doc = debug_extras.export_speedscope(pid)
        return Response(
            json.dumps(doc["speedscope"]),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/conditions/history")
def debug_condition_history() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify({"ok": True, "history": debug_session.list_condition_history()})


@app.get("/api/debug/skipFiles")
def debug_skip_files_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify({"ok": True, "skipFiles": debug_session.list_skip_files()})


@app.post("/api/debug/skipFiles")
def debug_skip_files_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    patterns = body.get("skipFiles") or body.get("patterns") or []
    if not isinstance(patterns, list):
        abort(400, "skipFiles must be list")
    return jsonify(debug_session.set_skip_files(patterns))


@app.post("/api/debug/setVariable")
def debug_set_variable() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.set_variable(
                variables_reference=int(body.get("variablesReference") or 0),
                name=str(body.get("name") or ""),
                value=str(body.get("value") or ""),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/setExpression")
def debug_set_expression() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.set_expression(
                expression=str(body.get("expression") or ""),
                value=str(body.get("value") or ""),
                frame_id=body.get("frameId"),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/breakpointLocations")
def debug_breakpoint_locations() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.breakpoint_locations(
                path=str(body.get("path") or ""),
                line=int(body.get("line") or 1),
                end_line=int(body["endLine"]) if body.get("endLine") is not None else None,
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/dataBreakpointInfo")
def debug_data_breakpoint_info() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.data_breakpoint_info(
                str(body.get("name") or ""),
                frame_id=body.get("frameId"),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/events")
def debug_events_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    sid = request.args.get("sessionId")
    return jsonify(debug_session.session_events(session_id=sid))


@app.post("/api/debug/events")
def debug_events_post() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    return jsonify(
        debug_session.session_events(
            session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            clear=bool(body.get("clear")),
        )
    )


@app.get("/api/debug/watchGroups")
def debug_watch_groups_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    return jsonify({"ok": True, "watchGroups": debug_session.list_watch_groups()})


@app.post("/api/debug/watchGroups")
def debug_watch_groups_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    groups = body.get("watchGroups") or body.get("groups") or {}
    if not isinstance(groups, dict):
        abort(400, "watchGroups must be object")
    if body.get("expression"):
        return jsonify(
            debug_session.add_watch_to_group(
                str(body.get("expression") or ""),
                str(body.get("group") or "default"),
            )
        )
    return jsonify(debug_session.set_watch_groups(groups))


@app.post("/api/debug/pathMappings/multiRoot")
def debug_path_mappings_multi_root() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    roots = body.get("roots") or body.get("folders") or None
    try:
        return jsonify(debug_session.sync_multi_root_mappings(WORKSPACE, roots=roots))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/ports/scan")
def debug_ports_scan() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_advanced.scan_attach_ports(
                str(body.get("host") or "127.0.0.1"),
                start=int(body.get("start") or 5678),
                end=int(body.get("end") or 5688),
                extra=body.get("extra") if isinstance(body.get("extra"), list) else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/logpointTemplates")
def debug_logpoint_templates_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    return jsonify(debug_advanced.load_logpoint_templates(WORKSPACE))


@app.post("/api/debug/logpointTemplates")
def debug_logpoint_templates_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    body = request.get_json(silent=True) or {}
    templates = body.get("templates") or []
    if not isinstance(templates, list):
        abort(400, "templates must be list")
    return jsonify(debug_advanced.save_logpoint_templates(WORKSPACE, templates))


@app.get("/api/debug/otel/spans")
def debug_otel_spans() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    return jsonify(debug_advanced.otel_list_spans(WORKSPACE, limit=int(request.args.get("limit") or 80)))


@app.post("/api/debug/otel/span")
def debug_otel_span_record() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    body = request.get_json(silent=True) or {}
    return jsonify(
        debug_advanced.otel_record_span(
            WORKSPACE,
            name=str(body.get("name") or "debug.manual"),
            session_id=str(body.get("sessionId") or ""),
            attributes=body.get("attributes") if isinstance(body.get("attributes"), dict) else None,
        )
    )


@app.post("/api/debug/wasm/dwarf")
def debug_wasm_dwarf() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(debug_advanced.wasm_dwarf_info(WORKSPACE, str(body.get("path") or "")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/core/symbols")
def debug_core_symbols() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    body = request.get_json(silent=True) or {}
    frames = body.get("frames") or []
    if not isinstance(frames, list):
        frames = []
    return jsonify(
        debug_advanced.enhance_core_symbols(
            WORKSPACE,
            frames,
            binary=str(body.get("binary") or ""),
            addresses=body.get("addresses") if isinstance(body.get("addresses"), list) else None,
        )
    )


@app.get("/api/debug/jupyter/config")
def debug_jupyter_config() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_advanced

    port = int(request.args.get("port") or 5678)
    return jsonify({"ok": True, "config": debug_advanced.jupyter_launch_config(WORKSPACE, port=port)})


@app.get("/api/debug/modules")
def debug_modules() -> Response:
    permissions.require(DATA_DIR, "debug")
    try:
        return jsonify(
            debug_session.list_modules(
                session_id=request.args.get("sessionId"),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/hotReload")
def debug_hot_reload() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.hot_reload(
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
                module=str(body.get("module") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/instructionBreakpoints")
def debug_instruction_bps_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify({"ok": True, "instructionBreakpoints": debug_features.list_instruction_breakpoints()})


@app.post("/api/debug/instructionBreakpoints")
def debug_instruction_bps_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    if body.get("remove"):
        out = debug_features.remove_instruction_breakpoint(str(body.get("id") or body.get("remove") or ""))
    elif body.get("instructionReference") or body.get("address"):
        out = debug_features.add_instruction_breakpoint(
            str(body.get("instructionReference") or body.get("address") or ""),
            offset=int(body.get("offset") or 0),
            condition=str(body.get("condition") or ""),
        )
    else:
        out = debug_features.set_instruction_breakpoints(body.get("breakpoints") or [])
    try:
        debug_session.apply_instruction_breakpoints(
            session_id=str(body["sessionId"]) if body.get("sessionId") else None
        )
    except Exception:
        pass
    return jsonify(out)


@app.get("/api/debug/varHistory")
def debug_var_history() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(
        debug_features.var_history(
            request.args.get("sessionId"),
            limit=int(request.args.get("limit") or 40),
        )
    )


@app.get("/api/debug/bpHits")
def debug_bp_hits() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(debug_features.bp_hit_stats())


@app.post("/api/debug/bpHits/clear")
def debug_bp_hits_clear() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(debug_features.clear_bp_hits())


@app.post("/api/debug/suggestCondition")
def debug_suggest_condition() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    vars_ = body.get("variables") if isinstance(body.get("variables"), list) else None
    return jsonify(
        debug_features.suggest_conditions(
            path=str(body.get("path") or ""),
            line=int(body.get("line") or 0),
            variables=vars_,
        )
    )


@app.post("/api/debug/otel/export")
def debug_otel_export() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    return jsonify(
        debug_features.otlp_export(
            WORKSPACE,
            endpoint=str(body.get("endpoint") or ""),
        )
    )


@app.get("/api/debug/chrome/dwarfInject")
def debug_chrome_dwarf_inject() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(debug_features.chrome_dwarf_inject_snippet(WORKSPACE))


@app.get("/api/debug/subprocessMatrix")
def debug_subprocess_matrix() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    st = debug_session.status()
    return jsonify(debug_features.subprocess_attach_matrix(st.get("sessions") or []))


@app.get("/api/debug/ssh/tunnels")
def debug_ssh_tunnels() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    return jsonify(debug_extras.ssh_list_tunnels())


@app.get("/api/debug/compounds/graph")
def debug_compounds_graph() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features, debug_launch as dl

    return jsonify(debug_features.compounds_graph(dl.load(WORKSPACE)))


@app.post("/api/debug/notebook/cells")
def debug_notebook_cells() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(debug_features.notebook_cells(WORKSPACE, str(body.get("path") or "")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/notebook/cell")
def debug_notebook_cell() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_features.notebook_cell_source(
                WORKSPACE,
                str(body.get("path") or ""),
                int(body.get("cellIndex") or 0),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/hardwareWatch")
def debug_hardware_watch() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_extras.gdb_hardware_watch(
                str(body.get("expression") or ""),
                access=str(body.get("access") or "write"),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/replay/start")
def debug_replay_start() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.start_session_recording(
                WORKSPACE,
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/replay/stop")
def debug_replay_stop() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    return jsonify(
        debug_session.stop_session_recording(
            session_id=str(body["sessionId"]) if body.get("sessionId") else None,
        )
    )


@app.get("/api/debug/replay")
def debug_replay_list() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(debug_features.list_recordings(WORKSPACE))


@app.post("/api/debug/replay/load")
def debug_replay_load() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    try:
        data = debug_features.load_recording(WORKSPACE, str(body.get("id") or body.get("replayId") or ""))
        # Open as postmortem-style session
        return jsonify(debug_session.open_postmortem_from_data(WORKSPACE, data))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/readonly")
def debug_readonly_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    return jsonify(debug_session.set_readonly_attach(bool(body.get("readonly") or body.get("enabled"))))


@app.post("/api/debug/stepInTargets")
def debug_step_in_targets() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.step_in_targets(
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
                frame_id=body.get("frameId"),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/stepInTarget")
def debug_step_in_target() -> Response:
    permissions.require(DATA_DIR, "debug")
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_session.step_in_with_target(
                target_id=body.get("targetId"),
                session_id=str(body["sessionId"]) if body.get("sessionId") else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/functionBreakpoints")
def debug_function_bps_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify({"ok": True, "functionBreakpoints": debug_features.list_function_breakpoints()})


@app.post("/api/debug/functionBreakpoints")
def debug_function_bps_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    names = body.get("breakpoints") or body.get("names") or body.get("functions") or []
    if body.get("name") and not names:
        names = [body]
    out = debug_features.set_function_breakpoints(names if isinstance(names, list) else [])
    # Apply to active session
    sess = debug_session._get(debug_session._ACTIVE_ID, require_alive=False)  # noqa: SLF001
    if sess and sess.alive and hasattr(sess, "apply_function_breakpoints"):
        try:
            sess.apply_function_breakpoints()  # type: ignore[attr-defined]
        except Exception:
            pass
    return jsonify(out)


@app.get("/api/debug/pins")
def debug_pins_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify({"ok": True, "pinned": debug_features.list_pinned_vars()})


@app.post("/api/debug/pins")
def debug_pins_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    if body.get("remove"):
        return jsonify(debug_features.unpin_variable(str(body.get("remove") or body.get("id") or "")))
    return jsonify(
        debug_features.pin_variable(str(body.get("expression") or ""), label=str(body.get("label") or ""))
    )


@app.post("/api/debug/liveShare/publish")
def debug_live_share_publish() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    st = debug_session.status(str(body["sessionId"]) if body.get("sessionId") else None)
    return jsonify(debug_features.live_share_publish(st, room=str(body.get("room") or "")))


@app.get("/api/debug/liveShare/<room>")
def debug_live_share_join(room: str) -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    try:
        return jsonify(debug_features.live_share_join(room))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 404)


@app.get("/api/debug/liveShare")
def debug_live_share_list() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(debug_features.live_share_list())


@app.get("/api/debug/platform")
def debug_platform_catalog() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_platform

    return jsonify(debug_platform.catalog_summary(WORKSPACE))


@app.post("/api/debug/extensions/install")
def debug_extension_install() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_platform

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_platform.install_extension_stub(
                WORKSPACE,
                str(body.get("id") or ""),
                label=str(body.get("label") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/extensions")
def debug_extensions_list() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_platform

    return jsonify(debug_platform.list_extensions(WORKSPACE))


@app.post("/api/debug/vault")
def debug_vault_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_features.vault_set(WORKSPACE, str(body.get("key") or ""), str(body.get("value") or ""))
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/vault")
def debug_vault_list() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    secrets = debug_features.vault_load(WORKSPACE)
    return jsonify({"ok": True, "keys": sorted(secrets.keys())})


@app.post("/api/debug/breakpoints/merge")
def debug_breakpoints_merge() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    local = body.get("local") or debug_session.list_breakpoints()
    remote = body.get("remote") or {}
    out = debug_features.merge_breakpoints(
        local, remote, strategy=str(body.get("strategy") or "union")
    )
    if body.get("apply"):
        for path, bps in (out.get("breakpoints") or {}).items():
            try:
                debug_session.set_breakpoints(path, bps)
            except Exception:
                pass
    return jsonify(out)


@app.post("/api/debug/triage")
def debug_triage() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    st = debug_session.status()
    return jsonify(
        debug_features.triage_report(
            WORKSPACE,
            session=st,
            postmortem=st.get("postmortem") if isinstance(st.get("postmortem"), dict) else None,
        )
    )


@app.post("/api/debug/suggestCondition/llm")
def debug_suggest_condition_llm() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    # Prefer ai.run when calling real model
    allow = bool(body.get("allowNetwork"))
    if allow:
        try:
            permissions.require(DATA_DIR, "ai.run", "network")
        except Exception:
            allow = False
    code = ""
    path = str(body.get("path") or "")
    if path:
        try:
            p = (WORKSPACE / path).resolve()
            p.relative_to(WORKSPACE.resolve())
            if p.is_file():
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                ln = max(1, int(body.get("line") or 1))
                code = "\n".join(lines[max(0, ln - 8) : ln + 8])
        except Exception:
            code = ""
    return jsonify(
        debug_features.suggest_conditions_llm(
            path=path,
            line=int(body.get("line") or 0),
            code_context=code,
            failure=str(body.get("failure") or ""),
            variables=body.get("variables") if isinstance(body.get("variables"), list) else None,
            allow_network=allow,
        )
    )


@app.get("/api/debug/tracepoints")
def debug_tracepoints_query() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(
        debug_features.query_tracepoints(
            q=str(request.args.get("q") or ""),
            path=str(request.args.get("path") or ""),
            limit=int(request.args.get("limit") or 80),
        )
    )


@app.post("/api/debug/profile/budget")
def debug_profile_budget() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_extras, debug_features

    body = request.get_json(silent=True) or {}
    pid = str(body.get("id") or body.get("profileId") or "")
    profile = {}
    if pid:
        try:
            profile = debug_extras.get_profile(pid) or {}
        except Exception:
            profile = body.get("profile") or {}
    else:
        profile = body.get("profile") or {}
    return jsonify(
        debug_features.profile_budget_check(
            WORKSPACE,
            profile if isinstance(profile, dict) else {},
            budget_ms=float(body.get("budgetMs") or 100),
            budget_self_pct=float(body.get("budgetSelfPct") or 40),
        )
    )


@app.get("/api/debug/catchpoints")
def debug_catchpoints_get() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(debug_features.get_catchpoints())


@app.post("/api/debug/catchpoints")
def debug_catchpoints_set() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    return jsonify(
        debug_features.set_catchpoints(
            throw=None if "throw" not in body else bool(body.get("throw")),
            signals=body.get("signals") if isinstance(body.get("signals"), list) else None,
        )
    )


@app.post("/api/debug/replay/diff")
def debug_replay_diff() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            debug_features.diff_replays(
                WORKSPACE,
                str(body.get("a") or body.get("left") or ""),
                str(body.get("b") or body.get("right") or ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.post("/api/debug/sbom")
def debug_sbom_load() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    body = request.get_json(silent=True) or {}
    try:
        return jsonify(debug_features.load_sbom(WORKSPACE, str(body.get("path") or "")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc, 400)


@app.get("/api/debug/sab")
def debug_shared_array_buffer() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    return jsonify(debug_features.shared_array_buffer_hint())


@app.get("/api/debug/rr/scrub")
def debug_rr_scrub() -> Response:
    permissions.require(DATA_DIR, "debug")
    from editor import debug_features

    st = debug_session.status(request.args.get("sessionId"))
    return jsonify(debug_features.rr_scrub_state(st))


@app.get("/favicon.ico")
def favicon() -> Response:
    return send_from_directory(app.static_folder, "favicon.ico")


atexit.register(lsp_client.shutdown_all)
atexit.register(debug_session.shutdown)


def main() -> None:
    if not DESKTOP:
        print("ZINTRIQ_DESKTOP=1 required for the editor host", file=sys.stderr)
        sys.exit(2)
    if len(TOKEN) < MIN_TOKEN_LENGTH:
        print("ZINTRIQ_DESKTOP_TOKEN missing or too short", file=sys.stderr)
        sys.exit(2)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    workspace_bootstrap.seed_workspace(WORKSPACE)
    host = "127.0.0.1"
    port = int(os.environ.get("PORT") or "8765")
    print(f"ZINTRIQ_READY pid={os.getpid()} port={port}", flush=True)
    try:
        from waitress import serve

        serve(app, host=host, port=port, ident=None, threads=4)
    except ImportError:
        app.run(host=host, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
