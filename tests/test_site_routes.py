"""Smoke tests for public site routes, retired URLs, desktop studio, and template url_for."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-site-routes-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
os.environ["CONTACT_EMAIL"] = "hello@zintriq.test"
for key in ("DATABASE_URL", "AUTH_PROVIDER", "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
    os.environ.pop(key, None)

PUBLIC_GET = (
    "/",
    "/?stay=1",
    "/product",
    "/download",
    "/hardware",
    "/pricing",
    "/docs",
    "/plugins",
    "/security",
    "/about",
    "/contact",
    "/changelog",
    "/compare/site-builders",
    "/compare/low-code",
    "/translate",
    "/status",
    "/legal/privacy",
    "/legal/terms",
    "/legal/cookies",
    "/legal/imprint",
    "/login",
    "/register",
    "/account",
    "/sitemap.xml",
    "/robots.txt",
)

RETIRED_GET = (
    "/primitives",
    "/templates",
    "/how-it-works",
    "/compositions",
    "/connections",
    "/customers",
    "/blog",
    "/community",
    "/activate",
    "/extend",
    "/discover",
    "/venues",
    "/places",
    "/home",
    "/studio",
    "/account/workspaces",
    "/builder",
    "/app/community",
    "/build",
    "/build/demo",
    "/build/demo/home",
    "/api/builder-core/projects",
)

URL_FOR_RE = re.compile(r"""url_for\(\s*['"]([A-Za-z_][\w.]*)['"]""")
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
DOTTED_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:nav|home|footer|auth|pricing|dl|hw|product|contact|about|sec|docs|"
    r"changelog|translate|plan|cta|form|theme|err|legal|page|region|aria|compare)\.[a-z0-9_.]+"
)


def _visible_html(html: str) -> str:
    html = SCRIPT_RE.sub("", html)
    html = STYLE_RE.sub("", html)
    return html


def _expected_statuses(path: str) -> set[int]:
    if path == "/" or path.startswith("/?stay="):
        return {200, 302}
    if path == "/account":
        return {302}
    return {200}


