"""Shared Flask session helpers for Builder HTTP tests. Not a TestCase module."""

from __future__ import annotations

import uuid


def login_editor(client, app_module):
    email = f"builder-http-{uuid.uuid4().hex[:12]}@example.com"
    with app_module.db() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, 'merchant')",
            (email, "x"),
        )
        user_id = int(cur.lastrowid)
    from universal_builder_core import ensure_studio_workspace_for_user

    ensure_studio_workspace_for_user(user_id)
    with app_module.db() as conn:
        row = conn.execute(
            "SELECT workspace_id FROM workspace_members WHERE user_id=? AND status='active' ORDER BY id LIMIT 1",
            (user_id,),
        ).fetchone()
        workspace_id = int(row["workspace_id"])
    csrf = "csrf-builder-http"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = csrf
        sess["active_workspace_id"] = workspace_id
    return user_id, workspace_id, csrf


def auth_headers(csrf: str) -> dict:
    return {"X-CSRF-Token": csrf, "Content-Type": "application/json"}
