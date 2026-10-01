"""G-1.6: verify password reset works for Firebase-only accounts.

A Firebase-only account has firebase_uid set and a placeholder password_hash
(e.g. "firebase-only" or empty). This test proves that the /forgot-password
→ /reset-password flow can convert such an account to a normal email/password
account, enabling G-2 (Firebase removal) without locking out existing users.
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

from werkzeug.security import generate_password_hash, check_password_hash

FIREBASE_EMAIL = "g16-firebase-only@example.com"
FIREBASE_UID = "firebase-uid-g16-test-12345"
NEW_PASSWORD = "G16NewPassword99!"


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
        "INSERT INTO users (email, password_hash, firebase_uid, account_kind) VALUES (?, ?, ?, ?)",
        (FIREBASE_EMAIL, "firebase-only", FIREBASE_UID, "merchant"),
    )
    conn.commit()
    conn.close()


def _client_with_csrf(flask_app):
    client = flask_app.test_client()
    client.get("/login")
    return client


def _get_csrf(client):
    with client.session_transaction() as sess:
        return sess["csrf_token"]


class FirebaseOnlyPasswordResetTest(unittest.TestCase):
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
        cls.flask_app.config["SECRET_KEY"] = "g16-test-secret"

    @classmethod
    def tearDownClass(cls):
        cls.app_module.DATABASE = cls._orig_database
        os.unlink(cls.db_path)

    def _user_id(self):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT id FROM users WHERE email=?", (FIREBASE_EMAIL,)).fetchone()
        conn.close()
        return row[0]

    def setUp(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE users SET password_hash='firebase-only' WHERE email=?", (FIREBASE_EMAIL,))
        conn.execute("DELETE FROM auth_tokens WHERE user_id=(SELECT id FROM users WHERE email=?)", (FIREBASE_EMAIL,))
        conn.commit()
        conn.close()

    def test_firebase_account_has_dummy_password(self):
        """Pre-condition: Firebase-only account has non-verifiable password_hash."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT password_hash, firebase_uid FROM users WHERE email=?", (FIREBASE_EMAIL,)
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "firebase-only", "pre-condition: dummy password_hash")
        self.assertEqual(row[1], FIREBASE_UID, "pre-condition: firebase_uid is set")
        self.assertFalse(
            check_password_hash(row[0], "anypassword"),
            "dummy hash must not verify against any password",
        )

    def test_forgot_password_creates_token_for_firebase_account(self):
        """POST /forgot-password creates a reset token for a Firebase-only account."""
        client = _client_with_csrf(self.flask_app)
        csrf = _get_csrf(client)
        response = client.post(
            "/forgot-password",
            data={"email": FIREBASE_EMAIL, "csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertIn(response.status_code, (301, 302), "forgot-password should redirect")

        conn = sqlite3.connect(self.db_path)
        token_row = conn.execute(
            "SELECT id FROM auth_tokens WHERE user_id=? AND purpose='reset' ORDER BY id DESC LIMIT 1",
            (self._user_id(),),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(token_row, "reset token must be created for Firebase-only account")

    def test_reset_password_sets_real_hash_for_firebase_account(self):
        """POST /reset-password/<token> sets a real PBKDF2 hash for a Firebase-only account."""
        uid = self._user_id()
        token = self.app_module.create_auth_token(uid, "reset")

        client = _client_with_csrf(self.flask_app)
        csrf = _get_csrf(client)
        response = client.post(
            f"/reset-password/{token}",
            data={
                "password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertIn(response.status_code, (301, 302), "reset-password should redirect after success")

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        self.assertTrue(row[0].startswith("pbkdf2:"), "password_hash must now be PBKDF2")
        self.assertTrue(check_password_hash(row[0], NEW_PASSWORD), "new password must verify")

    def test_firebase_account_can_login_after_reset(self):
        """After password reset, a Firebase-only account can login with email/password."""
        uid = self._user_id()

        reset_token = self.app_module.create_auth_token(uid, "reset")
        client = _client_with_csrf(self.flask_app)
        csrf = _get_csrf(client)
        client.post(
            f"/reset-password/{reset_token}",
            data={
                "password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        client2 = _client_with_csrf(self.flask_app)
        csrf2 = _get_csrf(client2)
        response = client2.post(
            "/login",
            data={"email": FIREBASE_EMAIL, "password": NEW_PASSWORD, "csrf_token": csrf2},
            follow_redirects=False,
        )
        self.assertIn(response.status_code, (301, 302), f"login should redirect, got {response.status_code}")
        with client2.session_transaction() as sess:
            self.assertIn("user_id", sess, "login must set user_id in session")
            self.assertEqual(sess["user_id"], uid)


if __name__ == "__main__":
    unittest.main()