class SiteRouteSmokeTests(unittest.TestCase):
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

    def setUp(self):
        self.client = self.app.test_client()

    def test_public_routes_en_and_zh(self):
        for lang in ("en", "zh-Hans", "zh-Hant"):
            for path in PUBLIC_GET:
                url = f"{path}?hl={lang}" if "?" not in path else f"{path}&hl={lang}"
                if path in ("/sitemap.xml", "/robots.txt"):
                    url = path
                resp = self.client.get(url)
                self.assertIn(
                    resp.status_code,
                    _expected_statuses(path),
                    f"{url} -> {resp.status_code}",
                )
                if resp.status_code != 200:
                    continue
                body = resp.get_data(as_text=True)
                if path in ("/sitemap.xml", "/robots.txt"):
                    self.assertTrue(body)
                    continue
                visible = _visible_html(body)
                stray = [
                    key
                    for key in DOTTED_KEY_RE.findall(visible)
                    if not key.endswith((".css", ".js", ".html", ".svg", ".png", ".ico", ".xml", ".txt"))
                ]
                self.assertEqual(stray, [], f"untranslated keys on {url}: {stray[:8]}")

        account = self.client.get("/app/account")
        self.assertIn(account.status_code, {301, 302, 303})
        self.assertTrue(
            (account.headers.get("Location") or "").endswith("/account")
            or "/account?" in (account.headers.get("Location") or "")
        )
        unauth = self.client.get("/account", follow_redirects=False)
        self.assertEqual(unauth.status_code, 302)
        self.assertTrue(
            (unauth.headers.get("Location") or "").endswith("/login")
            or "/login?" in (unauth.headers.get("Location") or "")
        )

    def test_region_does_not_override_language(self):
        self.client.set_cookie("mq_lang", "zh-Hans")
        html = self.client.get("/us/product").get_data(as_text=True)
        self.assertIn('lang="zh-Hans"', html)
        self.assertIn("产品", html)
        self.assertNotIn(">Product<", html.split("<main", 1)[0])

    def test_language_switch_strips_hl_and_sets_cookie(self):
        resp = self.client.get(
            "/locale/en",
            query_string={"next": "/product?hl=zh-Hans"},
        )
        self.assertIn(resp.status_code, {301, 302, 303})
        location = resp.headers.get("Location") or ""
        self.assertTrue(location.endswith("/product"), location)
        self.assertNotIn("hl=", location)
        self.assertTrue(
            any("mq_lang=en" in c for c in resp.headers.getlist("Set-Cookie"))
        )

    def test_choose_region_does_not_set_language_cookie(self):
        self.client.set_cookie("mq_lang", "en")
        resp = self.client.get("/choose-region/cn")
        self.assertIn(resp.status_code, {301, 302, 303})
        cookies = ";".join(resp.headers.getlist("Set-Cookie"))
        self.assertNotIn("mq_lang=", cookies)
        html = self.client.get("/cn/product").get_data(as_text=True)
        self.assertIn('lang="en"', html)
        self.assertIn("Product", html)

    def test_retired_routes_are_404(self):
        for path in RETIRED_GET:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 404, path)

    def test_application_paths_retired_on_web_only(self):
        from site_retired import is_retired_web_path

        for path in (
            "/build",
            "/build/demo/home",
            "/builder-runtime/demo/home/booking",
            "/api/builder-core/projects",
            "/api/builder-core/projects/1/publish",
        ):
            self.assertTrue(is_retired_web_path(path, desktop=False), path)
            self.assertFalse(is_retired_web_path(path, desktop=True), path)
        self.assertTrue(is_retired_web_path("/account/workspaces", desktop=False))
        self.assertFalse(is_retired_web_path("/account/workspaces", desktop=True))
        self.assertFalse(is_retired_web_path("/product", desktop=False))
        self.assertFalse(is_retired_web_path("/api/studio/surfaces", desktop=False))

    def test_hosted_plugin_catalog_json(self):
        resp = self.client.get("/plugins/catalog.json")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["kind"], "store")
        self.assertEqual(body["protocol"], 7)
        self.assertTrue(body["packs"])
        scene = self.client.get("/plugins/files/scene.zintriq-plugin.json")
        self.assertEqual(scene.status_code, 200)
        pack = scene.get_json()
        self.assertEqual(pack["id"], "official-scene")
        self.assertEqual(pack["origin"], "official")
        missing = self.client.get("/plugins/files/../app.py")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("signature", body["packs"][0])
        home = self.client.get("/?stay=1&hl=en").get_data(as_text=True)
        self.assertNotIn("mock-editor", home)
        self.assertNotIn("universal-builder.js", home)
        js = self.client.get("/static/builder/universal-builder.js")
        self.assertEqual(js.status_code, 404)
        editor_js = self.client.get("/static/studio/meta-editor.js")
        self.assertEqual(editor_js.status_code, 404)
        runtime = self.client.get("/static/builder/universal-runtime.css")
        self.assertEqual(runtime.status_code, 404)
        published = self.client.get("/static/builder/published-runtime.js")
        self.assertEqual(published.status_code, 404)
        editor = self.client.get("/studio")
        self.assertEqual(editor.status_code, 404)
        built = self.client.get("/build/demo/home")
        self.assertEqual(built.status_code, 404)
        api = self.client.get("/api/builder-core/projects")
        self.assertEqual(api.status_code, 404)
        download = self.client.get("/download?stay=1&hl=en").get_data(as_text=True)
        self.assertIn("This website has no editor", download)
        self.assertNotIn("Sign in with your Zintriq account", download)

    def test_offline_copy_is_future(self):
        banned = "after you sign in once"
        home = self.client.get("/?stay=1&hl=en").get_data(as_text=True)
        self.assertIn("coming later", home.lower())
        self.assertIn("Work offline", home)
        self.assertNotIn(banned, home.lower())
        pricing = self.client.get("/pricing?stay=1&hl=en").get_data(as_text=True)
        self.assertIn("Can I use it offline?", pricing)
        self.assertNotIn("work offline for up to 30 days", pricing.lower())
        self.assertIn("Coming later", pricing)
        security = self.client.get("/security?stay=1&hl=en").get_data(as_text=True)
        later_at = security.find("When those features ship")
        now_at = security.find("How it works today")
        offline_at = security.find("coming later. You will be able to keep working without the network")
        self.assertGreater(later_at, 0)
        self.assertGreater(offline_at, later_at)
        self.assertGreater(later_at, now_at)
        compare = self.client.get("/compare/site-builders?stay=1&hl=en").get_data(as_text=True)
        self.assertIn("Offline coming later", compare)
        self.assertNotIn("works offline", compare.lower())

    def test_unshipped_plan_copy_is_future(self):
        home = self.client.get("/?stay=1&hl=en").get_data(as_text=True)
        self.assertIn("Paid plans will include cloud sync", home)
        self.assertNotIn("Plans include cloud sync and storage, with no extra fees.", home)
        pricing = self.client.get("/pricing?stay=1&hl=en").get_data(as_text=True)
        self.assertIn("Paid plans will include the desktop app", pricing)
        self.assertIn("Browse, remix and share on Community", pricing)
        self.assertIn("Release history and one-click rollback", pricing)
        self.assertIn("when cloud sync and storage ship", pricing)
        self.assertIn("When paid plans and hosting exist", pricing)
        register = self.client.get("/register?stay=1&hl=en").get_data(as_text=True)
        self.assertIn("One account for this website, the app, and Community.", register)
        self.assertNotIn("The app and Community will use it later", register)
        terms = self.client.get("/legal/terms?hl=en").get_data(as_text=True)
        self.assertIn("Working without a network is planned", terms)
        self.assertNotIn("intended for about 30 days", terms)
        self.assertIn("When hosted publishing exists", terms)
        self.assertIn("When trials ship", pricing)
        self.assertIn("Download when the app is ready", pricing)
        self.assertNotIn("Afterwards your workspace becomes read-only", pricing)

    def test_template_url_for_endpoints_are_registered(self):
        registered = set(self.app.view_functions)
        missing = []
        for template in sorted((ROOT / "templates").rglob("*.html")):
            text = template.read_text(encoding="utf-8")
            for match in URL_FOR_RE.finditer(text):
                endpoint = match.group(1)
                if endpoint == "static":
                    continue
                if endpoint not in registered:
                    missing.append(f"{template.relative_to(ROOT)} -> {endpoint}")
        self.assertEqual(missing, [])

    def test_legal_pages_match_meta_system(self):
        banned = (
            "student project",
            "QR code generation",
            "Donations are non-refundable",
            "Trustpilot",
            "Google Reviews",
            "payment aggregation",
        )
        for path in ("/legal/privacy", "/legal/terms", "/legal/cookies", "/legal/imprint"):
            html = self.client.get(f"{path}?hl=en").get_data(as_text=True)
            lower = html.lower()
            for phrase in banned:
                self.assertNotIn(phrase.lower(), lower, f"{path} still has {phrase!r}")
            self.assertNotIn("InterVariable.woff2", html)
            if path in ("/legal/privacy", "/legal/terms", "/legal/cookies"):
                self.assertIn("Stripe", html)
            if path == "/legal/terms":
                self.assertIn("describe", lower)
            de = self.client.get(f"{path}?hl=de").get_data(as_text=True)
            self.assertIn("authentic versions", de)
            zh = self.client.get(f"{path}?hl=zh-Hans").get_data(as_text=True)
            self.assertIn("公司注册", zh)
            self.assertNotIn("个人学生项目", zh)
            self.assertNotIn("二维码生成", zh)


