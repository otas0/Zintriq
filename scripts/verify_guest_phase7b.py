#!/usr/bin/env python3
"""Smoke test Phase 7B — brand hub (sibling stores)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db, storefront_render_context
from guest_platform import brand_hub_for_store, migrate_guest_tables


def main() -> None:
    with db() as conn:
        migrate_guest_tables(conn)
        store = conn.execute(
            """SELECT * FROM stores
               WHERE owner_id IS NOT NULL AND COALESCE(status, 'active') != 'archived'
               LIMIT 1"""
        ).fetchone()
        if not store:
            print("guest Phase 7B: OK (logic only, no owned store)")
            return

        owner_id = store["owner_id"]
        sibling_slug = f"phase7b-{store['slug'][:8]}"
        existing = conn.execute("SELECT id FROM stores WHERE slug = ?", (sibling_slug,)).fetchone()
        sibling_id = existing["id"] if existing else None
        if not sibling_id:
            cur = conn.execute(
                """INSERT INTO stores (slug, name, owner_id, owner_name, status, description)
                   VALUES (?, ?, ?, ?, 'active', 'Phase 7B sibling')""",
                (sibling_slug, "Phase 7B Location B", owner_id, store["owner_name"] or "Test Brand"),
            )
            sibling_id = int(cur.lastrowid)
            conn.commit()

        hub = brand_hub_for_store(conn, dict(store))
        assert hub is not None
        assert len(hub["locations"]) >= 1
        assert any(loc["slug"] == sibling_slug for loc in hub["locations"])

        ctx = storefront_render_context(dict(store), preview_mode=False, view="shop")
        assert ctx.get("brand_hub") and ctx["brand_hub"]["locations"]

    client = app.test_client()
    r = client.get(f"/store/{store['slug']}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "sf-brand-hub" in body or "More from" in body

    if not existing:
        with db() as conn:
            conn.execute("DELETE FROM stores WHERE id = ?", (sibling_id,))
            conn.commit()

    print("guest Phase 7B: OK")


if __name__ == "__main__":
    main()
