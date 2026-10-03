"""Zintriq Studio surface — desktop/native composition shell, isolated from web Community.

Web owns: Community, marketing, published runtimes, account UX.
Studio owns: Project composition (Data / Interface / Logic / Connection / Publish).
Same Auth0/user identity; Studio may authenticate via session cookie OR Bearer API token.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import urllib.error
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

from flask import g, jsonify, redirect, render_template, request, session, url_for

_log = logging.getLogger("app.studio")

# Product surfaces (contracts — not modules)
SURFACE_WEB = "web"
SURFACE_STUDIO = "studio"
SURFACE_COMMUNITY = "community"

PRIMITIVES = ("data", "interface", "logic", "connection", "publish")

DEFAULT_DEEP_LINK_SCHEME = "zintriq"

STUDIO_TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT 'Studio',
    prefix TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT '["studio"]',
    last_used_at TEXT,
    expires_at TEXT,
    revoked_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_studio_api_tokens_user ON studio_api_tokens(user_id);
"""


def deep_link_scheme() -> str:
    return (os.environ.get("STUDIO_DEEP_LINK_SCHEME") or DEFAULT_DEEP_LINK_SCHEME).strip() or DEFAULT_DEEP_LINK_SCHEME


def community_path(package_id: str | None = None) -> str:
    if package_id:
        return f"/app/community?{urlencode({'package': package_id})}"
    return "/app/community"


def studio_home_path(install: str | None = None) -> str:
    if install:
        return f"/studio?{urlencode({'install': install})}"
    return "/studio"


def studio_project_path(project_id: int) -> str:
    return f"/studio/p/{int(project_id)}"


def studio_deep_link(*, action: str = "open", package_id: str | None = None, project_id: int | None = None) -> str:
    q: dict[str, str] = {"action": action}
    if package_id:
        q["package"] = package_id
    if project_id is not None:
        q["project"] = str(int(project_id))
    return f"{deep_link_scheme()}://studio?{urlencode(q)}"


def handoff_payload(*, package_id: str | None = None, project_id: int | None = None) -> dict:
    """URLs for Community (web) ↔ Studio (app) handoff without embedding Community in the app."""
    install = (package_id or "").strip() or None
    return {
        "surface_web": SURFACE_WEB,
        "surface_studio": SURFACE_STUDIO,
        "surface_community": SURFACE_COMMUNITY,
        "community_url": community_path(install),
        "studio_url": studio_project_path(project_id) if project_id else studio_home_path(install),
        "deep_link": studio_deep_link(action="install" if install else "open", package_id=install, project_id=project_id),
        "primitives": list(PRIMITIVES),
        "note": "Community and the project editor open in the desktop app. Same user identity.",
    }


