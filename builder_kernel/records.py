"""Live builder_data_records helpers with preview/published surface isolation."""

from __future__ import annotations

import json
from typing import Any

from builder_kernel.limits import PUBLIC_LIST_DEFAULT_LIMIT, PUBLIC_LIST_MAX_LIMIT

SURFACE_PREVIEW = "preview"
SURFACE_PUBLISHED = "published"
VALID_SURFACES = frozenset({SURFACE_PREVIEW, SURFACE_PUBLISHED})


def migrate_record_surface(conn) -> None:
    """Add surface column (default preview) and query index. Idempotent."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='builder_data_records'"
    ).fetchone()
    if not exists:
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(builder_data_records)").fetchall()}
    if "surface" not in cols:
        conn.execute(
            "ALTER TABLE builder_data_records ADD COLUMN surface TEXT NOT NULL DEFAULT 'preview'"
        )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_builder_data_records_surface
           ON builder_data_records(project_id, model_key, surface, status)"""
    )


def normalize_surface(value: str | None, *, default: str = SURFACE_PREVIEW) -> str:
    text = str(value or default).strip().lower()
    return text if text in VALID_SURFACES else default


def _json_data(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def list_live_records(
    conn,
    *,
    project_id: int,
    model_key: str,
    surface: str,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    surface = normalize_surface(surface)
    try:
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        offset = 0
    if limit is None:
        limit = PUBLIC_LIST_DEFAULT_LIMIT
    try:
        limit = max(1, min(PUBLIC_LIST_MAX_LIMIT, int(limit)))
    except (TypeError, ValueError):
        limit = PUBLIC_LIST_DEFAULT_LIMIT
    rows = conn.execute(
        """SELECT record_key, data, status, updated_at, created_at
           FROM builder_data_records
           WHERE project_id=? AND model_key=? AND surface=? AND status!='archived'
           ORDER BY id DESC LIMIT ? OFFSET ?""",
        (int(project_id), str(model_key), surface, limit, offset),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["data"] = _json_data(item.get("data"))
        item["model_key"] = model_key
        result.append(item)
    return result


def load_live_collections(
    conn,
    *,
    project_id: int,
    snapshot: dict,
    surface: str,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, list]:
    """Map model_key → record data dicts for repeater bindings."""
    collections: dict[str, list] = {}
    for model in snapshot.get("data_models") or []:
        model_key = str(model.get("model_key") or "")
        if not model_key:
            continue
        records = list_live_records(
            conn,
            project_id=project_id,
            model_key=model_key,
            surface=surface,
            limit=limit,
            offset=offset,
        )
        collections[model_key] = [item.get("data") or {} for item in records]
    return collections


def get_live_record(
    conn,
    *,
    project_id: int,
    model_key: str,
    record_key: str,
    surface: str,
) -> dict | None:
    surface = normalize_surface(surface)
    row = conn.execute(
        """SELECT record_key, data, status, updated_at, created_at, model_key
           FROM builder_data_records
           WHERE project_id=? AND model_key=? AND record_key=? AND surface=? AND status!='archived'""",
        (int(project_id), str(model_key), str(record_key), surface),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["data"] = _json_data(item.get("data"))
    return item


def model_allows_public_read(schema: dict | str | None) -> bool:
    if isinstance(schema, str):
        try:
            schema = json.loads(schema or "{}")
        except json.JSONDecodeError:
            return False
    if not isinstance(schema, dict):
        return False
    access = schema.get("x-access") if isinstance(schema.get("x-access"), dict) else {}
    return access.get("public_read") is True
