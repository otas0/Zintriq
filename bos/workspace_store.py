"""Internal workspace ↔ store shim.

Zintriq treats **Experience** as the customer-facing object. The legacy
``stores`` row exists only to satisfy ``qr_codes.store_id`` and old routing.
One workspace gets one internal store — never surfaced as a separate product.
"""

from __future__ import annotations

import json


def _column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def workspace_identity(conn, workspace_id: int) -> dict:
    """Business identity for experiences — workspace first, store as fallback."""
    ws = conn.execute(
        "SELECT name, logo_url, branding, settings_json FROM workspaces WHERE id=?",
        (workspace_id,),
    ).fetchone()
    branding: dict = {}
    extra: dict = {}
    if ws:
        raw = ws["branding"] if "branding" in ws.keys() else None
        if isinstance(raw, str) and raw.strip():
            try:
                branding = json.loads(raw)
            except json.JSONDecodeError:
                branding = {}
        elif isinstance(raw, dict):
            branding = raw
        if ws["settings_json"]:
            try:
                extra = json.loads(ws["settings_json"] or "{}")
            except json.JSONDecodeError:
                extra = {}
    store = conn.execute(
        "SELECT id, slug, name, contact, address FROM stores WHERE workspace_id=? ORDER BY id LIMIT 1",
        (workspace_id,),
    ).fetchone()
    business_name = (
        branding.get("business_name")
        or (ws["name"] if ws else None)
        or (store["name"] if store else None)
        or "My Business"
    )
    logo_url = branding.get("logo_url") or (ws["logo_url"] if ws and "logo_url" in ws.keys() else "") or ""
    contact: dict = {}
    for key in ("phone", "email", "address", "website"):
        if extra.get(key):
            contact[key] = extra[key]
        elif branding.get(key):
            contact[key] = branding[key]
        elif store and key in store.keys() and store[key]:
            contact[key] = store[key]
    if store and store["contact"] and "phone" not in contact:
        contact["phone"] = store["contact"]
    return {
        "business_name": str(business_name).strip() or "My Business",
        "logo_url": logo_url,
        "contact": contact,
        "store_id": store["id"] if store else None,
        "store_slug": store["slug"] if store else None,
    }


def ensure_workspace_store(conn, workspace_id: int, user_id: int) -> dict:
    """Ensure one internal store exists for the workspace; set default_store_id."""
    row = conn.execute(
        "SELECT id, slug, name FROM stores WHERE workspace_id=? ORDER BY id LIMIT 1",
        (workspace_id,),
    ).fetchone()
    if row:
        if _column_exists(conn, "workspaces", "default_store_id"):
            ws = conn.execute(
                "SELECT default_store_id FROM workspaces WHERE id=?", (workspace_id,),
            ).fetchone()
            if ws and not ws["default_store_id"]:
                conn.execute(
                    "UPDATE workspaces SET default_store_id=? WHERE id=?",
                    (row["id"], workspace_id),
                )
        return {"id": row["id"], "slug": row["slug"], "name": row["name"]}

    from app import new_store_slug

    ws = conn.execute("SELECT name FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
    name = ((ws["name"] if ws else None) or "My Business").strip() or "My Business"
    slug = new_store_slug()
    while conn.execute("SELECT 1 FROM stores WHERE slug=?", (slug,)).fetchone():
        slug = new_store_slug()
    conn.execute(
        """INSERT INTO stores (slug, name, owner_name, contact, description, owner_id, workspace_id)
           VALUES (?, ?, ?, '', '', ?, ?)""",
        (slug, name, name, user_id, workspace_id),
    )
    store_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    if _column_exists(conn, "workspaces", "default_store_id"):
        conn.execute(
            "UPDATE workspaces SET default_store_id=? WHERE id=?",
            (store_id, workspace_id),
        )
    store = conn.execute(
        "SELECT id, slug, name FROM stores WHERE id=?", (store_id,),
    ).fetchone()
    return {"id": store["id"], "slug": store["slug"], "name": store["name"]}
