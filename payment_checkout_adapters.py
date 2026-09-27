"""Real hosted checkout for merchant-connected payment providers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from observability.trace import trace

_log = logging.getLogger("app.payment_checkout")


def _http_json(
    url: str,
    *,
    method: str = "POST",
    payload: dict | None = None,
    headers: dict | None = None,
    form: dict | None = None,
    timeout: int = 15,
) -> dict:
    if form is not None:
        body = urllib.parse.urlencode({k: v for k, v in form.items() if v is not None}).encode()
        content_type = "application/x-www-form-urlencoded"
    elif payload is not None:
        body = json.dumps(payload).encode()
        content_type = "application/json"
    else:
        body = None
        content_type = "application/json"
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", content_type)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with trace("http.request", url=url, method=method):
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:400] if exc.fp else str(exc)
        raise RuntimeError(f"{exc.code}: {detail}") from exc


def _http_raw(url: str, body: bytes, headers: dict, *, method: str = "POST") -> dict:
    req = urllib.request.Request(url, data=body if method != "GET" else None, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with trace("http.request_raw", url=url, method=method):
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:400] if exc.fp else str(exc)
        raise RuntimeError(f"{exc.code}: {detail}") from exc


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def _money(amount: float) -> str:
    return f"{float(amount):.2f}"


def _cents(amount: float) -> int:
    return int(round(float(amount) * 100))


def create_hosted_checkout(
    provider: str,
    fields: dict[str, Any],
    *,
    amount: float,
    currency: str,
    description: str,
    reference: str,
    return_url: str,
    cancel_url: str,
    brand_name: str,
    customer_email: str = "",
    pay_url: str = "",
) -> dict[str, str]:
    """Create a real provider checkout session. Returns checkout_url + session_id."""
    fn = _CREATORS.get(provider)
    kwargs = dict(
        amount=amount,
        currency=currency.upper(),
        description=description[:120],
        reference=reference,
        return_url=return_url,
        cancel_url=cancel_url,
        brand_name=brand_name[:80],
        customer_email=customer_email,
        pay_url=pay_url,
    )
    if not fn:
        if pay_url:
            return {"checkout_url": pay_url, "session_id": reference}
        raise RuntimeError(f"{provider} checkout is not available")
    return fn(fields, **kwargs)


def verify_hosted_payment(
    provider: str,
    fields: dict[str, Any],
    *,
    session_id: str,
    query: dict[str, str] | None = None,
) -> bool:
    fn = _VERIFIERS.get(provider)
    if not fn:
        return False
    return bool(fn(fields, session_id=session_id, query=query or {}))


def _square(fields, **kw) -> dict[str, str]:
    token = fields.get("access_token") or fields.get("secret_key") or ""
    location = fields.get("location_id") or ""
    livemode = fields.get("livemode") or fields.get("mode") == "live"
    host = "https://connect.squareup.com" if livemode else "https://connect.squareupsandbox.com"
    data = _http_json(
        f"{host}/v2/online-checkout/payment-links",
        payload={
            "idempotency_key": secrets.token_hex(16),
            "quick_pay": {
                "name": kw["description"] or kw["brand_name"],
                "price_money": {"amount": _cents(kw["amount"]), "currency": kw["currency"]},
                "location_id": location,
            },
            "checkout_options": {
                "redirect_url": kw["return_url"],
            },
            "payment_note": kw["reference"],
        },
        headers={"Authorization": f"Bearer {token}", "Square-Version": "2024-01-18"},
    )
    url = (data.get("payment_link") or {}).get("url") or data.get("url")
    sid = (data.get("payment_link") or {}).get("id") or data.get("id") or ""
    if not url:
        raise RuntimeError("Square did not return a checkout URL")
    return {"checkout_url": url, "session_id": sid}


def _mollie(fields, **kw) -> dict[str, str]:
    key = fields.get("api_key") or fields.get("secret_key") or ""
    data = _http_json(
        "https://api.mollie.com/v2/payments",
        payload={
            "amount": {"currency": kw["currency"], "value": _money(kw["amount"])},
            "description": kw["description"] or kw["brand_name"],
            "redirectUrl": kw["return_url"],
            "cancelUrl": kw["cancel_url"],
            "metadata": {"reference": kw["reference"]},
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    url = (data.get("_links") or {}).get("checkout", {}).get("href")
    if not url:
        raise RuntimeError("Mollie did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _mollie_ok(fields, *, session_id, query) -> bool:
    key = fields.get("api_key") or fields.get("secret_key") or ""
    data = _http_json(
        f"https://api.mollie.com/v2/payments/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": f"Bearer {key}"},
    )
    return data.get("status") in ("paid", "authorized")


def _paystack(fields, **kw) -> dict[str, str]:
    key = fields.get("secret_key") or fields.get("api_key") or ""
    data = _http_json(
        "https://api.paystack.co/transaction/initialize",
        payload={
            "email": kw["customer_email"] or f"checkout+{kw['reference']}@customer.local",
            "amount": _cents(kw["amount"]),
            "currency": kw["currency"],
            "reference": kw["reference"],
            "callback_url": kw["return_url"],
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    inner = data.get("data") or {}
    url = inner.get("authorization_url")
    if not url:
        raise RuntimeError(data.get("message") or "Paystack did not return a checkout URL")
    return {"checkout_url": url, "session_id": inner.get("reference") or kw["reference"]}


def _paystack_ok(fields, *, session_id, query) -> bool:
    key = fields.get("secret_key") or fields.get("api_key") or ""
    ref = query.get("reference") or session_id
    data = _http_json(
        f"https://api.paystack.co/transaction/verify/{urllib.parse.quote(ref)}",
        method="GET",
        headers={"Authorization": f"Bearer {key}"},
    )
    return (data.get("data") or {}).get("status") == "success"


def _flutterwave(fields, **kw) -> dict[str, str]:
    key = fields.get("secret_key") or ""
    data = _http_json(
        "https://api.flutterwave.com/v3/payments",
        payload={
            "tx_ref": kw["reference"],
            "amount": _money(kw["amount"]),
            "currency": kw["currency"],
            "redirect_url": kw["return_url"],
            "customer": {"email": kw["customer_email"] or f"checkout+{kw['reference']}@customer.local"},
            "customizations": {"title": kw["brand_name"], "description": kw["description"]},
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    url = (data.get("data") or {}).get("link")
    if not url:
        raise RuntimeError(data.get("message") or "Flutterwave did not return a checkout URL")
    return {"checkout_url": url, "session_id": kw["reference"]}


def _flutterwave_ok(fields, *, session_id, query) -> bool:
    key = fields.get("secret_key") or ""
    tx_id = query.get("transaction_id") or query.get("tx_id") or ""
    if tx_id:
        data = _http_json(
            f"https://api.flutterwave.com/v3/transactions/{urllib.parse.quote(tx_id)}/verify",
            method="GET",
            headers={"Authorization": f"Bearer {key}"},
        )
        return (data.get("data") or {}).get("status") == "successful"
    data = _http_json(
        f"https://api.flutterwave.com/v3/transactions/verify_by_reference?tx_ref={urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": f"Bearer {key}"},
    )
    return (data.get("data") or {}).get("status") == "successful"


def _razorpay(fields, **kw) -> dict[str, str]:
    key_id = fields.get("key_id") or fields.get("client_id") or ""
    secret = fields.get("key_secret") or fields.get("client_secret") or ""
    data = _http_json(
        "https://api.razorpay.com/v1/payment_links",
        payload={
            "amount": _cents(kw["amount"]),
            "currency": kw["currency"],
            "description": kw["description"] or kw["brand_name"],
            "reference_id": kw["reference"][:40],
            "callback_url": kw["return_url"],
            "callback_method": "get",
        },
        headers={"Authorization": _basic(key_id, secret)},
    )
    url = data.get("short_url")
    if not url:
        raise RuntimeError("Razorpay did not return a payment link")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _razorpay_ok(fields, *, session_id, query) -> bool:
    key_id = fields.get("key_id") or fields.get("client_id") or ""
    secret = fields.get("key_secret") or fields.get("client_secret") or ""
    data = _http_json(
        f"https://api.razorpay.com/v1/payment_links/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": _basic(key_id, secret)},
    )
    return data.get("status") in ("paid", "partially_paid")


def _xendit(fields, **kw) -> dict[str, str]:
    key = fields.get("secret_key") or fields.get("api_key") or ""
    data = _http_json(
        "https://api.xendit.co/v2/invoices",
        payload={
            "external_id": kw["reference"],
            "amount": float(_money(kw["amount"])),
            "currency": kw["currency"],
            "description": kw["description"] or kw["brand_name"],
            "success_redirect_url": kw["return_url"],
            "failure_redirect_url": kw["cancel_url"],
        },
        headers={"Authorization": _basic(key, "")},
    )
    url = data.get("invoice_url")
    if not url:
        raise RuntimeError("Xendit did not return an invoice URL")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _xendit_ok(fields, *, session_id, query) -> bool:
    key = fields.get("secret_key") or fields.get("api_key") or ""
    data = _http_json(
        f"https://api.xendit.co/v2/invoices/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": _basic(key, "")},
    )
    return data.get("status") in ("PAID", "SETTLED")


def _omise(fields, **kw) -> dict[str, str]:
    secret = fields.get("secret_key") or ""
    data = _http_json(
        "https://api.omise.co/links",
        form={
            "amount": str(_cents(kw["amount"])),
            "currency": kw["currency"].lower(),
            "title": kw["brand_name"],
            "description": kw["description"],
        },
        headers={"Authorization": _basic(secret, "")},
    )
    url = data.get("payment_uri") or data.get("url")
    if not url:
        raise RuntimeError("Omise did not return a payment link")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _omise_ok(fields, *, session_id, query) -> bool:
    secret = fields.get("secret_key") or ""
    data = _http_json(
        f"https://api.omise.co/links/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": _basic(secret, "")},
    )
    return bool(data.get("used") or data.get("charges", {}).get("total", 0))


def _midtrans(fields, **kw) -> dict[str, str]:
    server = fields.get("server_key") or fields.get("secret_key") or ""
    data = _http_json(
        "https://app.sandbox.midtrans.com/snap/v1/transactions"
        if not fields.get("livemode")
        else "https://app.midtrans.com/snap/v1/transactions",
        payload={
            "transaction_details": {
                "order_id": kw["reference"],
                "gross_amount": int(round(float(kw["amount"]))),
            },
            "callbacks": {"finish": kw["return_url"]},
        },
        headers={"Authorization": _basic(server, "")},
    )
    token = data.get("token")
    url = data.get("redirect_url")
    if not url and token:
        base = "https://app.midtrans.com" if fields.get("livemode") else "https://app.sandbox.midtrans.com"
        url = f"{base}/snap/v2/vtweb/{token}"
    if not url:
        raise RuntimeError("Midtrans did not return a Snap URL")
    return {"checkout_url": url, "session_id": kw["reference"]}


def _midtrans_ok(fields, *, session_id, query) -> bool:
    server = fields.get("server_key") or fields.get("secret_key") or ""
    host = "https://api.midtrans.com" if fields.get("livemode") else "https://api.sandbox.midtrans.com"
    data = _http_json(
        f"{host}/v2/{urllib.parse.quote(session_id)}/status",
        method="GET",
        headers={"Authorization": _basic(server, "")},
    )
    return data.get("transaction_status") in ("settlement", "capture", "success")


def _mercado_pago(fields, **kw) -> dict[str, str]:
    token = fields.get("access_token") or fields.get("secret_key") or ""
    data = _http_json(
        "https://api.mercadopago.com/checkout/preferences",
        payload={
            "items": [{
                "title": kw["description"] or kw["brand_name"],
                "quantity": 1,
                "currency_id": kw["currency"],
                "unit_price": float(_money(kw["amount"])),
            }],
            "external_reference": kw["reference"],
            "back_urls": {
                "success": kw["return_url"],
                "failure": kw["cancel_url"],
                "pending": kw["return_url"],
            },
            "auto_return": "approved",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    url = data.get("init_point") or data.get("sandbox_init_point")
    if not url:
        raise RuntimeError("Mercado Pago did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _mercado_ok(fields, *, session_id, query) -> bool:
    status = (query.get("status") or query.get("collection_status") or "").lower()
    if status == "approved":
        return True
    token = fields.get("access_token") or ""
    payment_id = query.get("payment_id") or query.get("collection_id") or ""
    if not payment_id:
        return False
    data = _http_json(
        f"https://api.mercadopago.com/v1/payments/{urllib.parse.quote(payment_id)}",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    return data.get("status") == "approved"


def _yookassa(fields, **kw) -> dict[str, str]:
    shop = fields.get("shop_id") or fields.get("merchant_id") or ""
    secret = fields.get("secret_key") or ""
    data = _http_json(
        "https://api.yookassa.ru/v3/payments",
        payload={
            "amount": {"value": _money(kw["amount"]), "currency": kw["currency"]},
            "confirmation": {"type": "redirect", "return_url": kw["return_url"]},
            "capture": True,
            "description": kw["description"] or kw["brand_name"],
            "metadata": {"reference": kw["reference"]},
        },
        headers={
            "Authorization": _basic(shop, secret),
            "Idempotence-Key": secrets.token_hex(16),
        },
    )
    url = (data.get("confirmation") or {}).get("confirmation_url")
    if not url:
        raise RuntimeError("YooKassa did not return a confirmation URL")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _yookassa_ok(fields, *, session_id, query) -> bool:
    shop = fields.get("shop_id") or fields.get("merchant_id") or ""
    secret = fields.get("secret_key") or ""
    data = _http_json(
        f"https://api.yookassa.ru/v3/payments/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": _basic(shop, secret)},
    )
    return data.get("status") in ("succeeded", "waiting_for_capture")


def _sumup(fields, **kw) -> dict[str, str]:
    key = fields.get("api_key") or fields.get("access_token") or ""
    data = _http_json(
        "https://api.sumup.com/v0.1/checkouts",
        payload={
            "checkout_reference": kw["reference"],
            "amount": float(_money(kw["amount"])),
            "currency": kw["currency"],
            "description": kw["description"] or kw["brand_name"],
            "return_url": kw["return_url"],
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    url = data.get("hosted_checkout_url") or (data.get("checkout_url"))
    if not url and data.get("id"):
        url = f"https://checkout.sumup.com/pay/{data['id']}"
    if not url:
        raise RuntimeError("SumUp did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _sumup_ok(fields, *, session_id, query) -> bool:
    key = fields.get("api_key") or fields.get("access_token") or ""
    data = _http_json(
        f"https://api.sumup.com/v0.1/checkouts/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"Authorization": f"Bearer {key}"},
    )
    return data.get("status") == "PAID"


def _gocardless(fields, **kw) -> dict[str, str]:
    token = fields.get("access_token") or ""
    sandbox = not (fields.get("livemode") or fields.get("mode") in ("live", "production"))
    host = "https://api-sandbox.gocardless.com" if sandbox else "https://api.gocardless.com"
    headers = {
        "Authorization": f"Bearer {token}",
        "GoCardless-Version": "2015-07-06",
        "Idempotency-Key": secrets.token_hex(12),
    }
    request = _http_json(
        f"{host}/billing_requests",
        payload={
            "billing_requests": {
                "payment_request": {
                    "description": kw["description"] or kw["brand_name"],
                    "amount": _cents(kw["amount"]),
                    "currency": kw["currency"],
                },
                "metadata": {"reference": kw["reference"]},
            }
        },
        headers=headers,
    )
    br_id = (request.get("billing_requests") or {}).get("id")
    if not br_id:
        raise RuntimeError("GoCardless did not create a billing request")
    data = _http_json(
        f"{host}/billing_request_flows",
        payload={
            "billing_request_flows": {
                "redirect_uri": kw["return_url"],
                "exit_uri": kw["cancel_url"],
                "links": {"billing_request": br_id},
            }
        },
        headers={**headers, "Idempotency-Key": secrets.token_hex(12)},
    )
    url = (data.get("billing_request_flows") or {}).get("authorisation_url")
    if not url:
        raise RuntimeError("GoCardless did not return a checkout URL")
    return {"checkout_url": url, "session_id": br_id}


def _adyen(fields, **kw) -> dict[str, str]:
    key = fields.get("api_key") or ""
    merchant = fields.get("merchant_account") or ""
    data = _http_json(
        "https://checkout-test.adyen.com/v71/paymentLinks"
        if not fields.get("livemode")
        else "https://checkout-live.adyen.com/v71/paymentLinks",
        payload={
            "reference": kw["reference"],
            "amount": {"currency": kw["currency"], "value": _cents(kw["amount"])},
            "merchantAccount": merchant,
            "returnUrl": kw["return_url"],
            "shopperReference": kw["reference"],
        },
        headers={"X-API-Key": key},
    )
    url = data.get("url")
    if not url:
        raise RuntimeError("Adyen did not return a payment link")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _adyen_ok(fields, *, session_id, query) -> bool:
    key = fields.get("api_key") or ""
    host = (
        "https://checkout-live.adyen.com/v71/paymentLinks"
        if fields.get("livemode")
        else "https://checkout-test.adyen.com/v71/paymentLinks"
    )
    data = _http_json(
        f"{host}/{urllib.parse.quote(session_id)}",
        method="GET",
        headers={"X-API-Key": key},
    )
    return data.get("status") == "completed"


def _klarna(fields, **kw) -> dict[str, str]:
    cid = fields.get("client_id") or ""
    secret = fields.get("client_secret") or ""
    region = (fields.get("region") or "eu").lower()
    hosts = {
        "eu": "https://api.klarna.com",
        "na": "https://api-na.klarna.com",
        "oc": "https://api-oc.klarna.com",
    }
    host = hosts.get(region, hosts["eu"])
    if not fields.get("livemode"):
        host = host.replace("https://api", "https://api.playground")
        if "playground" not in host:
            host = {
                "eu": "https://api.playground.klarna.com",
                "na": "https://api-na.playground.klarna.com",
                "oc": "https://api-oc.playground.klarna.com",
            }.get(region, "https://api.playground.klarna.com")
    data = _http_json(
        f"{host}/hpp/v1/sessions",
        payload={
            "merchant_urls": {"success": kw["return_url"], "cancel": kw["cancel_url"], "back": kw["cancel_url"], "failure": kw["cancel_url"], "error": kw["cancel_url"]},
            "purchase_currency": kw["currency"],
            "order_amount": _cents(kw["amount"]),
            "order_tax_amount": 0,
            "order_lines": [{
                "type": "physical",
                "name": kw["description"] or kw["brand_name"],
                "quantity": 1,
                "unit_price": _cents(kw["amount"]),
                "total_amount": _cents(kw["amount"]),
            }],
        },
        headers={"Authorization": _basic(cid, secret)},
    )
    url = data.get("redirect_url")
    if not url:
        raise RuntimeError("Klarna did not return a hosted payment URL")
    return {"checkout_url": url, "session_id": data.get("session_id") or data.get("session_id", "")}


def _afterpay(fields, **kw) -> dict[str, str]:
    mid = fields.get("merchant_id") or ""
    secret = fields.get("secret_key") or ""
    host = "https://api.afterpay.com" if fields.get("livemode") else "https://api.us-sandbox.afterpay.com"
    data = _http_json(
        f"{host}/v2/checkouts",
        payload={
            "amount": {"amount": _money(kw["amount"]), "currency": kw["currency"]},
            "merchant": {
                "redirectConfirmUrl": kw["return_url"],
                "redirectCancelUrl": kw["cancel_url"],
            },
            "merchantReference": kw["reference"],
        },
        headers={"Authorization": _basic(mid, secret)},
    )
    url = data.get("redirectCheckoutUrl")
    if not url:
        raise RuntimeError("Afterpay did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("token", "")}


def _zip(fields, **kw) -> dict[str, str]:
    cid = fields.get("client_id") or ""
    secret = fields.get("client_secret") or ""
    host = "https://api.zip.co" if fields.get("livemode") else "https://api.sandbox.zip.co"
    data = _http_json(
        f"{host}/merchant/checkouts",
        payload={
            "shopper": {"email": kw["customer_email"] or f"checkout+{kw['reference']}@customer.local"},
            "order": {
                "reference": kw["reference"],
                "amount": float(_money(kw["amount"])),
                "currency": kw["currency"],
            },
            "config": {"redirect_uri": kw["return_url"]},
        },
        headers={"Authorization": _basic(cid, secret)},
    )
    url = data.get("uri") or (data.get("redirect_uri"))
    if not url:
        raise RuntimeError("Zip did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("id", "")}


def _eway(fields, **kw) -> dict[str, str]:
    key = fields.get("api_key") or ""
    password = fields.get("api_password") or ""
    host = "https://api.ewaypayments.com" if fields.get("livemode") else "https://api.sandbox.ewaypayments.com"
    data = _http_json(
        f"{host}/AccessCodesShared",
        payload={
            "Payment": {
                "TotalAmount": _cents(kw["amount"]),
                "InvoiceNumber": kw["reference"],
                "InvoiceDescription": kw["description"] or kw["brand_name"],
                "CurrencyCode": kw["currency"],
            },
            "RedirectUrl": kw["return_url"],
            "CancelUrl": kw["cancel_url"],
            "Method": "ProcessPayment",
            "TransactionType": "Purchase",
        },
        headers={"Authorization": _basic(key, password)},
    )
    url = data.get("SharedPaymentUrl")
    if not url:
        raise RuntimeError(data.get("Errors") or "eWAY did not return a payment URL")
    return {"checkout_url": url, "session_id": data.get("AccessCode", "")}


def _authorize_net(fields, **kw) -> dict[str, str]:
    login = fields.get("api_login_id") or ""
    tran = fields.get("transaction_key") or ""
    host = (
        "https://api.authorize.net/xml/v1/request.api"
        if fields.get("livemode")
        else "https://apitest.authorize.net/xml/v1/request.api"
    )
    data = _http_json(
        host,
        payload={
            "getHostedPaymentPageRequest": {
                "merchantAuthentication": {"name": login, "transactionKey": tran},
                "transactionRequest": {
                    "transactionType": "authCaptureTransaction",
                    "amount": _money(kw["amount"]),
                    "order": {"invoiceNumber": kw["reference"][:20]},
                },
                "hostedPaymentSettings": {
                    "setting": [
                        {"settingName": "hostedPaymentReturnOptions",
                         "settingValue": json.dumps({"url": kw["return_url"], "cancelUrl": kw["cancel_url"], "showReceipt": True})},
                    ]
                },
            }
        },
    )
    token = data.get("token")
    if not token:
        raise RuntimeError((data.get("messages") or {}).get("message") or "Authorize.net did not return a hosted page token")
    form_host = "https://accept.authorize.net/payment/payment" if fields.get("livemode") else "https://test.authorize.net/payment/payment"
    url = f"{form_host}?token={urllib.parse.quote(token)}"
    return {"checkout_url": url, "session_id": token[:40]}


def _braintree_client_token(fields: dict[str, Any]) -> str:
    merchant = fields.get("merchant_id") or ""
    public = fields.get("public_key") or ""
    private = fields.get("private_key") or fields.get("secret_key") or ""
    host = "https://payments.braintree-api.com" if fields.get("livemode") else "https://payments.sandbox.braintree-api.com"
    # GraphQL client token
    data = _http_json(
        f"{host}/graphql",
        payload={"query": "mutation { createClientToken { clientToken } }"},
        headers={
            "Authorization": _basic(public, private),
            "Braintree-Version": "2019-01-01",
        },
    )
    token = ((data.get("data") or {}).get("createClientToken") or {}).get("clientToken")
    if token:
        return token
    # REST fallback
    rest = "https://api.braintreegateway.com" if fields.get("livemode") else "https://api.sandbox.braintreegateway.com"
    data = _http_json(
        f"{rest}/merchants/{urllib.parse.quote(merchant)}/client_token",
        payload={},
        headers={"Authorization": _basic(public, private)},
    )
    token = (data.get("data") or {}).get("value") or data.get("clientToken") or data.get("client_token")
    if not token:
        raise RuntimeError("Braintree did not return a client token")
    return token


def _braintree(fields, **kw) -> dict[str, str]:
    token = _braintree_client_token(fields)
    pay_url = kw.get("pay_url") or kw["return_url"]
    sep = "&" if "?" in pay_url else "?"
    return {"checkout_url": f"{pay_url}{sep}bt=1", "session_id": token[:80]}


def _braintree_ok(fields, *, session_id, query) -> bool:
    return (query.get("bt_status") or "").lower() in ("settled", "submitted_for_settlement", "settling")


def _worldpay(fields, **kw) -> dict[str, str]:
    code = fields.get("merchant_code") or ""
    inst = fields.get("installation_id") or ""
    host = "https://secure.worldpay.com/wcc/purchase"
    params = {
        "instId": inst,
        "cartId": kw["reference"],
        "amount": _money(kw["amount"]),
        "currency": kw["currency"],
        "desc": kw["description"] or kw["brand_name"],
        "MC_callback": kw["return_url"],
    }
    if not fields.get("livemode"):
        params["testMode"] = "100"
    url = f"{host}?{urllib.parse.urlencode(params)}"
    return {"checkout_url": url, "session_id": kw["reference"]}


def _paypay_auth_headers(api_key: str, api_secret: str, path: str, body: bytes) -> dict[str, str]:
    epoch = str(int(time.time()))
    nonce = secrets.token_hex(8)
    content_type = "application/json;charset=UTF-8;"
    content_md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
    mac = "\n".join([api_key, path, content_type, epoch, content_md5, ""])
    signature = base64.b64encode(hmac.new(api_secret.encode(), mac.encode(), hashlib.sha256).digest()).decode()
    return {
        "Content-Type": content_type,
        "Authorization": f"hmac OPA-Auth:{api_key}:{signature}:{nonce}:{epoch}:{content_md5}",
    }


def _paypay(fields, **kw) -> dict[str, str]:
    merchant = fields.get("merchant_id") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    host = "https://api.paypay.ne.jp" if fields.get("livemode") else "https://stg-api.paypay.ne.jp"
    path = "/v2/codes"
    amount = kw["amount"]
    currency = kw["currency"] if kw["currency"] != "USD" else "JPY"
    payload = {
        "merchantPaymentId": kw["reference"][:64],
        "amount": {"amount": int(round(float(amount))) if currency == "JPY" else _cents(amount), "currency": currency},
        "codeType": "ORDER_QR",
        "orderDescription": kw["description"] or kw["brand_name"],
        "redirectUrl": kw["return_url"],
        "redirectType": "WEB_LINK",
        "requestedAt": int(time.time()),
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = _paypay_auth_headers(api_key, secret, path, body)
    if merchant:
        headers["X-ASSUME-MERCHANT"] = merchant
    data = _http_raw(f"{host}{path}", body, headers)
    inner = data.get("data") or data
    url = inner.get("url") or inner.get("deeplink")
    if not url:
        raise RuntimeError((data.get("resultInfo") or {}).get("message") or "PayPay did not return a payment URL")
    return {"checkout_url": url, "session_id": inner.get("codeId") or inner.get("merchantPaymentId") or kw["reference"]}


def _paypay_ok(fields, *, session_id, query) -> bool:
    merchant = fields.get("merchant_id") or ""
    api_key = fields.get("api_key") or ""
    secret = fields.get("api_secret") or ""
    host = "https://api.paypay.ne.jp" if fields.get("livemode") else "https://stg-api.paypay.ne.jp"
    path = f"/v2/codes/payments/{urllib.parse.quote(session_id)}"
    headers = _paypay_auth_headers(api_key, secret, path, b"")
    if merchant:
        headers["X-ASSUME-MERCHANT"] = merchant
    data = _http_json(f"{host}{path}", method="GET", headers=headers)
    status = ((data.get("data") or {}).get("status") or "").upper()
    return status in ("COMPLETED", "AUTHORIZED")


def _line_pay(fields, **kw) -> dict[str, str]:
    channel_id = fields.get("api_key") or fields.get("client_id") or fields.get("merchant_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    host = "https://api-pay.line.me" if fields.get("livemode") else "https://sandbox-api-pay.line.me"
    data = _http_json(
        f"{host}/v3/payments/request",
        payload={
            "amount": float(_money(kw["amount"])),
            "currency": kw["currency"],
            "orderId": kw["reference"],
            "packages": [{
                "id": kw["reference"][:50],
                "amount": float(_money(kw["amount"])),
                "products": [{"name": kw["description"] or kw["brand_name"], "quantity": 1, "price": float(_money(kw["amount"]))}],
            }],
            "redirectUrls": {"confirmUrl": kw["return_url"], "cancelUrl": kw["cancel_url"]},
        },
        headers={"X-LINE-ChannelId": channel_id, "X-LINE-ChannelSecret": secret},
    )
    info = (data.get("info") or {})
    url = (info.get("paymentUrl") or {}).get("web")
    if not url:
        raise RuntimeError(data.get("returnMessage") or "LINE Pay did not return a payment URL")
    return {"checkout_url": url, "session_id": info.get("transactionId") or kw["reference"]}


def _rakuten_pay(fields, **kw) -> dict[str, str]:
    merchant = fields.get("merchant_id") or ""
    key = fields.get("api_key") or fields.get("client_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    host = "https://api.checkout.rakuten.co.jp" if fields.get("livemode") else "https://api.checkout.rakuten.co.jp/sandbox"
    payload = {
        "serviceId": merchant,
        "itemId": kw["reference"][:40],
        "itemName": kw["description"] or kw["brand_name"],
        "amount": int(round(float(kw["amount"]))) if kw["currency"] == "JPY" else _cents(kw["amount"]),
        "currency": kw["currency"] if kw["currency"] != "USD" else "JPY",
        "successUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    data = _http_json(
        f"{host}/v1/payments",
        payload=payload,
        headers={"Authorization": _basic(key, secret), "X-Rakuten-Service-Id": merchant},
    )
    url = data.get("checkoutUrl") or data.get("redirectUrl") or data.get("paymentUrl")
    if not url:
        raise RuntimeError(data.get("message") or "Rakuten Pay did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("paymentId") or kw["reference"]}


def _grabpay(fields, **kw) -> dict[str, str]:
    partner = fields.get("merchant_id") or fields.get("client_id") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    host = "https://partner-api.grab.com" if fields.get("livemode") else "https://partner-api.stg-myteksi.com"
    token = _http_json(
        f"{host}/grabid/v1/oauth2/token",
        form={
            "client_id": api_key,
            "client_secret": secret,
            "grant_type": "client_credentials",
            "scope": "payment.one_time_charge",
        },
    )
    access = token.get("access_token")
    if not access:
        raise RuntimeError(token.get("error_description") or "GrabPay OAuth failed")
    path = "/grabpay/partner/v2/charge/init"
    payload = {
        "partnerGroupTxID": kw["reference"][:32],
        "partnerTxID": kw["reference"][:32],
        "currency": kw["currency"],
        "amount": _cents(kw["amount"]),
        "description": kw["description"] or kw["brand_name"],
        "merchantID": partner,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    content_digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
    string_to_sign = f"POST\napplication/json\n{date}\n{path}\n{content_digest}\n"
    signature = base64.b64encode(hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()).decode()
    data = _http_raw(
        f"{host}{path}",
        body,
        {
            "Content-Type": "application/json",
            "Date": date,
            "Authorization": f"Bearer {access}",
            "X-GID-AUX-POP": signature,
        },
    )
    url = data.get("request") or data.get("redirectURL") or data.get("checkoutURL")
    if not url and data.get("txID"):
        url = f"https://pay.grab.com/confirm?txID={urllib.parse.quote(data['txID'])}"
    if not url:
        raise RuntimeError(data.get("message") or "GrabPay did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("txID") or data.get("partnerTxID") or kw["reference"]}


def _shopeepay(fields, **kw) -> dict[str, str]:
    merchant = fields.get("merchant_id") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    host = "https://api.airpay.co.id" if fields.get("livemode") else "https://api.uat.airpay.co.id"
    payload = {
        "request_id": kw["reference"],
        "amount": _cents(kw["amount"]),
        "currency": kw["currency"],
        "merchant_ext_id": merchant,
        "return_url": kw["return_url"],
        "point_of_initiation": "app",
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    sign = hmac.new(secret.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    data = _http_raw(
        f"{host}/v3/merchant-host/order/create",
        body,
        {
            "Content-Type": "application/json",
            "X-Airpay-ClientId": api_key,
            "X-Airpay-Req-H": sign,
            "X-Timestamp": ts,
        },
    )
    url = (data.get("redirect_url_http") or data.get("redirect_url") or
           (data.get("data") or {}).get("redirect_url"))
    if not url:
        raise RuntimeError(data.get("message") or data.get("debug_msg") or "ShopeePay did not return a checkout URL")
    return {"checkout_url": url, "session_id": (data.get("data") or {}).get("order_sn") or kw["reference"]}


def _load_rsa_private(pem: str):
    from cryptography.hazmat.primitives import serialization

    raw = (pem or "").strip().replace("\\n", "\n")
    if not raw:
        raise RuntimeError("RSA private key is required")
    if "BEGIN" not in raw:
        raw = "-----BEGIN PRIVATE KEY-----\n" + raw + "\n-----END PRIVATE KEY-----"
    return serialization.load_pem_private_key(raw.encode(), password=None)


def _rsa2_sign(pem: str, content: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    key = _load_rsa_private(pem)
    sig = key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _alipay_hk(fields, **kw) -> dict[str, str]:
    app_id = fields.get("app_id") or fields.get("client_id") or fields.get("api_key") or ""
    private_key = fields.get("private_key") or fields.get("api_secret") or ""
    merchant = fields.get("merchant_id") or ""
    if not app_id or not private_key:
        raise RuntimeError("AlipayHK App ID and RSA private key are required")
    # Antom / Alipay+ cashier when the merchant was issued a Client-Id (not OpenAPI app_id).
    if fields.get("client_id") and not fields.get("app_id"):
        return _alipay_plus_cashier(fields, **kw)
    host = (
        fields.get("gateway")
        or ("https://openapi.alipay.hk/gateway.do" if fields.get("livemode") else "https://openapi-sandbox.dl.alipaydev.com/gateway.do")
    )
    biz = {
        "out_trade_no": kw["reference"][:64],
        "total_amount": _money(kw["amount"]),
        "subject": (kw["description"] or kw["brand_name"])[:256],
        "product_code": "QUICK_WAP_WAY",
    }
    if merchant:
        biz["seller_id"] = merchant
    params = {
        "app_id": app_id,
        "method": "alipay.trade.wap.pay",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "return_url": kw["return_url"],
        "notify_url": kw["return_url"],
        "biz_content": json.dumps(biz, separators=(",", ":"), ensure_ascii=False),
    }
    sign_content = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] != "")
    params["sign"] = _rsa2_sign(private_key, sign_content)
    return {"checkout_url": f"{host}?{urllib.parse.urlencode(params)}", "session_id": kw["reference"]}


def _alipay_plus_cashier(fields, **kw) -> dict[str, str]:
    client_id = fields.get("client_id") or fields.get("app_id") or ""
    private_key = fields.get("private_key") or fields.get("api_secret") or ""
    host = "https://open-sea-global.alipay.com" if fields.get("livemode") else "https://open-sea-global.alipay.com"
    uri = "/ams/api/v1/payments/pay"
    payload = {
        "productCode": "CASHIER_PAYMENT",
        "paymentRequestId": kw["reference"][:64],
        "paymentAmount": {"value": str(_cents(kw["amount"])), "currency": kw["currency"]},
        "order": {
            "orderDescription": kw["description"] or kw["brand_name"],
            "referenceOrderId": kw["reference"][:64],
        },
        "paymentRedirectUrl": kw["return_url"],
        "paymentNotifyUrl": kw["return_url"],
    }
    if fields.get("merchant_id"):
        payload["merchantAccountId"] = fields["merchant_id"]
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    request_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    content = f"POST {uri}\n{client_id}.{request_time}.{body}"
    signature = urllib.parse.quote(_rsa2_sign(private_key, content), safe="")
    data = _http_raw(
        f"{host}{uri}",
        body.encode(),
        {
            "Content-Type": "application/json; charset=UTF-8",
            "Client-Id": client_id,
            "Request-Time": request_time,
            "Signature": f"algorithm=RSA256,keyVersion=1,signature={signature}",
        },
    )
    url = (
        data.get("normalUrl")
        or (data.get("redirectActionForm") or {}).get("redirectUrl")
        or (data.get("paymentUrl") or {}).get("universalUrl")
    )
    if not url:
        raise RuntimeError((data.get("result") or {}).get("resultMessage") or "AlipayHK did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("paymentId") or kw["reference"]}


def _alipay_hk_ok(fields, *, session_id, query) -> bool:
    if (query.get("trade_status") or "").upper() in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return True
    app_id = fields.get("app_id") or fields.get("client_id") or ""
    private_key = fields.get("private_key") or fields.get("api_secret") or ""
    if not app_id or not private_key or fields.get("client_id") and not fields.get("app_id"):
        return False
    host = (
        fields.get("gateway")
        or ("https://openapi.alipay.hk/gateway.do" if fields.get("livemode") else "https://openapi-sandbox.dl.alipaydev.com/gateway.do")
    )
    params = {
        "app_id": app_id,
        "method": "alipay.trade.query",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "biz_content": json.dumps({"out_trade_no": session_id}, separators=(",", ":")),
    }
    sign_content = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] != "")
    params["sign"] = _rsa2_sign(private_key, sign_content)
    data = _http_json(f"{host}?{urllib.parse.urlencode(params)}", method="GET")
    inner = data.get("alipay_trade_query_response") or data
    return (inner.get("trade_status") or "").upper() in ("TRADE_SUCCESS", "TRADE_FINISHED")


def _wechat_auth_header(fields: dict[str, Any], method: str, path: str, body: str) -> dict[str, str]:
    mchid = fields.get("merchant_id") or fields.get("mchid") or ""
    serial = fields.get("serial_no") or ""
    private_key = fields.get("private_key") or ""
    if not mchid or not serial or not private_key:
        raise RuntimeError("WeChat Pay HK requires merchant ID, certificate serial, and private key")
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    message = f"{method}\n{path}\n{ts}\n{nonce}\n{body}\n"
    signature = _rsa2_sign(private_key, message)
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{mchid}",nonce_str="{nonce}",'
            f'timestamp="{ts}",serial_no="{serial}",signature="{signature}"'
        ),
    }


def _wechat_pay_hk(fields, **kw) -> dict[str, str]:
    mchid = fields.get("merchant_id") or fields.get("mchid") or ""
    appid = fields.get("appid") or fields.get("app_id") or fields.get("client_id") or ""
    if not appid:
        raise RuntimeError("WeChat Pay HK AppID is required")
    host = "https://apihk.mch.weixin.qq.com"
    path = "/v3/global/transactions/mweb"
    payload = {
        "appid": appid,
        "mchid": mchid,
        "description": (kw["description"] or kw["brand_name"])[:127],
        "out_trade_no": kw["reference"][:32],
        "notify_url": kw["return_url"],
        "trade_type": "MWEB",
        "amount": {"total": _cents(kw["amount"]), "currency": kw["currency"]},
        "scene_info": {"payer_client_ip": "127.0.0.1"},
    }
    if fields.get("merchant_category_code"):
        payload["merchant_category_code"] = fields["merchant_category_code"]
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    data = _http_raw(f"{host}{path}", body.encode(), _wechat_auth_header(fields, "POST", path, body))
    url = data.get("mweb_url") or data.get("h5_url") or data.get("code_url")
    if url and kw.get("return_url"):
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}redirect_url={urllib.parse.quote(kw['return_url'], safe='')}"
    if not url:
        raise RuntimeError(data.get("message") or data.get("code") or "WeChat Pay HK did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("prepay_id") or kw["reference"]}


def _wechat_pay_hk_ok(fields, *, session_id, query) -> bool:
    if (query.get("trade_state") or "").upper() == "SUCCESS":
        return True
    host = "https://apihk.mch.weixin.qq.com"
    path = f"/v3/global/transactions/out-trade-no/{urllib.parse.quote(session_id)}"
    data = _http_json(f"{host}{path}", method="GET", headers=_wechat_auth_header(fields, "GET", path, ""))
    return (data.get("trade_state") or "").upper() == "SUCCESS"


def _payme_sign(fields: dict[str, Any], method: str, path: str, date: str, digest: str) -> str:
    signing_key = (fields.get("signing_key") or fields.get("api_secret") or "").strip().replace("\\n", "\n")
    signing_string = f"(request-target): {method.lower()} {path}\ndate: {date}\ndigest: {digest}"
    if "BEGIN" in signing_key:
        return _rsa2_sign(signing_key, signing_string)
    raw = signing_key.encode()
    try:
        raw = base64.b64decode(signing_key)
    except Exception:
        _log.debug("checkout_signing_key_b64_decode_failed", exc_info=True, extra={"op": "_signing_key_raw"})
        raw = signing_key.encode()
    return base64.b64encode(hmac.new(raw, signing_string.encode(), hashlib.sha256).digest()).decode()


def _payme(fields, **kw) -> dict[str, str]:
    client_id = fields.get("client_id") or fields.get("api_key") or ""
    secret = fields.get("client_secret") or fields.get("api_secret") or ""
    key_id = fields.get("signing_key_id") or ""
    if not client_id or not secret or not key_id or not (fields.get("signing_key") or ""):
        raise RuntimeError("PayMe Client ID, Secret, Signing Key ID, and Signing Key are required")
    host = "https://api.payme.hsbc.com.hk" if fields.get("livemode") else "https://sandbox.api.payme.hsbc.com.hk"
    token = _http_json(
        f"{host}/oauth2/token",
        form={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret},
    )
    access = token.get("accessToken") or token.get("access_token")
    if not access:
        raise RuntimeError(token.get("error_description") or token.get("message") or "PayMe OAuth failed")
    path = "/payments/paymentrequests"
    payload = {
        "totalAmount": _cents(kw["amount"]),
        "currencyCode": kw["currency"] if kw["currency"] != "USD" else "HKD",
        "notificationUri": kw["return_url"],
        "appSuccessCallback": kw["return_url"],
        "appFailCallback": kw["cancel_url"],
        "merchantData": kw["reference"][:128],
    }
    if fields.get("merchant_id"):
        payload["merchantId"] = fields["merchant_id"]
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    digest = "SHA-256=" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    signature = _payme_sign(fields, "POST", path, date, digest)
    data = _http_raw(
        f"{host}{path}",
        body.encode(),
        {
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Date": date,
            "Digest": digest,
            "Signature": (
                f'keyId="{key_id}",algorithm="hs2019",'
                f'headers="(request-target) date digest",signature="{signature}"'
            ),
        },
    )
    url = data.get("webLink") or data.get("webUrl") or data.get("paymentUrl") or (data.get("links") or {}).get("web")
    if not url:
        raise RuntimeError(data.get("message") or data.get("error") or "PayMe did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("paymentRequestId") or data.get("id") or kw["reference"]}


def _payme_ok(fields, *, session_id, query) -> bool:
    status = (query.get("status") or query.get("paymentRequestStatus") or "").upper()
    if status in ("PR005", "COMPLETED", "SUCCESS", "PAID"):
        return True
    client_id = fields.get("client_id") or ""
    secret = fields.get("client_secret") or ""
    host = "https://api.payme.hsbc.com.hk" if fields.get("livemode") else "https://sandbox.api.payme.hsbc.com.hk"
    token = _http_json(
        f"{host}/oauth2/token",
        form={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret},
    )
    access = token.get("accessToken") or token.get("access_token")
    if not access:
        return False
    path = f"/payments/paymentrequests/{urllib.parse.quote(session_id)}"
    data = _http_json(f"{host}{path}", method="GET", headers={"Authorization": f"Bearer {access}"})
    return (data.get("status") or data.get("paymentRequestStatus") or "").upper() in (
        "PR005", "COMPLETED", "SUCCESS", "PAID",
    )


def _unionpay(fields, **kw) -> dict[str, str]:
    mer_id = fields.get("merchant_id") or ""
    cert_id = fields.get("cert_id") or fields.get("api_key") or ""
    private_key = fields.get("private_key") or fields.get("api_secret") or ""
    if not mer_id or not cert_id or not private_key:
        raise RuntimeError("UnionPay merId, certId, and private key are required")
    host = (
        "https://gateway.95516.com/gateway/api/frontTransReq.do"
        if fields.get("livemode")
        else "https://gateway.test.95516.com/gateway/api/frontTransReq.do"
    )
    currency_map = {"HKD": "344", "TWD": "901", "MOP": "446", "CNY": "156", "USD": "840", "JPY": "392"}
    params = {
        "version": "5.1.0",
        "encoding": "UTF-8",
        "signMethod": "01",
        "txnType": "01",
        "txnSubType": "01",
        "bizType": "000201",
        "channelType": "08",
        "accessType": "0",
        "merId": mer_id,
        "orderId": kw["reference"][:32],
        "txnTime": time.strftime("%Y%m%d%H%M%S"),
        "txnAmt": str(_cents(kw["amount"])),
        "currencyCode": currency_map.get(kw["currency"], "344"),
        "frontUrl": kw["return_url"],
        "backUrl": kw["return_url"],
        "certId": cert_id,
    }
    sign_content = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] != "")
    params["signature"] = _rsa2_sign(private_key, sign_content)
    return {"checkout_url": f"{host}?{urllib.parse.urlencode(params)}", "session_id": kw["reference"]}


def _jkopay(fields, **kw) -> dict[str, str]:
    store = fields.get("merchant_id") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or ""
    if not store or not api_key:
        raise RuntimeError("JKOPAY Store ID and API Key are required")
    host = "https://onlinepay.jkopay.com/platform/entry" if fields.get("livemode") else "https://uat-onlinepay.jkopay.com/platform/entry"
    order_id = kw["reference"][:40]
    total = str(int(round(float(kw["amount"])))) if kw["currency"] in ("TWD", "JPY") else str(_cents(kw["amount"]))
    nonce = secrets.token_hex(8)
    ts = str(int(time.time()))
    sign = hashlib.sha256(f"{store}{api_key}{nonce}{ts}{order_id}{total}".encode()).hexdigest()
    params = {
        "store": store,
        "order_id": order_id,
        "total": total,
        "result_url": kw["return_url"],
        "result_display_url": kw["return_url"],
        "nonce": nonce,
        "ts": ts,
        "sign": sign,
    }
    return {"checkout_url": f"{host}?{urllib.parse.urlencode(params)}", "session_id": order_id}


def _easy_wallet(fields, **kw) -> dict[str, str]:
    merchant = fields.get("merchant_id") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    if not merchant or not api_key or not secret:
        raise RuntimeError("Easy Wallet merchant ID, API key, and secret are required")
    host = "https://api.easycard.com.tw" if fields.get("livemode") else "https://uat-api.easycard.com.tw"
    payload = {
        "merchantId": merchant,
        "orderNo": kw["reference"][:40],
        "amount": int(round(float(kw["amount"]))) if kw["currency"] in ("TWD", "JPY") else _cents(kw["amount"]),
        "currency": kw["currency"] if kw["currency"] != "USD" else "TWD",
        "orderDesc": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    ts = str(int(time.time()))
    sign = hmac.new(secret.encode(), f"{api_key}.{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    data = _http_raw(
        f"{host}/ewallet/v1/orders",
        body,
        {
            "Content-Type": "application/json",
            "X-EasyCard-Key": api_key,
            "X-EasyCard-Timestamp": ts,
            "X-EasyCard-Signature": sign,
        },
    )
    url = data.get("paymentUrl") or data.get("checkoutUrl") or (data.get("data") or {}).get("paymentUrl")
    if not url:
        raise RuntimeError(data.get("message") or data.get("error") or "Easy Wallet did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("orderNo") or kw["reference"]}


def _mpay(fields, **kw) -> dict[str, str]:
    merchant = fields.get("merchant_id") or ""
    api_key = fields.get("api_key") or fields.get("client_id") or ""
    secret = fields.get("api_secret") or fields.get("client_secret") or ""
    if not merchant or not api_key or not secret:
        raise RuntimeError("MPay merchant ID, API key, and secret are required")
    host = "https://api.mpay.com.mo" if fields.get("livemode") else "https://uat-api.mpay.com.mo"
    payload = {
        "merchantId": merchant,
        "orderId": kw["reference"][:40],
        "amount": _cents(kw["amount"]),
        "currency": kw["currency"] if kw["currency"] != "USD" else "MOP",
        "description": kw["description"] or kw["brand_name"],
        "returnUrl": kw["return_url"],
        "cancelUrl": kw["cancel_url"],
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    ts = str(int(time.time()))
    sign = hmac.new(secret.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    data = _http_raw(
        f"{host}/online/v1/orders",
        body,
        {
            "Content-Type": "application/json",
            "X-MPay-Key": api_key,
            "X-MPay-Timestamp": ts,
            "X-MPay-Signature": sign,
        },
    )
    url = data.get("paymentUrl") or data.get("checkoutUrl") or (data.get("data") or {}).get("paymentUrl")
    if not url:
        raise RuntimeError(data.get("message") or data.get("error") or "MPay did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("orderId") or kw["reference"]}


_CREATORS = {
    "square": _square,
    "mollie": _mollie,
    "paystack": _paystack,
    "flutterwave": _flutterwave,
    "razorpay": _razorpay,
    "xendit": _xendit,
    "omise": _omise,
    "midtrans": _midtrans,
    "mercado_pago": _mercado_pago,
    "yookassa": _yookassa,
    "sumup": _sumup,
    "gocardless": _gocardless,
    "adyen": _adyen,
    "klarna": _klarna,
    "afterpay": _afterpay,
    "zip": _zip,
    "eway": _eway,
    "authorize_net": _authorize_net,
    "braintree": _braintree,
    "worldpay": _worldpay,
    "paypay": _paypay,
    "line_pay": _line_pay,
    "rakuten_pay": _rakuten_pay,
    "grabpay": _grabpay,
    "shopeepay": _shopeepay,
    "alipay_hk": _alipay_hk,
    "wechat_pay_hk": _wechat_pay_hk,
    "payme": _payme,
    "unionpay": _unionpay,
    "jkopay": _jkopay,
    "easy_wallet": _easy_wallet,
    "mpay": _mpay,
}

from payment_apac_adapters import APAC_CREATORS, APAC_VERIFIERS

_CREATORS.update(APAC_CREATORS)

_VERIFIERS = {
    "mollie": _mollie_ok,
    "paystack": _paystack_ok,
    "flutterwave": _flutterwave_ok,
    "razorpay": _razorpay_ok,
    "xendit": _xendit_ok,
    "omise": _omise_ok,
    "midtrans": _midtrans_ok,
    "mercado_pago": _mercado_ok,
    "yookassa": _yookassa_ok,
    "sumup": _sumup_ok,
    "adyen": _adyen_ok,
    "paypay": _paypay_ok,
    "braintree": _braintree_ok,
    "alipay_hk": _alipay_hk_ok,
    "wechat_pay_hk": _wechat_pay_hk_ok,
    "payme": _payme_ok,
}

_VERIFIERS.update(APAC_VERIFIERS)

from payment_registry_adapters import build_registry_extensions

_registry_c, _registry_v = build_registry_extensions(_CREATORS, _VERIFIERS)
_CREATORS.update(_registry_c)
_VERIFIERS.update(_registry_v)

from integration_catalog import payment_plugin_slugs
from payment_registry_adapters import _hosted_ok

for slug in payment_plugin_slugs():
    if slug in ("stripe", "paypal"):
        continue
    if slug in _CREATORS and slug not in _VERIFIERS:
        _VERIFIERS[slug] = _hosted_ok
