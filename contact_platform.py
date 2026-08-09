"""Contact Platform — universal relationship management for Business OS.

Physical storage uses `customer_profiles` (single source of truth) plus contact extension tables.
"""

from __future__ import annotations

import csv
import io
import json
import secrets
from datetime import datetime

from flask import abort, jsonify, request, session

CONTACT_STATUSES = ("active", "inactive", "archived")
CONTACT_CATEGORIES = ("person", "organization")
CONTACT_TYPES = (
    "customer", "supplier", "vendor", "partner", "contractor",
    "distributor", "organization", "other",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contact_type_links (
    contact_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    PRIMARY KEY (contact_id, type),
    FOREIGN KEY(contact_id) REFERENCES customer_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_contact_type_links_type ON contact_type_links(type);

CREATE TABLE IF NOT EXISTS contact_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER,
    from_contact_id INTEGER NOT NULL,
    to_contact_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_contact_id, to_contact_id, relationship_type),
    FOREIGN KEY(from_contact_id) REFERENCES customer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY(to_contact_id) REFERENCES customer_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_contact_relationships_from ON contact_relationships(from_contact_id);
CREATE INDEX IF NOT EXISTS idx_contact_relationships_to ON contact_relationships(to_contact_id);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_contact_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(customer_profiles)")}
    for col, ddl in (
        ("category", "TEXT DEFAULT 'person'"),
        ("website", "TEXT"),
        ("timezone", "TEXT"),
        ("position", "TEXT"),
        ("tax_number", "TEXT"),
        ("industry", "TEXT"),
        ("organization_id", "INTEGER"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE customer_profiles ADD COLUMN {col} {ddl}")
    # Backfill: existing profiles are people with customer type
    for row in conn.execute("SELECT id FROM customer_profiles").fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO contact_type_links (contact_id, type) VALUES (?, 'customer')",
            (row["id"],),
        )


def register_contact_platform(app) -> None:
    from app import current_user, db, login_required
    from bos.permissions import has_permission, require_permission

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    def ws_id() -> int | None:
        return session.get("active_workspace_id")

    def _norm_email(v):
        return (v or "").strip().lower() or None

    def _norm_phone(v):
        return "".join(c for c in (v or "") if c.isdigit() or c == "+") or None

    def _contact_code():
        return secrets.token_hex(4)

    def get_contact(conn, contact_id: int, owner_id: int):
        row = conn.execute(
            "SELECT * FROM customer_profiles WHERE id=? AND owner_id=?", (contact_id, owner_id),
        ).fetchone()
        if not row:
            abort(404)
        return row

    def _types(conn, contact_id: int) -> list[str]:
        return [r["type"] for r in conn.execute(
            "SELECT type FROM contact_type_links WHERE contact_id=? ORDER BY type", (contact_id,),
        ).fetchall()]

    def contact_to_api(conn, row, owner_id: int) -> dict:
        cid = row["id"]
        tags = conn.execute(
            """SELECT ct.* FROM customer_tags ct
               JOIN customer_tag_links ctl ON ctl.tag_id = ct.id WHERE ctl.customer_id=?""",
            (cid,),
        ).fetchall()
        org_name = None
        if row["organization_id"] if "organization_id" in row.keys() else None:
            org = conn.execute(
                "SELECT full_name, preferred_name FROM customer_profiles WHERE id=?",
                (row["organization_id"],),
            ).fetchone()
            if org:
                org_name = org["preferred_name"] or org["full_name"]
        types = _types(conn, cid)
        name = row["preferred_name"] or row["full_name"] or row["email"] or f"Contact #{row['customer_code']}"
        return {
            "id": cid,
            "contact_id": row["customer_code"],
            "category": row["category"] if "category" in row.keys() else "person",
            "types": types,
            "status": row["status"] or "active",
            "name": name,
            "display_name": name,
            "full_name": row["full_name"],
            "preferred_name": row["preferred_name"],
            "email": row["email"],
            "phone": row["phone"],
            "website": row["website"] if "website" in row.keys() else None,
            "address": row["address"],
            "timezone": row["timezone"] if "timezone" in row.keys() else None,
            "language": row["language"],
            "company": row["company"],
            "position": row["position"] if "position" in row.keys() else None,
            "tax_number": row["tax_number"] if "tax_number" in row.keys() else None,
            "industry": row["industry"] if "industry" in row.keys() else None,
            "avatar_url": row["avatar_url"],
            "organization_id": row["organization_id"] if "organization_id" in row.keys() else None,
            "organization_name": org_name,
            "workspace_id": row["workspace_id"],
            "tags": [dict(t) for t in tags],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_activity_at": row["last_activity_at"],
            "created_by": row["created_by"] if "created_by" in row.keys() else None,
            "updated_by": row["updated_by"] if "updated_by" in row.keys() else None,
        }

    def _emit(conn, event_type, contact_id, title, **kw):
        from bos.events import emit
        ws = kw.pop("workspace_id", None) or ws_id()
        emit(conn, event_type, "contact", contact_id, workspace_id=ws, user_id=uid(),
             actor="member", title=title, href="/app/contacts", **kw)

    def _log_activity(conn, contact_id, owner_id, activity_type, title, **kw):
        conn.execute(
            """INSERT INTO customer_activities
               (customer_id, owner_id, store_id, activity_type, title, detail, related_object_type, related_object_id, source, actor)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                contact_id, owner_id, kw.get("store_id"), activity_type, title,
                kw.get("detail") or "", kw.get("related_object_type"), kw.get("related_object_id"),
                kw.get("source") or "contact", kw.get("actor") or "owner",
            ),
        )
        conn.execute(
            "UPDATE customer_profiles SET last_activity_at=?, updated_at=? WHERE id=?",
            (_now(), _now(), contact_id),
        )

    def _check_ws_perm(conn, permission: str):
        ws = ws_id()
        if ws and not has_permission(conn, uid(), int(ws), permission):
            abort(403)

    def list_contacts(conn, owner_id: int, filters: dict) -> list:
        query = "SELECT * FROM customer_profiles WHERE owner_id=?"
        params: list = [owner_id]
        if filters.get("workspace_id"):
            query += " AND workspace_id=?"
            params.append(int(filters["workspace_id"]))
        if filters.get("status"):
            query += " AND status=?"
            params.append(filters["status"])
        elif filters.get("view") == "archived":
            query += " AND status='archived'"
        elif filters.get("view") != "archived":
            query += " AND status != 'archived'"
        if filters.get("category"):
            query += " AND category=?"
            params.append(filters["category"])
        if filters.get("view") == "recent":
            query += " AND created_at >= date('now', '-14 days')"
        if filters.get("type"):
            query += " AND id IN (SELECT contact_id FROM contact_type_links WHERE type=?)"
            params.append(filters["type"])
        if filters.get("tag_id"):
            query += " AND id IN (SELECT customer_id FROM customer_tag_links WHERE tag_id=?)"
            params.append(int(filters["tag_id"]))
        if filters.get("organization_id"):
            query += " AND organization_id=?"
            params.append(int(filters["organization_id"]))
        if filters.get("q"):
            like = f"%{filters['q']}%"
            query += " AND (full_name LIKE ? OR preferred_name LIKE ? OR email LIKE ? OR phone LIKE ? OR company LIKE ? OR customer_code LIKE ?)"
            params.extend([like] * 6)
        sort = filters.get("sort", "last_activity_at")
        if sort not in ("full_name", "created_at", "last_activity_at", "company"):
            sort = "last_activity_at"
        query += f" ORDER BY {sort} DESC LIMIT 500"
        return conn.execute(query, params).fetchall()

    @app.get("/api/contacts/context")
    @login_required
    def api_contacts_context():
        oid = uid()
        with db() as conn:
            from bos.permissions import member_role, permissions_for_role
            ws = ws_id()
            role = member_role(conn, oid, int(ws)) if ws else None
            perms = sorted(permissions_for_role(conn, role or "owner"))
        return jsonify({"permissions": perms, "types": list(CONTACT_TYPES), "categories": list(CONTACT_CATEGORIES)})

    @app.get("/api/contacts/summary")
    @login_required
    def api_contacts_summary():
        oid = uid()
        with db() as conn:
            _check_ws_perm(conn, "contact.read")
            ws_filter = " AND workspace_id=?" if ws_id() else ""
            params = [oid]
            if ws_id():
                params.append(ws_id())
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM customer_profiles WHERE owner_id=? AND status!='archived'{ws_filter}",
                params,
            ).fetchone()["c"]
            people = conn.execute(
                f"SELECT COUNT(*) AS c FROM customer_profiles WHERE owner_id=? AND category='person' AND status!='archived'{ws_filter}",
                params,
            ).fetchone()["c"]
            orgs = conn.execute(
                f"SELECT COUNT(*) AS c FROM customer_profiles WHERE owner_id=? AND category='organization' AND status!='archived'{ws_filter}",
                params,
            ).fetchone()["c"]
            recent = conn.execute(
                f"SELECT * FROM customer_profiles WHERE owner_id=? AND status!='archived'{ws_filter} ORDER BY created_at DESC LIMIT 5",
                params,
            ).fetchall()
            recent_api = [contact_to_api(conn, r, oid) for r in recent]
        return jsonify({
            "total": total, "people": people, "organizations": orgs,
            "recent": recent_api,
        })

    @app.get("/api/contacts")
    @login_required
    def api_contacts_list():
        oid = uid()
        filters = {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", ""),
            "type": request.args.get("type", ""),
            "category": request.args.get("category", ""),
            "tag_id": request.args.get("tag_id", ""),
            "organization_id": request.args.get("organization_id", ""),
            "view": request.args.get("view", "all"),
            "sort": request.args.get("sort", "last_activity_at"),
            "workspace_id": request.args.get("workspace_id") or ws_id(),
        }
        with db() as conn:
            _check_ws_perm(conn, "contact.read")
            rows = list_contacts(conn, oid, filters)
            return jsonify([contact_to_api(conn, r, oid) for r in rows])

    @app.get("/api/contacts/duplicates")
    @login_required
    def api_contacts_duplicates():
        oid = uid()
        with db() as conn:
            _check_ws_perm(conn, "contact.read")
            dupes = []
            seen = set()
            for row in conn.execute(
                "SELECT * FROM customer_profiles WHERE owner_id=? AND status!='archived'", (oid,),
            ).fetchall():
                keys = []
                if row["email"]:
                    keys.append(f"email:{row['email'].lower()}")
                if row["phone"]:
                    keys.append(f"phone:{row['phone']}")
                if row["full_name"] and row["company"]:
                    keys.append(f"nc:{row['full_name'].lower()}|{row['company'].lower()}")
                for k in keys:
                    if k in seen:
                        dupes.append(contact_to_api(conn, row, oid))
                        break
                    seen.add(k)
            # Group by email
            groups = {}
            for row in conn.execute(
                """SELECT * FROM customer_profiles WHERE owner_id=? AND email IS NOT NULL AND email!='' AND status!='archived'""",
                (oid,),
            ).fetchall():
                key = row["email"].lower()
                groups.setdefault(key, []).append(row)
            for email, rows in groups.items():
                if len(rows) > 1:
                    dupes.extend([contact_to_api(conn, r, oid) for r in rows])
            # Dedupe by id
            seen_ids = set()
            unique = []
            for d in dupes:
                if d["id"] not in seen_ids:
                    seen_ids.add(d["id"])
                    unique.append(d)
        return jsonify(unique)

    @app.get("/api/contacts/<int:contact_id>")
    @login_required
    def api_contact_detail(contact_id):
        oid = uid()
        with db() as conn:
            _check_ws_perm(conn, "contact.read")
            row = get_contact(conn, contact_id, oid)
            payload = contact_to_api(conn, row, oid)
            payload["timeline"] = [dict(a) for a in conn.execute(
                """SELECT ca.*, s.name AS store_name FROM customer_activities ca
                   LEFT JOIN stores s ON s.id = ca.store_id
                   WHERE ca.customer_id=? ORDER BY ca.created_at DESC LIMIT 100""",
                (contact_id,),
            ).fetchall()]
            payload["notes"] = [dict(n) for n in conn.execute(
                """SELECT n.*, u.email AS author_email FROM customer_notes n
                   LEFT JOIN users u ON u.id = n.author_id
                   WHERE n.customer_id=? ORDER BY n.is_pinned DESC, n.created_at DESC""",
                (contact_id,),
            ).fetchall()]
            payload["documents"] = [dict(f) for f in conn.execute(
                "SELECT * FROM customer_files WHERE customer_id=? ORDER BY created_at DESC", (contact_id,),
            ).fetchall()]
            payload["feedback"] = [dict(f) for f in conn.execute(
                """SELECT fr.id, fr.rating, fr.comment, fr.feedback_type, fr.created_at, s.name AS store_name
                   FROM feedback_records fr JOIN stores s ON s.id=fr.store_id
                   WHERE fr.customer_id=? ORDER BY fr.created_at DESC LIMIT 20""",
                (contact_id,),
            ).fetchall()]
            payload["transactions"] = [dict(o) for o in conn.execute(
                "SELECT id, reference, amount, status, created_at FROM orders WHERE customer_id=? ORDER BY created_at DESC LIMIT 20",
                (contact_id,),
            ).fetchall()]
            payload["tasks"] = [dict(t) for t in conn.execute(
                """SELECT id, title, status, priority, due_date FROM tasks
                   WHERE related_object_id=? AND related_object_type IN ('customer','contact')
                   ORDER BY updated_at DESC LIMIT 20""",
                (contact_id,),
            ).fetchall()]
            payload["relationships"] = [dict(r) for r in conn.execute(
                """SELECT cr.*, cp.full_name AS to_name, cp.category AS to_category
                   FROM contact_relationships cr
                   JOIN customer_profiles cp ON cp.id = cr.to_contact_id
                   WHERE cr.from_contact_id=?""",
                (contact_id,),
            ).fetchall()]
            payload["people"] = [contact_to_api(conn, p, oid) for p in conn.execute(
                "SELECT * FROM customer_profiles WHERE organization_id=? AND owner_id=?", (contact_id, oid),
            ).fetchall()] if (row["category"] if "category" in row.keys() else "person") == "organization" else []
            ratings = conn.execute(
                "SELECT AVG(rating) AS avg, COUNT(*) AS c FROM feedback_records WHERE customer_id=?",
                (contact_id,),
            ).fetchone()
            payload["insights"] = {
                "average_rating": round(ratings["avg"], 1) if ratings and ratings["avg"] else None,
                "feedback_count": int(ratings["c"] or 0) if ratings else 0,
            }
        return jsonify(payload)

    @app.post("/api/contacts")
    @login_required
    def api_contact_create():
        oid = uid()
        data = request.get_json(silent=True) or {}
        name = (data.get("full_name") or data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        with db() as conn:
            _check_ws_perm(conn, "contact.create")
            cur = conn.execute(
                """INSERT INTO customer_profiles
                   (owner_id, workspace_id, customer_code, full_name, preferred_name, email, phone, company,
                    address, language, country, status, category, website, timezone, position, tax_number,
                    industry, organization_id, updated_at, last_activity_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    oid, data.get("workspace_id") or ws_id(), _contact_code(), name,
                    (data.get("preferred_name") or "").strip() or None,
                    _norm_email(data.get("email")), _norm_phone(data.get("phone")),
                    (data.get("company") or "").strip() or None,
                    (data.get("address") or "").strip() or None,
                    data.get("language") or "en", (data.get("country") or "").strip() or None,
                    data.get("status") or "active",
                    data.get("category") or "person",
                    data.get("website"), data.get("timezone"), data.get("position"),
                    data.get("tax_number"), data.get("industry"), data.get("organization_id"),
                    _now(), _now(),
                ),
            )
            cid = cur.lastrowid
            from bos.collaboration import stamp_create
            stamp_create(conn, "customer_profiles", cid, oid)
            types = data.get("types") or ["customer"]
            for t in types:
                if t in CONTACT_TYPES:
                    conn.execute("INSERT OR IGNORE INTO contact_type_links (contact_id, type) VALUES (?, ?)", (cid, t))
            for tag_id in data.get("tag_ids") or []:
                conn.execute("INSERT OR IGNORE INTO customer_tag_links (customer_id, tag_id) VALUES (?, ?)", (cid, int(tag_id)))
            _log_activity(conn, cid, oid, "joined", "Contact created")
            _emit(conn, "contact.created", cid, f"Contact created: {name}")
            row = conn.execute("SELECT * FROM customer_profiles WHERE id=?", (cid,)).fetchone()
            payload = contact_to_api(conn, row, oid)
        return jsonify(payload), 201

    @app.patch("/api/contacts/<int:contact_id>")
    @login_required
    def api_contact_update(contact_id):
        oid = uid()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _check_ws_perm(conn, "contact.update")
            get_contact(conn, contact_id, oid)
            fields = (
                "full_name", "preferred_name", "email", "phone", "company", "address",
                "language", "country", "status", "avatar_url", "category", "website",
                "timezone", "position", "tax_number", "industry", "organization_id",
            )
            updates, params = [], []
            for f in fields:
                if f in data:
                    val = data[f]
                    if f == "email":
                        val = _norm_email(val)
                    elif f == "phone":
                        val = _norm_phone(val)
                    elif isinstance(val, str):
                        val = val.strip() or None
                    updates.append(f"{f}=?")
                    params.append(val)
            if updates:
                updates.extend(["updated_by=?", "updated_at=?"])
                params.extend([oid, _now(), contact_id, oid])
                conn.execute(f"UPDATE customer_profiles SET {', '.join(updates)} WHERE id=? AND owner_id=?", params)
            if "types" in data:
                conn.execute("DELETE FROM contact_type_links WHERE contact_id=?", (contact_id,))
                for t in data["types"]:
                    if t in CONTACT_TYPES:
                        conn.execute("INSERT INTO contact_type_links (contact_id, type) VALUES (?, ?)", (contact_id, t))
            _log_activity(conn, contact_id, oid, "updated", "Contact updated")
            _emit(conn, "contact.updated", contact_id, "Contact updated")
            row = conn.execute("SELECT * FROM customer_profiles WHERE id=?", (contact_id,)).fetchone()
            payload = contact_to_api(conn, row, oid)
        return jsonify(payload)

    @app.post("/api/contacts/<int:contact_id>/archive")
    @login_required
    def api_contact_archive(contact_id):
        oid = uid()
        with db() as conn:
            _check_ws_perm(conn, "contact.archive")
            get_contact(conn, contact_id, oid)
            conn.execute("UPDATE customer_profiles SET status='archived', updated_at=? WHERE id=?", (_now(), contact_id))
            _log_activity(conn, contact_id, oid, "archived", "Contact archived")
            _emit(conn, "contact.archived", contact_id, "Contact archived")
        return jsonify({"ok": True})

    @app.post("/api/contacts/<int:contact_id>/restore")
    @login_required
    def api_contact_restore(contact_id):
        oid = uid()
        with db() as conn:
            _check_ws_perm(conn, "contact.update")
            get_contact(conn, contact_id, oid)
            conn.execute("UPDATE customer_profiles SET status='active', updated_at=? WHERE id=?", (_now(), contact_id))
            _log_activity(conn, contact_id, oid, "restored", "Contact restored")
            _emit(conn, "contact.restored", contact_id, "Contact restored")
        return jsonify({"ok": True})

    @app.post("/api/contacts/merge")
    @login_required
    def api_contacts_merge():
        oid = uid()
        data = request.get_json(silent=True) or {}
        primary = int(data.get("primary_id") or 0)
        secondary = int(data.get("secondary_id") or 0)
        if not primary or not secondary or primary == secondary:
            return jsonify({"error": "primary_id and secondary_id required"}), 400
        with db() as conn:
            _check_ws_perm(conn, "contact.merge")
            get_contact(conn, primary, oid)
            sec = get_contact(conn, secondary, oid)
            for tbl, col in (
                ("customer_tag_links", "customer_id"), ("customer_group_members", "customer_id"),
                ("customer_notes", "customer_id"), ("customer_files", "customer_id"),
                ("customer_activities", "customer_id"), ("customer_store_links", "customer_id"),
            ):
                conn.execute(f"UPDATE {tbl} SET {col}=? WHERE {col}=?", (primary, secondary))
            conn.execute("UPDATE feedback_records SET customer_id=? WHERE customer_id=?", (primary, secondary))
            conn.execute("UPDATE orders SET customer_id=? WHERE customer_id=?", (primary, secondary))
            conn.execute(
                "UPDATE tasks SET related_object_id=? WHERE related_object_id=? AND related_object_type IN ('customer','contact')",
                (primary, secondary),
            )
            conn.execute("UPDATE customer_profiles SET organization_id=? WHERE organization_id=?", (primary, secondary))
            for t in _types(conn, secondary):
                conn.execute("INSERT OR IGNORE INTO contact_type_links (contact_id, type) VALUES (?, ?)", (primary, t))
            conn.execute("DELETE FROM contact_type_links WHERE contact_id=?", (secondary,))
            conn.execute("DELETE FROM contact_relationships WHERE from_contact_id=? OR to_contact_id=?", (secondary, secondary))
            conn.execute("DELETE FROM customer_profiles WHERE id=?", (secondary,))
            _log_activity(conn, primary, oid, "merge", f"Merged contact {sec['customer_code']}", detail=sec["full_name"])
            _emit(conn, "contact.merged", primary, "Contacts merged", metadata={"secondary_id": secondary})
        return jsonify({"ok": True, "primary_id": primary})

    @app.post("/api/contacts/batch")
    @login_required
    def api_contacts_batch():
        oid = uid()
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        ids = [int(i) for i in (data.get("ids") or [])]
        if not ids:
            return jsonify({"error": "No contacts selected"}), 400
        with db() as conn:
            ph = ",".join("?" * len(ids))
            valid = [r["id"] for r in conn.execute(
                f"SELECT id FROM customer_profiles WHERE owner_id=? AND id IN ({ph})", [oid, *ids],
            ).fetchall()]
            ws = ws_id()
            def _perm(key):
                return not ws or has_permission(conn, oid, int(ws), key)
            if action == "archive" and _perm("contact.archive"):
                conn.execute(f"UPDATE customer_profiles SET status='archived', updated_at=? WHERE id IN ({','.join('?'*len(valid))})", [_now(), *valid])
            elif action == "delete" and _perm("contact.delete"):
                conn.execute(f"UPDATE feedback_records SET customer_id=NULL WHERE customer_id IN ({','.join('?'*len(valid))})", valid)
                conn.execute(f"DELETE FROM customer_profiles WHERE id IN ({','.join('?'*len(valid))})", valid)
            elif action == "add_tags" and _perm("contact.update"):
                for cid in valid:
                    for tag_id in data.get("tag_ids") or []:
                        conn.execute("INSERT OR IGNORE INTO customer_tag_links (customer_id, tag_id) VALUES (?, ?)", (cid, int(tag_id)))
            else:
                return jsonify({"error": "Unknown action or permission denied"}), 400
        return jsonify({"ok": True, "count": len(valid)})

    @app.post("/api/contacts/<int:contact_id>/notes")
    @login_required
    def api_contact_note_create(contact_id):
        oid = uid()
        data = request.get_json(silent=True) or {}
        body = (data.get("body") or "").strip()
        if not body:
            return jsonify({"error": "Note body required"}), 400
        with db() as conn:
            _check_ws_perm(conn, "contact.update")
            get_contact(conn, contact_id, oid)
            cur = conn.execute(
                "INSERT INTO customer_notes (customer_id, author_id, body, is_pinned) VALUES (?, ?, ?, ?)",
                (contact_id, oid, body, 1 if data.get("is_pinned") else 0),
            )
            _log_activity(conn, contact_id, oid, "note", "Note added", detail=body[:120])
            _emit(conn, "contact.updated", contact_id, "Note added")
            row = conn.execute("SELECT * FROM customer_notes WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201

    @app.post("/api/contacts/<int:contact_id>/relationships")
    @login_required
    def api_contact_relationship_create(contact_id):
        oid = uid()
        data = request.get_json(silent=True) or {}
        to_id = int(data.get("to_contact_id") or 0)
        rel_type = (data.get("relationship_type") or "related").strip()
        if not to_id:
            return jsonify({"error": "to_contact_id required"}), 400
        with db() as conn:
            _check_ws_perm(conn, "contact.update")
            get_contact(conn, contact_id, oid)
            get_contact(conn, to_id, oid)
            conn.execute(
                """INSERT OR IGNORE INTO contact_relationships
                   (workspace_id, from_contact_id, to_contact_id, relationship_type, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (ws_id(), contact_id, to_id, rel_type, oid),
            )
            _emit(conn, "contact.relationship_created", contact_id, f"Relationship added: {rel_type}",
                  metadata={"to_contact_id": to_id})
            row = conn.execute(
                "SELECT * FROM contact_relationships WHERE from_contact_id=? AND to_contact_id=? AND relationship_type=?",
                (contact_id, to_id, rel_type),
            ).fetchone()
        return jsonify(dict(row)), 201

    @app.delete("/api/contacts/relationships/<int:rel_id>")
    @login_required
    def api_contact_relationship_delete(rel_id):
        oid = uid()
        with db() as conn:
            _check_ws_perm(conn, "contact.update")
            row = conn.execute(
                """SELECT cr.* FROM contact_relationships cr
                   JOIN customer_profiles cp ON cp.id = cr.from_contact_id
                   WHERE cr.id=? AND cp.owner_id=?""",
                (rel_id, oid),
            ).fetchone()
            if not row:
                abort(404)
            conn.execute("DELETE FROM contact_relationships WHERE id=?", (rel_id,))
            _emit(conn, "contact.relationship_removed", row["from_contact_id"], "Relationship removed")
        return jsonify({"ok": True})

    @app.get("/api/contacts/export")
    @login_required
    def api_contacts_export():
        oid = uid()
        with db() as conn:
            _check_ws_perm(conn, "contact.export")
            ids = request.args.get("ids", "")
            if ids:
                id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
                ph = ",".join("?" * len(id_list))
                rows = conn.execute(
                    f"SELECT * FROM customer_profiles WHERE owner_id=? AND id IN ({ph})", [oid, *id_list],
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM customer_profiles WHERE owner_id=?", (oid,)).fetchall()
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "contact_id", "category", "full_name", "preferred_name", "email", "phone", "company",
            "website", "status", "position", "industry", "created_at",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "contact_id": row["customer_code"],
                "category": row["category"] if "category" in row.keys() else "person",
                "full_name": row["full_name"],
                "preferred_name": row["preferred_name"],
                "email": row["email"],
                "phone": row["phone"],
                "company": row["company"],
                "website": row["website"] if "website" in row.keys() else "",
                "status": row["status"],
                "position": row["position"] if "position" in row.keys() else "",
                "industry": row["industry"] if "industry" in row.keys() else "",
                "created_at": row["created_at"],
            })
        return output.getvalue(), 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=contacts.csv"}

    @app.post("/api/contacts/import")
    @login_required
    def api_contacts_import():
        oid = uid()
        data = request.get_json(silent=True) or {}
        rows = data.get("rows") or []
        created = skipped = 0
        with db() as conn:
            _check_ws_perm(conn, "contact.create")
            for row in rows:
                email = _norm_email(row.get("email"))
                phone = _norm_phone(row.get("phone"))
                name = (row.get("full_name") or row.get("name") or "").strip()
                if not name:
                    continue
                existing = None
                if email:
                    existing = conn.execute(
                        "SELECT id FROM customer_profiles WHERE owner_id=? AND lower(email)=?", (oid, email),
                    ).fetchone()
                if not existing and phone:
                    existing = conn.execute(
                        "SELECT id FROM customer_profiles WHERE owner_id=? AND phone=?", (oid, phone),
                    ).fetchone()
                if existing:
                    skipped += 1
                    continue
                cur = conn.execute(
                    """INSERT INTO customer_profiles (owner_id, workspace_id, customer_code, full_name, email, phone, company, status, category, updated_at, last_activity_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
                    (oid, ws_id(), _contact_code(), name, email, phone,
                     (row.get("company") or "").strip() or None,
                     row.get("category") or "person", _now(), _now()),
                )
                cid = cur.lastrowid
                types = row.get("types") or ["customer"]
                if isinstance(types, str):
                    types = [t.strip() for t in types.split(",")]
                for t in types:
                    if t in CONTACT_TYPES:
                        conn.execute("INSERT INTO contact_type_links (contact_id, type) VALUES (?, ?)", (cid, t))
                _log_activity(conn, cid, oid, "import", "Contact imported", source="csv_import")
                created += 1
        return jsonify({"created": created, "skipped": skipped})

    # Legacy alias — customers API redirects conceptually; keep /api/customers working via customer_platform

    app.init_contact_tables = init_contact_tables
