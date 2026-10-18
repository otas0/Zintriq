"""Stage 2: desktop signs in with the existing Flask account (PKCE, not Auth0)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

from flask import abort, jsonify, redirect, render_template, request, session, url_for

from desktop.server_mode import desktop_enabled

CLIENT_ID = "zintriq-desktop"
REDIRECT_URI = "zintriq://auth/callback"
_TTL_SEC = 600
_SESSION_TTL_SEC = 30 * 24 * 3600


def reset_for_tests() -> None:
    from app import db

    with db() as conn:
        ensure_schema(conn)
        conn.execute("DELETE FROM desktop_auth_pending")
        conn.execute("DELETE FROM desktop_auth_codes")
        conn.execute("DELETE FROM desktop_app_sessions")
        try:
            from desktop_cloud import reset_cloud_for_tests

            reset_cloud_for_tests(conn)
        except ImportError:
            pass


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(str(verifier or "").encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_auth_pending (
            state TEXT PRIMARY KEY,
            challenge TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            device_name TEXT,
            os TEXT,
            version TEXT,
            expires_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_auth_codes (
            code TEXT PRIMARY KEY,
            challenge TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            email TEXT,
            device_name TEXT,
            os TEXT,
            version TEXT,
            expires_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_app_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            device_name TEXT NOT NULL,
            os TEXT,
            app_version TEXT,
            created_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            revoked_at REAL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_desktop_app_sessions_user ON desktop_app_sessions(user_id, revoked_at)"
    )


def revoke_all_desktop_sessions(conn, user_id: int) -> None:
    ensure_schema(conn)
    conn.execute(
        "UPDATE desktop_app_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (time.time(), int(user_id)),
    )


def list_desktop_devices(conn, user_id: int) -> list[dict[str, Any]]:
    ensure_schema(conn)
    now = time.time()
    rows = conn.execute(
        """
        SELECT id, device_name, os, app_version, last_seen_at
        FROM desktop_app_sessions
        WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?
        ORDER BY last_seen_at DESC
        """,
        (int(user_id), now),
    ).fetchall()
    devices = []
    for row in rows:
        devices.append(
            {
                "id": int(row["id"]),
                "device_name": row["device_name"] or "Computer",
                "os": row["os"] or "",
                "app_version": row["app_version"] or "",
                "last_seen": time.strftime("%Y-%m-%d %H:%M", time.gmtime(float(row["last_seen_at"]))),
            }
        )
    return devices


def _clean(value: str, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _conn():
    from app import db

    return db()


def _purge(conn, now: float) -> None:
    ensure_schema(conn)
    conn.execute("DELETE FROM desktop_auth_pending WHERE expires_at < ?", (now,))
    conn.execute("DELETE FROM desktop_auth_codes WHERE expires_at < ?", (now,))


def register_desktop_account(app) -> None:
    from app import current_user, login_required

    @app.get("/desktop/authorize")
    def desktop_authorize():
        if desktop_enabled():
            abort(404)
        pending = _load_pending(create=True)
        if isinstance(pending, str):
            return render_template("desktop_authorize_result.html", status="invalid"), 400
        session["desktop_auth_state"] = pending["state"]
        user = current_user()
        if not user:
            return redirect(url_for("login", next=nxt_from_request(), **{"from": "desktop"}))
        return render_template(
            "desktop_authorize.html",
            email=user.get("email") or "",
            device_name=pending.get("device_name") or "Zintriq",
            device_os=pending.get("os") or "",
            app_version=pending.get("version") or "",
            resume=nxt_from_request(),
        )

    @app.post("/desktop/authorize")
    @login_required
    def desktop_authorize_submit():
        if desktop_enabled():
            abort(404)
        state = str(session.get("desktop_auth_state") or "")
        with _conn() as conn:
            ensure_schema(conn)
            pending = conn.execute(
                "SELECT * FROM desktop_auth_pending WHERE state = ?",
                (state,),
            ).fetchone()
        if pending is None:
            return render_template("desktop_authorize_result.html", status="invalid"), 400
        decision = str(request.form.get("decision") or "").strip()
        if decision == "switch":
            session.pop("user_id", None)
            nxt = _safe_authorize_next(request.form.get("resume"))
            return redirect(url_for("login", next=nxt, **{"from": "desktop"}))
        if decision != "allow":
            with _conn() as conn:
                conn.execute("DELETE FROM desktop_auth_pending WHERE state = ?", (state,))
            return redirect(url_for("desktop_authorize_denied"))
        user = current_user()
        if not user:
            return render_template("desktop_authorize_result.html", status="invalid"), 400
        code = secrets.token_urlsafe(32)
        now = time.time()
        with _conn() as conn:
            ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO desktop_auth_codes
                (code, challenge, redirect_uri, user_id, email, device_name, os, version, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    pending["challenge"],
                    pending["redirect_uri"],
                    int(user["id"]),
                    str(user.get("email") or ""),
                    pending["device_name"],
                    pending["os"],
                    pending["version"],
                    now + _TTL_SEC,
                ),
            )
            conn.execute("DELETE FROM desktop_auth_pending WHERE state = ?", (state,))
        callback = f"{REDIRECT_URI}?{urlencode({'code': code, 'state': state})}"
        return render_template(
            "desktop_authorize_result.html",
            status="ok",
            callback=callback,
        )

    @app.get("/desktop/authorized")
    def desktop_authorize_ok():
        if desktop_enabled():
            abort(404)
        return render_template("desktop_authorize_result.html", status="ok")

    @app.get("/desktop/denied")
    def desktop_authorize_denied():
        if desktop_enabled():
            abort(404)
        return render_template("desktop_authorize_result.html", status="denied")

    @app.post("/api/desktop/token")
    def desktop_token():
        if desktop_enabled():
            abort(404)
        body = request.get_json(silent=True) or {}
        code = str(body.get("code") or "").strip()
        verifier = str(body.get("code_verifier") or "").strip()
        redirect_uri = str(body.get("redirect_uri") or "").strip()
        now = time.time()
        with _conn() as conn:
            ensure_schema(conn)
            _purge(conn, now)
            item = conn.execute(
                "SELECT * FROM desktop_auth_codes WHERE code = ?",
                (code,),
            ).fetchone()
            if item is None:
                return jsonify({"error": "invalid_grant"}), 400
            conn.execute("DELETE FROM desktop_auth_codes WHERE code = ?", (code,))
            if float(item["expires_at"] or 0) < now:
                return jsonify({"error": "invalid_grant"}), 400
            if redirect_uri != item["redirect_uri"]:
                return jsonify({"error": "invalid_grant"}), 400
            if pkce_challenge(verifier) != item["challenge"]:
                return jsonify({"error": "invalid_grant"}), 400
            token = secrets.token_urlsafe(32)
            token_key = hashlib.sha256(token.encode("ascii")).hexdigest()
            conn.execute(
                """
                INSERT INTO desktop_app_sessions
                (user_id, token_hash, device_name, os, app_version, created_at, last_seen_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    int(item["user_id"]),
                    token_key,
                    item["device_name"] or "Computer",
                    item["os"] or "",
                    item["version"] or "",
                    now,
                    now,
                    now + _SESSION_TTL_SEC,
                ),
            )
            return jsonify({
                "token": token,
                "user": {"id": int(item["user_id"]), "email": item["email"]},
            })

    @app.get("/api/desktop/session")
    def desktop_session_get():
        if desktop_enabled():
            abort(404)
        row = _load_session_row()
        if row is None:
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({
            "user": {"id": int(row["user_id"]), "email": row["email"] if "email" in row.keys() else ""},
            "device": {
                "id": int(row["id"]),
                "name": row["device_name"],
                "os": row["os"],
            },
        })

    @app.post("/account/desktop-devices/<int:device_id>/revoke")
    @login_required
    def account_desktop_device_revoke(device_id: int):
        if desktop_enabled():
            abort(404)
        user = current_user()
        now = time.time()
        with _conn() as conn:
            ensure_schema(conn)
            conn.execute(
                """
                UPDATE desktop_app_sessions
                SET revoked_at = ?
                WHERE id = ? AND user_id = ? AND revoked_at IS NULL
                """,
                (now, int(device_id), int(user["id"])),
            )
        return redirect(url_for("account"))


