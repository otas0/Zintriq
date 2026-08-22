#!/usr/bin/env python3
"""Smoke test SMTP configuration — sends one test message when configured."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: F401 — loads .env.local via app startup

from email_delivery import send_transactional_email, smtp_configured


def main() -> None:
    if not smtp_configured():
        print("SMTP not configured.")
        print("Set SMTP_HOST (and SMTP_USER/SMTP_PASSWORD) in .env.local or the environment.")
        print("See .env.example and docs/DEPLOYMENT.md")
        sys.exit(1)

    to = (os.environ.get("SMTP_TEST_TO") or os.environ.get("SMTP_USER") or "").strip()
    if not to:
        print("Set SMTP_TEST_TO or SMTP_USER to receive the test email.")
        sys.exit(1)

    host = os.environ.get("SMTP_HOST", "")
    port = os.environ.get("SMTP_PORT", "587")
    print(f"Sending test email via {host}:{port} → {to}")

    ok = send_transactional_email(
        to,
        "Zintriq SMTP test",
        "If you received this, SMTP is configured correctly.\n",
        html_body="<p>If you received this, <strong>SMTP is configured correctly</strong>.</p>",
    )
    if ok:
        print("verify_smtp: OK — check the inbox (and spam folder).")
    else:
        print("verify_smtp: FAIL — send_transactional_email returned False")
        sys.exit(1)


if __name__ == "__main__":
    main()
