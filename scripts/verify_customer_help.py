#!/usr/bin/env python3
"""Verify customer help center and onboarding."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from app import app
    from help_platform import help_topic, help_topics

    client = app.test_client()

    assert help_topic("how-it-works")
    assert len(help_topics()) >= 5

    r = client.get("/help")
    assert r.status_code == 200
    html = r.data.decode()
    assert "All topics" in html
    assert "ch-tabbar" in html

    r2 = client.get("/help/how-it-works")
    assert r2.status_code == 200
    assert "Scan the QR code" in r2.data.decode()

    r3 = client.get("/home")
    html3 = r3.data.decode()
    assert "mq-onboard" in html3
    assert "How it works" in html3
    assert 'class="ch-scan-steps material-module"' not in html3

    r4 = client.get("/account")
    assert b"Help" in r4.data

    print("verify_customer_help: all checks passed")


if __name__ == "__main__":
    main()
