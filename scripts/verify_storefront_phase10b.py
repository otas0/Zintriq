#!/usr/bin/env python3
"""Verify Phase 10B — storefront polish (see all, unit, mobile categories, prefix)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, build_item_group_nav, db, storefront_render_context
from storefront_platform import active_deals_for_storefront, category_label, migrate_storefront_columns


def main() -> None:
    assert category_label("08", 3) == "08"
    assert category_label(None, 3) == "03"

    with db() as conn:
        migrate_storefront_columns(conn)
        store = conn.execute("SELECT * FROM stores LIMIT 1").fetchone()
        if not store:
            print("storefront Phase 10B: OK (no stores, logic only)")
            return

        conn.execute(
            "INSERT INTO item_groups (store_id, name, prefix, display_order) VALUES (?, ?, ?, 99)",
            (store["id"], "10B Verify Group", "77"),
        )
        group_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute(
            """INSERT INTO items (store_id, name, price, status, unit, group_id)
               VALUES (?, ?, ?, 'published', ?, ?)""",
            (store["id"], "10B Verify Item", 9.5, "500 ml", group_id),
        )
        item_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute(
            """INSERT INTO store_deals (store_id, item_id, discount_type, discount_value, status)
               VALUES (?, ?, 'percent', 20, 'active')""",
            (store["id"], item_id),
        )
        conn.execute(
            "INSERT INTO item_groups (store_id, name, prefix, display_order) VALUES (?, ?, ?, 98)",
            (store["id"], "10B Verify Group B", "78"),
        )
        group_b = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute(
            """INSERT INTO items (store_id, name, price, status, unit, group_id)
               VALUES (?, ?, ?, 'published', ?, ?)""",
            (store["id"], "10B Verify Item B", 4.0, "250 g", group_b),
        )
        conn.commit()

        nav = build_item_group_nav(store["id"], published_only=True)
        prefixed = next((g for g in nav if g.get("prefix") == "77"), None)
        assert prefixed and prefixed["num"] == "77", nav
        assert len(nav) >= 2

        ctx = storefront_render_context(dict(store), preview_mode=False, view="shop")
        assert any(s.get("num") == "77" for s in ctx["catalog_sections"])

        deals = active_deals_for_storefront(conn, store["id"])
        deal = next((d for d in deals if d["item_id"] == item_id), None)
        assert deal and deal.get("item_unit") == "500 ml", deals

        slug = store["slug"]

    client = app.test_client()
    r = client.get(f"/store/{slug}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "sf-sidebar__toggle" in body
    assert "sf-search-wrap--sticky" in body
    assert "sf-categories--mobile" in body
    assert "See all →" in body

    with db() as conn:
        conn.execute("DELETE FROM store_deals WHERE store_id = ? AND item_id = ?", (store["id"], item_id))
        conn.execute("DELETE FROM items WHERE name LIKE '10B Verify Item%'")
        conn.execute("DELETE FROM item_groups WHERE id IN (?, ?)", (group_id, group_b))
        conn.commit()

    print("storefront Phase 10B: OK")


if __name__ == "__main__":
    main()
