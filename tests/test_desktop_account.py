"""Public Flask PKCE for desktop account linking (not Auth0, not local Flask)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-desktop-account-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
os.environ.pop("ZINTRIQ_DESKTOP", None)
os.environ.pop("ZINTRIQ_DESKTOP_TOKEN", None)
for key in ("DATABASE_URL", "AUTH_PROVIDER", "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
    os.environ.pop(key, None)

ROOT = Path(__file__).resolve().parents[1]


def _qs(**extra):
    params = {
        "response_type": "code",
        "client_id": "zintriq-desktop",
        "redirect_uri": "zintriq://auth/callback",
        "state": "state-token-ok",
        "code_challenge": "challenge-token-ok",
        "code_challenge_method": "S256",
        "os": "darwin",
        "version": "0.1.0",
    }
    params.update(extra)
    return "&".join(f"{key}={value}" for key, value in params.items())


class DesktopAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        os.environ.pop("ZINTRIQ_DESKTOP", None)
        os.environ.pop("ZINTRIQ_DESKTOP_TOKEN", None)
        os.environ["SQLITE_PATH"] = _TMP_DB.name
        app_module.DATABASE = Path(_TMP_DB.name)
        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.config["TESTING"] = True
        cls._phones = 0
        with cls.app.app_context():
            app_module.init_db()

    def setUp(self):
        os.environ.pop("ZINTRIQ_DESKTOP", None)
        os.environ.pop("ZINTRIQ_DESKTOP_TOKEN", None)
        from desktop_account import reset_for_tests

        reset_for_tests()
        self.client = self.app.test_client()

    def _login(self):
        email = f"desk-{os.urandom(4).hex()}@example.test"
        type(self)._phones += 1
        phone = f"+6012{self._phones:07d}"
        with self.app_module.db() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, account_kind, phone) VALUES (?, ?, 'merchant', ?)",
                (email, "x", phone),
            )
            user_id = int(cur.lastrowid)
        csrf = "csrf-desktop-account"
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["csrf_token"] = csrf
        return user_id, csrf

    def _bearer(self):
        from desktop_account import pkce_challenge

        user_id, csrf = self._login()
        verifier = "verifier-value-ok-16"
        challenge = pkce_challenge(verifier)
        self.client.get(f"/desktop/authorize?{_qs(code_challenge=challenge)}")
        allowed = self.client.post(
            "/desktop/authorize",
            data={"csrf_token": csrf, "decision": "allow"},
        )
        match = re.search(r'href="(zintriq://auth/callback[^"]+)"', allowed.get_data(as_text=True))
        code = parse_qs(urlparse(match.group(1).replace("&amp;", "&")).query)["code"][0]
        exchanged = self.client.post(
            "/api/desktop/token",
            data=json.dumps({
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "zintriq://auth/callback",
            }),
            content_type="application/json",
        )
        self.assertEqual(exchanged.status_code, 200, exchanged.get_data(as_text=True))
        return user_id, csrf, exchanged.get_json()["token"]

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(f"/desktop/authorize?{_qs()}")
        self.assertEqual(response.status_code, 302)
        location = response.headers.get("Location") or ""
        self.assertIn("/login", location)
        self.assertIn("from=desktop", location)
        self.assertIn("desktop/authorize", location)

    def test_register_from_desktop_keeps_authorize_next(self):
        nxt = "/desktop/authorize?" + _qs()
        page = self.client.get("/register", query_string={"from": "desktop", "next": nxt})
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("The website checks your account", html)
        with self.client.session_transaction() as sess:
            stored = sess.get("pending_login_next") or ""
        self.assertTrue(stored.startswith("/desktop/authorize"), stored)
    def test_invalid_client_is_generic_error(self):
        response = self.client.get(f"/desktop/authorize?{_qs(client_id='other')}")
        self.assertEqual(response.status_code, 400)
        body = response.get_data(as_text=True)
        card = body.split('id="mq-main"', 1)[-1].split("</main>", 1)[0]
        self.assertIn("Only start logging in from inside the Zintriq app.", card)
        self.assertNotIn("client_id", card)

    def test_allow_then_token_exchange(self):
        from desktop_account import pkce_challenge

        user_id, csrf = self._login()
        verifier = "verifier-value-ok-16"
        challenge = pkce_challenge(verifier)
        shown = self.client.get(f"/desktop/authorize?{_qs(code_challenge=challenge)}")
        self.assertEqual(shown.status_code, 200, shown.get_data(as_text=True)[:400])
        html = shown.get_data(as_text=True)
        self.assertIn("Connect Zintriq?", html)
        self.assertIn("mq-desk-auth", html)
        self.assertIn("paper-list", html)
        self.assertIn("paper-split", html)
        self.assertIn("btn-primary", html)
        allowed = self.client.post(
            "/desktop/authorize",
            data={"csrf_token": csrf, "decision": "allow", "resume": "/desktop/authorize"},
        )
        self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True)[:400])
        match = re.search(r'href="(zintriq://auth/callback[^"]+)"', allowed.get_data(as_text=True))
        self.assertIsNotNone(match)
        parsed = urlparse(match.group(1).replace("&amp;", "&"))
        code = parse_qs(parsed.query)["code"][0]
        exchanged = self.client.post(
            "/api/desktop/token",
            data=json.dumps({
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "zintriq://auth/callback",
            }),
            content_type="application/json",
        )
        self.assertEqual(exchanged.status_code, 200, exchanged.get_data(as_text=True))
        payload = exchanged.get_json()
        self.assertTrue(payload.get("token"))
        self.assertEqual(payload["user"]["id"], user_id)
        reused = self.client.post(
            "/api/desktop/token",
            data=json.dumps({
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "zintriq://auth/callback",
            }),
            content_type="application/json",
        )
        self.assertEqual(reused.status_code, 400)
        token = payload["token"]
        alive = self.client.get(
            "/api/desktop/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(alive.status_code, 200, alive.get_data(as_text=True))
        page = self.client.get("/account")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True)[:400])
        account_html = page.get_data(as_text=True)
        self.assertIn("Logged-in devices", account_html)
        self.assertIn("Computer", account_html)
        match_id = re.search(r"/account/desktop-devices/(\d+)/revoke", account_html)
        self.assertIsNotNone(match_id)
        revoked = self.client.post(
            match_id.group(0),
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        self.assertEqual(revoked.status_code, 200)
        dead = self.client.get(
            "/api/desktop/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(dead.status_code, 401)

    def test_wrong_verifier_rejected(self):
        from desktop_account import pkce_challenge

        _user_id, csrf = self._login()
        verifier = "verifier-value-ok-16"
        self.client.get(f"/desktop/authorize?{_qs(code_challenge=pkce_challenge(verifier))}")
        allowed = self.client.post(
            "/desktop/authorize",
            data={"csrf_token": csrf, "decision": "allow"},
        )
        match = re.search(r'href="(zintriq://auth/callback[^"]+)"', allowed.get_data(as_text=True))
        code = parse_qs(urlparse(match.group(1).replace("&amp;", "&")).query)["code"][0]
        bad = self.client.post(
            "/api/desktop/token",
            data=json.dumps({
                "code": code,
                "code_verifier": "wrong-verifier-xx",
                "redirect_uri": "zintriq://auth/callback",
            }),
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)

    def test_deny(self):
        _user_id, csrf = self._login()
        self.client.get(f"/desktop/authorize?{_qs()}")
        denied = self.client.post(
            "/desktop/authorize",
            data={"csrf_token": csrf, "decision": "deny"},
            follow_redirects=True,
        )
        self.assertEqual(denied.status_code, 200)
        self.assertIn("Request denied", denied.get_data(as_text=True))

    def test_desktop_host_404(self):
        from builder_http_support import application_client, disable_application_host

        client = application_client(self.app)
        try:
            missing = client.get(f"/desktop/authorize?{_qs()}")
            self.assertEqual(missing.status_code, 404)
            token = client.post("/api/desktop/token", json={"code": "x"})
            self.assertEqual(token.status_code, 404)
            session_get = client.get("/api/desktop/session")
            self.assertEqual(session_get.status_code, 404)
            self.assertEqual(client.get("/status").status_code, 404)
            self.assertEqual(client.get("/c/abcd1234abcd").status_code, 404)
            self.assertEqual(client.get("/api/desktop/cloud/drafts").status_code, 404)
            self.assertEqual(client.get("/api/desktop/cloud/catalog").status_code, 404)
            self.assertEqual(client.get("/api/desktop/cloud/mine").status_code, 404)
            self.assertEqual(client.post("/api/desktop/cloud/unpublish").status_code, 404)
            self.assertEqual(client.post("/api/desktop/cloud/publish-plugin").status_code, 404)
            self.assertEqual(client.get("/api/desktop/updates").status_code, 404)
            self.assertEqual(client.get("/api/desktop/cloud/collab/cafe").status_code, 404)
            self.assertEqual(client.get("/desktop/updates/latest-mac.yml").status_code, 404)
            self.assertEqual(client.get("/w/abcd1234abcd").status_code, 404)
        finally:
            disable_application_host()

    def test_cloud_sync_publish_and_share_page(self):
        _user_id, _csrf, token = self._bearer()
        headers = {"Authorization": f"Bearer {token}"}
        status = self.client.get("/status")
        self.assertEqual(status.status_code, 200)
        self.assertIn("cloud drafts", status.get_data(as_text=True))
        missing = self.client.put(
            "/api/desktop/cloud/drafts/cafe",
            data=json.dumps({"code": '{"title":"Cafe"}', "updated_at": "2026-10-04T12:00:00Z"}),
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 401)
        saved = self.client.put(
            "/api/desktop/cloud/drafts/cafe",
            data=json.dumps({"code": '{"title":"Cafe"}', "updated_at": "2026-10-04T12:00:00Z"}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))
        listed = self.client.get("/api/desktop/cloud/drafts", headers=headers)
        self.assertEqual(listed.status_code, 200)
        slugs = [item["slug"] for item in listed.get_json()["drafts"]]
        self.assertIn("cafe", slugs)
        collab = self.client.put(
            "/api/desktop/cloud/collab/cafe",
            data=json.dumps({"clock": {"aaa": 1}, "doc": {"form": "atom", "lamport": 1, "replica": "aaa", "type": "string", "value": "hi", "has_value": True}}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(collab.status_code, 200, collab.get_data(as_text=True))
        got = self.client.get("/api/desktop/cloud/collab/cafe", headers=headers)
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.get_json()["doc"]["value"], "hi")
        published = self.client.post(
            "/api/desktop/cloud/publish",
            data=json.dumps({"slug": "cafe", "title": "A café"}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(published.status_code, 200, published.get_data(as_text=True))
        share_id = published.get_json()["id"]
        page = self.client.get(f"/c/{share_id}")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("A café", html)
        self.assertIn("Open in Zintriq", html)
        self.assertIn(f"zintriq://c/{share_id}", html)
        blob = self.client.get(f"/api/desktop/cloud/shares/{share_id}")
        self.assertEqual(blob.status_code, 200)
        self.assertIn("Cafe", blob.get_json()["code"])
        catalog = self.client.get("/api/desktop/cloud/catalog")
        self.assertEqual(catalog.status_code, 200)
        names = [item["name"] for item in catalog.get_json()["packages"]]
        self.assertIn("A café", names)
        self.assertEqual(catalog.get_json()["packages"][0]["kind"], "system")
        self.assertNotIn("code", catalog.get_json()["packages"][0])
        plugin = self.client.post(
            "/api/desktop/cloud/publish-plugin",
            data=json.dumps({"pack": {"id": "community-shop", "name": "Shop stamp", "form": "Web", "stamp": True}}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(plugin.status_code, 200, plugin.get_data(as_text=True))
        plugins = self.client.get("/api/desktop/cloud/catalog?type=plugin")
        self.assertEqual(plugins.status_code, 200)
        plugin_names = [item["name"] for item in plugins.get_json()["packages"]]
        self.assertIn("Shop stamp", plugin_names)
        self.assertTrue(all(item["kind"] == "plugin" for item in plugins.get_json()["packages"]))
        self.assertNotIn("code", plugins.get_json()["packages"][0])
        mine = self.client.get("/api/desktop/cloud/mine", headers=headers)
        self.assertEqual(mine.status_code, 200)
        mine_names = [item["name"] for item in mine.get_json()["shares"]]
        self.assertIn("A café", mine_names)
        work = self.client.get(f"/w/{share_id}")
        self.assertEqual(work.status_code, 200)
        self.assertIn("Made with Zintriq", work.get_data(as_text=True))
        self.assertIn("A café", work.get_data(as_text=True))
        self.assertNotIn("me-code", work.get_data(as_text=True))
        updates = self.client.get("/api/desktop/updates")
        self.assertEqual(updates.status_code, 200)
        self.assertEqual(updates.get_json()["version"], "0.1.0")
        self.assertTrue(updates.get_json()["autoInstall"])
        self.assertEqual(updates.get_json()["feed"], "/desktop/updates")
        missing_feed = self.client.get("/desktop/updates/latest-mac.yml")
        self.assertEqual(missing_feed.status_code, 404)
        gone = self.client.get("/c/not-a-real-share")
        self.assertEqual(gone.status_code, 404)
        again = self.client.post(
            "/api/desktop/cloud/publish",
            data=json.dumps({"slug": "cafe", "title": "A café"}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.get_json()["id"], share_id)
        page_code = json.dumps({
            "form": "struct",
            "fields": {
                "kind": {"form": "atom", "type": "string", "value": "software.page"},
                "title": {"form": "atom", "type": "string", "value": "Hello page"},
            },
        })
        self.client.put(
            "/api/desktop/cloud/drafts/hello-page",
            data=json.dumps({"code": page_code, "updated_at": "2026-10-04T12:01:00Z"}),
            content_type="application/json",
            headers=headers,
        )
        page_pub = self.client.post(
            "/api/desktop/cloud/publish",
            data=json.dumps({"slug": "hello-page"}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(page_pub.status_code, 200, page_pub.get_data(as_text=True))
        page_id = page_pub.get_json()["id"]
        self.assertEqual(page_pub.get_json()["work"], f"/w/{page_id}")
        hosted = self.client.get(f"/w/{page_id}")
        self.assertEqual(hosted.status_code, 200)
        hosted_html = hosted.get_data(as_text=True)
        self.assertIn("Hello page", hosted_html)
        self.assertIn("Made with Zintriq", hosted_html)
        self.assertIn('data-page-kind="software.page"', hosted_html)
        self.assertIn("zq-hosted-badge", hosted_html)
        self.assertNotIn("me-code", hosted_html)
        pages = self.client.get("/api/desktop/cloud/catalog?type=page")
        page_names = [item["name"] for item in pages.get_json()["packages"]]
        self.assertIn("Hello page", page_names)
        dropped = self.client.post(
            "/api/desktop/cloud/unpublish",
            data=json.dumps({"id": page_id}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(dropped.status_code, 200)
        self.assertEqual(self.client.get(f"/c/{page_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/w/{page_id}").status_code, 404)
        pages_after = self.client.get("/api/desktop/cloud/catalog?type=page")
        self.assertNotIn("Hello page", [item["name"] for item in pages_after.get_json()["packages"]])

    def test_cloud_entitlement_and_publish_gate_when_billing_on(self):
        _user_id, _csrf, token = self._bearer()
        headers = {"Authorization": f"Bearer {token}"}
        open_ent = self.client.get("/api/desktop/cloud/entitlement", headers=headers)
        self.assertEqual(open_ent.status_code, 200)
        self.assertTrue(open_ent.get_json()["publish"])
        self.assertTrue(open_ent.get_json()["local_export"])
        os.environ["BILLING_ENABLED"] = "1"
        try:
            blocked = self.client.get("/api/desktop/cloud/entitlement", headers=headers)
            self.assertEqual(blocked.status_code, 200)
            body = blocked.get_json()
            self.assertTrue(body["billing_enabled"])
            self.assertFalse(body["cloud_active"])
            self.assertFalse(body["publish"])
            self.assertTrue(body["local_export"])
            denied = self.client.put(
                "/api/desktop/cloud/drafts/gated",
                data=json.dumps({"code": '{"title":"Gated"}', "updated_at": "2026-10-04T12:00:00Z"}),
                content_type="application/json",
                headers=headers,
            )
            self.assertEqual(denied.status_code, 402)
            self.assertEqual(denied.get_json()["code"], "subscription_required")
            from billing_platform import _upsert_subscription, ensure_schema, subscription_cloud_active
            from app import db as app_db

            with self.app.app_context():
                with app_db() as conn:
                    ensure_schema(conn)
                    _upsert_subscription(
                        conn,
                        user_id=_user_id,
                        plan="personal",
                        status="active",
                        customer_id="cus_gate",
                        subscription_id="sub_gate",
                    )
                    conn.commit()
                    self.assertTrue(subscription_cloud_active(conn, _user_id))
            allowed = self.client.put(
                "/api/desktop/cloud/drafts/gated",
                data=json.dumps({
                    "code": json.dumps({
                        "form": "struct",
                        "fields": {
                            "kind": {"form": "atom", "type": "string", "value": "software.page"},
                            "title": {"form": "atom", "type": "string", "value": "Gated page"},
                        },
                    }),
                    "updated_at": "2026-10-04T12:02:00Z",
                }),
                content_type="application/json",
                headers=headers,
            )
            self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True)[:300])
            published = self.client.post(
                "/api/desktop/cloud/publish",
                data=json.dumps({"slug": "gated"}),
                content_type="application/json",
                headers=headers,
            )
            self.assertEqual(published.status_code, 200, published.get_data(as_text=True)[:300])
            live = self.client.get(published.get_json()["work"])
            self.assertEqual(live.status_code, 200)
            self.assertIn("Gated page", live.get_data(as_text=True))
        finally:
            os.environ.pop("BILLING_ENABLED", None)

    def test_share_asset_served_on_hosted_page(self):
        _user_id, _csrf, token = self._bearer()
        headers = {"Authorization": f"Bearer {token}"}
        page_code = json.dumps({
            "form": "struct",
            "fields": {
                "kind": {"form": "atom", "type": "string", "value": "software.page"},
                "title": {"form": "atom", "type": "string", "value": "With image"},
                "body": {
                    "form": "sequence",
                    "items": [
                        {
                            "form": "struct",
                            "fields": {
                                "kind": {"form": "atom", "type": "string", "value": "image"},
                                "src": {"form": "atom", "type": "string", "value": "hero.png"},
                            },
                        }
                    ],
                },
            },
        })
        self.client.put(
            "/api/desktop/cloud/drafts/with-image",
            data=json.dumps({"code": page_code, "updated_at": "2026-10-04T13:00:00Z"}),
            content_type="application/json",
            headers=headers,
        )
        published = self.client.post(
            "/api/desktop/cloud/publish",
            data=json.dumps({"slug": "with-image"}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(published.status_code, 200, published.get_data(as_text=True)[:300])
        public_id = published.get_json()["id"]
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        uploaded = self.client.put(
            f"/api/desktop/cloud/shares/{public_id}/assets/hero.png",
            data=png,
            headers={**headers, "Content-Type": "image/png"},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.get_data(as_text=True)[:300])
        asset = self.client.get(f"/w/{public_id}/assets/hero.png")
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.data[:8], b"\x89PNG\r\n\x1a\n")
        html = self.client.get(f"/w/{public_id}").get_data(as_text=True)
        self.assertIn(f"/w/{public_id}/assets/hero.png", html)

    def test_hosting_grace_then_unpublished(self):
        from billing_platform import _upsert_subscription, ensure_schema
        from app import db as app_db
        from datetime import datetime, timedelta, timezone

        user_id, _csrf, token = self._bearer()
        headers = {"Authorization": f"Bearer {token}"}
        page_code = json.dumps({
            "form": "struct",
            "fields": {
                "kind": {"form": "atom", "type": "string", "value": "software.page"},
                "title": {"form": "atom", "type": "string", "value": "Grace page"},
            },
        })
        self.client.put(
            "/api/desktop/cloud/drafts/grace-page",
            data=json.dumps({"code": page_code, "updated_at": "2026-10-04T14:00:00Z"}),
            content_type="application/json",
            headers=headers,
        )
        published = self.client.post(
            "/api/desktop/cloud/publish",
            data=json.dumps({"slug": "grace-page"}),
            content_type="application/json",
            headers=headers,
        )
        public_id = published.get_json()["id"]
        os.environ["BILLING_ENABLED"] = "1"
        try:
            with self.app.app_context():
                with app_db() as conn:
                    ensure_schema(conn)
                    _upsert_subscription(
                        conn,
                        user_id=user_id,
                        plan="personal",
                        status="active",
                        customer_id="cus_grace",
                        subscription_id="sub_grace",
                    )
                    _upsert_subscription(
                        conn,
                        user_id=user_id,
                        plan="personal",
                        status="cancelled",
                        customer_id="cus_grace",
                        subscription_id="sub_grace",
                    )
                    row = conn.execute(
                        "SELECT hosting_until, cloud_data_until FROM zintriq_subscriptions WHERE user_id=?",
                        (user_id,),
                    ).fetchone()
                    self.assertTrue(row["hosting_until"])
                    self.assertTrue(row["cloud_data_until"])
            during = self.client.get(f"/w/{public_id}")
            self.assertEqual(during.status_code, 200)
            self.assertIn("Grace page", during.get_data(as_text=True))
            past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            with self.app.app_context():
                with app_db() as conn:
                    conn.execute(
                        "UPDATE zintriq_subscriptions SET hosting_until=? WHERE user_id=?",
                        (past, user_id),
                    )
                    conn.commit()
            gone = self.client.get(f"/w/{public_id}")
            self.assertEqual(gone.status_code, 410)
            gone_html = gone.get_data(as_text=True)
            self.assertTrue(
                "available right now" in gone_html or "paused" in gone_html.lower(),
                gone_html[:400],
            )
            card = self.client.get(f"/c/{public_id}")
            self.assertEqual(card.status_code, 410)
        finally:
            os.environ.pop("BILLING_ENABLED", None)

    def test_draft_revision_conflict(self):
        _user_id, _csrf, token = self._bearer()
        headers = {"Authorization": f"Bearer {token}"}
        first = self.client.put(
            "/api/desktop/cloud/drafts/rev-a",
            data=json.dumps({"code": '{"title":"A"}', "updated_at": "2026-10-04T15:00:00Z"}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["revision"], 1)
        second = self.client.put(
            "/api/desktop/cloud/drafts/rev-a",
            data=json.dumps({
                "code": '{"title":"B"}',
                "updated_at": "2026-10-04T15:01:00Z",
                "base_revision": 1,
            }),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json()["revision"], 2)
        conflict = self.client.put(
            "/api/desktop/cloud/drafts/rev-a",
            data=json.dumps({
                "code": '{"title":"C"}',
                "updated_at": "2026-10-04T15:02:00Z",
                "base_revision": 1,
            }),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.get_json()["code"], "conflict")
        self.assertEqual(conflict.get_json()["revision"], 2)
        tomb = self.client.delete("/api/desktop/cloud/drafts/rev-a", headers=headers)
        self.assertEqual(tomb.status_code, 200)
        self.assertTrue(tomb.get_json()["deleted_at"])
        listed = self.client.get("/api/desktop/cloud/drafts", headers=headers)
        row = next(item for item in listed.get_json()["drafts"] if item["slug"] == "rev-a")
        self.assertTrue(row["deleted_at"])

    def test_auth_js_builds_public_authorize_url(self):
        script = (
            "const { createPkcePair, buildDesktopAuthorizeUrl, buildDesktopRegisterUrl } = require('./desktop/auth');"
            "const { challenge } = createPkcePair();"
            "const url = buildDesktopAuthorizeUrl({"
            "origin: 'https://www.example.com/', clientId: 'zintriq-desktop',"
            "redirectUri: 'zintriq://auth/callback', state: 'abcdefgh',"
            "codeChallenge: challenge});"
            "if (!url.startsWith('https://www.example.com/desktop/authorize?')) process.exit(2);"
            "if (!url.includes('code_challenge_method=S256')) process.exit(3);"
            "const signup = buildDesktopRegisterUrl({ origin: 'https://www.example.com/', authorizeUrl: url });"
            "if (!signup.startsWith('https://www.example.com/register?')) process.exit(4);"
            "if (!signup.includes('from=desktop')) process.exit(5);"
            "if (!signup.includes(encodeURIComponent('/desktop/authorize?'))) process.exit(6);"
            "process.stdout.write(url);"
        )
        result = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("client_id=zintriq-desktop", result.stdout)

    def test_account_origin_skips_placeholders(self):
        script = (
            "const { resolveAccountOrigin } = require('./desktop/account_origin');"
            "const a = resolveAccountOrigin({ env: {}, fileCfg: { accountOrigin: 'https://spencer.trycloudflare.com' }, dotenv: { PUBLIC_BASE_URL: 'https://pub.example.test' } });"
            "if (a !== 'http://127.0.0.1:5001') process.exit(2);"
            "const b = resolveAccountOrigin({ env: { ZINTRIQ_ACCOUNT_ORIGIN: 'https://zintriq.com' } });"
            "if (b !== 'http://127.0.0.1:5001') process.exit(3);"
            "const c = resolveAccountOrigin({ env: { ZINTRIQ_ACCOUNT_ORIGIN: 'http://127.0.0.1:5002/' } });"
            "if (c !== 'http://127.0.0.1:5002') process.exit(4);"
            "process.stdout.write('ok');"
        )
        result = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "ok")

    def test_updater_compares_versions(self):
        script = (
            "const { isNewer, canAutoInstall, updateFeedUrl } = require('./desktop/updater');"
            "if (!isNewer('0.2.0', '0.1.0')) process.exit(2);"
            "if (isNewer('0.1.0', '0.1.0')) process.exit(3);"
            "if (isNewer('0.1.0', '0.2.0')) process.exit(4);"
            "if (canAutoInstall({ packaged: false })) process.exit(5);"
            "if (!canAutoInstall({ packaged: true, env: {} })) process.exit(6);"
            "if (canAutoInstall({ packaged: true, env: { ZINTRIQ_SMOKE: '1' } })) process.exit(7);"
            "if (updateFeedUrl('https://zintriq.com/') !== 'https://zintriq.com/desktop/updates') process.exit(8);"
            "process.stdout.write('ok');"
        )
        result = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "ok")

    def test_notarize_skips_without_apple_id(self):
        script = (
            "const { notarizeMac } = require('./desktop/packaging/notarize');"
            "notarizeMac({ electronPlatformName: 'darwin', appOutDir: '.', packager: { appInfo: { productFilename: 'Zintriq Studio' } } })"
            ".then((r) => { if (!r.skipped) process.exit(2); process.stdout.write(r.reason); })"
            ".catch((e) => { console.error(e); process.exit(1); });"
        )
        result = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("missing-credentials", result.stdout)

    def test_update_feed_file_is_served(self):
        folder = Path(tempfile.mkdtemp(prefix="zintriq-updates-"))
        (folder / "latest-mac.yml").write_text("version: 0.2.0\n", encoding="utf-8")
        previous = os.environ.get("STUDIO_UPDATE_DIR")
        os.environ["STUDIO_UPDATE_DIR"] = str(folder)
        try:
            response = self.client.get("/desktop/updates/latest-mac.yml")
            self.assertEqual(response.status_code, 200)
            self.assertIn("0.2.0", response.get_data(as_text=True))
            denied = self.client.get("/desktop/updates/secret.txt")
            self.assertEqual(denied.status_code, 404)
        finally:
            if previous is None:
                os.environ.pop("STUDIO_UPDATE_DIR", None)
            else:
                os.environ["STUDIO_UPDATE_DIR"] = previous
