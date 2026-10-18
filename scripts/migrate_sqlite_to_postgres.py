#!/usr/bin/env python3
"""Copy SQLite marketqr.db into Postgres (DATABASE_URL).

Usage:
  DATABASE_URL=postgresql://... python3 scripts/migrate_sqlite_to_postgres.py

Copies table-by-table. Does not rewrite Auth0 identities — local password users
keep password_hash; after cutover, invite them to Auth0 password reset.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db_adapter import open_connection, using_postgres  # noqa: E402


def main() -> int:
    if not using_postgres():
        print("Set DATABASE_URL to a postgresql://… endpoint first.", file=sys.stderr)
        return 2
    src_path = Path(os.environ.get("SQLITE_PATH") or (ROOT / "marketqr.db"))
    if not src_path.is_file():
        print(f"Missing SQLite file: {src_path}", file=sys.stderr)
        return 2

    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row
    tables = [
        r["name"]
        for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    dst = open_connection()
    print(f"Migrating {len(tables)} tables from {src_path} → DATABASE_URL")
    for table in tables:
        cols = [r["name"] for r in src.execute(f"PRAGMA table_info({table})")]
        if not cols:
            continue
        rows = src.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  {table}: empty")
            continue
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join(cols)
        sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        ok = 0
        for row in rows:
            try:
                dst.execute(sql, [row[c] for c in cols])
                ok += 1
            except Exception as exc:
                print(f"  {table}: skip row ({exc})")
        dst.commit()
        print(f"  {table}: {ok}/{len(rows)}")
    dst.close()
    src.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
