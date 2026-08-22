#!/usr/bin/env python3
"""Verify business help center (separate from customer /help)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from app import app
    from business_help_platform import business_help_topic, business_help_topics

    client = app.test_client()

    assert business_help_topic("how-it-works")
    assert len(business_help_topics()) >= 8

    r = client.get("/business/help")
    assert r.status_code == 200
    html = r.data.decode()
    assert "All topics" in html
    assert "Zintriq" in html
    assert "ch-tabbar" not in html

    r2 = client.get("/business/help/how-it-works")
    assert r2.status_code == 200
    assert "Create a store" in r2.data.decode()

    r3 = client.get("/help")
    assert b"Business Help" in r3.data

    print("verify_business_help: all checks passed")


if __name__ == "__main__":
    main()
