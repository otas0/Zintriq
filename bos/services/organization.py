"""Organization service."""

from __future__ import annotations

import re
import sqlite3

from bos.models import row_to_dict


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "organization"


def ensure_default_organization(conn: sqlite3.Connection, owner_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM organizations WHERE owner_id = ? ORDER BY id LIMIT 1",
        (owner_id,),
    ).fetchone()
    if row:
        return row_to_dict(row)
    name = "My Organization"
    slug = slugify(name)
    base = slug
    n = 1
    while conn.execute("SELECT 1 FROM organizations WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{n}"
        n += 1
    cursor = conn.execute(
        "INSERT INTO organizations (name, slug, owner_id, status) VALUES (?, ?, ?, 'active')",
        (name, slug, owner_id),
    )
    return row_to_dict(
        conn.execute("SELECT * FROM organizations WHERE id = ?", (cursor.lastrowid,)).fetchone()
    )


def list_organizations(conn: sqlite3.Connection, owner_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM organizations WHERE owner_id = ? ORDER BY name",
        (owner_id,),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_organization(conn: sqlite3.Connection, org_id: int, owner_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM organizations WHERE id = ? AND owner_id = ?",
        (org_id, owner_id),
    ).fetchone()
    return row_to_dict(row) if row else None


def update_organization(conn: sqlite3.Connection, org_id: int, owner_id: int, name: str, status: str) -> bool:
    result = conn.execute(
        "UPDATE organizations SET name = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_id = ?",
        (name.strip(), status, org_id, owner_id),
    )
    return result.rowcount > 0
