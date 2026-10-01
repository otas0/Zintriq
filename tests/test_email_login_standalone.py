"""G-0 pre-flight: verify email/password login works without Firebase.

This test proves that the /login route uses only werkzeug.security
password hashing and SQLite — zero Firebase dependency. If this test
passes, G-2 (Firebase removal) is safe to proceed.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.security import generate_password_hash

TEST_EMAIL = "g0-test-merchant@example.com"
TEST_PASSWORD = "G0StandaloneTest12!"
FIREBASE_ONLY_EMAIL = "g17-firebase-only@example.com"
FIREBASE_ONLY_UID = "firebase-uid-g17-test"


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
    conn.execute(
        "INSERT INTO users (email, password_hash, firebase_uid, account_kind) VALUES (?, ?, ?, ?)",
        (FIREBASE_ONLY_EMAIL, "firebase-only", FIREBASE_ONLY_UID, "merchant"),
    )
    conn.commit()
    conn.close()


def _client_with_csrf(flask_app):
    """Return a test client that has a valid CSRF token in its session."""
    client = flask_app.test_client()
    client.get("/login")
    return client


class EmailLoginStandaloneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp.close()
        cls.db_path = cls._tmp.name
        _create_test_db(cls.db_path)

        import app as app_module
        cls.app_module = app_module
        cls._orig_database = app_module.DATABASE
        app_module.DATABASE = Path(cls.db_path)

        cls.flask_app = app_module.app
        cls.flask_app.config["TESTING"] = True
        cls.flask_app.config["SECRET_KEY"] = "g0-test-secret"

    @classmethod
    def tearDownClass(cls):
        cls.app_module.DATABASE = cls._orig_database
        os.unlink(cls.db_path)

    def test_email_login_returns_redirect(self):
        """POST /login with valid email/password returns 302."""
        client = _client_with_csrf(self.flask_app)
        with client.session_transaction() as sess:
            csrf = sess["csrf_token"]

        response = client.post(
            "/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertIn(response.status_code, (301, 302), f"Expected redirect, got {response.status_code}")

    def test_email_login_sets_session(self):
        """POST /login sets session cookie (user_id in session)."""
        client = _client_with_csrf(self.flask_app)
        with client.session_transaction() as sess:
            csrf = sess["csrf_token"]

        response = client.post(
            "/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertIn(response.status_code, (301, 302))

        with client.session_transaction() as sess:
            self.assertIn("user_id", sess, "session must contain user_id after login")

    def test_email_login_no_firebase_call(self):
        """POST /login does NOT call any firebase_admin function."""
        import app as app_module

        firebase_mock = MagicMock()
        firebase_mock.initialize_app = MagicMock(side_effect=AssertionError("firebase_admin.initialize_app called during email login"))

        patches = []
        if getattr(app_module, "firebase_admin", None) is not None:
            p1 = patch.object(app_module, "firebase_admin", firebase_mock)
            patches.append(p1)
        if getattr(app_module, "firebase_auth", None) is not None:
            fa_mock = MagicMock(side_effect=AssertionError("firebase_auth called during email login"))
            p2 = patch.object(app_module, "firebase_auth", fa_mock)
            patches.append(p2)

        for p in patches:
            p.start()

        try:
            client = _client_with_csrf(self.flask_app)
            with client.session_transaction() as sess:
                csrf = sess["csrf_token"]

            response = client.post(
                "/login",
                data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "csrf_token": csrf},
                follow_redirects=False,
            )
            self.assertIn(response.status_code, (301, 302))
            firebase_mock.initialize_app.assert_not_called()
        finally:
            for p in patches:
                p.stop()

    def test_wrong_password_rejected(self):
        """POST /login with wrong password stays on login page."""
        client = _client_with_csrf(self.flask_app)
        with client.session_transaction() as sess:
            csrf = sess["csrf_token"]

        response = client.post(
            "/login",
            data={"email": TEST_EMAIL, "password": "WrongPassword99999!", "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200, "Wrong password should re-render login form")

    def test_firebase_only_dummy_password_rejected(self):
        """G-1.7: Firebase-only accounts cannot be accessed with dummy password guesses.

        A Firebase-only account has password_hash="firebase-only" (not a real
        PBKDF2 hash). This test verifies that common guesses are all rejected.
        """
        password_guesses = [
            "firebase-only",
            "",
            "firebase_only",
            "FIREBASE-ONLY",
            "firebase only",
        ]

        for guess in password_guesses:
            client = _client_with_csrf(self.flask_app)
            with client.session_transaction() as sess:
                csrf = sess["csrf_token"]

            response = client.post(
                "/login",
                data={"email": FIREBASE_ONLY_EMAIL, "password": guess, "csrf_token": csrf},
                follow_redirects=False,
            )
            self.assertEqual(
                response.status_code, 200,
                f"Password guess '{guess}' must be rejected (got {response.status_code})"
            )
            with client.session_transaction() as sess:
                self.assertNotIn(
                    "user_id", sess,
                    f"Password guess '{guess}' must NOT set user_id in session"
                )


if __name__ == "__main__":
    unittest.main()
