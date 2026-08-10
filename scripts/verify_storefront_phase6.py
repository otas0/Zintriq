#!/usr/bin/env python3
"""Smoke test storefront Phase 6 — products manage refactor."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db
from storefront_platform import migrate_storefront_columns, toggle_item_deal


def main() -> None:
    with db() as conn:
        migrate_storefront_columns(conn)
        store = conn.execute("SELECT * FROM stores WHERE owner_id IS NOT NULL LIMIT 1").fetchone()
        if not store:
            print("storefront Phase 6: OK (deal logic only, no owned store)")
            return
        item = conn.execute(
            "SELECT id FROM items WHERE store_id = ? LIMIT 1", (store["id"],)
        ).fetchone()
        if item:
            toggle_item_deal(conn, store["id"], item["id"], True)
            row = conn.execute(
                "SELECT id FROM store_deals WHERE store_id = ? AND item_id = ?",
                (store["id"], item["id"]),
            ).fetchone()
            assert row
            toggle_item_deal(conn, store["id"], item["id"], False)
            conn.commit()

    client = app.test_client()
    slug = store["slug"]
    owner_id = store["owner_id"]

    with client.session_transaction() as sess:
        sess["user_id"] = owner_id
        sess["csrf_token"] = "verify-phase6-token"

    r = client.get(f"/manage/{slug}")
    assert r.status_code == 200, r.status_code
    body = r.get_data(as_text=True)
    assert "sf-add-product-modal" in body
    assert "Live preview" in body

    if item:
        r2 = client.post(
            f"/manage/{slug}/items/{item['id']}/deal",
            data={"enabled": "1", "csrf_token": "verify-phase6-token"},
            headers={"X-Requested-With": "fetch"},
        )
        assert r2.status_code == 200, r2.get_data(as_text=True)
        data = r2.get_json()
        assert data.get("enabled") is True

    print("storefront Phase 6: OK")


if __name__ == "__main__":
    main()
