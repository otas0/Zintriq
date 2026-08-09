#!/usr/bin/env python3
"""Live check: Google Calendar plugin config + authenticated API smoke test."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Load .env.local before reading credentials
_env_local = os.path.join(ROOT, ".env.local")
if os.path.isfile(_env_local):
    for line in open(_env_local, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip("'\"")


def login_client(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "gc-test-csrf"


def main() -> int:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    redirect = os.environ.get(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://127.0.0.1:5001/api/integrations/google-calendar/oauth/callback",
    )

    print("Google Calendar live check")
    print("=" * 44)
    print(f"GOOGLE_CLIENT_ID:     {'set' if client_id else 'MISSING'}")
    print(f"GOOGLE_CLIENT_SECRET: {'set' if client_secret else 'MISSING'}")
    print(f"Redirect URI:         {redirect}")
    print()

    if not client_id:
        print("FAIL: Set GOOGLE_CLIENT_ID")
        return 1
    if not client_secret:
        print("FAIL: Set GOOGLE_CLIENT_SECRET (from Google Cloud → Credentials → OAuth client)")
        return 1

    os.environ.setdefault("SECRET_KEY", "gc-live-test")
    from app import app, db

    with app.app_context():
        with db() as conn:
            user = conn.execute("SELECT id, email FROM users ORDER BY id LIMIT 1").fetchone()
        if not user:
            print("FAIL: No users in database — register/login first")
            return 1

        client = app.test_client()
        login_client(client, int(user["id"]))

        r_plugins = client.get("/api/integrations/plugins")
        print(f"GET /api/integrations/plugins → {r_plugins.status_code}")
        if r_plugins.status_code != 200:
            print(r_plugins.get_data(as_text=True)[:300])
            return 1
        plugins = r_plugins.get_json()
        gc = next((p for p in plugins if p.get("slug") == "google_calendar"), None)
        print(f"  google_calendar plugin: {'found' if gc else 'missing'}")

        r_start = client.get("/api/integrations/google-calendar/oauth/start")
        print(f"GET /api/integrations/google-calendar/oauth/start → {r_start.status_code}")
        data = r_start.get_json() or {}
        if r_start.status_code == 200 and data.get("auth_url"):
            url = data["auth_url"]
            ok = (
                client_id in url
                and "calendar" in url
                and urllib.parse.quote(redirect, safe="") in url or redirect in url
            )
            print("  auth_url generated: YES")
            print(f"  redirect in auth_url: {'yes' if redirect in url else 'check manually'}")
        elif r_start.status_code == 503:
            print("  not configured on server — restart Flask with env vars")
            return 1
        else:
            print(f"  unexpected: {data}")
            return 1

        r_status = client.get("/api/integrations/google-calendar/status")
        print(f"GET /api/integrations/google-calendar/status → {r_status.status_code}")
        st = r_status.get_json() or {}
        print(f"  configured={st.get('configured')} connected={st.get('connected')} status={st.get('status')}")

    print("=" * 44)
    print("PASSED — OAuth start works. Complete Connect in browser with your Google account.")
    return 0


if __name__ == "__main__":
    import urllib.parse
    raise SystemExit(main())
