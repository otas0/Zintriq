"""SQLite helpers for the desktop transfer paths.

Phase 1 desktop is SQLite only. Web/Postgres adapters stay out of this package.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


def open_connection(sqlite_file: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(sqlite_file, timeout=60, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=60000")
    return connection


def commit_with_retry(connection, *, attempts: int = 8) -> None:
    for attempt in range(attempts):
        try:
            connection.commit()
            return
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "locked" not in msg or attempt >= attempts - 1:
                raise
            connection.rollback()
            time.sleep(min(0.05 * (2**attempt), 1.0))
