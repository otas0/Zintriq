"""Workspace service."""

from __future__ import annotations

import re
import sqlite3

from bos.models import row_to_dict
from bos.services.organization import ensure_default_organization, slugify


def ensure_default_workspace(conn: sqlite3.Connection, owner_id: int) -> dict:
    org = ensure_default_organization(conn, owner_id)
    row = conn.execute(
        "SELECT * FROM workspaces WHERE organization_id = ? ORDER BY id LIMIT 1",
        (org["id"],),
    ).fetchone()
    if row:
        return row_to_dict(row)
    name = "Main Workspace"
    slug = slugify(name)
    cursor = conn.execute(
        """INSERT INTO workspaces (organization_id, name, slug, type, status)
           VALUES (?, ?, ?, 'general', 'active')""",
        (org["id"], name, slug),
    )
    workspace = row_to_dict(
        conn.execute("SELECT * FROM workspaces WHERE id = ?", (cursor.lastrowid,)).fetchone()
    )
    conn.execute(
        "UPDATE stores SET workspace_id = ? WHERE owner_id = ? AND workspace_id IS NULL",
        (workspace["id"], owner_id),
    )
    return workspace


def list_workspaces(conn: sqlite3.Connection, owner_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT w.*, o.name AS organization_name,
                  (SELECT COUNT(*) FROM stores s WHERE s.workspace_id = w.id) AS asset_count
           FROM workspaces w
           JOIN organizations o ON o.id = w.organization_id
           WHERE o.owner_id = ?
           ORDER BY w.name""",
        (owner_id,),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_workspace(conn: sqlite3.Connection, workspace_id: int, owner_id: int) -> dict | None:
    row = conn.execute(
        """SELECT w.*, o.name AS organization_name
           FROM workspaces w
           JOIN organizations o ON o.id = w.organization_id
           WHERE w.id = ? AND o.owner_id = ?""",
        (workspace_id, owner_id),
    ).fetchone()
    return row_to_dict(row) if row else None


def create_workspace(conn: sqlite3.Connection, owner_id: int, name: str, org_id: int | None = None) -> dict:
    org = ensure_default_organization(conn, owner_id) if org_id is None else get_organization_for_owner(conn, org_id, owner_id)
    if not org:
        raise ValueError("Organization not found")
    slug = slugify(name)
    base = slug
    n = 1
    while conn.execute(
        "SELECT 1 FROM workspaces WHERE organization_id = ? AND slug = ?",
        (org["id"], slug),
    ).fetchone():
        slug = f"{base}-{n}"
        n += 1
    cursor = conn.execute(
        """INSERT INTO workspaces (organization_id, name, slug, type, status)
           VALUES (?, ?, ?, 'general', 'active')""",
        (org["id"], name.strip(), slug),
    )
    return row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id = ?", (cursor.lastrowid,)).fetchone())


def get_organization_for_owner(conn: sqlite3.Connection, org_id: int, owner_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM organizations WHERE id = ? AND owner_id = ?",
        (org_id, owner_id),
    ).fetchone()
    return row_to_dict(row) if row else None