def init_studio_tables(conn) -> None:
    conn.executescript(STUDIO_TOKEN_SCHEMA)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_studio_token(conn, user_id: int, *, name: str = "Studio", days: int = 90) -> tuple[str, dict]:
    raw = f"zst_{secrets.token_urlsafe(32)}"
    prefix = raw[:10]
    expires = (datetime.utcnow() + timedelta(days=max(1, min(days, 365)))).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """INSERT INTO studio_api_tokens (user_id, token_hash, name, prefix, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (int(user_id), _hash_token(raw), (name or "Studio")[:80], prefix, expires),
    )
    meta = {
        "id": int(cur.lastrowid),
        "name": (name or "Studio")[:80],
        "prefix": prefix,
        "expires_at": expires,
    }
    return raw, meta


def revoke_studio_token(conn, user_id: int, token_id: int) -> bool:
    cur = conn.execute(
        """UPDATE studio_api_tokens SET revoked_at=CURRENT_TIMESTAMP
           WHERE id=? AND user_id=? AND revoked_at IS NULL""",
        (int(token_id), int(user_id)),
    )
    return cur.rowcount > 0


def lookup_studio_token_user(conn, raw_token: str):
    token = (raw_token or "").strip()
    if not token.startswith("zst_"):
        return None
    row = conn.execute(
        """SELECT t.id AS token_id, t.user_id, u.email, u.account_kind
           FROM studio_api_tokens t
           JOIN users u ON u.id = t.user_id
           WHERE t.token_hash=? AND t.revoked_at IS NULL
             AND (t.expires_at IS NULL OR t.expires_at > CURRENT_TIMESTAMP)""",
        (_hash_token(token),),
    ).fetchone()
    if not row:
        return None
    conn.execute(
        "UPDATE studio_api_tokens SET last_used_at=CURRENT_TIMESTAMP WHERE id=?",
        (row["token_id"],),
    )
    return {"id": int(row["user_id"]), "email": row["email"], "auth": "studio_token"}


def extract_bearer_token() -> str | None:
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return (request.headers.get("X-Studio-Token") or "").strip() or None


def load_studio_bearer_user() -> None:
    """before_request: resolve Bearer studio token into g.studio_bearer_user."""
    g.studio_bearer_user = None
    raw = extract_bearer_token()
    if not raw:
        return
    from app import db
    from customer_account_platform import is_shopper_only_user

    with db() as conn:
        user = lookup_studio_token_user(conn, raw)
        if not user:
            return
        row = conn.execute("SELECT id, email, account_kind FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or is_shopper_only_user(conn, row):
            return
        g.studio_bearer_user = {"id": int(row["id"]), "email": row["email"], "auth": "studio_token"}


def request_has_studio_bearer() -> bool:
    return bool(getattr(g, "studio_bearer_user", None))


def studio_login_required(view):
    """Like login_required but accepts Studio Bearer tokens (JSON 401, no HTML redirect)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        from app import current_user

        user = current_user()
        if not user:
            if request_has_studio_bearer() or request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def register_studio_platform(app) -> None:
    from app import current_user, db, login_required

    @app.get("/studio/desktop")
    def studio_desktop_gate():
        """Public Electron entry — Auth0 Native PKCE, no session cookie required."""
        user = current_user()
        if user:
            from desktop.server_mode import desktop_enabled

            if desktop_enabled():
                return redirect(studio_home_path())
            return redirect(url_for("account"))
        return render_template("studio/desktop_gate.html")

    @app.get("/studio")
    @login_required
    def studio_home():
        # Reuse project dashboard; Studio is the product chrome, not Workspace modules.
        from universal_builder_core import ensure_studio_workspace_for_user

        user = current_user()
        needs_setup = ensure_studio_workspace_for_user(user["id"])
        from app import workspace_snapshot

        return render_template(
            "workspace_dashboard.html",
            page_title="Studio",
            workspace=workspace_snapshot(user["id"]),
            needs_workspace_setup=needs_setup,
            studio_mode=True,
            studio_base="/studio",
        )

    @app.get("/studio/p/<int:project_id>")
    @login_required
    def studio_editor(project_id: int):
        user = current_user()
        with db() as conn:
            project = conn.execute("SELECT * FROM builder_projects WHERE id=?", (project_id,)).fetchone()
            if not project:
                from flask import abort

                abort(404)
            member = conn.execute(
                """SELECT 1 FROM workspace_members
                   WHERE workspace_id=? AND user_id=? AND status='active'""",
                (int(project["workspace_id"]), int(user["id"])),
            ).fetchone()
            if not member:
                from flask import abort

                abort(403)
            session["active_workspace_id"] = int(project["workspace_id"])
        return render_template(
            "builder/editor.html",
            page_title=project["name"],
            project_id=project_id,
            studio_mode=True,
            studio_base="/studio",
            community_url=community_path(),
        )

    @app.get("/api/studio/surfaces")
    def api_studio_surfaces():
        return jsonify(
            {
                "surfaces": {
                    SURFACE_WEB: {"owns": ["marketing", "account", "published_runtimes"]},
                    SURFACE_COMMUNITY: {"path": "/app/community", "owns": ["discover", "import_handoff"]},
                    SURFACE_STUDIO: {
                        "path": "/studio",
                        "owns": list(PRIMITIVES),
                        "deep_link_scheme": deep_link_scheme(),
                    },
                },
                "primitives": list(PRIMITIVES),
            }
        )

    @app.get("/api/studio/handoff")
    def api_studio_handoff():
        package_id = (request.args.get("package") or "").strip() or None
        project_raw = request.args.get("project")
        project_id = int(project_raw) if project_raw and str(project_raw).isdigit() else None
        return jsonify(handoff_payload(package_id=package_id, project_id=project_id))

    @app.get("/api/studio/me")
    def api_studio_me():
        user = current_user()
        if not user:
            return jsonify({"ok": False, "error": "Authentication required"}), 401
        return jsonify(
            {
                "ok": True,
                "user": {"id": user["id"], "email": user["email"]},
                "auth": user.get("auth") or ("studio_token" if request_has_studio_bearer() else "session"),
                "studio_home": studio_home_path(),
                "community_url": community_path(),
            }
        )

    @app.post("/api/studio/tokens")
    @login_required
    def api_studio_create_token():
        if request_has_studio_bearer():
            return jsonify({"ok": False, "error": "Create tokens from a browser session"}), 403
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "Studio").strip()[:80]
        days = int(data.get("days") or 90)
        user = current_user()
        with db() as conn:
            raw, meta = create_studio_token(conn, user["id"], name=name, days=days)
        _log.info("studio_token_created user_id=%s prefix=%s", user["id"], meta["prefix"])
        return jsonify({"ok": True, "token": raw, "token_meta": meta, "hint": "Store once — shown only now."})

    @app.get("/api/studio/tokens")
    @login_required
    def api_studio_list_tokens():
        user = current_user()
        with db() as conn:
            rows = conn.execute(
                """SELECT id, name, prefix, last_used_at, expires_at, created_at, revoked_at
                   FROM studio_api_tokens WHERE user_id=? ORDER BY id DESC""",
                (user["id"],),
            ).fetchall()
        return jsonify(
            {
                "tokens": [
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "prefix": r["prefix"],
                        "last_used_at": r["last_used_at"],
                        "expires_at": r["expires_at"],
                        "created_at": r["created_at"],
                        "revoked": bool(r["revoked_at"]),
                    }
                    for r in rows
                ]
            }
        )

    @app.delete("/api/studio/tokens/<int:token_id>")
    @login_required
    def api_studio_revoke_token(token_id: int):
        user = current_user()
        with db() as conn:
            ok = revoke_studio_token(conn, user["id"], token_id)
        if not ok:
            return jsonify({"ok": False, "error": "Token not found"}), 404
        return jsonify({"ok": True})

    @app.post("/api/studio/auth/pkce/exchange")
    def api_studio_pkce_exchange():
        """Desktop Auth0 Native PKCE → Studio API token (no CSRF; public client)."""
        from app import upsert_user_from_auth_claims
        from integrations.auth.auth0_provider import Auth0AuthProvider

        data = request.get_json(silent=True) or {}
        code = (data.get("code") or "").strip()
        verifier = (data.get("code_verifier") or "").strip()
        redirect_uri = (data.get("redirect_uri") or "").strip()
        if not code or not verifier or not redirect_uri:
            return jsonify({"ok": False, "error": "code, code_verifier, and redirect_uri required"}), 400
        if not redirect_uri.startswith("zintriq://"):
            return jsonify({"ok": False, "error": "redirect_uri must use zintriq:// for Studio"}), 400

        provider = Auth0AuthProvider()
        if not provider.domain or not (os.environ.get("AUTH0_NATIVE_CLIENT_ID") or provider.client_id):
            return jsonify({"ok": False, "error": "Auth0 Native is not configured on the server"}), 503

        try:
            token_data = provider.exchange_code_pkce(
                code=code,
                code_verifier=verifier,
                redirect_uri=redirect_uri,
            )
            claims = provider.claims_from_token_response(token_data)
        except (ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
            _log.warning("studio_pkce_exchange_failed error=%s", str(exc)[:160])
            return jsonify({"ok": False, "error": "Could not complete sign-in"}), 401

        with db() as conn:
            user_id = upsert_user_from_auth_claims(conn, claims)
            raw, meta = create_studio_token(conn, user_id, name="Desktop Studio", days=90)
            row = conn.execute("SELECT id, email FROM users WHERE id=?", (user_id,)).fetchone()
        return jsonify(
            {
                "ok": True,
                "token": raw,
                "token_meta": meta,
                "user": {"id": int(row["id"]), "email": row["email"]},
            }
        )

    @app.get("/api/studio/download/<platform>")
    def api_studio_download(platform: str):
        """Redirect to configured installer URLs for the marketing download page."""
        key = {
            "mac": "STUDIO_DOWNLOAD_MAC_URL",
            "macos": "STUDIO_DOWNLOAD_MAC_URL",
            "darwin": "STUDIO_DOWNLOAD_MAC_URL",
            "win": "STUDIO_DOWNLOAD_WIN_URL",
            "windows": "STUDIO_DOWNLOAD_WIN_URL",
            "linux": "STUDIO_DOWNLOAD_LINUX_URL",
        }.get((platform or "").strip().lower())
        if not key:
            return jsonify({"ok": False, "error": "Unknown platform"}), 404
        url = (os.environ.get(key) or "").strip()
        if not url:
            return redirect(url_for("marketing_download", pending=platform))
        return redirect(url)
