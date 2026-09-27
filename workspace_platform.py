"""Workspace Platform — primary operating container for Zintriq."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from flask import abort, jsonify, request, session

_log = logging.getLogger("app.workspace")

WORKSPACE_STATUSES = ("active", "archived", "suspended")
WORKSPACE_ROLES = ("owner", "administrator", "manager", "member", "viewer")
WORKSPACE_MODULES = (
    "qr", "feedback", "customers", "catalog", "inventory", "orders",
    "appointments", "membership", "documents", "team", "operations", "analytics",
)


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workspace_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'staff',
    status TEXT DEFAULT 'active',
    invited_at TEXT,
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, user_id),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workspace_modules (
    workspace_id INTEGER NOT NULL,
    module_id TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    PRIMARY KEY (workspace_id, module_id),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workspace_favorites (
    user_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, workspace_id),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workspace_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    actor_id INTEGER,
    object_type TEXT,
    object_id INTEGER,
    action TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_activity_ws ON workspace_activity(workspace_id);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


def init_workspace_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    ws_cols = {r["name"] for r in conn.execute("PRAGMA table_info(workspaces)")}
    for col, ddl in (
        ("logo_url", "TEXT"),
        ("timezone", "TEXT DEFAULT 'Asia/Singapore'"),
        ("language", "TEXT DEFAULT 'en'"),
        ("region", "TEXT"),
        ("currency", "TEXT DEFAULT 'USD'"),
        ("default_store_id", "INTEGER"),
        ("branding", "TEXT"),
        ("settings_json", "TEXT"),
    ):
        if col not in ws_cols:
            conn.execute(f"ALTER TABLE workspaces ADD COLUMN {col} {ddl}")

    cp_cols = {r["name"] for r in conn.execute("PRAGMA table_info(customer_profiles)")}
    if "workspace_id" in cp_cols or conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='customer_profiles'"
    ).fetchone():
        cp_cols = {r["name"] for r in conn.execute("PRAGMA table_info(customer_profiles)")}
        if "workspace_id" not in cp_cols:
            conn.execute("ALTER TABLE customer_profiles ADD COLUMN workspace_id INTEGER")

    _backfill_workspace_membership(conn)
    _backfill_customer_workspace_ids(conn)


def _backfill_workspace_membership(conn) -> None:
    """Ensure every workspace has an owner member from organization owner."""
    for ws in conn.execute(
        """SELECT w.id, o.owner_id FROM workspaces w
           JOIN organizations o ON o.id = w.organization_id"""
    ).fetchall():
        exists = conn.execute(
            "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
            (ws["id"], ws["owner_id"]),
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO workspace_members (workspace_id, user_id, role, status, joined_at)
                   VALUES (?, ?, 'owner', 'active', CURRENT_TIMESTAMP)""",
                (ws["id"], ws["owner_id"]),
            )
        for mod in WORKSPACE_MODULES:
            conn.execute(
                "INSERT OR IGNORE INTO workspace_modules (workspace_id, module_id, enabled) VALUES (?, ?, 1)",
                (ws["id"], mod),
            )


def _backfill_customer_workspace_ids(conn) -> None:
    for row in conn.execute(
        """SELECT cp.id, cp.owner_id FROM customer_profiles cp
           WHERE cp.workspace_id IS NULL"""
    ).fetchall():
        ws = conn.execute(
            """SELECT w.id FROM workspaces w
               JOIN organizations o ON o.id = w.organization_id
               WHERE o.owner_id = ? ORDER BY w.id LIMIT 1""",
            (row["owner_id"],),
        ).fetchone()
        if ws:
            conn.execute("UPDATE customer_profiles SET workspace_id=? WHERE id=?", (ws["id"], row["id"]))


def log_workspace_activity(conn, workspace_id, action, title, *, actor_id=None, object_type=None, object_id=None, detail=""):
    from bos.events import emit, event_type as ev_type

    obj_type = object_type or "workspace"
    obj_id = object_id or workspace_id
    emit(
        conn,
        ev_type(obj_type, action if action in ("created", "updated", "archived", "restored", "deleted") else "updated"),
        obj_type,
        int(obj_id),
        workspace_id=workspace_id,
        user_id=actor_id,
        actor="owner" if actor_id else "system",
        title=title,
        detail=detail,
        href="/app/workspaces",
    )


