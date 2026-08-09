#!/usr/bin/env python3
"""Register Google Calendar push watches + run one inbound poll (after tunnel/Flask restart)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app, db
from google_calendar_plugin import poll_google_calendar_inbound, refresh_all_google_watches


def main() -> int:
    public = os.environ.get("PUBLIC_BASE_URL", "")
    print(f"PUBLIC_BASE_URL={public or '(not set)'}")
    print(f"GOOGLE_CALENDAR_POLL_SECONDS={os.environ.get('GOOGLE_CALENDAR_POLL_SECONDS', '60')}")
    with app.app_context():
        refresh_all_google_watches(app)
        with db() as conn:
            watches = conn.execute(
                "SELECT connection_id, channel_id, expiration FROM google_calendar_watch_channels"
            ).fetchall()
        print(f"Registered watch channels: {len(watches)}")
        for w in watches:
            print(f"  connection #{w['connection_id']} channel={w['channel_id'][:12]}…")
        result = poll_google_calendar_inbound(app)
        print(f"Poll result: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