class DesktopStudioRouteTests(unittest.TestCase):
    def test_desktop_studio_and_community_return_200(self):
        if os.environ.get("ZINTRIQ_DESKTOP") == "1":
            self.skipTest("parent environment enables desktop mode")
        temp = Path(tempfile.mkdtemp(prefix="zintriq-site-routes-desk-"))
        data_dir = temp / "data"
        data_dir.mkdir()
        token = "r" * 32 + "oute-desk-token"
        script = r"""
import os, sys
from pathlib import Path

token = sys.argv[1]
data_dir = sys.argv[2]
os.environ["ZINTRIQ_DESKTOP"] = "1"
os.environ["ZINTRIQ_DESKTOP_TOKEN"] = token
os.environ["ZINTRIQ_DATA_DIR"] = data_dir
os.environ["PORT"] = "5999"
os.environ["SECRET_KEY"] = "desktop-site-routes"
os.environ.pop("DATABASE_URL", None)

import app as app_module
app_module.app.config["TESTING"] = True
app_module.init_db()
client = app_module.app.test_client()
headers = {
    "X-Zintriq-Desktop-Token": token,
    "Host": "127.0.0.1:5999",
}
environ = {"REMOTE_ADDR": "127.0.0.1"}
studio = client.get("/studio", headers=headers, environ_base=environ)
community = client.get("/app/community", headers=headers, environ_base=environ)
assert studio.status_code == 200, studio.get_data(as_text=True)[:800]
assert community.status_code == 200, community.get_data(as_text=True)[:800]
assert 'href="/app/community"' in studio.get_data(as_text=True)
meta = client.get("/studio/meta", headers=headers, environ_base=environ)
assert meta.status_code == 200, meta.status_code
retired = client.get("/studio/p/1", headers=headers, environ_base=environ)
assert retired.status_code in (301, 302, 303), retired.status_code
print("ok")
"""
        proc = subprocess.run(
            [str(PYTHON), "-c", script, token, str(data_dir)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            self.fail((proc.stderr or "")[-4000:] or (proc.stdout or "")[-4000:] or "desktop subprocess failed")
        self.assertIn("ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
