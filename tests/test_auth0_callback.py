"""Auth0 callback upsert — no live Auth0 network calls."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class Auth0CallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp.close()
        conn = sqlite3.connect(cls._tmp.name)
        conn.executescript(
            """
            CREATE TABLE users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              firebase_uid TEXT,
              two_factor_secret TEXT,
              account_kind TEXT DEFAULT 'merchant',
              auth_provider TEXT DEFAULT 'local',
              auth_provider_id TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE user_profiles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL UNIQUE,
              auth_provider TEXT NOT NULL DEFAULT 'local',
              auth_provider_id TEXT,
              email TEXT NOT NULL,
              full_name TEXT DEFAULT '',
              avatar_url TEXT DEFAULT '',
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE workspace_members (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              workspace_id INTEGER,
              user_id INTEGER,
              status TEXT
            );
            """
        )
        conn.commit()
        conn.close()

        os.environ["AUTH_PROVIDER"] = "auth0"
        os.environ["AUTH0_DOMAIN"] = "example.eu.auth0.com"
        os.environ["AUTH0_CLIENT_ID"] = "cid"
        os.environ["AUTH0_CLIENT_SECRET"] = "secret"
        os.environ["AUTH0_CALLBACK_URL"] = "http://localhost/auth/callback"
        os.environ.pop("DATABASE_URL", None)

        import app as app_module

        cls.app_module = app_module
        cls._orig = app_module.DATABASE
        app_module.DATABASE = Path(cls._tmp.name)

        cls.flask_app = app_module.app
        cls.flask_app.config["TESTING"] = True
        cls.flask_app.config["SECRET_KEY"] = "auth0-test"

    @classmethod
    def tearDownClass(cls):
        cls.app_module.DATABASE = cls._orig
        for key in (
            "AUTH_PROVIDER",
            "AUTH0_DOMAIN",
            "AUTH0_CLIENT_ID",
            "AUTH0_CLIENT_SECRET",
            "AUTH0_CALLBACK_URL",
        ):
            os.environ.pop(key, None)
        os.unlink(cls._tmp.name)

    def test_callback_creates_user(self):
        client = self.flask_app.test_client()
        with client.session_transaction() as sess:
            sess["auth0_oauth_state"] = "state-xyz"

        fake = MagicMock()
        fake.exchange_code.return_value = {"access_token": "atok"}
        fake.claims_from_token_response.return_value = {
            "auth_provider": "auth0",
            "auth_provider_id": "auth0|abc123",
            "email": "owner@example.com",
            "email_verified": True,
            "full_name": "Owner",
        }
        fake.is_configured.return_value = True
        fake.slug = "auth0"

        with patch("integrations.auth.get_auth_provider", return_value=fake), patch(
            "integrations.auth.auth0_enabled", return_value=True
        ):
            resp = client.get("/auth/callback?code=abc&state=state-xyz", follow_redirects=False)

        self.assertEqual(resp.status_code, 404)
        conn = sqlite3.connect(self._tmp.name)
        row = conn.execute(
            "SELECT email, auth_provider, auth_provider_id FROM users"
        ).fetchone()
        conn.close()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
