"""Sitemap, robots, and noindex for incomplete locales."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-seo-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
os.environ["CONTACT_EMAIL"] = "hello@zintriq.test"
for key in ("DATABASE_URL", "AUTH_PROVIDER", "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
    os.environ.pop(key, None)


class SiteSeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        os.environ.pop("DATABASE_URL", None)
        os.environ["SQLITE_PATH"] = _TMP_DB.name
        os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
        app_module.DATABASE = Path(_TMP_DB.name)
        cls.app = app_module.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    def test_sitemap_lists_launch_pages_and_picker_languages(self):
        xml = self.client.get("/sitemap.xml").get_data(as_text=True)
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)
        self.assertIn("https://zintriq.test/product", xml)
        self.assertIn("https://zintriq.test/product?hl=zh-Hans", xml)
        self.assertIn("https://zintriq.test/pricing", xml)
        self.assertIn("hreflang=\"x-default\"", xml)
        self.assertIn("hreflang=\"en\"", xml)
        self.assertIn("hreflang=\"zh-Hans\"", xml)
        self.assertNotIn("/account", xml)
        self.assertNotIn("/studio", xml)
        self.assertNotIn("/app/", xml)

    def test_robots_allows_public_and_blocks_private(self):
        text = self.client.get("/robots.txt").get_data(as_text=True)
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
        self.assertIn("Allow: /", text)
        self.assertIn("Disallow: /account", text)
        self.assertIn("Disallow: /api", text)
        self.assertIn("Disallow: /studio", text)
        self.assertIn("Disallow: /app", text)
        self.assertIn("Disallow: /locale", text)
        self.assertIn("Sitemap: https://zintriq.test/sitemap.xml", text)

    def test_noindex_for_partial_locale_only(self):
        english = self.client.get("/product").get_data(as_text=True)
        self.assertIn('rel="canonical"', english)
        self.assertIn('name="description"', english)
        self.assertIn("og:title", english)
        self.assertNotIn("noindex", english)
        partial = self.client.get("/product?hl=de")
        html = partial.get_data(as_text=True)
        self.assertIn("noindex", html)

    def test_docs_hides_hardware_in_stage_one(self):
        html = self.client.get("/docs").get_data(as_text=True)
        self.assertIn("What Zintriq is", html)
        self.assertIn("How you make something", html)
        self.assertIn("Hardware is one target", html)
        footer = html.split("<footer", 1)[-1]
        self.assertIn(">Docs<", footer)
        self.assertNotIn("Install and first project", footer)

    def test_contact_fallback_without_mail(self):
        os.environ.pop("SMTP_HOST", None)
        html = self.client.get("/contact").get_data(as_text=True)
        self.assertIn("Contact us", html)
        self.assertIn("hello@zintriq.test", html)
        self.assertNotIn('name="topic"', html)
        os.environ["SMTP_HOST"] = "console"
        forms = self.client.get("/contact").get_data(as_text=True)
        self.assertIn('name="message"', forms)
        os.environ.pop("SMTP_HOST", None)

    def test_residency_copy_not_rendered(self):
        for path in (
            "/",
            "/?stay=1",
            "/product",
            "/about",
            "/security",
            "/legal/privacy",
            "/legal/terms",
            "/legal/imprint",
            "/login?local=1",
            "/register?local=1",
        ):
            html = self.client.get(path).get_data(as_text=True)
            self.assertNotIn("Shanghai", html, path)
            self.assertNotIn("Frankfurt", html, path)
            self.assertNotIn("上海", html, path)
            self.assertNotIn("法兰克福", html, path)

    def test_contact_email_default(self):
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath("site_config.py").read_text()
        self.assertIn('"zintriq@gmail.com"', source)

    def test_footer_has_region_name_and_legal_label(self):
        html = self.client.get("/product").get_data(as_text=True)
        self.assertIn("Region:", html)
        self.assertIn("International", html)
        self.assertIn("Legal", html)
        self.assertNotIn("Imprint", html)
        self.assertIn("Docs", html.split("<footer", 1)[-1])
        self.assertNotIn("How the meta-system works", html.split("<footer", 1)[-1])
        self.assertNotIn("How to make in the app", html.split("<footer", 1)[-1])
        self.assertNotIn("Help translate", html.split("<footer", 1)[-1])
        self.assertNotIn("Start translating", html.split("<footer", 1)[-1])
