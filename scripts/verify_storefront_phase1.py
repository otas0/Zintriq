#!/usr/bin/env python3
"""Smoke test storefront Phase 1 helpers."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storefront_platform import (
    DEFAULT_TIMEZONE,
    build_store_profile,
    hours_from_form,
    hours_status,
    maps_directions_url,
    migrate_storefront_columns,
    parse_hours_json,
    store_rating_summary,
)


class FakeForm(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def main() -> int:
    conn = sqlite3.connect(ROOT / "marketqr.db")
    conn.row_factory = sqlite3.Row
    migrate_storefront_columns(conn)

    hours_json = hours_from_form(FakeForm({
        "hours_mon_closed": "0", "hours_mon_open": "09:00", "hours_mon_close": "21:00",
        "hours_tue_closed": "1",
        "hours_wed_closed": "0", "hours_wed_open": "10:00", "hours_wed_close": "18:00",
        "hours_thu_closed": "1", "hours_fri_closed": "1", "hours_sat_closed": "1", "hours_sun_closed": "1",
    }))
    parsed = parse_hours_json(hours_json)
    assert parsed["mon"]["open"] == "09:00"
    assert "tue" not in parsed or not parsed.get("tue")

    store = {
        "id": 1,
        "name": "Test Store",
        "description": "Desc",
        "address": "123 Main St, Singapore",
        "contact": "+65 0000",
        "background_image": None,
        "business_hours_json": hours_json,
        "business_hours": "",
        "timezone": DEFAULT_TIMEZONE,
    }
    status = hours_status(store, now=datetime(2026, 8, 3, 14, 0, tzinfo=ZoneInfo(DEFAULT_TIMEZONE)))
    assert status["has_structured_hours"]
    assert status["status_line"]

    url = maps_directions_url(store["address"])
    assert url and "google.com/maps" in url

    profile = build_store_profile(conn, store)
    assert profile["maps_url"]
    assert "hours" in profile

    ratings = store_rating_summary(conn, store["id"])
    assert "count" in ratings

    print("storefront Phase 1: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
