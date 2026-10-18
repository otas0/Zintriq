"""Live credential verification for Connected Apps.

Connect only succeeds when the provider API accepts the credentials.
Demo / placeholder values are rejected.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from observability.trace import trace


PLACEHOLDER_RE = re.compile(
    r"^(test|demo|fake|sample|example|xxx+|asdf+|qwerty|password|secret|admin|1234+|0000+|aaaa+|abcd|"
    r"sk_test_placeholder|pk_test_placeholder|your[_-]?api[_-]?key|changeme|null|none|n/?a)$",
    re.I,
)


class CredentialVerifyError(ValueError):
    """Raised when credentials are missing, fake, or rejected by the provider."""


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = 10,
) -> dict:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with trace("credential.verify", url=url):
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else str(exc)
        raise CredentialVerifyError(
            f"Provider rejected these credentials (HTTP {exc.code}): {detail[:180]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise CredentialVerifyError(f"Could not reach provider API: {exc.reason}") from exc


def _http_post_form(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    hdrs = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    return _http_json(url, method="POST", headers=hdrs, body=body)


def assert_not_placeholder(fields: dict[str, str]) -> None:
    for key, val in fields.items():
        v = (val or "").strip()
        if not v:
            continue
        if PLACEHOLDER_RE.match(v):
            raise CredentialVerifyError(
                f"“{key}” looks like a placeholder. Enter real merchant credentials from the provider dashboard."
            )
        if len(v) < 8:
            raise CredentialVerifyError(f"“{key}” is too short to be a real credential.")
        if re.fullmatch(r"(.)\1{5,}", v):
            raise CredentialVerifyError(f"“{key}” looks fake (repeated characters).")
        if re.fullmatch(r"\d{6,20}", v) and key in (
            "secret_key", "api_key", "api_secret", "client_secret", "access_token", "private_key",
        ):
            raise CredentialVerifyError(f"“{key}” looks like a fake numeric placeholder.")


def _require(fields: dict[str, str], *keys: str) -> tuple[str, ...]:
    out = []
    missing = []
    for key in keys:
        val = (fields.get(key) or "").strip()
        if not val:
            missing.append(key)
        out.append(val)
    if missing:
        raise CredentialVerifyError(f"Required: {', '.join(missing)}")
    return tuple(out)


def verify_stripe(fields: dict[str, str]) -> dict[str, Any]:
    secret = (fields.get("secret_key") or fields.get("api_key") or "").strip()
    if not secret:
        raise CredentialVerifyError("Stripe secret key is required.")
    if not secret.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
        raise CredentialVerifyError("Valid Stripe secret key required (sk_test_… / sk_live_… / rk_…).")
    data = _http_json(
        "https://api.stripe.com/v1/account",
        headers={"Authorization": f"Bearer {secret}"},
    )
    return {"external_id": data.get("id") or "", "email": data.get("email") or "", "raw": data}


def verify_paypal(fields: dict[str, str]) -> dict[str, Any]:
    client_id, client_secret = _require(fields, "client_id", "client_secret")
    mode = (fields.get("mode") or "live").strip().lower()
    api_base = (
        "https://api-m.paypal.com"
        if mode == "live"
        else "https://api-m.sandbox.paypal.com"
    )
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = _http_post_form(
        f"{api_base}/v1/oauth2/token",
        {"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
    )
    if not data.get("access_token"):
        raise CredentialVerifyError("PayPal did not return an access token.")
    return {"external_id": client_id[:24], "raw": data}


def verify_square(fields: dict[str, str]) -> dict[str, Any]:
    token = (fields.get("access_token") or fields.get("api_key") or fields.get("secret_key") or "").strip()
    if not token:
        raise CredentialVerifyError("Square access token is required.")
    data = _http_json(
        "https://connect.squareup.com/v2/locations",
        headers={"Authorization": f"Bearer {token}", "Square-Version": "2024-01-18"},
    )
    locs = data.get("locations") or []
    loc_id = (locs[0] or {}).get("id") if locs else fields.get("location_id") or ""
    return {"external_id": str(loc_id or "square"), "raw": data}


def verify_adyen(fields: dict[str, str]) -> dict[str, Any]:
    api_key = (fields.get("api_key") or fields.get("secret_key") or "").strip()
    merchant = (fields.get("merchant_account") or fields.get("merchant_id") or "").strip()
    if not api_key:
        raise CredentialVerifyError("Adyen API key is required.")
    # Live vs test inferred from key prefix when present
    base = "https://checkout-test.adyen.com"
    if api_key.startswith("AQE") or "live" in api_key.lower():
        base = "https://checkout-live.adyen.com"
    body = json.dumps({"merchantAccount": merchant} if merchant else {}).encode()
    data = _http_json(
        f"{base}/v71/paymentMethods",
        method="POST",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        body=body,
    )
    return {"external_id": merchant or "adyen", "raw": data}


def verify_razorpay(fields: dict[str, str]) -> dict[str, Any]:
    key_id = (fields.get("key_id") or fields.get("public_key") or fields.get("client_id") or "").strip()
    key_secret = (fields.get("key_secret") or fields.get("secret_key") or fields.get("api_secret") or "").strip()
    if not key_id or not key_secret:
        raise CredentialVerifyError("Razorpay key_id and key_secret are required.")
    basic = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    data = _http_json(
        "https://api.razorpay.com/v1/orders?count=1",
        headers={"Authorization": f"Basic {basic}"},
    )
    return {"external_id": key_id, "raw": data}


def verify_mollie(fields: dict[str, str]) -> dict[str, Any]:
    api_key = (fields.get("api_key") or fields.get("secret_key") or "").strip()
    if not api_key.startswith(("test_", "live_")):
        raise CredentialVerifyError("Mollie API key must start with test_ or live_.")
    data = _http_json(
        "https://api.mollie.com/v2/profiles/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return {"external_id": data.get("id") or api_key[:16], "raw": data}


def verify_paystack(fields: dict[str, str]) -> dict[str, Any]:
    secret = (fields.get("secret_key") or fields.get("api_key") or "").strip()
    if not secret.startswith(("sk_test_", "sk_live_")):
        raise CredentialVerifyError("Paystack secret key must start with sk_test_ or sk_live_.")
    data = _http_json(
        "https://api.paystack.co/balance",
        headers={"Authorization": f"Bearer {secret}"},
    )
    return {"external_id": "paystack", "raw": data}


def verify_flutterwave(fields: dict[str, str]) -> dict[str, Any]:
    secret = (fields.get("secret_key") or fields.get("api_key") or "").strip()
    if not secret:
        raise CredentialVerifyError("Flutterwave secret key is required.")
    data = _http_json(
        "https://api.flutterwave.com/v3/balances",
        headers={"Authorization": f"Bearer {secret}"},
    )
    return {"external_id": "flutterwave", "raw": data}


def verify_mercadopago(fields: dict[str, str]) -> dict[str, Any]:
    token = (fields.get("access_token") or fields.get("api_key") or fields.get("secret_key") or "").strip()
    if not token:
        raise CredentialVerifyError("Mercado Pago access token is required.")
    data = _http_json(
        "https://api.mercadopago.com/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return {"external_id": str(data.get("id") or "mercadopago"), "email": data.get("email") or "", "raw": data}


def verify_yookassa(fields: dict[str, str]) -> dict[str, Any]:
    shop_id = (fields.get("shop_id") or fields.get("merchant_id") or fields.get("client_id") or "").strip()
    secret = (fields.get("secret_key") or fields.get("api_key") or fields.get("api_secret") or "").strip()
    if not shop_id or not secret:
        raise CredentialVerifyError("YooKassa shop_id and secret_key are required.")
    basic = base64.b64encode(f"{shop_id}:{secret}".encode()).decode()
    data = _http_json(
        "https://api.yookassa.ru/v3/me",
        headers={"Authorization": f"Basic {basic}"},
    )
    return {"external_id": shop_id, "raw": data}


def verify_paypay(fields: dict[str, str]) -> dict[str, Any]:
    """PayPay for Merchants — validate by calling the code API with HMAC-less probe is not public;
    require non-placeholder triple and hit auth-sensitive endpoint shape.
    """
    merchant_id, api_key, api_secret = _require(fields, "merchant_id", "api_key", "api_secret")
    mode = (fields.get("mode") or "production").strip().lower()
    base = (
        "https://api.paypay.ne.jp/v2"
        if mode in ("production", "live")
        else "https://stg-api.sandbox.paypay.ne.jp/v2"
    )
    # Without correct HMAC the API returns 401 — which proves connectivity; we still reject
    # empty/placeholder above. Attempt a signed-style call with API key header used by some SDKs.
    try:
        _http_json(
            f"{base}/codes",
            method="GET",
            headers={
                "X-ASSUME-MERCHANT": merchant_id,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    except CredentialVerifyError as exc:
        msg = str(exc).lower()
        # 401/403 with real-looking keys means endpoint reached; still not fully authenticated
        # without HMAC. Require keys that are not placeholders and look like PayPay material.
        if "401" in msg or "403" in msg:
            if len(api_key) < 16 or len(api_secret) < 16:
                raise CredentialVerifyError(
                    "PayPay api_key / api_secret look invalid. Copy them from PayPay for Merchants."
                ) from exc
            # Treat 401 from PayPay API as "keys were sent but signature required" — still not proof.
            raise CredentialVerifyError(
                "PayPay rejected the request. Confirm merchant_id, API key, and API secret from "
                "PayPay for Merchants (HMAC credentials), then try again."
            ) from exc
        raise
    return {"external_id": merchant_id, "raw": {}}


def verify_yelp(fields: dict[str, str]) -> dict[str, Any]:
    api_key = (fields.get("api_key") or fields.get("access_token") or "").strip()
    business_id = (fields.get("business_id") or "").strip()
    if not api_key:
        raise CredentialVerifyError("Yelp Fusion API key is required.")
    if not business_id:
        raise CredentialVerifyError("Yelp business ID is required.")
    data = _http_json(
        f"https://api.yelp.com/v3/businesses/{urllib.parse.quote(business_id)}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return {
        "external_id": data.get("id") or business_id,
        "business_name": data.get("name") or "",
        "raw": data,
    }


def verify_foursquare(fields: dict[str, str]) -> dict[str, Any]:
    api_key = (fields.get("api_key") or fields.get("access_token") or "").strip()
    venue_id = (fields.get("venue_id") or fields.get("business_id") or "").strip()
    if not api_key or not venue_id:
        raise CredentialVerifyError("Foursquare API key and venue ID are required.")
    data = _http_json(
        f"https://api.foursquare.com/v3/places/{urllib.parse.quote(venue_id)}",
        headers={"Authorization": api_key, "Accept": "application/json"},
    )
    return {"external_id": venue_id, "business_name": data.get("name") or "", "raw": data}


PAYMENT_VERIFIERS = {
    "stripe": verify_stripe,
    "paypal": verify_paypal,
    "square": verify_square,
    "adyen": verify_adyen,
    "razorpay": verify_razorpay,
    "mollie": verify_mollie,
    "paystack": verify_paystack,
    "flutterwave": verify_flutterwave,
    "mercado_pago": verify_mercadopago,
    "yookassa": verify_yookassa,
    "paypay": verify_paypay,
}

REPUTATION_VERIFIERS = {
    "yelp": verify_yelp,
    "foursquare": verify_foursquare,
}


def verify_payment_credentials(provider: str, fields: dict[str, str]) -> dict[str, Any]:
    provider = (provider or "").lower().strip()
    cleaned = {k: (v or "").strip() for k, v in fields.items() if (v or "").strip()}
    assert_not_placeholder(cleaned)
    verifier = PAYMENT_VERIFIERS.get(provider)
    if not verifier:
        raise CredentialVerifyError(
            f"Live verification is required for “{provider}”, but this server has no API check "
            f"for it yet. Use Stripe, PayPal, Square, Adyen, Razorpay, Mollie, Paystack, "
            f"Flutterwave, Mercado Pago, YooKassa, or PayPay — or connect via OAuth when configured."
        )
    return verifier(cleaned)


def verify_reputation_credentials(provider: str, fields: dict[str, str]) -> dict[str, Any]:
    provider = (provider or "").lower().strip()
    cleaned = {k: (v or "").strip() for k, v in fields.items() if (v or "").strip()}
    assert_not_placeholder(cleaned)
    verifier = REPUTATION_VERIFIERS.get(provider)
    if not verifier:
        raise CredentialVerifyError(
            f"Live verification is required for “{provider}”. "
            f"Use OAuth (Tripadvisor / OpenTable / …) when configured, "
            f"or connect Yelp / Foursquare with a real API key that the provider accepts."
        )
    return verifier(cleaned)
