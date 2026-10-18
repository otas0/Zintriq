"""Smoke tests for creator /account vs in-work customer account URLs."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-account-urls-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
for key in ("DATABASE_URL", "AUTH_PROVIDER", "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
    os.environ.pop(key, None)


class AccountUrlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        os.environ.pop("DATABASE_URL", None)
        os.environ["SQLITE_PATH"] = _TMP_DB.name
        app_module.DATABASE = Path(_TMP_DB.name)
        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.config["TESTING"] = True
        with cls.app.app_context():
            app_module.init_db()
            with app_module.db() as conn:
                cur = conn.execute(
                    "INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, ?)",
                    (
                        "shopper@example.test",
                        generate_password_hash("ShopperPass12!", method="pbkdf2:sha256:600000"),
                        "customer",
                    ),
                )
                cls.customer_id = int(cur.lastrowid)
                conn.execute(
                    "INSERT INTO stores (slug, name, owner_id, status) VALUES (?, ?, ?, ?)",
                    ("cafe-demo", "Cafe Demo", None, "active"),
                )

    def setUp(self):
        self.client = self.app.test_client()

    def test_unauth_account_redirects_to_login(self):
        resp = self.client.get("/account", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        location = resp.headers.get("Location") or ""
        self.assertTrue(location.endswith("/login") or "/login?" in location, location)

    def test_app_account_redirects_to_account(self):
        resp = self.client.get("/app/account", follow_redirects=False)
        self.assertIn(resp.status_code, {301, 302, 303})
        location = resp.headers.get("Location") or ""
        self.assertTrue(location.endswith("/account") or "/account?" in location, location)

    def test_storefront_account_nav(self):
        resp = self.client.get("/store/cafe-demo")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True)[:400])
        html = resp.get_data(as_text=True)
        self.assertIn('href="/store/cafe-demo/account"', html)

    def test_customer_login_stays_in_store(self):
        page = self.client.get("/store/cafe-demo/account/login")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True)[:400])
        with self.client.session_transaction() as sess:
            csrf = sess.get("csrf_token")
        resp = self.client.post(
            "/store/cafe-demo/account/login",
            data={
                "csrf_token": csrf,
                "email": "shopper@example.test",
                "password": "ShopperPass12!",
                "next": "/store/cafe-demo/account",
            },
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, {200, 302, 303})
        if resp.status_code in {302, 303}:
            location = resp.headers.get("Location") or ""
            self.assertIn("/store/cafe-demo/", location)
        with self.client.session_transaction() as sess:
            self.assertEqual(int(sess.get("customer_user_id") or 0), self.customer_id)

    def test_desktop_auth_rules_keep_creator_account_open(self):
        from desktop.server_mode import AUTH_RULES

        self.assertNotIn("/account", AUTH_RULES)
        self.assertNotIn("/account/workspaces", AUTH_RULES)
        self.assertIn("/store/<work_slug>/account/login", AUTH_RULES)
        self.assertIn("/build/<work_slug>/account/login", AUTH_RULES)
        self.assertNotIn("/account/switch/business", AUTH_RULES)


if __name__ == "__main__":
    unittest.main()
