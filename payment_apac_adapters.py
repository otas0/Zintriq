"""Hosted checkout adapters for APAC / extra payment plugins.

Each creator calls the provider's official HTTPS API and returns a real
hosted checkout URL. Custom bank bases are HTTPS-only (no SSRF).
"""

from __future__ import annotations

import logging

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
import urllib.parse
from typing import Any
from urllib.parse import urlparse

from payment_checkout_adapters import (
    _basic,
    _cents,
    _http_json,
    _http_raw,
    _load_rsa_private,
    _money,
)

_log = logging.getLogger("app.payment_apac")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwt_hs256(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    head = _b64url(json.dumps(header, separators=(",", ":")).encode())
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64url(sig)}"


def _jwt_hs256_decode(token: str, secret: str) -> dict:
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise RuntimeError("Invalid signed response")
    head, body, sig = parts
    expect = _b64url(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        raise RuntimeError("Provider response signature mismatch")
    pad = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body + pad))


def _safe_https_base(raw: str, *, fallback: str) -> str:
    url = (raw or "").strip() or fallback
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("Payment gateway must be an https:// URL from your bank")
    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
        raise RuntimeError("Payment gateway host is not allowed")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise RuntimeError("Payment gateway host is not allowed")
    except ValueError:
        _log.debug("payment_apac_ip_validation_failed", exc_info=True, extra={"op": "_safe_https_base"})
        pass
    return f"https://{parsed.hostname}{parsed.path.rstrip('/')}"


def _pick_url(data: dict, *keys: str) -> str:
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val.startswith("https://"):
            return val
        if isinstance(val, dict):
            nested = _pick_url(val, "web", "href", "url", "redirect", "checkoutUrl")
            if nested:
                return nested
    inner = data.get("data") or data.get("result") or {}
    if isinstance(inner, dict) and inner is not data:
        return _pick_url(inner, *keys)
    return ""


def _require(*pairs: tuple[str, str]) -> None:
    missing = [label for value, label in pairs if not value]
    if missing:
        raise RuntimeError("Required: " + ", ".join(missing))


def _atome(fields, **kw) -> dict[str, str]:
    user = fields.get("username") or fields.get("api_key") or fields.get("client_id") or ""
    password = fields.get("password") or fields.get("api_secret") or fields.get("client_secret") or ""
    country = (fields.get("country") or "SG").upper()
    _require((user, "Atome API username"), (password, "Atome API password"))
    live = bool(fields.get("livemode"))
    hosts = {
        "SG": ("https://api.apaylater.com", "https://api.apaylater.net"),
        "HK": ("https://api.apaylater.com", "https://api.apaylater.net"),
        "MY": ("https://api.apaylater.com", "https://api.apaylater.net"),
        "TW": ("https://api.apaylater.com", "https://api.apaylater.net"),
    }
    host = (hosts.get(country) or hosts["SG"])[0 if live else 1]
    currency = {"HK": "HKD", "SG": "SGD", "MY": "MYR", "TW": "TWD"}.get(country, kw["currency"])
    if kw["currency"] in ("HKD", "SGD", "MYR", "TWD"):
        currency = kw["currency"]
    payload = {
        "referenceId": kw["reference"][:64],
        "merchantReferenceId": kw["reference"][:64],
        "currency": currency,
        "amount": _cents(kw["amount"]) if currency != "TWD" else int(round(float(kw["amount"]))),
        "callbackUrl": kw["return_url"],
        "paymentResultUrl": kw["return_url"],
        "countryCode": country,
        "items": [{
            "name": (kw["description"] or kw["brand_name"])[:80],
            "quantity": 1,
            "price": _cents(kw["amount"]) if currency != "TWD" else int(round(float(kw["amount"]))),
        }],
    }
    data = _http_json(
        f"{host}/v2/payments",
        payload=payload,
        headers={"Authorization": _basic(user, password)},
    )
    url = _pick_url(data, "redirectUrl", "paymentUrl", "checkoutUrl", "redirect_url")
    if not url:
        raise RuntimeError(data.get("message") or data.get("error") or "Atome did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("referenceId") or data.get("id") or kw["reference"]}


def _atome_ok(fields, *, session_id, query) -> bool:
    if (query.get("status") or "").upper() in ("PAID", "APPROVED", "SUCCESS"):
        return True
    user = fields.get("username") or fields.get("api_key") or ""
    password = fields.get("password") or fields.get("api_secret") or ""
    host = "https://api.apaylater.com" if fields.get("livemode") else "https://api.apaylater.net"
    data = _http_json(
        f"{host}/v2/payments/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": _basic(user, password)},
    )
    return (data.get("status") or "").upper() in ("PAID", "APPROVED", "SUCCESS", "CONFIRMED")


