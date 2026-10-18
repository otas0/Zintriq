"""Zintriq SaaS Stripe Checkout (gated) and webhook signature checks."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote_plus
from urllib.request import Request

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECRET_KEY"] = "test-billing-secret"
os.environ["SQLITE_PATH"] = _TMP_DB.name
os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
os.environ.pop("BILLING_ENABLED", None)
os.environ.pop("ZINTRIQ_STRIPE_SECRET_KEY", None)
os.environ.pop("ZINTRIQ_STRIPE_WEBHOOK_SECRET", None)
os.environ.pop("ZINTRIQ_STRIPE_PRICE_PERSONAL", None)
os.environ.pop("ZINTRIQ_STRIPE_PRICE_TEAM", None)
os.environ.pop("ZINTRIQ_STRIPE_LIVE", None)
for key in ("DATABASE_URL", "AUTH_PROVIDER", "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"):
    os.environ.pop(key, None)


def _sign(secret: str, payload: bytes) -> str:
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


class BillingPlatformTests(unittest.TestCase):
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
                        "billing-user@example.test",
                        hash_password("BillingPass99!"),
                        "merchant",
                        "+60123456789",
                    ),
                )
                cls.user_id = int(cur.lastrowid)

    def setUp(self):
        self.client = self.app.test_client()
        os.environ["PUBLIC_BASE_URL"] = "https://zintriq.test"
        for key in (
            "BILLING_ENABLED",
            "ZINTRIQ_STRIPE_SECRET_KEY",
            "ZINTRIQ_STRIPE_WEBHOOK_SECRET",
            "ZINTRIQ_STRIPE_PRICE_PERSONAL",
            "ZINTRIQ_STRIPE_PRICE_TEAM",
            "ZINTRIQ_STRIPE_LIVE",
            "ZINTRIQ_STRIPE_PORTAL_CONFIGURATION",
        ):
            os.environ.pop(key, None)

    def _authed_csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            return sess.get("csrf_token")

    def test_account_hides_subscription_when_billing_closed(self):
        self._authed_csrf()
        html = self.client.get("/account").get_data(as_text=True)
        self.assertNotIn("account.billing.title", html)
        self.assertNotIn("id=\"account-billing\"", html)
        self.assertNotIn("No cloud subscription", html)
        self.assertNotIn("Cancel or change plan", html)

    def test_checkout_disabled_is_404(self):
        token = self._authed_csrf()
        resp = self.client.post(
            "/billing/checkout",
            data={"csrf_token": token, "plan": "personal"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_checkout_requires_login(self):
        os.environ["BILLING_ENABLED"] = "1"
        os.environ["ZINTRIQ_STRIPE_SECRET_KEY"] = "sk_test_x"
        os.environ["ZINTRIQ_STRIPE_PRICE_PERSONAL"] = "price_personal"
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            token = sess.get("csrf_token")
        resp = self.client.post(
            "/billing/checkout",
            data={"csrf_token": token, "plan": "personal"},
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, {302, 303})
        self.assertIn("/login", resp.headers.get("Location") or "")

    def test_checkout_redirects_to_stripe_when_ready(self):
        os.environ["BILLING_ENABLED"] = "1"
        os.environ["ZINTRIQ_STRIPE_SECRET_KEY"] = "sk_test_x"
        os.environ["ZINTRIQ_STRIPE_PRICE_PERSONAL"] = "price_personal"
        token = self._authed_csrf()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"id": "cs_test", "url": "https://checkout.stripe.com/c/cs_test"}).encode()

        with patch("billing_platform.urllib.request.urlopen", return_value=_Resp()) as mocked:
            resp = self.client.post(
                "/billing/checkout",
                data={"csrf_token": token, "plan": "personal"},
                follow_redirects=False,
            )
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers.get("Location"), "https://checkout.stripe.com/c/cs_test")
        req = mocked.call_args[0][0]
        self.assertIsInstance(req, Request)
        self.assertIn(b"sk_test_x" not in (req.data or b""), (True,))
        self.assertIn("price_personal", (req.data or b"").decode())
        self.assertNotIn("STRIPE_SECRET_KEY", (req.headers.get("Authorization") or ""))

    def test_webhook_rejects_bad_signature(self):
        os.environ["ZINTRIQ_STRIPE_WEBHOOK_SECRET"] = "whsec_test"
        resp = self.client.post(
            "/webhooks/stripe-billing",
            data=b'{"type":"checkout.session.completed"}',
            content_type="application/json",
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_webhook_binds_subscription_to_user(self):
        os.environ["ZINTRIQ_STRIPE_WEBHOOK_SECRET"] = "whsec_test"
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_1",
                        "client_reference_id": str(self.user_id),
                        "metadata": {"user_id": str(self.user_id), "plan": "personal"},
                        "customer": "cus_1",
                        "subscription": "sub_1",
                    }
                },
            }
        ).encode()
        resp = self.client.post(
            "/webhooks/stripe-billing",
            data=payload,
            content_type="application/json",
            headers={"Stripe-Signature": _sign("whsec_test", payload)},
        )
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            with self.app_module.db() as conn:
                row = conn.execute(
                    "SELECT plan, status, stripe_customer_id FROM zintriq_subscriptions WHERE user_id=?",
                    (self.user_id,),
                ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["plan"], "personal")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["stripe_customer_id"], "cus_1")

    def test_webhook_updated_and_account_panel(self):
        os.environ["ZINTRIQ_STRIPE_WEBHOOK_SECRET"] = "whsec_test"
        os.environ["BILLING_ENABLED"] = "1"
        completed = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_2",
                        "client_reference_id": str(self.user_id),
                        "metadata": {"user_id": str(self.user_id), "plan": "personal"},
                        "customer": "cus_2",
                        "subscription": "sub_2",
                    }
                },
            }
        ).encode()
        self.assertEqual(
            self.client.post(
                "/webhooks/stripe-billing",
                data=completed,
                content_type="application/json",
                headers={"Stripe-Signature": _sign("whsec_test", completed)},
            ).status_code,
            200,
        )
        updated = json.dumps(
            {
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_2",
                        "status": "past_due",
                        "customer": "cus_2",
                    }
                },
            }
        ).encode()
        self.assertEqual(
            self.client.post(
                "/webhooks/stripe-billing",
                data=updated,
                content_type="application/json",
                headers={"Stripe-Signature": _sign("whsec_test", updated)},
            ).status_code,
            200,
        )
        self._authed_csrf()
        html = self.client.get("/account").get_data(as_text=True)
        self.assertIn("Cloud subscription", html)
        self.assertIn("Publish &amp; sync", html)
        self.assertIn("Payment due", html)

    def test_portal_requires_customer_then_redirects(self):
        os.environ["BILLING_ENABLED"] = "1"
        os.environ["ZINTRIQ_STRIPE_SECRET_KEY"] = "sk_test_x"
        token = self._authed_csrf()
        missing = self.client.post(
            "/billing/portal",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        self.assertIn(missing.status_code, {302, 303})
        self.assertIn("/account", missing.headers.get("Location") or "")

        os.environ["ZINTRIQ_STRIPE_WEBHOOK_SECRET"] = "whsec_test"
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_portal",
                        "metadata": {"user_id": str(self.user_id), "plan": "team"},
                        "customer": "cus_portal",
                        "subscription": "sub_portal",
                    }
                },
            }
        ).encode()
        self.client.post(
            "/webhooks/stripe-billing",
            data=payload,
            content_type="application/json",
            headers={"Stripe-Signature": _sign("whsec_test", payload)},
        )
        token = self._authed_csrf()
        html = self.client.get("/account").get_data(as_text=True)
        self.assertIn("/billing/portal", html)
        self.assertIn("Cancel or change plan", html)

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"url": "https://billing.stripe.com/p/session/test"}).encode()

        with patch("billing_platform.urllib.request.urlopen", return_value=_Resp()) as mocked:
            resp = self.client.post(
                "/billing/portal",
                data={"csrf_token": token},
                follow_redirects=False,
            )
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers.get("Location"), "https://billing.stripe.com/p/session/test")
        req = mocked.call_args[0][0]
        self.assertIn("cus_portal", (req.data or b"").decode())
        self.assertIn("zintriq.test", unquote_plus((req.data or b"").decode()))

    def test_subscription_updated_maps_team_price(self):
        os.environ["ZINTRIQ_STRIPE_WEBHOOK_SECRET"] = "whsec_test"
        os.environ["ZINTRIQ_STRIPE_PRICE_PERSONAL"] = "price_personal"
        os.environ["ZINTRIQ_STRIPE_PRICE_TEAM"] = "price_team"
        start = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_switch",
                        "metadata": {"user_id": str(self.user_id), "plan": "personal"},
                        "customer": "cus_switch",
                        "subscription": "sub_switch",
                    }
                },
            }
        ).encode()
        self.client.post(
            "/webhooks/stripe-billing",
            data=start,
            content_type="application/json",
            headers={"Stripe-Signature": _sign("whsec_test", start)},
        )
        switched = json.dumps(
            {
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_switch",
                        "status": "active",
                        "customer": "cus_switch",
                        "items": {"data": [{"price": {"id": "price_team"}}]},
                    }
                },
            }
        ).encode()
        self.client.post(
            "/webhooks/stripe-billing",
            data=switched,
            content_type="application/json",
            headers={"Stripe-Signature": _sign("whsec_test", switched)},
        )
        with self.app.app_context():
            with self.app_module.db() as conn:
                row = conn.execute(
                    "SELECT plan, status FROM zintriq_subscriptions WHERE user_id=?",
                    (self.user_id,),
                ).fetchone()
        self.assertEqual(row["plan"], "team")
        self.assertEqual(row["status"], "active")

    def test_live_key_without_flag_is_not_ready(self):
        os.environ["BILLING_ENABLED"] = "1"
        os.environ["ZINTRIQ_STRIPE_SECRET_KEY"] = "sk_live_nope"
        os.environ["ZINTRIQ_STRIPE_PRICE_PERSONAL"] = "price_personal"
        from billing_platform import billing_checkout_ready

        self.assertFalse(billing_checkout_ready())
        html = self.client.get("/pricing").get_data(as_text=True)
        self.assertNotIn('name="plan" value="personal"', html)

    def test_pricing_shows_test_price_checkout_form(self):
        os.environ["BILLING_ENABLED"] = "1"
        os.environ["ZINTRIQ_STRIPE_SECRET_KEY"] = "sk_test_x"
        os.environ["ZINTRIQ_STRIPE_PRICE_PERSONAL"] = "price_personal"
        os.environ["ZINTRIQ_STRIPE_PRICE_TEAM"] = "price_team"
        html = self.client.get("/pricing").get_data(as_text=True)
        self.assertIn('action="/billing/checkout"', html)
        self.assertIn('name="plan" value="personal"', html)
        self.assertIn('name="plan" value="team"', html)
        self.assertNotIn("Plans are coming soon", html)

    def test_auth_pages_skip_inter_preload(self):
        html = self.client.get("/login?local=1").get_data(as_text=True)
        self.assertNotIn("InterVariable.woff2", html)
        self.assertIn("css/public.css", html)
        self.assertIn('id="login-email"', html)
        done = self.client.get("/checkout/done").get_data(as_text=True)
        self.assertIn("Payment complete", done)
        self.assertIn("Publish &amp; sync", done)

    def test_billing_status_reflects_subscription(self):
        token = self._authed_csrf()
        before = self.client.get("/billing/status")
        self.assertEqual(before.status_code, 200)
        body = before.get_json()
        self.assertFalse(body["cloud_active"])
        self.assertTrue(body["local_export"])
        self.assertFalse(body["publish"])
        self.assertFalse(body["sync"])
        os.environ["ZINTRIQ_STRIPE_WEBHOOK_SECRET"] = "whsec_test"
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_status",
                        "metadata": {"user_id": str(self.user_id), "plan": "personal"},
                        "customer": "cus_status",
                        "subscription": "sub_status",
                    }
                },
            }
        ).encode()
        self.assertEqual(
            self.client.post(
                "/webhooks/stripe-billing",
                data=payload,
                content_type="application/json",
                headers={"Stripe-Signature": _sign("whsec_test", payload)},
            ).status_code,
            200,
        )
        after = self.client.get("/billing/status", headers={"X-CSRF-Token": token})
        self.assertEqual(after.status_code, 200)
        data = after.get_json()
        self.assertTrue(data["cloud_active"])
        self.assertEqual(data["plan"], "personal")
        self.assertTrue(data["publish"])
        self.assertTrue(data["sync"])
        self.assertTrue(data["local_export"])

    def test_account_subscribe_cta_when_checkout_ready(self):
        os.environ["BILLING_ENABLED"] = "1"
        os.environ["ZINTRIQ_STRIPE_SECRET_KEY"] = "sk_test_x"
        os.environ["ZINTRIQ_STRIPE_PRICE_PERSONAL"] = "price_personal"
        self._authed_csrf()
        html = self.client.get("/account").get_data(as_text=True)
        self.assertIn("id=\"account-billing\"", html)
        self.assertIn("Publish &amp; sync", html)
        self.assertIn('action="/billing/checkout"', html)
        self.assertIn('name="plan" value="personal"', html)

    def test_pricing_copy_is_publish_sync_not_hosting_sku(self):
        html = self.client.get("/pricing").get_data(as_text=True)
        self.assertIn("Publish &amp; sync", html)
        self.assertIn("Cloud subscription", html)
        self.assertIn("Not a generic hosting plan", html)
        self.assertNotIn("hosting package", html.lower())
        self.assertNotIn("AI Builder", html)


if __name__ == "__main__":
    unittest.main()