def load_desktop_session() -> Optional[dict[str, Any]]:
    row = _load_session_row()
    if row is None:
        return None
    return {
        "user_id": int(row["user_id"]),
        "email": str(row["email"] or ""),
        "device_id": int(row["id"]),
    }


def _load_session_row() -> Optional[Any]:
    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if len(token) < 16:
        return None
    token_key = hashlib.sha256(token.encode("ascii")).hexdigest()
    now = time.time()
    from app import db

    with db() as conn:
        ensure_schema(conn)
        row = conn.execute(
            """
            SELECT s.*, u.email
            FROM desktop_app_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_key,),
        ).fetchone()
        if row is None:
            return None
        if row["revoked_at"] is not None or float(row["expires_at"] or 0) < now:
            return None
        conn.execute(
            "UPDATE desktop_app_sessions SET last_seen_at = ? WHERE id = ?",
            (now, int(row["id"])),
        )
        return row


def _load_pending(*, create: bool):
    now = time.time()
    client_id = _clean(request.args.get("client_id"), 64)
    redirect_uri = _clean(request.args.get("redirect_uri"), 128)
    state = _clean(request.args.get("state"), 128)
    challenge = _clean(request.args.get("code_challenge"), 128)
    method = _clean(request.args.get("code_challenge_method"), 16)
    if client_id != CLIENT_ID or redirect_uri != REDIRECT_URI:
        return "invalid"
    if method != "S256" or len(challenge) < 16 or len(state) < 8:
        return "invalid"
    with _conn() as conn:
        ensure_schema(conn)
        _purge(conn, now)
        if create:
            conn.execute(
                """
                INSERT INTO desktop_auth_pending
                (state, challenge, redirect_uri, device_name, os, version, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state) DO UPDATE SET
                    challenge=excluded.challenge,
                    redirect_uri=excluded.redirect_uri,
                    device_name=excluded.device_name,
                    os=excluded.os,
                    version=excluded.version,
                    expires_at=excluded.expires_at
                """,
                (
                    state,
                    challenge,
                    redirect_uri,
                    _clean(request.args.get("device_name"), 80) or "Computer",
                    _clean(request.args.get("os"), 40),
                    _clean(request.args.get("version"), 32),
                    now + _TTL_SEC,
                ),
            )
        pending = conn.execute(
            "SELECT * FROM desktop_auth_pending WHERE state = ?",
            (state,),
        ).fetchone()
        if pending is None:
            return "invalid"
        return dict(pending)


def nxt_from_request() -> str:
    nxt = request.full_path if request.query_string else request.path
    if nxt.endswith("?"):
        nxt = nxt[:-1]
    return nxt


def _safe_authorize_next(value: str) -> str:
    nxt = str(value or "").strip()
    if nxt.startswith("/desktop/authorize?") or nxt == "/desktop/authorize":
        return nxt
    return "/desktop/authorize"