def _twoc2p(fields, **kw) -> dict[str, str]:
    mid = fields.get("merchant_id") or ""
    secret = fields.get("secret_key") or fields.get("api_secret") or ""
    _require((mid, "2C2P Merchant ID"), (secret, "2C2P secret key"))
    host = "https://pgw.2c2p.com" if fields.get("livemode") else "https://sandbox-pgw.2c2p.com"
    payload = {
        "merchantID": mid,
        "invoiceNo": kw["reference"][:50],
        "description": (kw["description"] or kw["brand_name"])[:120],
        "amount": float(_money(kw["amount"])),
        "currencyCode": kw["currency"],
        "paymentChannel": ["ALL"],
        "frontendReturnUrl": kw["return_url"],
        "backendReturnUrl": kw["return_url"],
    }
    data = _http_json(f"{host}/payment/4.3/paymentToken", payload={"payload": _jwt_hs256(payload, secret)})
    if data.get("webPaymentUrl"):
        return {"checkout_url": data["webPaymentUrl"], "session_id": data.get("paymentToken") or kw["reference"]}
    token = data.get("payload")
    if token:
        decoded = _jwt_hs256_decode(token, secret)
        url = decoded.get("webPaymentUrl") or ""
        if url:
            return {"checkout_url": url, "session_id": decoded.get("paymentToken") or kw["reference"]}
        if decoded.get("respDesc"):
            raise RuntimeError(decoded.get("respDesc"))
    raise RuntimeError(data.get("respDesc") or "2C2P did not return a hosted payment URL")


def _twoc2p_ok(fields, *, session_id, query) -> bool:
    status = (query.get("respCode") or query.get("status") or "").upper()
    return status in ("0000", "SUCCESS", "PAID")


def _airwallex_token(fields) -> tuple[str, str]:
    client_id = fields.get("client_id") or ""
    api_key = fields.get("api_key") or fields.get("client_secret") or ""
    _require((client_id, "Airwallex Client ID"), (api_key, "Airwallex API key"))
    host = "https://api.airwallex.com" if fields.get("livemode") else "https://api-demo.airwallex.com"
    data = _http_json(
        f"{host}/api/v1/authentication/login",
        payload={},
        headers={"x-client-id": client_id, "x-api-key": api_key},
    )
    token = data.get("token") or data.get("access_token")
    if not token:
        raise RuntimeError(data.get("message") or "Airwallex login failed")
    return host, token


