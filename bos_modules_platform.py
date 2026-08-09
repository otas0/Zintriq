"""Business OS module APIs — organizations, catalog, orders, team, tags, assets, documents, operations."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import abort, jsonify, request, session

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    store_id INTEGER,
    customer_id INTEGER,
    reference TEXT,
    amount REAL NOT NULL DEFAULT 0,
    status TEXT DEFAULT 'pending',
    line_items TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_orders_workspace ON orders(workspace_id, created_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_bos_modules_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)


def register_bos_modules_platform(app) -> None:
    from app import current_user, db, login_required
    from bos.services.organization import ensure_default_organization, get_organization, update_organization

    def user_id():
        user = current_user()
        if not user:
            abort(401)
        return user["id"]

    def active_workspace_id(uid: int) -> int:
        ws_id = session.get("active_workspace_id")
        if ws_id:
            with db() as conn:
                if conn.execute(
                    "SELECT 1 FROM workspace_members WHERE user_id=? AND workspace_id=? AND status='active'",
                    (uid, ws_id),
                ).fetchone():
                    return int(ws_id)
        with db() as conn:
            row = conn.execute(
                """SELECT w.id FROM workspaces w
                   JOIN workspace_members wm ON wm.workspace_id = w.id
                   WHERE wm.user_id=? AND wm.status='active' ORDER BY w.id LIMIT 1""",
                (uid,),
            ).fetchone()
        if not row:
            abort(404)
        return int(row["id"])

    def ws_access(conn, uid: int, ws_id: int) -> bool:
        return bool(conn.execute(
            "SELECT 1 FROM workspace_members WHERE user_id=? AND workspace_id=? AND status='active'",
            (uid, ws_id),
        ).fetchone())

    def emit_mod(conn, event_type, object_type, object_id, ws_id, uid, title, **kw):
        try:
            from bos.events import emit
            emit(conn, event_type, object_type, object_id, workspace_id=ws_id, user_id=uid,
                 actor="owner", title=title, **kw)
        except Exception:
            pass

    @app.get("/api/organizations/current")
    @login_required
    def api_org_current():
        uid = user_id()
        with db() as conn:
            org = ensure_default_organization(conn, uid)
            ws_count = conn.execute(
                """SELECT COUNT(*) AS c FROM workspaces w
                   JOIN organizations o ON o.id = w.organization_id WHERE o.owner_id=?""",
                (uid,),
            ).fetchone()["c"]
        return jsonify({**org, "workspace_count": ws_count})

    @app.patch("/api/organizations/<int:org_id>")
    @login_required
    def api_org_update(org_id):
        uid = user_id()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            org = get_organization(conn, org_id, uid)
            if not org:
                abort(404)
            name = (data.get("name") or org["name"]).strip()
            status = data.get("status") or org.get("status") or "active"
            update_organization(conn, org_id, uid, name, status)
            row = conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
        return jsonify(dict(row))

    @app.get("/api/catalog")
    @login_required
    def api_catalog_list():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        q = request.args.get("q", "").strip().lower()
        with db() as conn:
            if not ws_access(conn, uid, ws_id):
                abort(403)
            sql = """SELECT i.*, s.name AS store_name, s.slug AS store_slug
                     FROM items i JOIN stores s ON s.id = i.store_id
                     WHERE s.workspace_id = ?"""
            params: list = [ws_id]
            if q:
                sql += " AND (LOWER(i.name) LIKE ? OR LOWER(COALESCE(i.sku,'')) LIKE ?)"
                params.extend([f"%{q}%", f"%{q}%"])
            sql += " ORDER BY i.updated_at DESC, i.id DESC"
            rows = conn.execute(sql, params).fetchall()
        return jsonify([_catalog_row(r) for r in rows])

    @app.get("/api/catalog/summary")
    @login_required
    def api_catalog_summary():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        with db() as conn:
            if not ws_access(conn, uid, ws_id):
                abort(403)
            c = conn.execute(
                """SELECT COUNT(*) AS c FROM items i JOIN stores s ON s.id=i.store_id
                   WHERE s.workspace_id=?""",
                (ws_id,),
            ).fetchone()["c"]
        return jsonify({"total": c})

    @app.get("/api/catalog/<int:item_id>")
    @login_required
    def api_catalog_detail(item_id):
        uid = user_id()
        with db() as conn:
            row = conn.execute(
                """SELECT i.*, s.name AS store_name, s.slug AS store_slug, s.workspace_id
                   FROM items i JOIN stores s ON s.id = i.store_id WHERE i.id=?""",
                (item_id,),
            ).fetchone()
            if not row or not ws_access(conn, uid, row["workspace_id"]):
                abort(404)
        return jsonify(_catalog_row(row))

    @app.patch("/api/catalog/<int:item_id>")
    @login_required
    def api_catalog_update(item_id):
        uid = user_id()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            row = conn.execute(
                """SELECT i.*, s.workspace_id FROM items i
                   JOIN stores s ON s.id=i.store_id WHERE i.id=?""",
                (item_id,),
            ).fetchone()
            if not row or not ws_access(conn, uid, row["workspace_id"]):
                abort(404)
            fields = []
            params = []
            for col in ("name", "price", "description", "sku", "status", "inventory"):
                if col in data:
                    fields.append(f"{col}=?")
                    params.append(data[col])
            if fields:
                fields.append("updated_at=?")
                params.append(_now())
                params.append(item_id)
                conn.execute(f"UPDATE items SET {', '.join(fields)} WHERE id=?", params)
                emit_mod(conn, "catalog.updated", "catalog", item_id, row["workspace_id"], uid,
                         f"Product updated: {data.get('name', row['name'])}")
            updated = conn.execute(
                """SELECT i.*, s.name AS store_name, s.slug AS store_slug
                   FROM items i JOIN stores s ON s.id=i.store_id WHERE i.id=?""",
                (item_id,),
            ).fetchone()
        return jsonify(_catalog_row(updated))

    @app.get("/api/transactions")
    @login_required
    def api_transactions_list():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        with db() as conn:
            if not ws_access(conn, uid, ws_id):
                abort(403)
            rows = conn.execute(
                """SELECT o.*, cp.full_name AS customer_name, s.name AS store_name
                   FROM orders o
                   LEFT JOIN customer_profiles cp ON cp.id = o.customer_id
                   LEFT JOIN stores s ON s.id = o.store_id
                   WHERE o.workspace_id=? ORDER BY o.created_at DESC""",
                (ws_id,),
            ).fetchall()
        return jsonify([_order_row(r) for r in rows])

    @app.post("/api/transactions")
    @login_required
    def api_transactions_create():
        uid = user_id()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_workspace_id(uid))
        with db() as conn:
            if not ws_access(conn, uid, ws_id):
                abort(403)
            ref = (data.get("reference") or f"ORD-{_now()[:10].replace('-', '')}").strip()
            cur = conn.execute(
                """INSERT INTO orders (workspace_id, store_id, customer_id, reference, amount, status, line_items, notes, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ws_id, data.get("store_id"), data.get("customer_id"), ref,
                    float(data.get("amount") or 0), data.get("status") or "pending",
                    json.dumps(data.get("line_items") or []), data.get("notes") or "", _now(),
                ),
            )
            oid = cur.lastrowid
            from bos.collaboration import stamp_create
            stamp_create(conn, "orders", oid, uid)
            emit_mod(conn, "order.created", "order", oid, ws_id, uid, f"Order {ref} created",
                     metadata={"amount": data.get("amount")})
            row = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return jsonify(_order_row(row)), 201

    @app.patch("/api/transactions/<int:order_id>")
    @login_required
    def api_transactions_update(order_id):
        uid = user_id()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row or not ws_access(conn, uid, row["workspace_id"]):
                abort(404)
            fields, params = [], []
            for col in ("status", "amount", "notes", "customer_id", "store_id"):
                if col in data:
                    fields.append(f"{col}=?")
                    params.append(data[col])
            if fields:
                fields.append("updated_at=?")
                params.append(_now())
                params.append(order_id)
                conn.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id=?", params)
                if data.get("status") == "completed":
                    emit_mod(conn, "order.completed", "order", order_id, row["workspace_id"], uid,
                             "Order completed", metadata={"amount": row["amount"]})
            updated = conn.execute(
                """SELECT o.*, cp.full_name AS customer_name, s.name AS store_name
                   FROM orders o LEFT JOIN customer_profiles cp ON cp.id=o.customer_id
                   LEFT JOIN stores s ON s.id=o.store_id WHERE o.id=?""",
                (order_id,),
            ).fetchone()
        return jsonify(_order_row(updated))

    @app.post("/api/transactions/batch")
    @login_required
    def api_transactions_batch():
        uid = user_id()
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        ids = [int(i) for i in (data.get("ids") or [])]
        if not ids:
            return jsonify({"error": "No orders selected"}), 400
        with db() as conn:
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT id, workspace_id FROM orders WHERE id IN ({placeholders})", ids,
            ).fetchall()
            valid_ids = [r["id"] for r in rows if ws_access(conn, uid, r["workspace_id"])]
            if not valid_ids:
                return jsonify({"error": "No accessible orders"}), 403
            ph = ",".join("?" * len(valid_ids))
            if action == "archive":
                conn.execute(f"UPDATE orders SET status='archived', updated_at=? WHERE id IN ({ph})",
                             [_now(), *valid_ids])
            elif action == "delete":
                conn.execute(f"DELETE FROM orders WHERE id IN ({ph})", valid_ids)
            elif action == "complete":
                conn.execute(f"UPDATE orders SET status='completed', updated_at=? WHERE id IN ({ph})",
                             [_now(), *valid_ids])
            else:
                return jsonify({"error": "Unknown action"}), 400
        return jsonify({"ok": True, "count": len(valid_ids)})

    @app.get("/api/tags")
    @login_required
    def api_tags_list():
        uid = user_id()
        with db() as conn:
            rows = conn.execute(
                """SELECT t.*, (SELECT COUNT(*) FROM customer_tag_links l WHERE l.tag_id=t.id) AS usage_count
                   FROM customer_tags t WHERE t.owner_id=? ORDER BY t.name""",
                (uid,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/tags")
    @login_required
    def api_tags_create():
        uid = user_id()
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        with db() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO customer_tags (owner_id, name, color) VALUES (?, ?, ?)",
                    (uid, name, data.get("color") or "#888888"),
                )
                row = conn.execute("SELECT * FROM customer_tags WHERE id=?", (cur.lastrowid,)).fetchone()
            except Exception:
                return jsonify({"error": "Tag already exists"}), 409
        return jsonify(dict(row)), 201

    @app.delete("/api/tags/<int:tag_id>")
    @login_required
    def api_tags_delete(tag_id):
        uid = user_id()
        with db() as conn:
            conn.execute("DELETE FROM customer_tag_links WHERE tag_id=?", (tag_id,))
            conn.execute("DELETE FROM customer_tags WHERE id=? AND owner_id=?", (tag_id, uid))
        return jsonify({"ok": True})

    @app.get("/api/assets")
    @login_required
    def api_assets_list():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        assets = []
        with db() as conn:
            if not ws_access(conn, uid, ws_id):
                abort(403)
            for r in conn.execute(
                """SELECT q.id, q.name, q.code, 'store_qr' AS asset_type, s.name AS store_name, s.slug AS store_slug
                   FROM qr_codes q JOIN stores s ON s.id=q.store_id WHERE s.workspace_id=?""",
                (ws_id,),
            ).fetchall():
                assets.append({**dict(r), "href": f"/manage/{r['store_slug']}/qr-codes"})
            for r in conn.execute(
                """SELECT bc.id, bc.card_code AS code, 'business_card' AS asset_type, s.name AS store_name, s.slug AS store_slug
                   FROM business_cards bc JOIN stores s ON s.id=bc.store_id WHERE s.workspace_id=?""",
                (ws_id,),
            ).fetchall():
                assets.append({**dict(r), "name": f"Business card {r['code']}", "href": f"/manage/{r['store_slug']}/business-cards"})
            for r in conn.execute(
                """SELECT qp.id, qp.name, qp.product_code AS code, 'product_qr' AS asset_type, s.name AS store_name, s.slug AS store_slug
                   FROM qr_products qp JOIN stores s ON s.id=qp.store_id WHERE s.workspace_id=?""",
                (ws_id,),
            ).fetchall():
                assets.append({**dict(r), "href": f"/manage/{r['store_slug']}/product-qr"})
            for r in conn.execute(
                """SELECT e.id, e.name, 'event' AS asset_type, s.name AS store_name, s.slug AS store_slug
                   FROM events e JOIN stores s ON s.id=e.store_id WHERE s.workspace_id=?""",
                (ws_id,),
            ).fetchall():
                assets.append({**dict(r), "code": "", "href": f"/manage/{r['store_slug']}/event-passes"})
            for r in conn.execute(
                """SELECT c.id, c.name, c.point_code AS code, 'check_in' AS asset_type, s.name AS store_name, s.slug AS store_slug
                   FROM check_in_points c JOIN stores s ON s.id=c.store_id WHERE s.workspace_id=?""",
                (ws_id,),
            ).fetchall():
                assets.append({**dict(r), "href": f"/manage/{r['store_slug']}/check-in"})
        return jsonify(assets)

    @app.get("/api/documents")
    @login_required
    def api_documents_list():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        with db() as conn:
            if not ws_access(conn, uid, ws_id):
                abort(403)
            rows = conn.execute(
                """SELECT cf.*, cp.full_name AS customer_name, cp.id AS customer_id
                   FROM customer_files cf
                   JOIN customer_profiles cp ON cp.id = cf.customer_id
                   WHERE cp.workspace_id=? OR (cp.workspace_id IS NULL AND cp.owner_id=?)
                   ORDER BY cf.created_at DESC""",
                (ws_id, uid),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/bos/summary")
    @login_required
    def api_bos_summary():
        uid = user_id()
        ws_id = active_workspace_id(uid)
        with db() as conn:
            org = ensure_default_organization(conn, uid)
            ws_count = conn.execute(
                """SELECT COUNT(*) AS c FROM workspace_members wm
                   WHERE wm.user_id=? AND wm.status='active'""",
                (uid,),
            ).fetchone()["c"]
            catalog_count = conn.execute(
                """SELECT COUNT(*) AS c FROM items i JOIN stores s ON s.id=i.store_id
                   WHERE s.workspace_id=?""",
                (ws_id,),
            ).fetchone()["c"]
            customer_count = conn.execute(
                "SELECT COUNT(*) AS c FROM customer_profiles WHERE owner_id=? AND status != 'archived'",
                (uid,),
            ).fetchone()["c"]
            order_count = conn.execute(
                "SELECT COUNT(*) AS c FROM orders WHERE workspace_id=?", (ws_id,),
            ).fetchone()["c"]
        return jsonify({
            "organization": org["name"],
            "workspaces": ws_count,
            "catalog": catalog_count,
            "customers": customer_count,
            "orders": order_count,
        })


def _catalog_row(row) -> dict:
    d = dict(row)
    status = d.get("status") or "published"
    if status == "published":
        status = "active"
    return {
        "id": d["id"],
        "name": d["name"],
        "sku": d.get("sku") or "",
        "price": d.get("price") or 0,
        "description": d.get("description") or "",
        "status": status,
        "inventory": d.get("inventory"),
        "store_id": d["store_id"],
        "store_name": d.get("store_name"),
        "store_slug": d.get("store_slug"),
        "image_url": d.get("image_url"),
        "updated_at": d.get("updated_at"),
        "href": f"/manage/{d.get('store_slug')}/items/{d['id']}/edit" if d.get("store_slug") else None,
    }


def _order_row(row) -> dict:
    d = dict(row)
    line_items = d.get("line_items") or "[]"
    if isinstance(line_items, str):
        line_items = json.loads(line_items)
    return {
        "id": d["id"],
        "workspace_id": d["workspace_id"],
        "reference": d.get("reference") or "",
        "amount": d.get("amount") or 0,
        "status": d.get("status") or "pending",
        "customer_id": d.get("customer_id"),
        "customer_name": d.get("customer_name"),
        "store_id": d.get("store_id"),
        "store_name": d.get("store_name"),
        "notes": d.get("notes") or "",
        "line_items": line_items,
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }
