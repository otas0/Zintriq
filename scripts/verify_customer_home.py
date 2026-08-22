#!/usr/bin/env python3
"""Verify customer home hub — distinct Home vs Places roles."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from app import app, db
    from customer_home_platform import home_feed
    from guest_platform import ensure_visitor_key, migrate_guest_tables

    client = app.test_client()
    with app.app_context():
        with db() as conn:
            migrate_guest_tables(conn)
            feed = home_feed(conn, "test-visitor")
        assert "venues" in feed
        assert "continue_place" in feed
        assert "recent_places_total" in feed

    r = client.get("/home")
    assert r.status_code == 200
    html = r.data.decode()
    assert "Markets &amp; venues" in html or "Markets & venues" in html
    assert "How it works" not in html or "mq-onboard" in html
    assert "places-search" not in html
    assert "guest-places__list" not in html or "ch-resume-shop" in html or "ch-home__places-link" in html

    with client.session_transaction() as sess:
        sess.clear()
    client.get("/store/bcdeiohu")
    with client.session_transaction() as sess:
        ensure_visitor_key(sess)

    r4 = client.get("/places")
    html4 = r4.data.decode()
    assert "places-search" in html4
    assert "places-sort" in html4
    assert "Markets &amp; venues" not in html4

    r5 = client.get("/home")
    html5 = r5.data.decode()
    assert "mq-onboard" in html5
    assert 'data-onboarding-mode="guest"' in html5
    assert 'data-onboarding-open="1"' in html5

    print("verify_customer_home: all checks passed")


if __name__ == "__main__":
    main()
