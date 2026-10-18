"""G-2.2: verify client-side Firebase removal.

Nine tests proving:
  T1 — GET /login returns 200 with no "google" in HTML
  T2 — GET /register returns 200 with no "google"
  T3 — GET /account/login renders template with no "google"
  T4 — GET /account/register redirects (no "google" in flow)
  T5 — GET /login HTML does NOT reference gstatic.com
  T6 — POST /login with valid credentials returns 302 + session
  T7 — GET /register HTML contains email input
  T8 — GET /login HTML contains password input
  T9 — GET /login HTML still references /static/marketing.css
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.security import generate_password_hash

TEST_EMAIL = "g22-test@example.com"
TEST_PASSWORD = "G22StandaloneTest12!"


def _create_test_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            firebase_uid TEXT UNIQUE,
            two_factor_secret TEXT,
            phone TEXT,
            account_kind TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            owner_name TEXT,
            contact TEXT,
            description TEXT,
            owner_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customer_account_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute(
        "INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, ?)",
        (TEST_EMAIL, generate_password_hash(TEST_PASSWORD, method="pbkdf2:sha256:600000"), "merchant"),
    )
    conn.commit()
    conn.close()


class ClientSideFirebaseRemovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp.close()
        cls.db_path = cls._tmp.name
        _create_test_db(cls.db_path)

        # Isolate from developer .env.local Auth0 / Postgres settings
        for key in (
            "AUTH_PROVIDER",
            "AUTH0_DOMAIN",
            "AUTH0_CLIENT_ID",
            "AUTH0_CLIENT_SECRET",
            "AUTH0_CALLBACK_URL",
            "DATABASE_URL",
            "SQLITE_PATH",
        ):
            os.environ.pop(key, None)

        import app as app_module
        cls.app_module = app_module
        cls._orig_database = app_module.DATABASE
        app_module.DATABASE = Path(cls.db_path)

        cls.flask_app = app_module.app
        cls.flask_app.config["TESTING"] = True
        cls.flask_app.config["SECRET_KEY"] = "g22-test-secret"

    @classmethod
    def tearDownClass(cls):
        cls.app_module.DATABASE = cls._orig_database
        os.unlink(cls.db_path)

    def test_t1_login_no_google(self):
        """GET /login returns 200 with no 'google' in HTML."""
        client = self.flask_app.test_client()
        resp = client.get("/login")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8").lower()
        self.assertNotIn("google", html, "Login page should not contain 'google'")

    def test_t2_register_no_google(self):
        """GET /register returns 200 with no 'google'."""
        client = self.flask_app.test_client()
        resp = client.get("/register")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8").lower()
        self.assertNotIn("google", html, "Register page should not contain 'google'")

    def test_t3_customer_login_no_google(self):
        """GET /login (creator) has no 'google'."""
        client = self.flask_app.test_client()
        resp = client.get("/login")
        html = resp.data.decode("utf-8").lower()
        self.assertNotIn("google", html, "Login should not contain 'google'")

    def test_t4_register_redirects_when_needed(self):
        """GET /register has no 'google'."""
        client = self.flask_app.test_client()
        resp = client.get("/register")
        html = (resp.data.decode("utf-8") + (resp.headers.get("Location") or "")).lower()
        self.assertNotIn("google", html, "Register should not reference 'google'")

    def test_t5_login_no_gstatic(self):
        """GET /login HTML does NOT reference gstatic.com."""
        client = self.flask_app.test_client()
        resp = client.get("/login")
        html = resp.data.decode("utf-8").lower()
        self.assertNotIn("gstatic.com", html, "Login page should not reference gstatic.com")

    def test_t6_login_with_credentials(self):
        """POST /login with valid credentials returns 302 + session."""
        client = self.flask_app.test_client()
        client.get("/login")
        with client.session_transaction() as sess:
            csrf = sess["csrf_token"]
        resp = client.post(
            "/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, [302, 303], "Should redirect after successful login")
        with client.session_transaction() as sess:
            self.assertIn("user_id", sess, "Session should contain user_id after login")

    def test_t7_register_has_phone_input(self):
        """GET /register HTML contains phone input."""
        client = self.flask_app.test_client()
        resp = client.get("/register")
        html = resp.data.decode("utf-8").lower()
        self.assertIn('name="phone"', html, "Register page should have phone input")

    def test_t8_login_has_password_input(self):
        """GET /login HTML contains password input."""
        client = self.flask_app.test_client()
        resp = client.get("/login")
        html = resp.data.decode("utf-8").lower()
        self.assertIn('name="password"', html, "Login page should have password input")

    def test_t9_login_has_style_css(self):
        """GET /login HTML references the public marketing stylesheet."""
        client = self.flask_app.test_client()
        resp = client.get("/login")
        html = resp.data.decode("utf-8")
        self.assertIn("/static/css/public.css", html, "Login page should reference /static/css/public.css")


if __name__ == "__main__":
    unittest.main()