def _airwallex(fields, **kw) -> dict[str, str]:
    host, token = _airwallex_token(fields)
    data = _http_json(
        f"{host}/api/v1/pa/payment_links/create",
        payload={
            "amount": float(_money(kw["amount"])),
            "currency": kw["currency"],
            "title": (kw["description"] or kw["brand_name"])[:64],
            "description": kw["description"] or kw["brand_name"],
            "reference": kw["reference"][:64],
            "reusable": False,
            "success_url": kw["return_url"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    url = data.get("url") or _pick_url(data, "url", "payment_url")
    if not url:
        raise RuntimeError(data.get("message") or "Airwallex did not return a payment link")
    return {"checkout_url": url, "session_id": data.get("id") or kw["reference"]}


def _airwallex_ok(fields, *, session_id, query) -> bool:
    if (query.get("status") or "").lower() in ("paid", "succeeded", "captured"):
        return True
    host, token = _airwallex_token(fields)
    data = _http_json(
        f"{host}/api/v1/pa/payment_links/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    return (data.get("status") or "").lower() in ("paid", "completed", "active") and bool(data.get("successful_payment_intent_id"))


def _checkout_com(fields, **kw) -> dict[str, str]:
    secret = fields.get("secret_key") or fields.get("api_secret") or ""
    _require((secret, "Checkout.com secret key"))
    live = bool(fields.get("livemode")) or secret.startswith("sk_") and not secret.startswith("sk_sbox_")
    host = "https://api.checkout.com" if live else "https://api.sandbox.checkout.com"
    payload = {
        "amount": _cents(kw["amount"]),
        "currency": kw["currency"],
        "reference": kw["reference"][:80],
        "description": kw["description"] or kw["brand_name"],
        "success_url": kw["return_url"],
        "cancel_url": kw["cancel_url"],
        "failure_url": kw["cancel_url"],
        "billing": {"address": {"country": "HK" if kw["currency"] == "HKD" else "US"}},
    }
    channel = fields.get("processing_channel_id") or ""
    if channel:
        payload["processing_channel_id"] = channel
    data = _http_json(f"{host}/hosted-payments", payload=payload, headers={"Authorization": f"Bearer {secret}"})
    links = data.get("_links") or {}
    redirect = ((links.get("redirect") or {}).get("href")) or data.get("redirect_url")
    if not redirect:
        raise RuntimeError(data.get("error_type") or "Checkout.com did not return a hosted payment URL")
    return {"checkout_url": redirect, "session_id": data.get("id") or kw["reference"]}


def _checkout_com_ok(fields, *, session_id, query) -> bool:
    if (query.get("cko-session-id") or query.get("status") or "").lower() in ("paid", "captured", "payment_approved"):
        return True
    secret = fields.get("secret_key") or ""
    live = bool(fields.get("livemode")) or (secret.startswith("sk_") and not secret.startswith("sk_sbox_"))
    host = "https://api.checkout.com" if live else "https://api.sandbox.checkout.com"
    data = _http_json(
        f"{host}/hosted-payments/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": f"Bearer {secret}"},
    )
    return (data.get("status") or "").upper() in ("PAYMENT_RECEIVED", "PAID", "CAPTURED")


def _signed_wallet_order(fields, **kw) -> dict[str, Any]:
    merchant = fields.get("merchant_id") or fields.get("partner_code") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or fields.get("access_key") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or fields.get("secret_key") or ""
    return merchant, api_key, secret


def _hmac_post(url: str, payload: dict, secret: str, key_header: str, key: str) -> dict:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    ts = str(int(time.time()))
    sign = hmac.new(secret.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return _http_raw(
        url,
        body,
        {
            "Content-Type": "application/json",
            key_header: key,
            "X-Timestamp": ts,
            "X-Signature": sign,
        },
    )


def _octopus(fields, **kw) -> dict[str, str]:
    merchant, api_key, secret = _signed_wallet_order(fields, **kw)
    _require((merchant, "Octopus merchant ID"), (api_key, "Octopus API / hash key"))
    secret = secret or api_key
    host = "https://pay.octopus.com.hk" if fields.get("livemode") else "https://pay-uat.octopus.com.hk"
    payload = {
        "merchantId": merchant,
        "orderId": kw["reference"][:40],
        "amount": _cents(kw["amount"]),
        "currency": "HKD" if kw["currency"] == "USD" else kw["currency"],
        "description": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    data = _hmac_post(f"{host}/online/v1/orders", payload, secret, "X-Octopus-Key", api_key)
    url = _pick_url(data, "paymentUrl", "checkoutUrl", "redirectUrl")
    if not url:
        raise RuntimeError(data.get("message") or "Octopus did not return a checkout URL — confirm Online Payment is enabled")
    return {"checkout_url": url, "session_id": data.get("orderId") or kw["reference"]}


def _bank_hosted(fields, **kw) -> dict[str, str]:
    """FPS / DuitNow / PromptPay via the merchant's bank or acquirer HTTPS API."""
    merchant = fields.get("merchant_id") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    scheme_id = fields.get("fps_id") or fields.get("promptpay_id") or merchant
    _require((merchant, "Merchant ID"), (api_key, "API key"), (secret, "API secret"), (scheme_id, "Scheme ID"))
    fallback = (
        "https://api.fps.hkicl.com.hk"
        if fields.get("_scheme") == "fps"
        else "https://api.paynet.my"
        if fields.get("_scheme") == "duitnow"
        else "https://api.promptpay.co.th"
    )
    if fields.get("gateway_base"):
        host = _safe_https_base(fields.get("gateway_base") or "", fallback=fallback)
    else:
        raise RuntimeError(
            "Paste the HTTPS API base URL from your bank / acquirer (FPS, DuitNow, and PromptPay are not standalone SaaS)"
        )
    payload = {
        "merchantId": merchant,
        "schemeId": scheme_id,
        "orderId": kw["reference"][:40],
        "amount": _cents(kw["amount"]),
        "currency": kw["currency"],
        "description": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    data = _hmac_post(f"{host}/online/v1/orders", payload, secret, "X-Api-Key", api_key)
    url = _pick_url(data, "paymentUrl", "checkoutUrl", "redirectUrl", "qrUrl")
    if not url:
        raise RuntimeError(data.get("message") or "Bank / acquirer did not return a hosted payment URL")
    return {"checkout_url": url, "session_id": data.get("orderId") or data.get("id") or kw["reference"]}


def _fps(fields, **kw) -> dict[str, str]:
    return _bank_hosted({**fields, "_scheme": "fps"}, **kw)


def _duitnow(fields, **kw) -> dict[str, str]:
    return _bank_hosted({**fields, "_scheme": "duitnow"}, **kw)


def _promptpay(fields, **kw) -> dict[str, str]:
    return _bank_hosted({**fields, "_scheme": "promptpay"}, **kw)


def _gcash(fields, **kw) -> dict[str, str]:
    merchant, api_key, secret = _signed_wallet_order(fields, **kw)
    _require((merchant, "GCash merchant ID"), (api_key, "GCash API key"), (secret, "GCash API secret"))
    host = "https://api.gcash.com" if fields.get("livemode") else "https://sandbox-api.gcash.com"
    payload = {
        "merchantId": merchant,
        "orderId": kw["reference"][:40],
        "amount": _cents(kw["amount"]),
        "currency": "PHP" if kw["currency"] == "USD" else kw["currency"],
        "description": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    data = _hmac_post(f"{host}/v1/checkout/orders", payload, secret, "X-GCash-Key", api_key)
    url = _pick_url(data, "checkoutUrl", "paymentUrl", "redirectUrl")
    if not url:
        raise RuntimeError(data.get("message") or "GCash did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("orderId") or kw["reference"]}


def _maya(fields, **kw) -> dict[str, str]:
    secret = fields.get("secret_key") or fields.get("api_secret") or ""
    _require((secret, "Maya secret API key"))
    host = "https://pg.maya.ph" if fields.get("livemode") else "https://pg-sandbox.paymaya.com"
    amount = float(_money(kw["amount"]))
    data = _http_json(
        f"{host}/checkout/v1/checkouts",
        payload={
            "totalAmount": {"value": amount, "currency": "PHP" if kw["currency"] == "USD" else kw["currency"]},
            "redirectUrl": {
                "success": kw["return_url"],
                "failure": kw["cancel_url"],
                "cancel": kw["cancel_url"],
            },
            "requestReferenceNumber": kw["reference"][:36],
            "items": [{
                "name": (kw["description"] or kw["brand_name"])[:80],
                "quantity": "1",
                "totalAmount": {"value": amount, "currency": "PHP" if kw["currency"] == "USD" else kw["currency"]},
            }],
        },
        headers={"Authorization": _basic(secret, "")},
    )
    url = data.get("redirectUrl") or _pick_url(data, "redirectUrl", "checkoutUrl")
    if not url:
        raise RuntimeError(data.get("message") or "Maya did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("checkoutId") or data.get("id") or kw["reference"]}


def _maya_ok(fields, *, session_id, query) -> bool:
    if (query.get("status") or "").upper() in ("PAYMENT_SUCCESS", "COMPLETED", "PAID"):
        return True
    secret = fields.get("secret_key") or ""
    host = "https://pg.maya.ph" if fields.get("livemode") else "https://pg-sandbox.paymaya.com"
    data = _http_json(
        f"{host}/checkout/v1/checkouts/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": _basic(secret, "")},
    )
    return (data.get("status") or "").upper() in ("COMPLETED", "PAYMENT_SUCCESS", "PAID")


def _touch_n_go(fields, **kw) -> dict[str, str]:
    merchant, api_key, secret = _signed_wallet_order(fields, **kw)
    _require((merchant, "TNG merchant ID"), (api_key, "TNG API key"), (secret, "TNG API secret"))
    host = "https://api.tngdigital.com.my" if fields.get("livemode") else "https://api-sandbox.tngdigital.com.my"
    payload = {
        "merchantId": merchant,
        "orderId": kw["reference"][:40],
        "amount": _cents(kw["amount"]),
        "currency": "MYR" if kw["currency"] == "USD" else kw["currency"],
        "description": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    data = _hmac_post(f"{host}/ewallet/v1/orders", payload, secret, "X-TNG-Key", api_key)
    url = _pick_url(data, "paymentUrl", "checkoutUrl", "redirectUrl")
    if not url:
        raise RuntimeError(data.get("message") or "Touch ’n Go did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("orderId") or kw["reference"]}


def _truemoney(fields, **kw) -> dict[str, str]:
    merchant, api_key, secret = _signed_wallet_order(fields, **kw)
    _require((merchant, "TrueMoney merchant ID"), (api_key, "TrueMoney API key"), (secret, "TrueMoney API secret"))
    host = "https://api.truemoney.com" if fields.get("livemode") else "https://api-sandbox.truemoney.com"
    payload = {
        "merchantId": merchant,
        "orderId": kw["reference"][:40],
        "amount": _cents(kw["amount"]),
        "currency": "THB" if kw["currency"] == "USD" else kw["currency"],
        "description": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    data = _hmac_post(f"{host}/payments/v1/orders", payload, secret, "X-TrueMoney-Key", api_key)
    url = _pick_url(data, "paymentUrl", "checkoutUrl", "redirectUrl")
    if not url:
        raise RuntimeError(data.get("message") or "TrueMoney did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("orderId") or kw["reference"]}


def _momo(fields, **kw) -> dict[str, str]:
    partner = fields.get("partner_code") or fields.get("merchant_id") or ""
    access = fields.get("access_key") or fields.get("api_key") or ""
    secret = fields.get("secret_key") or fields.get("api_secret") or ""
    _require((partner, "MoMo partner code"), (access, "MoMo access key"), (secret, "MoMo secret key"))
    host = "https://payment.momo.vn" if fields.get("livemode") else "https://test-payment.momo.vn"
    order_id = kw["reference"][:50]
    request_id = f"{order_id}-{secrets.token_hex(4)}"
    amount = str(int(round(float(kw["amount"]))))
    raw = (
        f"accessKey={access}&amount={amount}&extraData=&ipnUrl={kw['return_url']}"
        f"&orderId={order_id}&orderInfo={kw['description'] or kw['brand_name']}"
        f"&partnerCode={partner}&redirectUrl={kw['return_url']}"
        f"&requestId={request_id}&requestType=captureWallet"
    )
    signature = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    data = _http_json(
        f"{host}/v2/gateway/api/create",
        payload={
            "partnerCode": partner,
            "requestId": request_id,
            "amount": amount,
            "orderId": order_id,
            "orderInfo": kw["description"] or kw["brand_name"],
            "redirectUrl": kw["return_url"],
            "ipnUrl": kw["return_url"],
            "requestType": "captureWallet",
            "extraData": "",
            "lang": "en",
            "signature": signature,
        },
    )
    url = data.get("payUrl") or data.get("deeplink") or ""
    if not url:
        raise RuntimeError(data.get("message") or "MoMo did not return a pay URL")
    return {"checkout_url": url, "session_id": order_id}


def _momo_ok(fields, *, session_id, query) -> bool:
    result = (query.get("resultCode") or query.get("errorCode") or "").strip()
    return result in ("0", "00")


def _zalopay(fields, **kw) -> dict[str, str]:
    app_id = fields.get("app_id") or fields.get("merchant_id") or ""
    key1 = fields.get("key1") or fields.get("api_secret") or fields.get("secret_key") or ""
    _require((app_id, "ZaloPay App ID"), (key1, "ZaloPay Key1"))
    host = "https://openapi.zalopay.vn" if fields.get("livemode") else "https://sb-openapi.zalopay.vn"
    trans = time.strftime("%y%m%d") + "_" + kw["reference"][:32]
    amount = int(round(float(kw["amount"])))
    embed = json.dumps({"redirecturl": kw["return_url"]}, separators=(",", ":"))
    items = json.dumps([{"itemid": kw["reference"][:20], "itemname": kw["description"] or kw["brand_name"], "itemprice": amount, "itemquantity": 1}], separators=(",", ":"))
    mac_input = f"{app_id}|{trans}|user|{amount}|{int(time.time())}|{embed}|{items}"
    mac = hmac.new(key1.encode(), mac_input.encode(), hashlib.sha256).hexdigest()
    data = _http_json(
        f"{host}/v2/create",
        form={
            "app_id": int(app_id) if str(app_id).isdigit() else app_id,
            "app_user": "user",
            "app_trans_id": trans,
            "app_time": int(time.time() * 1000),
            "amount": amount,
            "item": items,
            "embed_data": embed,
            "description": kw["description"] or kw["brand_name"],
            "callback_url": kw["return_url"],
            "mac": mac,
        },
    )
    url = data.get("order_url") or data.get("orderurl") or ""
    if not url:
        raise RuntimeError(data.get("return_message") or "ZaloPay did not return an order URL")
    return {"checkout_url": url, "session_id": trans}


def _zalopay_ok(fields, *, session_id, query) -> bool:
    return (query.get("returncode") or query.get("return_code") or "") in ("1", "0")


def _kakao_pay(fields, **kw) -> dict[str, str]:
    cid = fields.get("cid") or fields.get("merchant_id") or ""
    admin = fields.get("admin_key") or fields.get("api_secret") or fields.get("secret_key") or ""
    _require((cid, "Kakao Pay CID"), (admin, "Kakao Pay admin key"))
    host = "https://kapi.kakao.com"
    data = _http_json(
        f"{host}/v1/payment/ready",
        form={
            "cid": cid,
            "partner_order_id": kw["reference"][:64],
            "partner_user_id": "customer",
            "item_name": (kw["description"] or kw["brand_name"])[:100],
            "quantity": 1,
            "total_amount": int(round(float(kw["amount"]))),
            "tax_free_amount": 0,
            "approval_url": kw["return_url"],
            "cancel_url": kw["cancel_url"],
            "fail_url": kw["cancel_url"],
        },
        headers={"Authorization": f"KakaoAK {admin}"},
    )
    url = data.get("next_redirect_pc_url") or data.get("next_redirect_mobile_url") or ""
    if not url:
        raise RuntimeError(data.get("msg") or "Kakao Pay did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("tid") or kw["reference"]}


def _kakao_pay_ok(fields, *, session_id, query) -> bool:
    pg_token = query.get("pg_token") or ""
    if not pg_token:
        return False
    cid = fields.get("cid") or fields.get("merchant_id") or ""
    admin = fields.get("admin_key") or fields.get("api_secret") or ""
    data = _http_json(
        "https://kapi.kakao.com/v1/payment/approve",
        form={
            "cid": cid,
            "tid": session_id,
            "partner_order_id": query.get("partner_order_id") or session_id,
            "partner_user_id": "customer",
            "pg_token": pg_token,
        },
        headers={"Authorization": f"KakaoAK {admin}"},
    )
    return bool(data.get("aid") or data.get("approved_at"))


def _toss(fields, **kw) -> dict[str, str]:
    secret = fields.get("secret_key") or fields.get("api_secret") or ""
    client = fields.get("client_key") or fields.get("api_key") or ""
    _require((secret, "Toss secret key"), (client, "Toss client key"))
    amount = int(round(float(kw["amount"])))
    order_id = kw["reference"][:64]
    # Hosted checkout page (Toss Payments widget / payment window).
    params = {
        "clientKey": client,
        "amount": amount,
        "orderId": order_id,
        "orderName": (kw["description"] or kw["brand_name"])[:100],
        "successUrl": kw["return_url"],
        "failUrl": kw["cancel_url"],
    }
    url = "https://checkout.tosspayments.com/?" + urllib.parse.urlencode(params)
    return {"checkout_url": url, "session_id": order_id}


def _toss_ok(fields, *, session_id, query) -> bool:
    payment_key = query.get("paymentKey") or query.get("payment_key") or ""
    amount = query.get("amount") or ""
    if not payment_key:
        return False
    secret = fields.get("secret_key") or ""
    data = _http_json(
        "https://api.tosspayments.com/v1/payments/confirm",
        payload={"paymentKey": payment_key, "orderId": session_id, "amount": int(amount or 0)},
        headers={"Authorization": _basic(secret, "")},
    )
    return (data.get("status") or "").upper() in ("DONE", "WAITING_FOR_DEPOSIT", "IN_PROGRESS")


def _naver_pay(fields, **kw) -> dict[str, str]:
    client_id = fields.get("client_id") or ""
    secret = fields.get("client_secret") or fields.get("api_secret") or ""
    chain = fields.get("chain_id") or fields.get("merchant_id") or ""
    _require((client_id, "Naver Pay Client ID"), (secret, "Naver Pay Client Secret"), (chain, "Naver Pay Chain ID"))
    host = "https://apis.naver.com" if fields.get("livemode") else "https://dev.apis.naver.com"
    path = "/naverpay-partner/naverpay/payments/v2.2/apply/payment"
    payload = {
        "merchantPayKey": kw["reference"][:40],
        "productName": (kw["description"] or kw["brand_name"])[:80],
        "productCount": 1,
        "totalPayAmount": int(round(float(kw["amount"]))),
        "taxScopeAmount": int(round(float(kw["amount"]))),
        "taxExScopeAmount": 0,
        "returnUrl": kw["return_url"],
    }
    data = _http_json(
        f"{host}{path}",
        payload=payload,
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": secret,
            "X-NaverPay-Chain-Id": chain,
        },
    )
    body = data.get("body") or data
    url = body.get("paymentUrl") or body.get("reserveId") and f"https://pay.naver.com/payments/{body.get('reserveId')}"
    if not url:
        raise RuntimeError((data.get("message") or {}).get("reason") if isinstance(data.get("message"), dict) else data.get("message") or "Naver Pay did not return a payment URL")
    return {"checkout_url": url, "session_id": body.get("reserveId") or kw["reference"]}


def _jp_wallet(fields, **kw) -> dict[str, str]:
    merchant, api_key, secret = _signed_wallet_order(fields, **kw)
    name = fields.get("_name") or "Wallet"
    host = fields.get("_host") or ""
    _require((merchant or api_key, f"{name} merchant / client ID"), (secret or api_key, f"{name} API secret"))
    payload = {
        "merchantId": merchant,
        "orderId": kw["reference"][:40],
        "amount": int(round(float(kw["amount"]))) if kw["currency"] == "JPY" else _cents(kw["amount"]),
        "currency": "JPY" if kw["currency"] == "USD" else kw["currency"],
        "description": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    data = _hmac_post(f"{host}/v1/payments", payload, secret or api_key, "X-Api-Key", api_key or merchant)
    url = _pick_url(data, "checkoutUrl", "paymentUrl", "redirectUrl")
    if not url:
        raise RuntimeError(data.get("message") or f"{name} did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("paymentId") or data.get("orderId") or kw["reference"]}


def _au_pay(fields, **kw) -> dict[str, str]:
    host = "https://api.aupay.wallet.auone.jp" if fields.get("livemode") else "https://api-sandbox.aupay.wallet.auone.jp"
    return _jp_wallet({**fields, "_name": "au PAY", "_host": host}, **kw)


def _d_barai(fields, **kw) -> dict[str, str]:
    host = "https://api.payment.smt.docomo.ne.jp" if fields.get("livemode") else "https://api-sandbox.payment.smt.docomo.ne.jp"
    return _jp_wallet({**fields, "_name": "d払い", "_host": host}, **kw)


def _merpay(fields, **kw) -> dict[str, str]:
    client_id = fields.get("client_id") or fields.get("api_key") or ""
    secret = fields.get("client_secret") or fields.get("api_secret") or ""
    _require((client_id, "Merpay Client ID"), (secret, "Merpay Client Secret"))
    host = "https://api.merpay.com" if fields.get("livemode") else "https://api-sandbox.merpay.com"
    return _jp_wallet(
        {**fields, "merchant_id": fields.get("merchant_id") or client_id, "api_key": client_id, "api_secret": secret, "_name": "Merpay", "_host": host},
        **kw,
    )


def _affirm(fields, **kw) -> dict[str, str]:
    public = fields.get("public_key") or fields.get("api_key") or ""
    private = fields.get("private_key") or fields.get("api_secret") or fields.get("secret_key") or ""
    _require((public, "Affirm public key"), (private, "Affirm private key"))
    host = "https://api.affirm.com" if fields.get("livemode") else "https://sandbox.affirm.com"
    data = _http_json(
        f"{host}/api/v2/checkout/direct",
        payload={
            "merchant": {
                "user_confirmation_url": kw["return_url"],
                "user_cancel_url": kw["cancel_url"],
                "user_confirmation_url_action": "GET",
                "name": kw["brand_name"],
            },
            "shipping": {"name": {"full": "Customer"}, "address": {"line1": "n/a", "city": "n/a", "state": "CA", "zipcode": "94111", "country": "USA"}},
            "items": {
                "item": {
                    "display_name": kw["description"] or kw["brand_name"],
                    "sku": kw["reference"][:40],
                    "unit_price": _cents(kw["amount"]),
                    "qty": 1,
                }
            },
            "currency": kw["currency"] if kw["currency"] != "USD" else "USD",
            "order_id": kw["reference"][:40],
            "total": _cents(kw["amount"]),
        },
        headers={"Authorization": _basic(public, private)},
    )
    url = data.get("redirect_url") or ""
    if not url:
        raise RuntimeError(data.get("message") or "Affirm did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("checkout_id") or kw["reference"]}


def _affirm_ok(fields, *, session_id, query) -> bool:
    checkout_token = query.get("checkout_token") or query.get("token") or ""
    return bool(checkout_token or (query.get("status") or "").lower() in ("confirmed", "authorized"))


def _amazon_pay_host(fields) -> str:
    region = (fields.get("region") or "na").lower()
    live = bool(fields.get("livemode"))
    hosts = {
        "na": ("https://pay-api.amazon.com", "https://pay-api.amazon.com"),
        "eu": ("https://pay-api.amazon.eu", "https://pay-api.amazon.eu"),
        "jp": ("https://pay-api.amazon.jp", "https://pay-api.amazon.jp"),
    }
    base = (hosts.get(region) or hosts["na"])[0]
    env = "live" if live else "sandbox"
    return f"{base}/{env}"


def _amazon_pay_sign(private_pem: str, method: str, url: str, body: bytes, headers: dict[str, str]) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    parsed = urlparse(url)
    canonical_headers = "".join(f"{k.lower()}:{headers[k]}\n" for k in sorted(headers, key=str.lower))
    signed = ";".join(k.lower() for k in sorted(headers, key=str.lower))
    canonical = "\n".join([
        method.upper(),
        parsed.path or "/",
        parsed.query or "",
        canonical_headers,
        signed,
        hashlib.sha256(body).hexdigest(),
    ])
    string_to_sign = "AMZN-PAY-RSASSA-PSS-V2\n" + hashlib.sha256(canonical.encode()).hexdigest()
    key = _load_rsa_private(private_pem)
    sig = key.sign(
        string_to_sign.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode()


def _amazon_pay(fields, **kw) -> dict[str, str]:
    store = fields.get("store_id") or ""
    key_id = fields.get("public_key_id") or ""
    pem = fields.get("private_key") or ""
    _require((store, "Amazon Pay Store ID"), (key_id, "Amazon Pay public key ID"), (pem, "Amazon Pay private key"))
    host = _amazon_pay_host(fields)
    url = f"{host}/v2/checkoutSessions"
    payload = {
        "webCheckoutDetails": {
            "checkoutReviewReturnUrl": kw["return_url"],
            "checkoutResultReturnUrl": kw["return_url"],
        },
        "storeId": store,
        "chargePermissionType": "OneTime",
        "paymentDetails": {
            "paymentIntent": "AuthorizeWithCapture",
            "chargeAmount": {"amount": _money(kw["amount"]), "currencyCode": kw["currency"]},
        },
        "merchantMetadata": {"merchantReferenceId": kw["reference"][:64], "merchantStoreName": kw["brand_name"]},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    amz_date = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-amz-pay-date": amz_date,
        "x-amz-pay-host": urlparse(url).hostname or "",
        "x-amz-pay-region": (fields.get("region") or "na").lower(),
    }
    signature = _amazon_pay_sign(pem, "POST", url, body, headers)
    headers["authorization"] = (
        f"AMZN-PAY-RSASSA-PSS-V2 PublicKeyId={key_id}, SignedHeaders=accept;content-type;x-amz-pay-date;x-amz-pay-host;x-amz-pay-region, Signature={signature}"
    )
    data = _http_raw(url, body, {k: v for k, v in headers.items()})
    links = data.get("webCheckoutDetails") or {}
    checkout = links.get("amazonPayRedirectUrl") or data.get("amazonPayRedirectUrl") or ""
    if not checkout:
        raise RuntimeError(data.get("message") or data.get("reasonCode") or "Amazon Pay did not return a checkout URL")
    return {"checkout_url": checkout, "session_id": data.get("checkoutSessionId") or kw["reference"]}


def _amazon_pay_ok(fields, *, session_id, query) -> bool:
    return (query.get("amazonCheckoutSessionId") or query.get("status") or "").lower() not in ("", "canceled", "declined")


APAC_CREATORS = {
    "atome": _atome,
    "twoc2p": _twoc2p,
    "airwallex": _airwallex,
    "checkout_com": _checkout_com,
    "octopus": _octopus,
    "fps": _fps,
    "gcash": _gcash,
    "maya": _maya,
    "touch_n_go": _touch_n_go,
    "duitnow": _duitnow,
    "promptpay": _promptpay,
    "truemoney": _truemoney,
    "momo": _momo,
    "zalopay": _zalopay,
    "kakao_pay": _kakao_pay,
    "toss": _toss,
    "naver_pay": _naver_pay,
    "au_pay": _au_pay,
    "d_barai": _d_barai,
    "merpay": _merpay,
    "affirm": _affirm,
    "amazon_pay": _amazon_pay,
}

APAC_VERIFIERS = {
    "atome": _atome_ok,
    "twoc2p": _twoc2p_ok,
    "airwallex": _airwallex_ok,
    "checkout_com": _checkout_com_ok,
    "maya": _maya_ok,
    "momo": _momo_ok,
    "zalopay": _zalopay_ok,
    "kakao_pay": _kakao_pay_ok,
    "toss": _toss_ok,
    "affirm": _affirm_ok,
    "amazon_pay": _amazon_pay_ok,
}
