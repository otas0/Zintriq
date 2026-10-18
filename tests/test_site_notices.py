"""Download, launch-notice, and hardware waitlist mail."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-notice-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
os.environ["SMTP_HOST"] = "smtp.test"
os.environ["SITE_NOTICE_LIMIT"] = "5"
for key in ("DATABASE_URL", "AUTH_PROVIDER", "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
    os.environ.pop(key, None)


class SiteNoticeTests(unittest.TestCase):
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
            with patch("db_adapter.using_postgres", return_value=False), patch(
                "app.using_postgres", return_value=False, create=True
            ):
                app_module.init_db()

    def setUp(self):
        os.environ["SMTP_HOST"] = "smtp.test"
        os.environ["SITE_NOTICE_LIMIT"] = "5"
        self.client = self.app.test_client()
        with self.app.app_context():
            from app import db

            with db() as conn:
                from site_notices import init_site_notice_tables

                init_site_notice_tables(conn)
                conn.execute("DELETE FROM site_notices")
                conn.execute("DELETE FROM site_notice_hits")

    def _csrf(self, path):
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        match = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
        self.assertIsNotNone(match)
        return match.group(1), page

    def _post(self, path, **fields):
        token, _page = self._csrf(path)
        fields["csrf_token"] = token
        return self.client.post(path, data=fields)

    def test_download_link_stores_sends_and_rejects_duplicate(self):
        with patch("email_delivery.send_transactional_email", return_value=True) as send:
            first = self._post("/download", kind="download_link", email="ada@example.com")
            body = first.get_data(as_text=True)
            self.assertIn("Sent to ada@example.com.", body)
            self.assertEqual(send.call_count, 1)
            self.assertIn("/notify/unsubscribe/", send.call_args[0][2])
            second = self._post("/download", kind="download_link", email="ada@example.com")
            again = second.get_data(as_text=True)
            self.assertIn("already on the list", again)
            self.assertEqual(send.call_count, 1)
        with self.app.app_context():
            from app import db

            with db() as conn:
                row = conn.execute(
                    "SELECT email, kind FROM site_notices WHERE email = ?",
                    ("ada@example.com",),
                ).fetchone()
        self.assertEqual(row["kind"], "download_link")

    def test_rate_limit(self):
        os.environ["SITE_NOTICE_LIMIT"] = "2"
        with patch("email_delivery.send_transactional_email", return_value=True):
            self._post("/download", kind="download_link", email="one@example.com")
            self._post("/download", kind="download_link", email="two@example.com")
            blocked = self._post("/download", kind="download_link", email="three@example.com")
        self.assertIn("Too many requests", blocked.get_data(as_text=True))
        with self.app.app_context():
            from app import db

            with db() as conn:
                count = conn.execute("SELECT COUNT(*) AS n FROM site_notices").fetchone()["n"]
        self.assertEqual(count, 2)

    def test_form_hidden_without_mail(self):
        os.environ.pop("SMTP_HOST", None)
        page = self.client.get("/download")
        html = page.get_data(as_text=True)
        self.assertNotIn('name="kind"', html)
        self.assertIn("Coming soon", html)

    def test_hardware_waitlist(self):
        with patch("email_delivery.send_transactional_email", return_value=True) as send:
            page = self._post(
                "/hardware",
                kind="hardware_wait",
                email="hw@example.com",
                region="Germany",
                use="a queue display",
            )
        self.assertIn("hw@example.com", page.get_data(as_text=True))
        self.assertEqual(send.call_count, 1)

    def test_pricing_yearly_keeps_cents(self):
        page = self.client.get("/pricing")
        html = page.get_data(as_text=True)
        self.assertIn("$100 / year", html)
        self.assertIn("$8.33", html)
        self.assertIn("$200 per seat / year", html)
        self.assertIn("$16.67", html)
        self.assertIn("per seat", html)
        self.assertNotIn("Most popular", html)
        self.assertIn("/download", html)
        self.assertIn("plan-card__cta", html)
        self.assertNotIn("/download#notify", html)

    def test_subscription_copy_uses_stripe_not_paddle(self):
        import json

        root = Path(__file__).resolve().parents[1]
        for name in ("en.json", "zh-Hans.json"):
            data = json.loads((root / "i18n" / "locales" / name).read_text(encoding="utf-8"))
            self.assertIn("Stripe", data["pricing.faq.charge.a"])
            self.assertIn("Stripe", data["footer.mor"])
            self.assertNotIn("Paddle", data["pricing.faq.charge.a"])
            self.assertNotIn("Paddle", data["footer.mor"])
            self.assertNotIn("{mor_name}", data["contact.billing_note"])
        for path in ("/pricing", "/contact"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertNotIn("Paddle", html)

    def test_unified_platform_notify_form(self):
        html = self.client.get("/download").get_data(as_text=True)
        self.assertEqual(html.count('name="kind" value="platform_notify"'), 1)
        self.assertIn('name="platform"', html)
        self.assertIn("Your email", html)
        self.assertIn('id="dl-notify-email"', html)

    def test_accessible_auth_and_marketing_forms(self):
        login = self.client.get("/login?local=1").get_data(as_text=True)
        form = login.split('class="mq-auth-form"', 1)[-1].split("</form>", 1)[0]
        self.assertIn('id="login-email"', form)
        self.assertIn('autocomplete="username"', form)
        self.assertIn('autocomplete="current-password"', form)
        self.assertNotIn('autocomplete="off"', form)
        register = self.client.get("/register?local=1").get_data(as_text=True)
        self.assertIn('autocomplete="one-time-code"', register)
        self.assertIn('autocomplete="new-password"', register)
        forgot = self.client.get("/forgot-password").get_data(as_text=True)
        self.assertIn('autocomplete="one-time-code"', forgot)
        self.assertIn('for="forgot-code"', forgot)
        contact = self.client.get("/contact").get_data(as_text=True)
        self.assertNotIn("Paddle", contact)
        docs = self.client.get("/docs").get_data(as_text=True)
        self.assertIn('for="docs-search"', docs)
        self.assertIn('enterkeyhint="search"', docs)
        self.assertIn("no editor", docs)
        self.assertIn("How you make something", docs)
        self.assertNotIn("InterVariable.woff2", docs)
        hardware = self.client.get("/hardware").get_data(as_text=True)
        self.assertIn('for="hw-wait-region"', hardware)
        download = self.client.get("/download").get_data(as_text=True)
        self.assertNotIn('style="margin:0"', download)

    def test_theme_cookie_on_html(self):
        self.client.set_cookie("mq_theme", "dark")
        html = self.client.get("/product").get_data(as_text=True)
        self.assertIn('data-theme="dark"', html)
        self.assertIn('data-theme-pref="dark"', html)
        self.assertIn("data-theme-cycle", html)

    def test_phase2_pages_render(self):
        for path, needle in (
            ("/product", "meta-space"),
            ("/hardware", "physical world"),
            ("/security", "Security &amp; privacy"),
            ("/about", "meta-space"),
            ("/contact", "Contact us"),
            ("/docs", "Search docs"),
            ("/changelog", "Changelog"),
            ("/compare/site-builders", "Common website builders"),
            ("/compare/low-code", "Common low-code platforms"),
            ("/translate", "Bring Zintriq"),
            ("/login?local=1", "Log in to Zintriq"),
            ("/register?local=1", "Create your Zintriq account"),
        ):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200, path)
            self.assertIn(needle, page.get_data(as_text=True), path)

    def test_security_page_desktop_and_stripe(self):
        html = self.client.get("/security").get_data(as_text=True)
        self.assertIn("Stripe", html)
        self.assertIn("desktop", html.lower())
        self.assertNotIn("Frankfurt", html)
        self.assertNotIn("Shanghai", html)
        self.assertNotIn("Google services", html.lower())
        self.assertNotIn("InterVariable.woff2", html)
        zh = self.client.get("/security?hl=zh-Hans").get_data(as_text=True)
        self.assertIn("桌面", zh)
        self.assertIn("暂缓", zh)

    def test_community_template_has_no_raw_keys(self):
        from flask import render_template

        with self.app.app_context(), self.app.test_request_context("/app/community"):
            html = render_template(
                "studio/community.html",
                pending_package="",
                studio_mode=True,
                studio_base="/studio",
                workspace={"name": "Studio"},
            )
        main = html.split("<main", 1)[1].split("</main>", 1)[0]
        self.assertNotIn("page.community", main)
        self.assertNotRegex(main, r"(?<![A-Za-z0-9_-])(?:community|item|share|profile)\.[a-z0-9_.]+")
        self.assertIn("da-community", main)
        self.assertIn("Your published descriptions", html)
        self.assertNotIn("COMMUNITY_BOOT", html)
