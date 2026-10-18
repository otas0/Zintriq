"""Studio surface isolation + Community handoff + Bearer API tokens."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Force SQLite before app import (override .env.local DATABASE_URL).
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-studio-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
for key in (
    "AUTH_PROVIDER",
    "AUTH0_DOMAIN",
    "AUTH0_CLIENT_ID",
    "AUTH0_CLIENT_SECRET",
    "DATABASE_URL",
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
):
    os.environ.pop(key, None)

# Prevent .env.local from re-injecting DATABASE_URL during import.
_real_load = None


class StudioContractTests(unittest.TestCase):
    def test_handoff_payload(self):
        from studio_platform import handoff_payload

        payload = handoff_payload(package_id="pkg.demo", project_id=12)
        self.assertEqual(payload["community_url"], "/app/community?package=pkg.demo")
        self.assertEqual(payload["studio_url"], "/studio/meta")
        self.assertTrue(payload["deep_link"].startswith("zintriq://studio?"))
        self.assertIn("package=pkg.demo", payload["deep_link"])

    def test_surfaces_api_public(self):
        os.environ.pop("DATABASE_URL", None)
        import app as app_module

        client = app_module.app.test_client()
        resp = client.get("/api/studio/surfaces")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("studio", data["surfaces"])
        self.assertIn("community", data["surfaces"])
        self.assertEqual(data["primitives"], ["describe", "simulate", "instantiate", "boundary", "space"])

    def test_download_page_renders(self):
        os.environ.pop("DATABASE_URL", None)
        import app as app_module

        client = app_module.app.test_client()
        resp = client.get("/download")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"macOS", resp.data)
        self.assertNotIn(b"Zintriq Studio", resp.data)


class StudioAuthRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SQLITE_PATH"] = _TMP_DB.name
        import app as app_module

        # .env.local overwrites env on import — force SQLite for this suite.
        os.environ.pop("DATABASE_URL", None)
        os.environ["SQLITE_PATH"] = _TMP_DB.name
        app_module.DATABASE = Path(_TMP_DB.name)

        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.config["TESTING"] = True
        with cls.app.app_context():
            with patch("db_adapter.using_postgres", return_value=False), patch(
                "app.using_postgres", return_value=False, create=True
            ):
                app_module.init_db()

    def setUp(self):
        os.environ.pop("DATABASE_URL", None)
        self.client = self.app.test_client()
        with self.app.app_context():
            from app import db
            from studio_platform import init_studio_tables

            with patch("db_adapter.using_postgres", return_value=False), patch(
                "app.using_postgres", return_value=False, create=True
            ):
                with db() as conn:
                    init_studio_tables(conn)
                    conn.execute(
                        "INSERT OR IGNORE INTO users (id, email, password_hash, account_kind) VALUES (9001, ?, ?, 'merchant')",
                        ("studio.tester@example.com", "x"),
                    )

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 9001
            sess["csrf_token"] = "csrf-studio"

    def test_studio_home_requires_auth(self):
        resp = self.client.get("/studio", follow_redirects=False)
        self.assertEqual(resp.status_code, 404)

    def test_web_account_workspaces_is_gone(self):
        self._login()
        resp = self.client.get("/account/workspaces", follow_redirects=False)
        self.assertEqual(resp.status_code, 404)

    def test_legacy_builder_redirects_to_studio(self):
        self._login()
        with patch("app.using_postgres", return_value=False, create=True):
            resp = self.client.get("/app/builder", follow_redirects=False)
        self.assertEqual(resp.status_code, 404)

    def test_bearer_token_me(self):
        self._login()
        create = self.client.post(
            "/api/studio/tokens",
            json={"name": "test", "days": 7, "csrf_token": "csrf-studio"},
            headers={"X-CSRF-Token": "csrf-studio"},
        )
        self.assertEqual(create.status_code, 200, create.data)
        token = create.get_json()["token"]
        self.assertTrue(token.startswith("zst_"))

        with self.client.session_transaction() as sess:
            sess.clear()
        me = self.client.get("/api/studio/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200, me.data)
        body = me.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["user"]["id"], 9001)
        self.assertEqual(body["auth"], "studio_token")

    def test_desktop_gate_public(self):
        resp = self.client.get("/studio/desktop", follow_redirects=False)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"sd-sign-in", resp.data)
        self.assertIn(b"Zintriq Studio", resp.data)

    def test_desktop_gate_redirects_when_logged_in(self):
        self._login()
        resp = self.client.get("/studio/desktop", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/account", resp.headers.get("Location") or "")

    def test_pkce_exchange_retired_for_desktop_authorize(self):
        resp = self.client.post(
            "/api/studio/auth/pkce/exchange",
            json={
                "code": "auth-code",
                "code_verifier": "verifier",
                "redirect_uri": "zintriq://auth/callback",
            },
        )
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
