"""Creator phone login, trusted device, forgot-password, and account extras."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-creator-auth-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
os.environ["SMS_PROVIDER"] = "console"
for key in ("DATABASE_URL", "AUTH_PROVIDER", "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
    os.environ.pop(key, None)

PHONE = "+60123456789"
PASSWORD = "CreatorAuthPass99!"
COMMON_PW = "password12345"


class CreatorAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module
        from password_policy import hash_password

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
                    """INSERT INTO users (email, password_hash, account_kind, phone)
                       VALUES (?, ?, ?, ?)""",
                    (
                        "creator-auth@example.test",
                        hash_password(PASSWORD),
                        "merchant",
                        PHONE,
                    ),
                )
                cls.user_id = int(cur.lastrowid)
                conn.execute(
                    """INSERT INTO users (email, password_hash, account_kind, phone)
                       VALUES (?, ?, ?, ?)""",
                    (
                        "reset-auth@example.test",
                        hash_password(PASSWORD),
                        "merchant",
                        "+60111111111",
                    ),
                )
                cls.reset_phone = "+60111111111"
                conn.execute(
                    """INSERT INTO users (email, password_hash, account_kind)
                       VALUES (?, ?, ?)""",
                    (
                        "legacy-no-phone@example.test",
                        generate_password_hash("LegacyPass99!", method="pbkdf2:sha256:600000"),
                        "merchant",
                    ),
                )

    def setUp(self):
        self.client = self.app.test_client()

    def _csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            return sess.get("csrf_token")

    def test_new_device_requires_sms(self):
        csrf = self._csrf()
        with patch("customer_verification.generate_otp_code", return_value="654321"):
            resp = self.client.post(
                "/login",
                data={"csrf_token": csrf, "email": PHONE, "password": PASSWORD},
                follow_redirects=False,
            )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("device_code", html)
        with self.client.session_transaction() as sess:
            self.assertEqual(int(sess.get("pending_device_user_id") or 0), self.user_id)
            self.assertNotIn("user_id", sess)
            csrf = sess["csrf_token"]
        resp = self.client.post(
            "/login/device",
            data={"csrf_token": csrf, "device_code": "654321"},
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, {302, 303})
        cookie = self.client.get_cookie("zintriq_device")
        self.assertIsNotNone(cookie)
        with self.client.session_transaction() as sess:
            self.assertEqual(int(sess.get("user_id") or 0), self.user_id)

    def test_trusted_cookie_skips_sms(self):
        from trusted_devices import COOKIE_NAME, issue_trusted_device

        with self.app.app_context():
            with self.app_module.db() as conn:
                token = issue_trusted_device(conn, self.user_id, label="test")
        self.client.set_cookie("zintriq_device", token)
        csrf = self._csrf()
        resp = self.client.post(
            "/login",
            data={"csrf_token": csrf, "email": PHONE, "password": PASSWORD},
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, {302, 303})
        with self.client.session_transaction() as sess:
            self.assertEqual(int(sess.get("user_id") or 0), self.user_id)

    def test_wrong_password_is_generic(self):
        csrf = self._csrf()
        resp = self.client.post(
            "/login",
            data={"csrf_token": csrf, "email": PHONE, "password": "nope-nope-nope"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Phone or password is incorrect.", resp.get_data(as_text=True))

    def test_forgot_sms_then_reset_invalidates_sessions(self):
        csrf = self._csrf()
        with patch("customer_verification.generate_otp_code", return_value="111222"):
            send = self.client.post(
                "/forgot-password",
                data={"csrf_token": csrf, "phone": self.reset_phone},
                follow_redirects=False,
            )
        self.assertIn(send.status_code, {302, 303})
        with self.client.session_transaction() as sess:
            csrf = sess["csrf_token"]
        verify = self.client.post(
            "/forgot-password/verify",
            data={"csrf_token": csrf, "phone": self.reset_phone, "code": "111222"},
            follow_redirects=False,
        )
        self.assertIn(verify.status_code, {302, 303})
        location = verify.headers.get("Location") or ""
        self.assertIn("/reset-password/", location)
        token = location.rsplit("/", 1)[-1]
        with self.client.session_transaction() as sess:
            csrf = sess["csrf_token"]
        new_pw = "FreshResetPass88!"
        reset = self.client.post(
            f"/reset-password/{token}",
            data={"csrf_token": csrf, "password": new_pw, "confirm_password": new_pw},
            follow_redirects=False,
        )
        self.assertIn(reset.status_code, {302, 303})
        with self.app.app_context():
            with self.app_module.db() as conn:
                row = conn.execute(
                    "SELECT id, session_version FROM users WHERE phone = ?",
                    (self.reset_phone,),
                ).fetchone()
                devices = conn.execute(
                    "SELECT COUNT(*) AS n FROM trusted_devices WHERE user_id = ?",
                    (row["id"],),
                ).fetchone()
        self.assertGreaterEqual(int(row["session_version"] or 1), 2)
        self.assertEqual(int(devices["n"]), 0)

    def test_verify_phone_uses_marketing_portal_header(self):
        with self.app.app_context():
            with self.app_module.db() as conn:
                row = conn.execute(
                    "SELECT id, session_version FROM users WHERE email = ?",
                    ("legacy-no-phone@example.test",),
                ).fetchone()
                uid = int(row["id"])
                sess_ver = int(row["session_version"] or 1)
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
            sess["session_version"] = sess_ver
        page = self.client.get("/account/verify-phone?hl=zh-Hans", follow_redirects=False)
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("css/tokens-marketing.css", html)
        self.assertIn("css/public.css", html)
        self.assertIn("site-nav__links", html)
        self.assertIn("/product", html)
        self.assertIn("/download", html)
        self.assertIn("force-phone", html)
        self.assertIn('name="action" value="send"', html)
        self.assertIn("请先绑定手机号", html)
        header = html.split("<main", 1)[0]
        self.assertNotIn("我的账户", header)
        self.assertIn("退出登录", header)
        self.assertIn("简体中文", header)

    def test_legacy_user_not_forced_to_verify_phone(self):
        csrf = self._csrf()
        resp = self.client.post(
            "/login",
            data={
                "csrf_token": csrf,
                "email": "legacy-no-phone@example.test",
                "password": "LegacyPass99!",
            },
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, {302, 303})
        gated = self.client.get("/account", follow_redirects=False)
        loc = gated.headers.get("Location") or ""
        self.assertNotIn("/account/verify-phone", loc)

    def test_link_email_and_change_phone(self):
        csrf = self._csrf()
        with self.app.app_context():
            with self.app_module.db() as conn:
                ver = conn.execute(
                    "SELECT session_version FROM users WHERE id = ?",
                    (self.user_id,),
                ).fetchone()
                sess_ver = int(ver["session_version"] or 1) if ver else 1
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["session_version"] = sess_ver
            csrf = sess["csrf_token"]
        with patch("customer_verification.generate_otp_code", return_value="333444"):
            send = self.client.post(
                "/account/link-email/send",
                data={"csrf_token": csrf, "email": "linked@example.test"},
                follow_redirects=False,
            )
        self.assertIn(send.status_code, {302, 303})
        with self.client.session_transaction() as sess:
            csrf = sess["csrf_token"]
        check = self.client.post(
            "/account/link-email/check",
            data={"csrf_token": csrf, "email": "linked@example.test", "code": "333444"},
            follow_redirects=False,
        )
        self.assertIn(check.status_code, {302, 303})
        page = self.client.get("/account", follow_redirects=False)
        self.assertIn(page.status_code, {200, 302, 303})

    def test_common_password_rejected(self):
        from password_policy import password_issues

        self.assertIsNotNone(password_issues(COMMON_PW))
        self.assertIsNone(password_issues("UniqueHorseBattery99!"))

    def test_prompt1_i18n_keys(self):
        import json

        root = Path(__file__).resolve().parent.parent / "i18n" / "locales"
        en = json.loads((root / "en.json").read_text(encoding="utf-8"))
        zh = json.loads((root / "zh-Hans.json").read_text(encoding="utf-8"))
        for key in (
            "auth.phone.send_code",
            "auth.register.consent",
            "auth.login.new_device",
            "auth.forgot.sent_neutral",
            "account.phone.required",
            "account.welcome",
        ):
            self.assertIn(key, en)
            self.assertIn(key, zh)

    def test_common_passwords_file(self):
        path = Path(__file__).resolve().parent.parent / "data" / "common-passwords.txt"
        self.assertTrue(path.is_file())
        count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        self.assertGreaterEqual(count, 100_000)


if __name__ == "__main__":
    unittest.main()
