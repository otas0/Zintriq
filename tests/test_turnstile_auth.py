"""Turnstile CAPTCHA on auth forms — no Google; optional when keys unset."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

os.environ.setdefault("SECRET_KEY", "test-turnstile-secret")
for key in (
    "AUTH_PROVIDER",
    "AUTH0_DOMAIN",
    "AUTH0_CLIENT_ID",
    "AUTH0_CLIENT_SECRET",
    "DATABASE_URL",
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "TURNSTILE_REQUIRED",
):
    os.environ.pop(key, None)


class TurnstileUnitTests(unittest.TestCase):
    def test_unconfigured_allows(self):
        from turnstile_protect import request_passes_turnstile, turnstile_configured

        self.assertFalse(turnstile_configured())
        with mock.patch("turnstile_protect.extract_turnstile_token", return_value=""):
            self.assertTrue(request_passes_turnstile())

    def test_configured_requires_token(self):
        from turnstile_protect import verify_turnstile

        with mock.patch.dict(
            os.environ,
            {
                "TURNSTILE_SITE_KEY": "site",
                "TURNSTILE_SECRET_KEY": "secret",
            },
            clear=False,
        ):
            self.assertFalse(verify_turnstile(""))

    def test_verify_success_mocked(self):
        from turnstile_protect import verify_turnstile

        class _Resp:
            def read(self):
                return json.dumps({"success": True}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch.dict(
            os.environ,
            {"TURNSTILE_SITE_KEY": "site", "TURNSTILE_SECRET_KEY": "secret"},
            clear=False,
        ):
            with mock.patch("urllib.request.urlopen", return_value=_Resp()):
                self.assertTrue(verify_turnstile("tok", "1.2.3.4"))


class TurnstileRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app = app_module.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-test-token"

    def test_register_get_no_widget_without_keys(self):
        resp = self.client.get("/register?local=1")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"cf-turnstile", resp.data)
        self.assertNotIn(b"google.com/recaptcha", resp.data)

    def test_register_get_shows_widget_with_site_key(self):
        with mock.patch.dict(os.environ, {"TURNSTILE_SITE_KEY": "1x00000000000000000000AA"}, clear=False):
            resp = self.client.get("/register?local=1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"cf-turnstile", resp.data)
        self.assertIn(b"1x00000000000000000000AA", resp.data)
        self.assertNotIn(b"google.com/recaptcha", resp.data)

    def test_login_post_rejects_without_token_when_configured(self):
        with mock.patch.dict(
            os.environ,
            {
                "TURNSTILE_SITE_KEY": "site",
                "TURNSTILE_SECRET_KEY": "secret",
            },
            clear=False,
        ):
            with mock.patch("turnstile_protect.verify_turnstile", return_value=False):
                resp = self.client.post(
                    "/login?local=1",
                    data={
                        "csrf_token": "csrf-test-token",
                        "email": "nobody@example.com",
                        "password": "password-long-enough",
                    },
                    follow_redirects=True,
                )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"security check", resp.data.lower())


if __name__ == "__main__":
    unittest.main()