def _accessible_workspace_count(conn, user_id: int) -> int:
    return int(conn.execute(
        """SELECT COUNT(*) AS c FROM workspace_members wm
           JOIN workspaces w ON w.id = wm.workspace_id
           WHERE wm.user_id=? AND wm.status='active'""",
        (user_id,),
    ).fetchone()["c"])


def _workspace_owner(conn, workspace_id: int, user_id: int) -> bool:
    row = conn.execute(
        "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=? AND status='active'",
        (workspace_id, user_id),
    ).fetchone()
    return bool(row and row["role"] == "owner")


def register_workspace_platform(app) -> None:
    from app import current_user, db, login_required
    from bos.services.organization import ensure_default_organization
    from bos.services.workspace import ensure_default_workspace

    def user_id():
        user = current_user()
        if not user:
            abort(401)
        return user["id"]

    def active_workspace_id(uid: int) -> int:
        ws_id = session.get("active_workspace_id")
        if ws_id and _user_can_access(uid, ws_id):
            return int(ws_id)
        with db() as conn:
            ensure_default_organization(conn, uid)
            ws = ensure_default_workspace(conn, uid)
            session["active_workspace_id"] = ws["id"]
            return ws["id"]

    def _user_can_access(uid: int, workspace_id: int) -> bool:
        with db() as conn:
            row = conn.execute(
                """SELECT 1 FROM workspace_members wm
                   JOIN workspaces w ON w.id = wm.workspace_id
                   WHERE wm.user_id=? AND wm.workspace_id=? AND wm.status='active'
                     AND w.status != 'archived'""",
                (uid, workspace_id),
            ).fetchone()
            return row is not None

    def get_workspace_or_404(uid: int, workspace_id: int):
        with db() as conn:
            row = conn.execute(
                """SELECT w.*, o.name AS organization_name,
                          (SELECT COUNT(*) FROM qr_experiences qe
                           WHERE qe.workspace_id = w.id AND qe.status != 'archived') AS experience_count
                   FROM workspaces w
                   JOIN organizations o ON o.id = w.organization_id
                   JOIN workspace_members wm ON wm.workspace_id = w.id
                   WHERE w.id=? AND wm.user_id=? AND wm.status='active'""",
                (workspace_id, uid),
            ).fetchone()
        if not row:
            abort(404)
        return row

    def workspace_to_api(row, uid: int) -> dict:
        wid = row["id"]
        with db() as conn:
            is_fav = conn.execute(
                "SELECT 1 FROM workspace_favorites WHERE user_id=? AND workspace_id=?",
                (uid, wid),
            ).fetchone() is not None
            role = conn.execute(
                "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                (wid, uid),
            ).fetchone()
            modules = conn.execute(
                "SELECT module_id, enabled FROM workspace_modules WHERE workspace_id=?",
                (wid,),
            ).fetchall()
        payload = dict(row)
        payload["is_favorite"] = is_fav
        payload["role"] = role["role"] if role else None
        payload["modules"] = {m["module_id"]: bool(m["enabled"]) for m in modules}
        return payload

    def workspace_overview(workspace_id: int, uid: int) -> dict:
        with db() as conn:
            stores = conn.execute(
                "SELECT COUNT(*) AS c FROM stores WHERE workspace_id=? AND status != 'archived'",
                (workspace_id,),
            ).fetchone()["c"]
            customers = conn.execute(
                "SELECT COUNT(*) AS c FROM customer_profiles WHERE workspace_id=? AND status != 'archived'",
                (workspace_id,),
            ).fetchone()["c"]
            feedback = conn.execute(
                """SELECT COUNT(*) AS c FROM feedback_records fr
                   JOIN stores s ON s.id = fr.store_id WHERE s.workspace_id=?""",
                (workspace_id,),
            ).fetchone()["c"]
            qr_assets = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_codes q
                   JOIN stores s ON s.id = q.store_id WHERE s.workspace_id=?""",
                (workspace_id,),
            ).fetchone()["c"]
            members = conn.execute(
                "SELECT COUNT(*) AS c FROM workspace_members WHERE workspace_id=? AND status='active'",
                (workspace_id,),
            ).fetchone()["c"]
            recent_activity = conn.execute(
                """SELECT wa.*, u.email AS actor_email FROM workspace_activity wa
                   LEFT JOIN users u ON u.id = wa.actor_id
                   WHERE wa.workspace_id=? ORDER BY wa.created_at DESC LIMIT 15""",
                (workspace_id,),
            ).fetchall()
            recent_stores = conn.execute(
                "SELECT id, name, slug, status FROM stores WHERE workspace_id=? ORDER BY updated_at DESC LIMIT 5",
                (workspace_id,),
            ).fetchall()
        return {
            "stores": int(stores or 0),
            "customers": int(customers or 0),
            "feedback": int(feedback or 0),
            "qr_assets": int(qr_assets or 0),
            "members": int(members or 0),
            "recent_activity": [dict(a) for a in recent_activity],
            "recent_stores": [dict(s) for s in recent_stores],
        }

    def aggregate_workspace_activity(conn, workspace_id: int, limit: int = 50):
        """Pull cross-platform events into workspace activity if sparse."""
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM workspace_activity WHERE workspace_id=?", (workspace_id,),
        ).fetchone()["c"]
        if count >= 5:
            return
        for row in conn.execute(
            """SELECT ca.id, ca.activity_type, ca.title, ca.created_at, ca.customer_id
               FROM customer_activities ca
               JOIN customer_profiles cp ON cp.id = ca.customer_id
               WHERE cp.workspace_id=? ORDER BY ca.created_at DESC LIMIT ?""",
            (workspace_id, limit),
        ).fetchall():
            log_workspace_activity(
                conn, workspace_id, row["activity_type"], row["title"],
                object_type="customer", object_id=row["customer_id"],
                detail=f"Imported from customer timeline #{row['id']}",
            )

    # --- API ---

    @app.get("/api/workspaces")
    @login_required
    def api_workspaces_list():
        uid = user_id()
        q = request.args.get("q", "").strip().lower()
        with db() as conn:
            rows = conn.execute(
                """SELECT w.*, o.name AS organization_name,
                          (SELECT COUNT(*) FROM qr_experiences qe
                           WHERE qe.workspace_id = w.id AND qe.status != 'archived') AS experience_count
                   FROM workspaces w
                   JOIN workspace_members wm ON wm.workspace_id = w.id
                   JOIN organizations o ON o.id = w.organization_id
                   WHERE wm.user_id = ? AND wm.status = 'active'
                   ORDER BY w.name""",
                (uid,),
            ).fetchall()
            if not rows:
                ensure_default_organization(conn, uid)
                ensure_default_workspace(conn, uid)
                rows = conn.execute(
                    """SELECT w.*, o.name AS organization_name,
                              (SELECT COUNT(*) FROM qr_experiences qe
                               WHERE qe.workspace_id = w.id AND qe.status != 'archived') AS experience_count
                       FROM workspaces w
                       JOIN workspace_members wm ON wm.workspace_id = w.id
                       JOIN organizations o ON o.id = w.organization_id
                       WHERE wm.user_id = ? AND wm.status = 'active'
                       ORDER BY w.name""",
                    (uid,),
                ).fetchall()
            fav_ids = {
                r["workspace_id"] for r in conn.execute(
                    "SELECT workspace_id FROM workspace_favorites WHERE user_id=?", (uid,),
                ).fetchall()
            }
        result = []
        for r in rows:
            item = workspace_to_api(dict(r), uid)
            item["is_favorite"] = r["id"] in fav_ids
            if q and q not in (item.get("name") or "").lower() and q not in (item.get("slug") or ""):
                continue
            result.append(item)
        recent = session.get("recent_workspace_ids") or []
        return jsonify({"workspaces": result, "recent_ids": recent, "active_id": active_workspace_id(uid)})

    @app.get("/api/workspaces/current")
    @login_required
    def api_workspace_current():
        uid = user_id()
        wid = active_workspace_id(uid)
        row = get_workspace_or_404(uid, wid)
        payload = workspace_to_api(row, uid)
        payload["overview"] = workspace_overview(wid, uid)
        return jsonify(payload)

    @app.post("/api/workspaces/switch")
    @login_required
    def api_workspace_switch():
        uid = user_id()
        data = request.get_json(silent=True) or {}
        wid = data.get("workspace_id")
        if not wid or not _user_can_access(uid, int(wid)):
            return jsonify({"error": "Workspace not accessible"}), 403
        session["active_workspace_id"] = int(wid)
        recent = [int(wid)] + [i for i in (session.get("recent_workspace_ids") or []) if i != int(wid)]
        session["recent_workspace_ids"] = recent[:8]
        row = get_workspace_or_404(uid, int(wid))
        return jsonify(workspace_to_api(row, uid))

    @app.post("/api/workspaces")
    @login_required
    def api_workspace_create():
        uid = user_id()
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip() or "New Workspace"
        with db() as conn:
            org = ensure_default_organization(conn, uid)
            slug = _slugify(name)
            base = slug
            n = 1
            while conn.execute(
                "SELECT 1 FROM workspaces WHERE organization_id=? AND slug=?", (org["id"], slug),
            ).fetchone():
                slug = f"{base}-{n}"
                n += 1
            cur = conn.execute(
                """INSERT INTO workspaces (organization_id, name, slug, type, status, updated_at)
                   VALUES (?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)""",
                (org["id"], name, slug, data.get("type") or "general"),
            )
            wid = cur.lastrowid
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (wid, uid),
            )
            for mod in WORKSPACE_MODULES:
                conn.execute(
                    "INSERT INTO workspace_modules (workspace_id, module_id, enabled) VALUES (?, ?, 1)",
                    (wid, mod),
                )
            conn.execute(
                "UPDATE stores SET workspace_id=? WHERE owner_id=? AND workspace_id IS NULL", (wid, uid),
            )
            from bos.workspace_store import ensure_workspace_store
            ensure_workspace_store(conn, int(wid), uid)
            from bos.workflows import _seed_workspace_workflows
            _seed_workspace_workflows(conn, wid)
            log_workspace_activity(conn, wid, "created", f"Workspace «{name}» created", actor_id=uid)
            row = conn.execute("SELECT * FROM workspaces WHERE id=?", (wid,)).fetchone()
        session["active_workspace_id"] = wid
        return jsonify(workspace_to_api(row, uid)), 201

    @app.get("/api/workspaces/<int:workspace_id>")
    @login_required
    def api_workspace_detail(workspace_id):
        uid = user_id()
        row = get_workspace_or_404(uid, workspace_id)
        payload = workspace_to_api(row, uid)
        payload["overview"] = workspace_overview(workspace_id, uid)
        return jsonify(payload)

    @app.patch("/api/workspaces/<int:workspace_id>")
    @login_required
    def api_workspace_update(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        data = request.get_json(silent=True) or {}
        fields = ("name", "type", "status", "logo_url", "timezone", "language", "region", "currency", "default_store_id")
        updates, params = [], []
        for f in fields:
            if f in data:
                updates.append(f"{f}=?")
                params.append(data[f])
        if not updates:
            return jsonify({"ok": True})
        updates.append("updated_at=?")
        params.append(_now())
        params.append(workspace_id)
        with db() as conn:
            conn.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE id=?", params)
            log_workspace_activity(conn, workspace_id, "updated", "Workspace settings updated", actor_id=uid)
            row = conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        return jsonify(workspace_to_api(row, uid))

    @app.post("/api/workspaces/<int:workspace_id>/archive")
    @login_required
    def api_workspace_archive(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        with db() as conn:
            conn.execute(
                "UPDATE workspaces SET status='archived', updated_at=? WHERE id=?", (_now(), workspace_id),
            )
            log_workspace_activity(conn, workspace_id, "archived", "Workspace archived", actor_id=uid)
        return jsonify({"ok": True})

    @app.post("/api/workspaces/<int:workspace_id>/restore")
    @login_required
    def api_workspace_restore(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        with db() as conn:
            conn.execute(
                "UPDATE workspaces SET status='active', updated_at=? WHERE id=?", (_now(), workspace_id),
            )
            log_workspace_activity(conn, workspace_id, "restored", "Workspace restored", actor_id=uid)
        return jsonify({"ok": True})

    @app.post("/api/workspaces/<int:workspace_id>/delete")
    @login_required
    def api_workspace_delete(workspace_id):
        uid = user_id()
        row = get_workspace_or_404(uid, workspace_id)
        with db() as conn:
            if not _workspace_owner(conn, workspace_id, uid):
                return jsonify({"error": "Only workspace owners can delete a workspace"}), 403
            if _accessible_workspace_count(conn, uid) < 2:
                return jsonify({"error": "You must keep at least one workspace"}), 400

            fallback = conn.execute(
                """SELECT w.id FROM workspaces w
                   JOIN workspace_members wm ON wm.workspace_id = w.id
                   WHERE wm.user_id=? AND wm.status='active' AND w.id != ?
                   ORDER BY w.id LIMIT 1""",
                (uid, workspace_id),
            ).fetchone()
            if not fallback:
                return jsonify({"error": "You must keep at least one workspace"}), 400

            next_id = int(fallback["id"])
            ws_name = row["name"]

            conn.execute("UPDATE stores SET workspace_id=? WHERE workspace_id=?", (next_id, workspace_id))
            conn.execute("UPDATE customer_profiles SET workspace_id=? WHERE workspace_id=?", (next_id, workspace_id))

            from bos.events import emit, event_type as ev_type
            emit(
                conn,
                ev_type("workspace", "deleted"),
                "workspace",
                workspace_id,
                workspace_id=workspace_id,
                user_id=uid,
                actor="owner",
                title=f"Workspace «{ws_name}» deleted",
                href="/app/workspaces",
            )

            conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))

        if session.get("active_workspace_id") == workspace_id:
            session["active_workspace_id"] = next_id
        recent = [i for i in (session.get("recent_workspace_ids") or []) if i != workspace_id]
        session["recent_workspace_ids"] = recent

        return jsonify({"ok": True, "next_workspace_id": next_id})

    @app.post("/api/workspaces/<int:workspace_id>/favorite")
    @login_required
    def api_workspace_favorite(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            if data.get("favorite", True):
                conn.execute(
                    "INSERT OR IGNORE INTO workspace_favorites (user_id, workspace_id) VALUES (?, ?)",
                    (uid, workspace_id),
                )
            else:
                conn.execute(
                    "DELETE FROM workspace_favorites WHERE user_id=? AND workspace_id=?",
                    (uid, workspace_id),
                )
        return jsonify({"ok": True})

    @app.get("/api/workspaces/<int:workspace_id>/stores")
    @login_required
    def api_workspace_stores(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        q = request.args.get("q", "").strip()
        with db() as conn:
            query = "SELECT * FROM stores WHERE workspace_id=?"
            params: list = [workspace_id]
            if q:
                query += " AND (name LIKE ? OR slug LIKE ?)"
                params.extend([f"%{q}%", f"%{q}%"])
            query += " ORDER BY name"
            rows = conn.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/workspaces/<int:workspace_id>/members")
    @login_required
    def api_workspace_members(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        with db() as conn:
            rows = conn.execute(
                """SELECT wm.*, u.email FROM workspace_members wm
                   JOIN users u ON u.id = wm.user_id
                   WHERE wm.workspace_id=? ORDER BY wm.role, u.email""",
                (workspace_id,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/workspaces/<int:workspace_id>/members")
    @login_required
    def api_workspace_invite(workspace_id):
        """Legacy route — creates a pending invitation (Team Platform)."""
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        data = request.get_json(silent=True) or {}
        import hashlib
        import secrets
        from bos.permissions import require_permission
        from bos.events import emit

        email = (data.get("email") or "").strip().lower()
        role = data.get("role") or "member"
        if role == "staff":
            role = "member"
        if role not in WORKSPACE_ROLES or role == "owner":
            return jsonify({"error": "Invalid role"}), 400
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        from datetime import datetime, timedelta, timezone
        expires = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0).isoformat()
        with db() as conn:
            require_permission(conn, uid, workspace_id, "member.invite")
            pending = conn.execute(
                "SELECT id FROM workspace_invitations WHERE workspace_id=? AND lower(email)=? AND status='pending'",
                (workspace_id, email),
            ).fetchone()
            if pending:
                return jsonify({"error": "Invitation already pending"}), 409
            cur = conn.execute(
                """INSERT INTO workspace_invitations
                   (workspace_id, email, role, token_hash, status, invited_by, expires_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (workspace_id, email, role, token_hash, uid, expires),
            )
            emit(conn, "member.invited", "member", cur.lastrowid, workspace_id=workspace_id, user_id=uid,
                 actor="member", title=f"Invited {email} as {role}", href="/app/team")
        return jsonify({"ok": True, "accept_url": f"/accept-invite?token={token}"}), 201

    @app.patch("/api/workspaces/<int:workspace_id>/members/<int:member_user_id>")
    @login_required
    def api_workspace_member_update(workspace_id, member_user_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            from bos.permissions import has_permission, require_permission
            if "role" in data:
                require_permission(conn, uid, workspace_id, "member.update")
            if "status" in data:
                perm = "member.suspend" if data["status"] == "suspended" else "member.remove" if data["status"] == "removed" else "member.update"
                require_permission(conn, uid, workspace_id, perm)
            if "role" in data and data["role"] in WORKSPACE_ROLES:
                role = "member" if data["role"] == "staff" else data["role"]
                conn.execute(
                    "UPDATE workspace_members SET role=?, updated_by=? WHERE workspace_id=? AND user_id=?",
                    (role, uid, workspace_id, member_user_id),
                )
            if "status" in data:
                conn.execute(
                    "UPDATE workspace_members SET status=?, updated_by=? WHERE workspace_id=? AND user_id=?",
                    (data["status"], uid, workspace_id, member_user_id),
                )
        return jsonify({"ok": True})

    @app.get("/api/workspaces/<int:workspace_id>/modules")
    @login_required
    def api_workspace_modules(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        with db() as conn:
            rows = conn.execute(
                "SELECT module_id, enabled FROM workspace_modules WHERE workspace_id=?",
                (workspace_id,),
            ).fetchall()
        return jsonify({r["module_id"]: bool(r["enabled"]) for r in rows})

    @app.post("/api/workspaces/<int:workspace_id>/modules")
    @login_required
    def api_workspace_modules_update(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        data = request.get_json(silent=True) or {}
        modules = data.get("modules") or {}
        with db() as conn:
            for mod_id, enabled in modules.items():
                conn.execute(
                    """INSERT INTO workspace_modules (workspace_id, module_id, enabled)
                       VALUES (?, ?, ?) ON CONFLICT(workspace_id, module_id)
                       DO UPDATE SET enabled=excluded.enabled""",
                    (workspace_id, mod_id, 1 if enabled else 0),
                )
            log_workspace_activity(conn, workspace_id, "modules_updated", "Module settings updated", actor_id=uid)
        return jsonify({"ok": True})

    @app.get("/api/workspaces/<int:workspace_id>/activity")
    @login_required
    def api_workspace_activity(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        limit = min(request.args.get("limit", 50, type=int), 200)
        obj_type = request.args.get("object_type", "")
        with db() as conn:
            aggregate_workspace_activity(conn, workspace_id)
            query = """SELECT wa.*, u.email AS actor_email FROM workspace_activity wa
                       LEFT JOIN users u ON u.id = wa.actor_id WHERE wa.workspace_id=?"""
            params: list = [workspace_id]
            if obj_type:
                query += " AND wa.object_type=?"
                params.append(obj_type)
            query += " ORDER BY wa.created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/workspaces/<int:workspace_id>/search")
    @login_required
    def api_workspace_search(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        q = request.args.get("q", "").strip()
        if not q or len(q) < 2:
            return jsonify([])
        like = f"%{q}%"
        results = []
        with db() as conn:
            for r in conn.execute(
                "SELECT id, name, slug FROM stores WHERE workspace_id=? AND (name LIKE ? OR slug LIKE ?) LIMIT 10",
                (workspace_id, like, like),
            ).fetchall():
                results.append({"type": "store", "id": r["id"], "label": r["name"], "href": f"/manage/{r['slug']}"})
            for r in conn.execute(
                """SELECT cp.id, cp.full_name, cp.email, cp.customer_code FROM customer_profiles cp
                   WHERE cp.workspace_id=? AND (
                     cp.full_name LIKE ? OR cp.email LIKE ? OR cp.customer_code LIKE ?
                     OR cp.phone LIKE ? OR cp.company LIKE ?
                     OR cp.id IN (
                       SELECT ctl.customer_id FROM customer_tag_links ctl
                       JOIN customer_tags ct ON ct.id = ctl.tag_id
                       WHERE ct.name LIKE ?
                     )
                   ) LIMIT 10""",
                (workspace_id, like, like, like, like, like, like),
            ).fetchall():
                results.append({"type": "contact", "id": r["id"], "label": r["full_name"] or r["email"], "href": "/app/contacts"})
            for r in conn.execute(
                """SELECT wm.user_id AS id, u.email, u.display_name FROM workspace_members wm
                   JOIN users u ON u.id = wm.user_id
                   WHERE wm.workspace_id=? AND wm.status='active'
                     AND (u.email LIKE ? OR COALESCE(u.display_name,'') LIKE ?) LIMIT 10""",
                (workspace_id, like, like),
            ).fetchall():
                label = r["display_name"] or r["email"]
                results.append({"type": "member", "id": r["id"], "label": label, "href": "/app/team"})
            for r in conn.execute(
                """SELECT id, title FROM tasks WHERE workspace_id=? AND status != 'archived'
                   AND (title LIKE ? OR description LIKE ?) LIMIT 10""",
                (workspace_id, like, like),
            ).fetchall():
                results.append({"type": "task", "id": r["id"], "label": r["title"], "href": "/app/operations"})
            for r in conn.execute(
                """SELECT cp.id, cp.full_name, cp.email FROM customer_profiles cp
                   JOIN contact_type_links ctl ON ctl.contact_id = cp.id
                   WHERE cp.workspace_id=? AND ctl.type LIKE ? LIMIT 5""",
                (workspace_id, like),
            ).fetchall():
                results.append({"type": "contact", "id": r["id"], "label": f"{r['full_name'] or r['email']} (type match)", "href": "/app/contacts"})
            for r in conn.execute(
                """SELECT fr.id, fr.comment, s.name AS store_name FROM feedback_records fr
                   JOIN stores s ON s.id=fr.store_id
                   WHERE s.workspace_id=? AND fr.comment LIKE ? LIMIT 10""",
                (workspace_id, like),
            ).fetchall():
                results.append({"type": "feedback", "id": r["id"], "label": (r["comment"] or "")[:60] or "Feedback", "href": "/app/customers#feedback"})
            if _table_exists(conn, "qr_experiences"):
                for r in conn.execute(
                    """SELECT e.id, e.name, e.status, s.slug AS store_slug
                       FROM qr_experiences e
                       LEFT JOIN stores s ON s.id = e.store_id
                       WHERE e.workspace_id=? AND e.status!='archived' AND e.name LIKE ? LIMIT 10""",
                    (workspace_id, like),
                ).fetchall():
                    href = (
                        f"/manage/{r['store_slug']}/landing-qr#experience/{r['id']}"
                        if r["store_slug"]
                        else f"/app/store#experience/{r['id']}"
                    )
                    results.append({"type": "qr_experience", "id": r["id"], "label": r["name"], "href": href})
            if _table_exists(conn, "bookings"):
                for r in conn.execute(
                    """SELECT id, title, customer_name FROM bookings
                       WHERE workspace_id=? AND status!='cancelled'
                         AND (title LIKE ? OR customer_name LIKE ?) LIMIT 10""",
                    (workspace_id, like, like),
                ).fetchall():
                    label = r["customer_name"] or r["title"] or "Booking"
                    results.append({"type": "booking", "id": r["id"], "label": label, "href": "/app/booking"})
        return jsonify(results)

    @app.get("/api/workspaces/<int:workspace_id>/settings")
    @login_required
    def api_workspace_settings_get(workspace_id):
        uid = user_id()
        row = get_workspace_or_404(uid, workspace_id)
        settings = {}
        if row["settings_json"]:
            try:
                settings = json.loads(row["settings_json"])
            except json.JSONDecodeError:
                _log.debug("workspace_settings_json_parse_failed", exc_info=True, extra={"op": "api_workspace_settings_get"})
                pass
        branding = row["branding"]
        if isinstance(branding, str) and branding.strip():
            try:
                branding = json.loads(branding)
            except json.JSONDecodeError:
                branding = {}
        elif not isinstance(branding, dict):
            branding = branding or {}
        with db() as conn:
            ws_count = _accessible_workspace_count(conn, uid)
            is_owner = _workspace_owner(conn, workspace_id, uid)
        return jsonify({
            "name": row["name"], "logo_url": row["logo_url"], "timezone": row["timezone"],
            "language": row["language"], "region": row["region"], "currency": row["currency"],
            "default_store_id": row["default_store_id"], "branding": branding,
            "extra": settings,
            "can_delete": is_owner and ws_count >= 2,
            "workspace_count": ws_count,
        })

    @app.post("/api/workspaces/<int:workspace_id>/settings")
    @login_required
    def api_workspace_settings_save(workspace_id):
        uid = user_id()
        get_workspace_or_404(uid, workspace_id)
        data = request.get_json(silent=True) or {}
        extra = data.pop("extra", None)
        with db() as conn:
            row = conn.execute(
                "SELECT name, logo_url, timezone, language, region, currency, default_store_id, branding, settings_json FROM workspaces WHERE id=?",
                (workspace_id,),
            ).fetchone()
            branding_val = data.get("branding", row["branding"])
            if isinstance(branding_val, dict):
                branding_val = json.dumps(branding_val)
            from i18n_platform import normalize_language, set_active_language

            lang = normalize_language(data.get("language", row["language"]))
            conn.execute(
                """UPDATE workspaces SET name=?, logo_url=?, timezone=?, language=?,
                   region=?, currency=?, default_store_id=?, branding=?, settings_json=?, updated_at=?
                   WHERE id=?""",
                (
                    data.get("name", row["name"]), data.get("logo_url", row["logo_url"]),
                    data.get("timezone", row["timezone"]), lang,
                    data.get("region", row["region"]), data.get("currency", row["currency"]),
                    data.get("default_store_id", row["default_store_id"]), branding_val,
                    json.dumps(extra) if extra is not None else row["settings_json"], _now(), workspace_id,
                ),
            )
            log_workspace_activity(conn, workspace_id, "settings_updated", "Workspace settings saved", actor_id=uid)
        # Apply workspace language to this user's UI immediately
        set_active_language(lang)
        from flask import make_response
        from i18n_platform import LANG_COOKIE, language_meta, translate

        body = {
            "ok": True,
            "language": lang,
            "reload": True,
            "message": translate("settings.saved", lang),
            "dir": language_meta(lang).get("dir", "ltr"),
        }
        resp = make_response(jsonify(body))
        resp.set_cookie(LANG_COOKIE, lang, max_age=60 * 60 * 24 * 365, samesite="Lax", path="/")
        return resp

    app.active_workspace_id = active_workspace_id
    app.log_workspace_activity = log_workspace_activity
