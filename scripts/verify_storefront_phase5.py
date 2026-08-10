#!/usr/bin/env python3
"""Smoke test storefront Phase 5 — polish (prefix, unit, see all)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, build_item_group_nav, db, storefront_render_context
from storefront_platform import category_label, migrate_storefront_columns


def main() -> None:
    assert category_label("08", 3) == "08"
    assert category_label(None, 3) == "03"
    assert category_label("12.", 1) == "12"

    with db() as conn:
        migrate_storefront_columns(conn)
        store = conn.execute("SELECT * FROM stores LIMIT 1").fetchone()
        if not store:
            print("storefront Phase 5: OK (no stores, logic only)")
            return

        conn.execute(
            "INSERT INTO item_groups (store_id, name, prefix, display_order) VALUES (?, ?, ?, 99)",
            (store["id"], "Phase5 Verify Group", "88"),
        )
        group_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute(
            """INSERT INTO items (store_id, name, price, status, unit, group_id)
               VALUES (?, ?, ?, 'published', ?, ?)""",
            (store["id"], "Phase5 Verify Item", 4.5, "250 g", group_id),
        )
        conn.commit()

        nav = build_item_group_nav(store["id"], published_only=True)
        prefixed = next((g for g in nav if g.get("prefix") == "88"), None)
        assert prefixed and prefixed["num"] == "88", nav

        ctx = storefront_render_context(dict(store), preview_mode=False, view="shop")
        assert any(s.get("num") == "88" for s in ctx["catalog_sections"]), ctx["catalog_sections"]

        conn.execute("DELETE FROM items WHERE name = 'Phase5 Verify Item'")
        conn.execute("DELETE FROM item_groups WHERE id = ?", (group_id,))
        conn.commit()

    client = app.test_client()
    slug = store["slug"]
    r = client.get(f"/store/{slug}")
    assert r.status_code == 200, r.status_code
    body = r.get_data(as_text=True)
    assert "sf-sidebar__toggle" in body
    assert "sf-search-wrap--sticky" in body

    print("storefront Phase 5: OK")


if __name__ == "__main__":
    main()
