"""Team Platform — multi-user collaboration foundation for Business OS."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import abort, jsonify, redirect, render_template, request, session, url_for

from bos.permissions import (
    TEAM_ROLES,
    has_permission,
    init_permissions_tables,
    is_workspace_owner,
    list_roles_with_permissions,
    member_role,
    normalize_role,
    permissions_for_role,
    require_permission,
)

MEMBER_STATUSES = ("active", "invited", "suspended", "removed")
INVITATION_STATUSES = ("pending", "accepted", "expired", "cancelled")
INVITE_TTL_DAYS = 7
PRESENCE_ONLINE_SECONDS = 300

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workspace_invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE,
    role TEXT NOT NULL DEFAULT 'member',
    token_hash TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',
    invited_by INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    accepted_user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(invited_by) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_invitations_ws ON workspace_invitations(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_workspace_invitations_email ON workspace_invitations(email, status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).replace(microsecond=0).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def init_team_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    init_permissions_tables(conn)

    wm_cols = {r["name"] for r in conn.execute("PRAGMA table_info(workspace_members)")}
    for col, ddl in (
        ("last_active_at", "TEXT"),
        ("updated_by", "INTEGER"),
        ("invited_by", "INTEGER"),
        ("removed_at", "TEXT"),
    ):
        if col not in wm_cols:
            conn.execute(f"ALTER TABLE workspace_members ADD COLUMN {col} {ddl}")

    user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    for col, ddl in (
        ("display_name", "TEXT"),
        ("avatar_url", "TEXT"),
        ("last_active_at", "TEXT"),
    ):
        if col not in user_cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

    conn.execute("UPDATE workspace_members SET role='member' WHERE role='staff'")

    from bos.collaboration import init_collaboration_columns
    init_collaboration_columns(conn)


def touch_user_presence(conn, user_id: int) -> None:
    ts = _now()
    conn.execute("UPDATE users SET last_active_at=? WHERE id=?", (ts, user_id))
    conn.execute(
        """UPDATE workspace_members SET last_active_at=?
           WHERE user_id=? AND status='active'""",
        (ts, user_id),
    )


def _presence_state(last_active_at: str | None) -> str:
    if not last_active_at:
        return "offline"
    try:
        ts = datetime.fromisoformat(last_active_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        return "online" if delta.total_seconds() <= PRESENCE_ONLINE_SECONDS else "offline"
    except (ValueError, TypeError):
        return "offline"


def _display_name(row) -> str:
    d = dict(row) if not isinstance(row, dict) else row
    return (d.get("display_name") or d.get("email") or "User").strip()


def _member_to_api(row, *, viewer_id: int | None = None) -> dict:
    from bos.mvp_schema import normalize_mvp_role

    d = dict(row)
    name = _display_name(d)
    last = d.get("last_active_at") or d.get("user_last_active_at")
    role = normalize_role(d.get("role")) or "member"
    return {
        "id": d["user_id"],
        "user_id": d["user_id"],
        "member_id": d.get("id"),
        "email": d.get("email") or "",
        "display_name": name,
        "avatar_url": d.get("avatar_url"),
        "role": role,
        "mvp_role": normalize_mvp_role(role),
        "status": d.get("status") or "active",
        "joined_at": d.get("joined_at"),
        "created_at": d.get("joined_at"),
        "invited_at": d.get("invited_at"),
        "last_active_at": last,
        "presence": _presence_state(last),
        "is_self": viewer_id is not None and d["user_id"] == viewer_id,
    }


def _emit_team(conn, event_type: str, object_id: int, workspace_id: int, user_id: int, title: str, **kw):
    from bos.events import emit
    emit(conn, event_type, "member", object_id, workspace_id=workspace_id, user_id=user_id,
         actor="member", title=title, href="/app/team", **kw)


def _expire_stale_invitations(conn, workspace_id: int | None = None) -> None:
    now = _now()
    sql = "UPDATE workspace_invitations SET status='expired' WHERE status='pending' AND expires_at < ?"
    params: list = [now]
    if workspace_id:
        sql += " AND workspace_id=?"
        params.append(workspace_id)
    conn.execute(sql, params)


def register_team_platform(app) -> None:
    from app import current_user, db, login_required

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return user["id"]

    def active_ws_id(user_id: int) -> int:
        ws_id = session.get("active_workspace_id")
        if ws_id:
            with db() as conn:
                if member_role(conn, user_id, int(ws_id)):
                    return int(ws_id)
        with db() as conn:
            row = conn.execute(
                """SELECT workspace_id FROM workspace_members
                   WHERE user_id=? AND status='active' ORDER BY joined_at LIMIT 1""",
                (user_id,),
            ).fetchone()
            if not row:
                abort(404)
            session["active_workspace_id"] = row["workspace_id"]
            return int(row["workspace_id"])

    def ws_from_request(user_id: int) -> int:
        ws = request.args.get("workspace_id", type=int)
        if not ws:
            body = request.get_json(silent=True) or {}
            ws = body.get("workspace_id")
        return int(ws or active_ws_id(user_id))

    def guard_ws(user_id: int, workspace_id: int):
        with db() as conn:
            touch_user_presence(conn, user_id)
            if not member_role(conn, user_id, workspace_id):
                abort(403)

    # ── Context / permissions ────────────────────────────────────────────────

    @app.get("/api/team/context")
    @login_required
    def api_team_context():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        with db() as conn:
            role = member_role(conn, user_id, ws_id)
            perms = sorted(permissions_for_role(conn, role or ""))
            ws = conn.execute("SELECT id, name FROM workspaces WHERE id=?", (ws_id,)).fetchone()
            member_count = conn.execute(
                "SELECT COUNT(*) AS c FROM workspace_members WHERE workspace_id=? AND status != 'removed'",
                (ws_id,),
            ).fetchone()["c"]
            pending_invites = conn.execute(
                "SELECT COUNT(*) AS c FROM workspace_invitations WHERE workspace_id=? AND status='pending'",
                (ws_id,),
            ).fetchone()["c"]
        return jsonify({
            "workspace_id": ws_id,
            "workspace_name": ws["name"] if ws else "",
            "role": role,
            "permissions": perms,
            "member_count": member_count,
            "pending_invitations": pending_invites,
        })

    @app.get("/api/team/summary")
    @login_required
    def api_team_summary():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        with db() as conn:
            _expire_stale_invitations(conn, ws_id)
            active = conn.execute(
                "SELECT COUNT(*) AS c FROM workspace_members WHERE workspace_id=? AND status='active'",
                (ws_id,),
            ).fetchone()["c"]
            suspended = conn.execute(
                "SELECT COUNT(*) AS c FROM workspace_members WHERE workspace_id=? AND status='suspended'",
                (ws_id,),
            ).fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM workspace_invitations WHERE workspace_id=? AND status='pending'",
                (ws_id,),
            ).fetchone()["c"]
            online = 0
            for r in conn.execute(
                """SELECT u.last_active_at FROM workspace_members wm
                   JOIN users u ON u.id = wm.user_id
                   WHERE wm.workspace_id=? AND wm.status='active'""",
                (ws_id,),
            ).fetchall():
                if _presence_state(r["last_active_at"]) == "online":
                    online += 1
        return jsonify({"active": active, "suspended": suspended, "pending_invitations": pending, "online": online})

    # ── Members ──────────────────────────────────────────────────────────────

    @app.get("/api/team/members")
    @login_required
    def api_team_members():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        q = request.args.get("q", "").strip().lower()
        status = request.args.get("status", "").strip()
        role = request.args.get("role", "").strip()
        sort = request.args.get("sort", "name")
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.read")
            sql = """SELECT wm.*, u.email, u.display_name, u.avatar_url, u.last_active_at AS user_last_active_at
                     FROM workspace_members wm JOIN users u ON u.id = wm.user_id
                     WHERE wm.workspace_id=? AND wm.status != 'removed'"""
            params: list = [ws_id]
            if status and status in MEMBER_STATUSES:
                sql += " AND wm.status=?"
                params.append(status)
            if role and role in TEAM_ROLES:
                sql += " AND wm.role=?"
                params.append(role)
            if q:
                sql += " AND (LOWER(u.email) LIKE ? OR LOWER(COALESCE(u.display_name,'')) LIKE ?)"
                params.extend([f"%{q}%", f"%{q}%"])
            order = {
                "name": "u.display_name, u.email",
                "email": "u.email",
                "role": "wm.role, u.email",
                "joined": "wm.joined_at DESC",
                "active": "u.last_active_at DESC",
            }.get(sort, "u.display_name, u.email")
            sql += f" ORDER BY {order}"
            rows = conn.execute(sql, params).fetchall()
        return jsonify([_member_to_api(r, viewer_id=user_id) for r in rows])

    @app.get("/api/team/members/<int:member_user_id>")
    @login_required
    def api_team_member_detail(member_user_id):
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.read")
            row = conn.execute(
                """SELECT wm.*, u.email, u.display_name, u.avatar_url, u.last_active_at AS user_last_active_at
                   FROM workspace_members wm JOIN users u ON u.id = wm.user_id
                   WHERE wm.workspace_id=? AND wm.user_id=? AND wm.status != 'removed'""",
                (ws_id, member_user_id),
            ).fetchone()
            if not row:
                abort(404)
            activity = conn.execute(
                """SELECT event_type, title, detail, created_at, user_id
                   FROM domain_events WHERE workspace_id=? AND object_type='member' AND object_id=?
                   ORDER BY created_at DESC LIMIT 20""",
                (ws_id, member_user_id),
            ).fetchall()
            role_for_perms = normalize_role(row["role"]) or "member"
            perms = sorted(permissions_for_role(conn, role_for_perms))
        payload = _member_to_api(row, viewer_id=user_id)
        payload["activity"] = [dict(a) for a in activity]
        payload["permissions"] = perms
        return jsonify(payload)

    @app.patch("/api/team/members/<int:member_user_id>")
    @login_required
    def api_team_member_update(member_user_id):
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            target = conn.execute(
                "SELECT * FROM workspace_members WHERE workspace_id=? AND user_id=? AND status != 'removed'",
                (ws_id, member_user_id),
            ).fetchone()
            if not target:
                abort(404)
            if "role" in data:
                require_permission(conn, user_id, ws_id, "member.update")
                new_role = normalize_role(data["role"])
                if new_role not in TEAM_ROLES:
                    return jsonify({"error": "Invalid role"}), 400
                if new_role == "owner":
                    return jsonify({"error": "Use transfer ownership to assign owner role"}), 400
                if target["role"] == "owner":
                    return jsonify({"error": "Cannot change owner role directly"}), 400
                conn.execute(
                    "UPDATE workspace_members SET role=?, updated_by=? WHERE workspace_id=? AND user_id=?",
                    (new_role, user_id, ws_id, member_user_id),
                )
                user = conn.execute("SELECT email FROM users WHERE id=?", (member_user_id,)).fetchone()
                _emit_team(conn, "member.role_updated", member_user_id, ws_id, user_id,
                           f"Role updated to {new_role} for {user['email'] if user else member_user_id}")
            if "status" in data:
                new_status = data["status"]
                if new_status == "suspended":
                    require_permission(conn, user_id, ws_id, "member.suspend")
                elif new_status == "active":
                    require_permission(conn, user_id, ws_id, "member.update")
                elif new_status == "removed":
                    require_permission(conn, user_id, ws_id, "member.remove")
                else:
                    return jsonify({"error": "Invalid status"}), 400
                if target["role"] == "owner" and new_status in ("suspended", "removed"):
                    return jsonify({"error": "Cannot suspend or remove workspace owner"}), 400
                if new_status == "removed":
                    conn.execute(
                        """UPDATE workspace_members SET status='removed', removed_at=?, updated_by=?
                           WHERE workspace_id=? AND user_id=?""",
                        (_now(), user_id, ws_id, member_user_id),
                    )
                    user = conn.execute("SELECT email FROM users WHERE id=?", (member_user_id,)).fetchone()
                    _emit_team(conn, "member.removed", member_user_id, ws_id, user_id,
                               f"Removed {user['email'] if user else member_user_id} from workspace")
                else:
                    conn.execute(
                        "UPDATE workspace_members SET status=?, updated_by=? WHERE workspace_id=? AND user_id=?",
                        (new_status, user_id, ws_id, member_user_id),
                    )
            row = conn.execute(
                """SELECT wm.*, u.email, u.display_name, u.avatar_url, u.last_active_at AS user_last_active_at
                   FROM workspace_members wm JOIN users u ON u.id = wm.user_id
                   WHERE wm.workspace_id=? AND wm.user_id=?""",
                (ws_id, member_user_id),
            ).fetchone()
            role_for_perms = normalize_role(row["role"]) if row else "member"
            perms = sorted(permissions_for_role(conn, role_for_perms or "member"))
        payload = _member_to_api(row, viewer_id=user_id)
        payload["permissions"] = perms
        return jsonify(payload)

    @app.post("/api/team/members/batch")
    @login_required
    def api_team_members_batch():
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_ws_id(user_id))
        guard_ws(user_id, ws_id)
        action = data.get("action")
        ids = [int(i) for i in (data.get("user_ids") or [])]
        if not ids:
            return jsonify({"error": "No members selected"}), 400
        count = 0
        with db() as conn:
            for mid in ids:
                target = conn.execute(
                    "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=? AND status != 'removed'",
                    (ws_id, mid),
                ).fetchone()
                if not target or target["role"] == "owner":
                    continue
                if action == "remove" and has_permission(conn, user_id, ws_id, "member.remove"):
                    conn.execute(
                        "UPDATE workspace_members SET status='removed', removed_at=?, updated_by=? WHERE workspace_id=? AND user_id=?",
                        (_now(), user_id, ws_id, mid),
                    )
                    _emit_team(conn, "member.removed", mid, ws_id, user_id, f"Member removed (batch)")
                    count += 1
                elif action == "suspend" and has_permission(conn, user_id, ws_id, "member.suspend"):
                    conn.execute(
                        "UPDATE workspace_members SET status='suspended', updated_by=? WHERE workspace_id=? AND user_id=?",
                        (user_id, ws_id, mid),
                    )
                    count += 1
                elif action == "activate" and has_permission(conn, user_id, ws_id, "member.update"):
                    conn.execute(
                        "UPDATE workspace_members SET status='active', updated_by=? WHERE workspace_id=? AND user_id=?",
                        (user_id, ws_id, mid),
                    )
                    count += 1
                elif action == "role" and has_permission(conn, user_id, ws_id, "member.update"):
                    role = normalize_role(data.get("role"))
                    if role and role in TEAM_ROLES and role != "owner":
                        conn.execute(
                            "UPDATE workspace_members SET role=?, updated_by=? WHERE workspace_id=? AND user_id=?",
                            (role, user_id, ws_id, mid),
                        )
                        count += 1
        return jsonify({"ok": True, "count": count})

    # ── Invitations ──────────────────────────────────────────────────────────

    @app.get("/api/team/invitations")
    @login_required
    def api_team_invitations():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.read")
            _expire_stale_invitations(conn, ws_id)
            rows = conn.execute(
                """SELECT wi.*, u.email AS invited_by_email
                   FROM workspace_invitations wi
                   JOIN users u ON u.id = wi.invited_by
                   WHERE wi.workspace_id=? ORDER BY wi.created_at DESC""",
                (ws_id,),
            ).fetchall()
        return jsonify([_invitation_to_api(r) for r in rows])

    @app.post("/api/team/invitations")
    @login_required
    def api_team_invitation_create():
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_ws_id(user_id))
        guard_ws(user_id, ws_id)
        email = (data.get("email") or "").strip().lower()
        role = normalize_role(data.get("role") or "member") or "member"
        if not email:
            return jsonify({"error": "Email required"}), 400
        if role not in TEAM_ROLES or role == "owner":
            return jsonify({"error": "Invalid role for invitation"}), 400
        token = secrets.token_urlsafe(32)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.invite")
            existing = conn.execute(
                """SELECT 1 FROM workspace_members wm JOIN users u ON u.id=wm.user_id
                   WHERE wm.workspace_id=? AND lower(u.email)=? AND wm.status='active'""",
                (ws_id, email),
            ).fetchone()
            if existing:
                return jsonify({"error": "User is already an active member"}), 409
            pending = conn.execute(
                "SELECT id FROM workspace_invitations WHERE workspace_id=? AND lower(email)=? AND status='pending'",
                (ws_id, email),
            ).fetchone()
            if pending:
                return jsonify({"error": "Invitation already pending for this email"}), 409
            cur = conn.execute(
                """INSERT INTO workspace_invitations
                   (workspace_id, email, role, token_hash, status, invited_by, expires_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (ws_id, email, role, _token_hash(token), user_id, _expires_at()),
            )
            inv_id = cur.lastrowid
            _emit_team(conn, "member.invited", inv_id, ws_id, user_id, f"Invited {email} as {role}",
                       metadata={"email": email, "role": role})
            row = conn.execute("SELECT * FROM workspace_invitations WHERE id=?", (inv_id,)).fetchone()
        payload = _invitation_to_api(row)
        payload["accept_url"] = f"/accept-invite?token={token}"
        payload["token"] = token  # returned once for share link
        return jsonify(payload), 201

    @app.post("/api/team/invitations/<int:inv_id>/cancel")
    @login_required
    def api_team_invitation_cancel(inv_id):
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_ws_id(user_id))
        guard_ws(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.invite")
            row = conn.execute(
                "SELECT * FROM workspace_invitations WHERE id=? AND workspace_id=?",
                (inv_id, ws_id),
            ).fetchone()
            if not row or row["status"] != "pending":
                return jsonify({"error": "Invitation not found or not pending"}), 404
            conn.execute("UPDATE workspace_invitations SET status='cancelled' WHERE id=?", (inv_id,))
            _emit_team(conn, "member.invitation_cancelled", inv_id, ws_id, user_id,
                       f"Invitation cancelled for {row['email']}")
        return jsonify({"ok": True})

    @app.post("/api/team/invitations/<int:inv_id>/resend")
    @login_required
    def api_team_invitation_resend(inv_id):
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_ws_id(user_id))
        guard_ws(user_id, ws_id)
        token = secrets.token_urlsafe(32)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.invite")
            row = conn.execute(
                "SELECT * FROM workspace_invitations WHERE id=? AND workspace_id=? AND status='pending'",
                (inv_id, ws_id),
            ).fetchone()
            if not row:
                return jsonify({"error": "Pending invitation not found"}), 404
            conn.execute(
                "UPDATE workspace_invitations SET token_hash=?, expires_at=?, invited_by=? WHERE id=?",
                (_token_hash(token), _expires_at(), user_id, inv_id),
            )
        return jsonify({
            "ok": True,
            "accept_url": f"/accept-invite?token={token}",
            "token": token,
        })

    @app.get("/api/team/invitations/mine")
    @login_required
    def api_team_my_invitations():
        user_id = uid()
        with db() as conn:
            user = conn.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                abort(404)
            _expire_stale_invitations(conn)
            rows = conn.execute(
                """SELECT wi.*, w.name AS workspace_name
                   FROM workspace_invitations wi JOIN workspaces w ON w.id = wi.workspace_id
                   WHERE lower(wi.email)=? AND wi.status='pending' AND wi.expires_at >= ?""",
                (user["email"].lower(), _now()),
            ).fetchall()
        return jsonify([{**_invitation_to_api(r), "workspace_name": r["workspace_name"]} for r in rows])

    @app.post("/api/team/invitations/accept")
    @login_required
    def api_team_invitation_accept():
        user_id = uid()
        data = request.get_json(silent=True) or {}
        token = (data.get("token") or request.args.get("token") or "").strip()
        if not token:
            return jsonify({"error": "Token required"}), 400
        with db() as conn:
            user = conn.execute("SELECT id, email FROM users WHERE id=?", (user_id,)).fetchone()
            inv = conn.execute(
                "SELECT * FROM workspace_invitations WHERE token_hash=? AND status='pending'",
                (_token_hash(token),),
            ).fetchone()
            if not inv:
                return jsonify({"error": "Invalid or expired invitation"}), 404
            if inv["expires_at"] < _now():
                conn.execute("UPDATE workspace_invitations SET status='expired' WHERE id=?", (inv["id"],))
                return jsonify({"error": "Invitation expired"}), 410
            if user["email"].lower() != inv["email"].lower():
                return jsonify({"error": "Invitation email does not match your account"}), 403
            try:
                conn.execute(
                    """INSERT INTO workspace_members (workspace_id, user_id, role, status, invited_at, joined_at, invited_by)
                       VALUES (?, ?, ?, 'active', ?, ?, ?)""",
                    (inv["workspace_id"], user_id, inv["role"], inv["created_at"], _now(), inv["invited_by"]),
                )
            except Exception:
                conn.execute(
                    """UPDATE workspace_members SET role=?, status='active', joined_at=?, invited_by=?
                       WHERE workspace_id=? AND user_id=?""",
                    (inv["role"], _now(), inv["invited_by"], inv["workspace_id"], user_id),
                )
            conn.execute(
                "UPDATE workspace_invitations SET status='accepted', accepted_at=?, accepted_user_id=? WHERE id=?",
                (_now(), user_id, inv["id"]),
            )
            _emit_team(conn, "member.joined", user_id, inv["workspace_id"], user_id,
                       f"{user['email']} joined the workspace", metadata={"invitation_id": inv["id"]})
            session["active_workspace_id"] = inv["workspace_id"]
        return jsonify({"ok": True, "workspace_id": inv["workspace_id"]})

    @app.get("/accept-invite")
    def team_accept_invite_page():
        token = request.args.get("token", "")
        if not current_user():
            return redirect(url_for("login", next=f"/accept-invite?token={token}"))
        return render_template("team_accept_invite.html", token=token)

    # ── Roles & permissions ──────────────────────────────────────────────────

    @app.get("/api/team/roles")
    @login_required
    def api_team_roles():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.read")
            roles = list_roles_with_permissions(conn)
        return jsonify(roles)

    @app.get("/api/team/permissions")
    @login_required
    def api_team_permissions():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.read")
            rows = conn.execute("SELECT key, description FROM permissions ORDER BY key").fetchall()
        return jsonify([dict(r) for r in rows])

    # ── Activity ─────────────────────────────────────────────────────────────

    @app.get("/api/team/activity")
    @login_required
    def api_team_activity():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        member_id = request.args.get("member_id", type=int)
        limit = min(request.args.get("limit", 50, type=int), 200)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.read")
            sql = """SELECT de.*, u.email AS actor_email, u.display_name AS actor_name
                     FROM domain_events de LEFT JOIN users u ON u.id = de.user_id
                     WHERE de.workspace_id=? AND de.event_type LIKE 'member.%'"""
            params: list = [ws_id]
            if member_id:
                sql += " AND de.object_id=?"
                params.append(member_id)
            sql += " ORDER BY de.created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])

    # ── Presence ─────────────────────────────────────────────────────────────

    @app.get("/api/team/presence")
    @login_required
    def api_team_presence():
        user_id = uid()
        ws_id = ws_from_request(user_id)
        guard_ws(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "member.read")
            rows = conn.execute(
                """SELECT wm.user_id, u.email, u.display_name, u.last_active_at
                   FROM workspace_members wm JOIN users u ON u.id = wm.user_id
                   WHERE wm.workspace_id=? AND wm.status='active'""",
                (ws_id,),
            ).fetchall()
        return jsonify([
            {
                "user_id": r["user_id"],
                "email": r["email"],
                "display_name": _display_name(r),
                "presence": _presence_state(r["last_active_at"]),
                "last_active_at": r["last_active_at"],
            }
            for r in rows
        ])

    # ── Transfer ownership ───────────────────────────────────────────────────

    @app.post("/api/team/transfer-ownership")
    @login_required
    def api_team_transfer_ownership():
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_ws_id(user_id))
        new_owner_id = int(data.get("new_owner_id") or 0)
        if not new_owner_id:
            return jsonify({"error": "new_owner_id required"}), 400
        guard_ws(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "workspace.transfer_ownership")
            if not is_workspace_owner(conn, user_id, ws_id):
                return jsonify({"error": "Only the owner can transfer ownership"}), 403
            target = conn.execute(
                "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=? AND status='active'",
                (ws_id, new_owner_id),
            ).fetchone()
            if not target:
                return jsonify({"error": "New owner must be an active member"}), 400
            conn.execute(
                "UPDATE workspace_members SET role='administrator', updated_by=? WHERE workspace_id=? AND user_id=?",
                (user_id, ws_id, user_id),
            )
            conn.execute(
                "UPDATE workspace_members SET role='owner', updated_by=? WHERE workspace_id=? AND user_id=?",
                (user_id, ws_id, new_owner_id),
            )
            new_user = conn.execute("SELECT email FROM users WHERE id=?", (new_owner_id,)).fetchone()
            _emit_team(conn, "workspace.ownership_transferred", ws_id, ws_id, user_id,
                       f"Ownership transferred to {new_user['email'] if new_user else new_owner_id}",
                       metadata={"new_owner_id": new_owner_id})
        return jsonify({"ok": True})

    # Legacy list endpoint used by old team page
    @app.get("/api/team")
    @login_required
    def api_team_list_legacy():
        return api_team_members()

    app.init_team_tables = init_team_tables
    app.touch_user_presence = touch_user_presence


def _invitation_to_api(row) -> dict:
    d = dict(row)
    return {
        "id": d["id"],
        "workspace_id": d["workspace_id"],
        "email": d["email"],
        "role": normalize_role(d.get("role")) or "member",
        "status": d.get("status") or "pending",
        "invited_by": d.get("invited_by"),
        "invited_by_email": d.get("invited_by_email"),
        "expires_at": d.get("expires_at"),
        "accepted_at": d.get("accepted_at"),
        "created_at": d.get("created_at"),
    }
