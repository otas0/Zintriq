"""Workspace permission catalog and role-based access checks."""

from __future__ import annotations

import sqlite3

# Default roles — behavior is defined only through permissions, never role names in business logic.
TEAM_ROLES = ("owner", "administrator", "manager", "member", "viewer")

# Legacy alias migrated at init.
ROLE_ALIASES = {"staff": "member"}

ALL_PERMISSIONS: tuple[str, ...] = (
    "workspace.read",
    "workspace.update",
    "workspace.delete",
    "workspace.transfer_ownership",
    "member.read",
    "member.invite",
    "member.update",
    "member.remove",
    "member.suspend",
    "customer.read",
    "customer.create",
    "customer.update",
    "customer.delete",
    "customer.manage",
    "interaction.read",
    "contact.read",
    "contact.create",
    "contact.update",
    "contact.archive",
    "contact.delete",
    "contact.merge",
    "contact.export",
    "booking.read",
    "booking.create",
    "booking.update",
    "booking.cancel",
    "booking.assign",
    "calendar.read",
    "calendar.create",
    "calendar.update",
    "checkin.read",
    "checkin.create",
    "checkin.update",
    "checkin.complete",
    "checkin.delete",
    "feedback.read",
    "feedback.create",
    "feedback.update",
    "feedback.delete",
    "feedback.reply",
    "feedback.archive",
    "survey.manage",
    "integration.manage",
    "catalog.read",
    "catalog.update",
    "task.read",
    "task.create",
    "task.update",
    "task.assign",
    "task.complete",
    "task.archive",
    "task.delete",
    "qr_experience.read",
    "qr_experience.create",
    "qr_experience.update",
    "qr_experience.publish",
    "qr_experience.delete",
    "analytics.read",
    "analytics.export",
    "template.read",
    "template.create",
    "template.manage",
    "workflow.read",
    "workflow.create",
    "workflow.update",
    "workflow.publish",
    "workflow.delete",
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(ALL_PERMISSIONS),
    "administrator": frozenset(p for p in ALL_PERMISSIONS if p not in ("workspace.delete", "workspace.transfer_ownership")),
    "manager": frozenset({
        "workspace.read", "workspace.update",
        "member.read", "member.invite", "member.update", "member.suspend",
        "customer.read", "customer.create", "customer.update", "customer.manage",
        "interaction.read",
        "contact.read", "contact.create", "contact.update", "contact.archive", "contact.export",
        "booking.read", "booking.create", "booking.update", "booking.cancel", "booking.assign",
        "calendar.read", "calendar.create", "calendar.update",
        "checkin.read", "checkin.create", "checkin.update", "checkin.complete",
        "feedback.read", "feedback.create", "feedback.update", "feedback.delete",
        "feedback.reply", "feedback.archive", "survey.manage",
        "catalog.read", "catalog.update",
        "task.read", "task.create", "task.update", "task.assign", "task.complete", "task.archive",
        "qr_experience.read", "qr_experience.create", "qr_experience.update",
        "qr_experience.publish", "qr_experience.delete",
        "analytics.read",
        "template.read", "template.create", "template.manage",
        "workflow.read", "workflow.create", "workflow.update", "workflow.publish", "workflow.delete",
    }),
    "member": frozenset({
        "workspace.read", "member.read",
        "customer.read", "customer.create", "customer.update",
        "interaction.read",
        "contact.read", "contact.create", "contact.update",
        "booking.read", "booking.create", "booking.update", "booking.cancel", "booking.assign",
        "calendar.read", "calendar.create", "calendar.update",
        "checkin.read", "checkin.create", "checkin.update", "checkin.complete",
        "feedback.read", "feedback.create", "feedback.reply",
        "catalog.read",
        "task.read", "task.create", "task.update", "task.assign", "task.complete",
        "qr_experience.read", "qr_experience.create", "qr_experience.update",
        "analytics.read",
        "template.read", "template.create",
        "workflow.read", "workflow.create", "workflow.update",
    }),
    "viewer": frozenset({
        "workspace.read", "member.read",
        "customer.read", "contact.read", "booking.read", "calendar.read", "checkin.read", "feedback.read", "catalog.read",
        "interaction.read",
        "task.read",
        "qr_experience.read",
        "analytics.read",
        "template.read",
        "workflow.read",
    }),
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS workspace_role_permissions (
    role TEXT NOT NULL,
    permission_key TEXT NOT NULL,
    PRIMARY KEY (role, permission_key),
    FOREIGN KEY(permission_key) REFERENCES permissions(key)
);
"""


def init_permissions_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    for key in ALL_PERMISSIONS:
        conn.execute(
            "INSERT OR IGNORE INTO permissions (key, description) VALUES (?, ?)",
            (key, key.replace(".", " ").title()),
        )
    for role, perms in ROLE_PERMISSIONS.items():
        for key in perms:
            conn.execute(
                "INSERT OR IGNORE INTO workspace_role_permissions (role, permission_key) VALUES (?, ?)",
                (role, key),
            )
    conn.execute("UPDATE workspace_members SET role='member' WHERE role='staff'")


def normalize_role(role: str | None) -> str | None:
    if not role:
        return None
    return ROLE_ALIASES.get(role, role)


def member_role(conn: sqlite3.Connection, user_id: int, workspace_id: int) -> str | None:
    row = conn.execute(
        """SELECT role FROM workspace_members
           WHERE workspace_id=? AND user_id=? AND status IN ('active', 'invited', 'suspended')""",
        (workspace_id, user_id),
    ).fetchone()
    if not row:
        return None
    return normalize_role(row["role"])


def permissions_for_role(conn: sqlite3.Connection, role: str) -> set[str]:
    role = normalize_role(role) or ""
    rows = conn.execute(
        "SELECT permission_key FROM workspace_role_permissions WHERE role=?",
        (role,),
    ).fetchall()
    if rows:
        return {r["permission_key"] for r in rows}
    return set(ROLE_PERMISSIONS.get(role, ()))


def has_permission(conn: sqlite3.Connection, user_id: int, workspace_id: int, permission: str) -> bool:
    role = member_role(conn, user_id, workspace_id)
    if not role:
        return False
    return permission in permissions_for_role(conn, role)


def require_permission(conn: sqlite3.Connection, user_id: int, workspace_id: int, permission: str) -> None:
    if not has_permission(conn, user_id, workspace_id, permission):
        from flask import abort
        abort(403)


def is_workspace_owner(conn: sqlite3.Connection, user_id: int, workspace_id: int) -> bool:
    return member_role(conn, user_id, workspace_id) == "owner"


def list_roles_with_permissions(conn: sqlite3.Connection) -> list[dict]:
    result = []
    for role in TEAM_ROLES:
        result.append({
            "id": role,
            "label": role.replace("_", " ").title(),
            "permissions": sorted(permissions_for_role(conn, role)),
        })
    return result
