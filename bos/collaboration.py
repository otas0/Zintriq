"""Collaboration metadata — created_by / updated_by from authenticated users."""

from __future__ import annotations

import sqlite3


def init_collaboration_columns(conn: sqlite3.Connection) -> None:
    """Add collaboration metadata columns where missing."""
    for table, cols in (
        ("customer_profiles", ("created_by", "updated_by")),
        ("orders", ("created_by", "updated_by")),
        ("items", ("created_by", "updated_by")),
    ):
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
        ).fetchone():
            continue
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER")


def stamp_create(conn: sqlite3.Connection, table: str, row_id: int, user_id: int) -> None:
    conn.execute(
        f"UPDATE {table} SET created_by=?, updated_by=? WHERE id=?",
        (user_id, user_id, row_id),
    )


def stamp_update(conn: sqlite3.Connection, table: str, row_id: int, user_id: int) -> None:
    conn.execute(f"UPDATE {table} SET updated_by=? WHERE id=?", (user_id, row_id))
