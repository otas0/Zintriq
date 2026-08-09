#!/usr/bin/env python3
"""Smoke test storefront Phase 2 — deals."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db, init_db
from storefront_platform import (
    active_deals_for_storefront,
    compute_sale_price,
    default_deal_label,
    migrate_store_deals,
    resolve_deal,
    save_deal_from_form,
)


class FakeForm(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def main() -> int:
    init_db()
    conn = __import__("sqlite3").connect(ROOT / "marketqr.db")
    conn.row_factory = __import__("sqlite3").Row
    migrate_store_deals(conn)

    assert default_deal_label("percent", 20) == "20% off"
    assert compute_sale_price(100, "percent", 20) == 80.0
    assert compute_sale_price(100, "fixed", 15) == 85.0

    store = conn.execute("SELECT id FROM stores LIMIT 1").fetchone()
    if not store:
        print("storefront Phase 2: OK (no stores, logic only)")
        return 0
    store_id = store["id"]
    item = conn.execute(
        "SELECT id, price FROM items WHERE store_id=? LIMIT 1", (store_id,)
    ).fetchone()
    if item:
        save_deal_from_form(conn, store_id, item["id"], FakeForm({
            f"deal_enabled_{item['id']}": "1",
            f"deal_type_{item['id']}": "percent",
            f"deal_value_{item['id']}": "20",
            f"deal_featured_{item['id']}": "1",
        }))
        conn.commit()
        deals = active_deals_for_storefront(conn, store_id)
        assert deals, "expected at least one active deal"
        assert deals[0]["sale_price"] < float(item["price"])

    with app.test_client() as c:
        slug = conn.execute("SELECT slug FROM stores WHERE id=?", (store_id,)).fetchone()["slug"]
        r = c.get(f"/store/{slug}")
        assert r.status_code == 200
        if item:
            assert b"sf-deals-bar" in r.data or b"Deals" in r.data

    print("storefront Phase 2: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
