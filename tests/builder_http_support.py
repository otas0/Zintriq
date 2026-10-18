"""Shared Flask helpers for Builder HTTP tests. Not a TestCase module.

Builder / Application routes are desktop-only. Web tests must not call them.
"""

from __future__ import annotations

import os
import uuid

APPLICATION_TOKEN = "a" * 32 + "application-test-token"


def enable_application_host() -> None:
    os.environ["ZINTRIQ_DESKTOP"] = "1"
    os.environ["ZINTRIQ_DESKTOP_TOKEN"] = APPLICATION_TOKEN
    os.environ["PORT"] = os.environ.get("PORT") or "5001"
    # Full Workbench for existing suite; MVP AI Builder tests set this to 1 explicitly.
    os.environ.setdefault("ZINTRIQ_MVP_AI_BUILDER", "0")


def disable_application_host() -> None:
    os.environ.pop("ZINTRIQ_DESKTOP", None)
    os.environ.pop("ZINTRIQ_DESKTOP_TOKEN", None)
    os.environ.pop("ZINTRIQ_MVP_AI_BUILDER", None)


def application_client(app):
    """Flask test client that presents the desktop Application token."""
    enable_application_host()
    client = app.test_client()
    port = os.environ.get("PORT") or "5001"
    token = os.environ.get("ZINTRIQ_DESKTOP_TOKEN") or APPLICATION_TOKEN
    client.environ_base["HTTP_HOST"] = f"localhost:{port}"
    client.environ_base["REMOTE_ADDR"] = "127.0.0.1"
    original_open = client.open

    def open_with_desktop(*args, **kwargs):
        host = f"localhost:{port}"
        headers = dict(kwargs.pop("headers", None) or {})
        headers["X-Zintriq-Desktop-Token"] = token
        headers["Host"] = host
        kwargs["headers"] = headers
        extra = dict(client.environ_base)
        extra.update(kwargs.pop("environ_base", None) or {})
        extra["REMOTE_ADDR"] = extra.get("REMOTE_ADDR") or "127.0.0.1"
        extra["HTTP_HOST"] = host
        kwargs["environ_base"] = extra
        return original_open(*args, **kwargs)

    client.open = open_with_desktop
    return client


def login_editor(client, app_module):
    from desktop.server_mode import desktop_enabled, ensure_local_owner

    if desktop_enabled():
        with app_module.db() as conn:
            user_id, workspace_id = ensure_local_owner(conn)
        csrf = "csrf-builder-http"
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["csrf_token"] = csrf
            sess["active_workspace_id"] = workspace_id
        return user_id, workspace_id, csrf
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
