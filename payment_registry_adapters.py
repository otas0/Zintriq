"""Checkout adapters for batch-2 and remaining payment plugins."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.parse
from typing import Callable

from payment_apac_adapters import (
    _bank_hosted,
    _hmac_post,
    _pick_url,
    _require,
    _signed_wallet_order,
)
from payment_checkout_adapters import (
    _basic,
    _cents,
    _http_json,
    _http_raw,
    _money,
)


def _hosted_ok(fields, *, session_id, query) -> bool:
    status = (query.get("status") or query.get("payment_status") or query.get("respCode") or "").lower()
    if status in (
        "paid", "success", "successful", "completed", "approved", "captured",
        "0000", "payment_success", "succeeded", "authorized", "settled",
    ):
        return True
    if query.get("checkout_token") or query.get("token") or query.get("PayerID"):
        return True
    return bool(query.get("reference") and status not in ("failed", "cancelled", "canceled", "declined"))


def _wallet(host_live: str, host_sandbox: str, *, path: str = "/online/v1/orders", key_header: str = "X-Api-Key") -> Callable:
    def fn(fields, **kw):
        merchant, api_key, secret = _signed_wallet_order(fields, **kw)
        _require((merchant, "Merchant ID"), (api_key, "API key"), (secret, "API secret"))
        host = host_live if fields.get("livemode") else host_sandbox
        payload = {
            "merchantId": merchant,
            "orderId": kw["reference"][:40],
            "amount": _cents(kw["amount"]),
            "currency": kw["currency"],
            "description": kw["description"] or kw["brand_name"],
            "returnUrl": kw["return_url"],
            "cancelUrl": kw["cancel_url"],
        }
        data = _hmac_post(f"{host.rstrip('/')}{path}", payload, secret, key_header, api_key)
        url = _pick_url(data, "checkoutUrl", "paymentUrl", "redirectUrl", "webPaymentUrl", "authorization_url")
        if not url:
            raise RuntimeError(data.get("message") or data.get("error") or "Provider did not return a checkout URL")
        return {"checkout_url": url, "session_id": data.get("orderId") or data.get("id") or kw["reference"]}

    return fn


def _invoice_basic(host_live: str, host_sandbox: str, *, path: str = "/v2/invoices") -> Callable:
    def fn(fields, **kw):
        key = fields.get("api_key") or fields.get("secret_key") or ""
        secret = fields.get("api_secret") or fields.get("client_secret") or ""
        auth = _basic(key, secret) if secret else f"Bearer {key}"
        host = host_live if fields.get("livemode") else host_sandbox
        data = _http_json(
            f"{host.rstrip('/')}{path}",
            payload={
                "external_id": kw["reference"],
                "amount": float(_money(kw["amount"])),
                "currency": kw["currency"],
                "description": kw["description"] or kw["brand_name"],
                "success_redirect_url": kw["return_url"],
                "failure_redirect_url": kw["cancel_url"],
            },
            headers={"Authorization": auth},
        )
        url = _pick_url(data, "invoice_url", "checkout_url", "payment_url", "short_url")
        if not url:
            raise RuntimeError(data.get("message") or "Provider did not return a checkout URL")
        return {"checkout_url": url, "session_id": data.get("id") or kw["reference"]}

    return fn


def _phonepe(fields, **kw) -> dict[str, str]:
    mid = fields.get("merchant_id") or ""
    salt = fields.get("api_secret") or fields.get("salt_key") or ""
    key = fields.get("api_key") or fields.get("salt_index") or "1"
    _require((mid, "PhonePe Merchant ID"), (salt, "PhonePe salt key"))
    host = "https://api.phonepe.com/apis/hermes" if fields.get("livemode") else "https://api-preprod.phonepe.com/apis/hermes"
    payload = {
        "merchantId": mid,
        "merchantTransactionId": kw["reference"][:40],
        "merchantUserId": kw["customer_email"] or f"guest-{kw['reference'][:12]}",
        "amount": _cents(kw["amount"]) * 100,
        "redirectUrl": kw["return_url"],
        "redirectMode": "GET",
        "paymentInstrument": {"type": "PAY_PAGE"},
    }
    body = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    path = f"/pg/v1/pay/{body}"
    checksum = hashlib.sha256(f"{path}{salt}".encode()).hexdigest() + "###" + str(key)
    data = _http_json(
        f"{host}/pg/v1/pay",
        payload={"request": body},
        headers={"X-VERIFY": checksum, "Content-Type": "application/json"},
    )
    inner = data.get("data") or {}
    url = _pick_url(data, "url", "redirectUrl") or _pick_url(inner, "url", "redirectUrl")
    instr = inner.get("instrumentResponse") if isinstance(inner, dict) else None
    if isinstance(instr, dict):
        url = url or instr.get("redirectInfo", {}).get("url") or instr.get("url")
    if not url:
        raise RuntimeError(data.get("message") or "PhonePe did not return a checkout URL")
    return {"checkout_url": url, "session_id": kw["reference"]}


def _paytm(fields, **kw) -> dict[str, str]:
    mid = fields.get("merchant_id") or ""
    key = fields.get("merchant_key") or fields.get("api_key") or ""
    _require((mid, "Paytm Merchant ID"), (key, "Paytm merchant key"))
    host = "https://securegw.paytm.in" if fields.get("livemode") else "https://securegw-stage.paytm.in"
    order_id = kw["reference"][:40]
    body = {
        "requestType": "Payment",
        "mid": mid,
        "websiteName": "DEFAULT",
        "orderId": order_id,
        "callbackUrl": kw["return_url"],
        "txnAmount": {"value": _money(kw["amount"]), "currency": kw["currency"]},
        "userInfo": {"custId": kw["customer_email"] or order_id},
    }
    checksum = base64.b64encode(
        hmac.new(key.encode(), json.dumps(body, separators=(",", ":")).encode(), hashlib.sha256).digest()
    ).decode()
    data = _http_json(
        f"{host}/theia/api/v1/initiateTransaction?mid={urllib.parse.quote(mid)}&orderId={urllib.parse.quote(order_id)}",
        payload={"head": {"signature": checksum}, "body": body},
    )
    inner = data.get("body") or {}
    if inner.get("resultInfo", {}).get("resultStatus") != "S":
        raise RuntimeError(inner.get("resultInfo", {}).get("resultMsg") or "Paytm initiate failed")
    url = f"{host}/theia/processTransaction?orderId={urllib.parse.quote(order_id)}"
    return {"checkout_url": url, "session_id": order_id}


def _cashfree(fields, **kw) -> dict[str, str]:
    app_id = fields.get("app_id") or fields.get("client_id") or fields.get("api_key") or ""
    secret = fields.get("secret_key") or fields.get("api_secret") or ""
    _require((app_id, "Cashfree App ID"), (secret, "Cashfree secret key"))
    host = "https://api.cashfree.com/pg" if fields.get("livemode") else "https://sandbox.cashfree.com/pg"
    data = _http_json(
        f"{host}/orders",
        payload={
            "order_id": kw["reference"][:40],
            "order_amount": float(_money(kw["amount"])),
            "order_currency": kw["currency"],
            "customer_details": {
                "customer_id": kw["customer_email"] or kw["reference"][:20],
                "customer_email": kw["customer_email"] or f"checkout+{kw['reference']}@customer.local",
            },
            "order_meta": {"return_url": kw["return_url"]},
        },
        headers={"x-client-id": app_id, "x-client-secret": secret, "x-api-version": "2023-08-01"},
    )
    url = _pick_url(data, "payment_link", "payment_url")
    if not url and data.get("payment_session_id"):
        url = f"{host}/checkout/{data['payment_session_id']}"
    if not url:
        raise RuntimeError(data.get("message") or "Cashfree did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("order_id") or kw["reference"]}


def _paymongo(fields, **kw) -> dict[str, str]:
    key = fields.get("secret_key") or fields.get("api_key") or ""
    _require((key, "PayMongo secret key"))
    host = "https://api.paymongo.com"
    data = _http_json(
        f"{host}/v1/checkout_sessions",
        payload={
            "data": {
                "attributes": {
                    "line_items": [{
                        "amount": _cents(kw["amount"]),
                        "currency": kw["currency"].upper(),
                        "name": (kw["description"] or kw["brand_name"])[:80],
                        "quantity": 1,
                    }],
                    "payment_method_types": ["card", "gcash", "grab_pay", "paymaya"],
                    "success_url": kw["return_url"],
                    "cancel_url": kw["cancel_url"],
                    "description": kw["reference"],
                }
            }
        },
        headers={"Authorization": _basic(key, ""), "Content-Type": "application/json"},
    )
    attrs = (data.get("data") or {}).get("attributes") or {}
    url = attrs.get("checkout_url") or attrs.get("redirect_url")
    if not url:
        raise RuntimeError("PayMongo did not return a checkout URL")
    return {"checkout_url": url, "session_id": (data.get("data") or {}).get("id") or kw["reference"]}


def _revolut(fields, **kw) -> dict[str, str]:
    key = fields.get("secret_key") or fields.get("api_key") or ""
    _require((key, "Revolut Merchant API secret"))
    host = "https://merchant.revolut.com/api" if fields.get("livemode") else "https://sandbox-merchant.revolut.com/api"
    data = _http_json(
        f"{host}/orders",
        payload={
            "amount": _cents(kw["amount"]),
            "currency": kw["currency"],
            "description": kw["description"] or kw["brand_name"],
            "merchant_order_ext_ref": kw["reference"][:40],
            "customer_email": kw["customer_email"] or None,
            "redirect_url": kw["return_url"],
        },
        headers={"Authorization": f"Bearer {key}", "Revolut-Api-Version": "2023-09-01"},
    )
    url = _pick_url(data, "checkout_url", "payment_url")
    if not url and data.get("token"):
        url = f"https://checkout.revolut.com/payment-link/{data['token']}"
    if not url:
        raise RuntimeError(data.get("message") or "Revolut did not return a checkout URL")
    return {"checkout_url": url, "session_id": data.get("id") or kw["reference"]}


def _billplz(fields, **kw) -> dict[str, str]:
    key = fields.get("api_key") or ""
    secret = fields.get("api_secret") or ""
    coll = fields.get("collection_id") or fields.get("merchant_id") or key
    _require((coll, "Billplz collection ID"))
    host = "https://www.billplz.com/api/v3" if fields.get("livemode") else "https://www.billplz-sandbox.com/api/v3"
    data = _http_json(
        f"{host}/bills",
        form={
            "collection_id": coll,
            "description": kw["description"] or kw["brand_name"],
            "email": kw["customer_email"] or f"checkout+{kw['reference']}@customer.local",
            "name": kw["brand_name"][:80],
            "amount": str(_cents(kw["amount"])),
            "callback_url": kw["return_url"],
            "redirect_url": kw["return_url"],
            "reference_1_label": "Order",
            "reference_1": kw["reference"][:40],
        },
        headers={"Authorization": _basic(key, secret or "")},
    )
    url = data.get("url")
    if not url:
        raise RuntimeError(data.get("error") or "Billplz did not return a bill URL")
    return {"checkout_url": url, "session_id": data.get("id") or kw["reference"]}


def _payu(fields, **kw) -> dict[str, str]:
    key = fields.get("api_key") or fields.get("merchant_key") or ""
    salt = fields.get("api_secret") or fields.get("salt") or ""
    mid = fields.get("merchant_id") or ""
    _require((key, "PayU merchant key"), (salt, "PayU salt"), (mid, "PayU merchant ID"))
    host = "https://secure.payu.in" if fields.get("livemode") else "https://test.payu.in"
    if kw["currency"] not in ("INR", "USD") and fields.get("payu_host"):
        host = fields["payu_host"]
    txnid = kw["reference"][:25]
    amount = _money(kw["amount"])
    product = (kw["description"] or kw["brand_name"])[:100]
    email = kw["customer_email"] or f"checkout+{txnid}@customer.local"
    hash_val = hashlib.sha512(f"{key}|{txnid}|{amount}|{product}|{mid}|{email}|||||||||||{salt}".encode()).hexdigest()
    query = urllib.parse.urlencode({
        "key": key, "txnid": txnid, "amount": amount, "productinfo": product,
        "firstname": "Customer", "email": email, "phone": "9999999999",
        "surl": kw["return_url"], "furl": kw["cancel_url"], "hash": hash_val,
    })
    return {"checkout_url": f"{host.rstrip('/')}/_payment?{query}", "session_id": txnid}


def _scheme_bank(scheme: str, fallback: str) -> Callable:
    def fn(fields, **kw):
        extra = dict(fields)
        if not extra.get("gateway_base"):
            extra["gateway_base"] = fallback
        return _bank_hosted({**extra, "_scheme": scheme}, **kw)

    return fn


def _midtrans_wallet(enabled: str) -> Callable:
    def fn(fields, **kw):
        from payment_checkout_adapters import _midtrans
        return _midtrans({**fields, "enabled_payments": enabled}, **kw)

    return fn


def _stripe_wallet(fields, **kw) -> dict[str, str]:
    """Apple Pay / Google Pay via Stripe Checkout (wallets show when enabled on the Stripe account)."""
    key = fields.get("secret_key") or fields.get("api_key") or ""
    _require((key, "Stripe secret key"))
    body = urllib.parse.urlencode({
        "mode": "payment",
        "success_url": kw["return_url"],
        "cancel_url": kw["cancel_url"],
        "line_items[0][price_data][currency]": kw["currency"].lower(),
        "line_items[0][price_data][product_data][name]": (kw["description"] or kw["brand_name"])[:120],
        "line_items[0][price_data][unit_amount]": str(_cents(kw["amount"])),
        "line_items[0][quantity]": "1",
        "metadata[reference]": kw["reference"][:40],
    }).encode()
    data = _http_raw(
        "https://api.stripe.com/v1/checkout/sessions",
        body,
        {"Authorization": f"Bearer {key}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    url = data.get("url") or ""
    sid = data.get("id") or kw["reference"]
    if not url:
        err = data.get("error") or {}
        raise RuntimeError(err.get("message") if isinstance(err, dict) else data.get("message") or "Stripe did not return a checkout URL")
    return {"checkout_url": url, "session_id": sid}


_WALLET_HOSTS: dict[str, tuple[str, str]] = {
    "macau_pass": ("https://api.macau-pass.com", "https://sandbox.macau-pass.com"),
    "bnu_pay": ("https://api.bnucard.com", "https://sandbox.bnucard.com"),
    "boc_pay": ("https://api.bochk.com", "https://sandbox.bochk.com"),
    "icash_pay": ("https://api.icashpay.com.tw", "https://sandbox.icashpay.com.tw"),
    "pi_wallet": ("https://api.piwallet.com.tw", "https://sandbox.piwallet.com.tw"),
    "pxpay_plus": ("https://api.pxpayplus.com", "https://sandbox.pxpayplus.com"),
    "favepay": ("https://api.favepay.com", "https://sandbox.favepay.com"),
    "boost": ("https://api.myboost.com.my", "https://sandbox.myboost.com.my"),
    "dana": ("https://api.dana.id", "https://api-sandbox.dana.id"),
    "linkaja": ("https://api.linkaja.id", "https://sandbox.linkaja.id"),
    "coins_ph": ("https://api.coins.ph", "https://sandbox.coins.ph"),
    "dragonpay": ("https://gw.dragonpay.net", "https://test.dragonpay.net"),
    "rabbit_line_pay": ("https://api.rabbit.co.th", "https://sandbox.rabbit.co.th"),
    "scb_easy": ("https://api.scb.co.th", "https://sandbox.scb.co.th"),
    "viettel_money": ("https://api.viettelmoney.vn", "https://sandbox.viettelmoney.vn"),
    "vnpay": ("https://vnpayment.vn", "https://sandbox.vnpayment.vn"),
    "bakong": ("https://api.bakong.nbc.gov.kh", "https://sandbox.bakong.nbc.gov.kh"),
    "wave_money": ("https://api.wavemoney.com.mm", "https://sandbox.wavemoney.com.mm"),
    "paidy": ("https://api.paidy.com", "https://api-sandbox.paidy.com"),
    "payco": ("https://api.payco.com", "https://sandbox.payco.com"),
    "smilepay": ("https://api.mysmilepay.com", "https://sandbox.mysmilepay.com"),
    "samsung_pay": ("https://api.samsung.com/pay", "https://sandbox-api.samsung.com/pay"),
    "ccavenue": ("https://secure.ccavenue.com", "https://test.ccavenue.com"),
    "instamojo": ("https://api.instamojo.com", "https://test.instamojo.com"),
    "pine_labs": ("https://api.pinelabs.com", "https://sandbox.pinelabs.com"),
    "bkash": ("https://tokenized.pay.bka.sh", "https://tokenized.sandbox.bka.sh"),
    "khalti": ("https://a.khalti.com", "https://dev.khalti.com"),
    "esewa": ("https://epay.esewa.com.np", "https://rc.esewa.com.np"),
    "poli": ("https://api.polipayments.com", "https://sandbox.polipayments.com"),
    "payto": ("https://api.auspayplus.com.au", "https://sandbox.auspayplus.com.au"),
    "windcave": ("https://sec.windcave.com", "https://uat.windcave.com"),
    "cash_app_pay": ("https://api.cash.app", "https://sandbox.api.cash.app"),
    "clover": ("https://api.clover.com", "https://sandbox.dev.clover.com"),
    "toast": ("https://ws-api.toasttab.com", "https://ws-sandbox-api.toasttab.com"),
    "lightspeed": ("https://api.lightspeedhq.com", "https://api.trial.lightspeedhq.com"),
    "fiserv": ("https://api.fiserv.com", "https://sandbox.api.fiserv.com"),
    "moneris": ("https://api.moneris.com", "https://sandbox.moneris.com"),
    "interac": ("https://api.interac.ca", "https://sandbox.interac.ca"),
    "pagarme": ("https://api.pagar.me", "https://api.pagar.me"),
    "pagseguro": ("https://api.pagseguro.com", "https://sandbox.api.pagseguro.com"),
    "dlocal": ("https://api.dlocal.com", "https://sandbox.dlocal.com"),
    "ebanx": ("https://api.ebanx.com", "https://sandbox.ebanx.com"),
    "conekta": ("https://api.conekta.io", "https://api.conekta.io"),
    "openpay": ("https://api.openpay.mx", "https://sandbox-api.openpay.mx"),
    "kushki": ("https://api.kushkipagos.com", "https://api-uat.kushkipagos.com"),
    "chipper_cash": ("https://api.chippercash.com", "https://sandbox.chippercash.com"),
    "mpesa": ("https://api.safaricom.co.ke", "https://sandbox.safaricom.co.ke"),
    "payfast": ("https://api.payfast.co.za", "https://sandbox.payfast.co.za"),
    "peach_payments": ("https://api.peachpayments.com", "https://sandbox.peachpayments.com"),
    "hyperpay": ("https://eu-prod.oppwa.com", "https://eu-test.oppwa.com"),
    "tap_payments": ("https://api.tap.company", "https://api.tap.company"),
    "paytabs": ("https://secure.paytabs.com", "https://secure-egypt.paytabs.com"),
    "network_international": ("https://api.network.ae", "https://api-sandbox.network.ae"),
    "fawry": ("https://api.fawry.com", "https://staging.fawry.com"),
    "wise": ("https://api.wise.com", "https://api.sandbox.transferwise.com"),
    "payoneer": ("https://api.payoneer.com", "https://api.sandbox.payoneer.com"),
    "bluesnap": ("https://ws.bluesnap.com", "https://sandbox.bluesnap.com"),
    "paddle": ("https://api.paddle.com", "https://sandbox-api.paddle.com"),
    "fastspring": ("https://api.fastspring.com", "https://sandbox-api.fastspring.com"),
    "twocheckout": ("https://api.2checkout.com", "https://api.2checkout.com"),
    "cybersource": ("https://api.cybersource.com", "https://apitest.cybersource.com"),
    "global_payments": ("https://api.globalpay.com", "https://apis.sandbox.globalpay.com"),
    "nuvei": ("https://secure.safecharge.com", "https://ppp-test.safecharge.com"),
    "paysafe": ("https://api.paysafe.com", "https://api.test.paysafe.com"),
    "worldline": ("https://api.worldline.com", "https://api-sandbox.worldline.com"),
    "sezzle": ("https://gateway.sezzle.com", "https://sandbox.gateway.sezzle.com"),
    "splitit": ("https://api.splitit.com", "https://sandbox.splitit.com"),
    "tabby": ("https://api.tabby.ai", "https://api.tabby.ai"),
    "tamara": ("https://api.tamara.co", "https://api-sandbox.tamara.co"),
    "scalapay": ("https://api.scalapay.com", "https://integration.api.scalapay.com"),
    "trustly": ("https://api.trustly.com", "https://test.trustly.com"),
    "przelewy24": ("https://secure.przelewy24.pl", "https://sandbox.przelewy24.pl"),
    "blik": ("https://api.blik.com", "https://sandbox.blik.com"),
    "mb_way": ("https://api.mbway.pt", "https://sandbox.mbway.pt"),
    "bizum": ("https://api.bizum.es", "https://sandbox.bizum.es"),
    "satispay": ("https://api.satispay.com", "https://staging-api.satispay.com"),
    "payconiq": ("https://api.payconiq.com", "https://api.payconiq.com"),
    "twint": ("https://api.twint.ch", "https://api.twint.ch"),
    "vipps": ("https://api.vipps.no", "https://apitest.vipps.no"),
    "swish": ("https://api.swish.nu", "https://sandbox.swish.nu"),
    "shopify_payments": ("https://api.shopify.com", "https://api.shopify.com"),
    "nets": ("https://api.nets.com.sg", "https://sandbox.nets.com.sg"),
    "paylah": ("https://api.dbs.com.sg", "https://sandbox-api.dbs.com.sg"),
    "hitpay": ("https://api.hit-pay.com", "https://sandbox.hit-pay.com"),
    "red_dot_payment": ("https://api.reddotpayment.com", "https://sandbox.reddotpayment.com"),
    "ipay88": ("https://payment.ipay88.com.my", "https://sandbox.ipay88.com.my"),
    "revenue_monster": ("https://api.revenuemonster.my", "https://sandbox.revenuemonster.my"),
    "curlec": ("https://api.curlec.com", "https://sandbox.curlec.com"),
    "senangpay": ("https://app.senangpay.my", "https://sandbox.senangpay.my"),
}

_ALIASES: dict[str, str] = {
    "clearpay": "afterpay",
    "venmo": "braintree",
    "hoolah": "atome",
    "grab_paylater": "grabpay",
    "sofort": "klarna",
    "line_pay_tw": "line_pay",
    "tap_and_go": "octopus",
    "becs_direct_debit": "gocardless",
    "ideal": "mollie",
    "bancontact": "mollie",
    "giropay": "mollie",
    "eps": "mollie",
    "ovo": "midtrans_ovo",
    "gopay": "midtrans_gopay",
    "qris": "midtrans_qris",
    "shop_pay": "shopify_payments",
    "interac": "moneris",
}

_MOLLIE_ALIASES = {"ideal", "bancontact", "giropay", "eps", "sofort"}


def build_registry_extensions(
    base_creators: dict[str, Callable],
    base_verifiers: dict[str, Callable],
) -> tuple[dict[str, Callable], dict[str, Callable]]:
    from payment_checkout_adapters import _midtrans_ok, _mollie_ok, _xendit_ok

    creators: dict[str, Callable] = {}
    verifiers: dict[str, Callable] = {}
    all_creators = {**base_creators, **creators}

    def alias(target: str) -> Callable:
        def fn(fields, **kw):
            creator = all_creators.get(target) or creators.get(target)
            if not creator:
                raise RuntimeError(f"Checkout adapter {target} is not configured")
            return creator(fields, **kw)

        return fn

    midtrans_map = {
        "midtrans_ovo": _midtrans_wallet("ovo"),
        "midtrans_gopay": _midtrans_wallet("gopay"),
        "midtrans_qris": _midtrans_wallet("qris"),
    }
    for key, fn in midtrans_map.items():
        creators[key] = fn
        verifiers[key] = _midtrans_ok

    specials = {
        "phonepe": _phonepe,
        "paytm": _paytm,
        "cashfree": _cashfree,
        "paymongo": _paymongo,
        "revolut": _revolut,
        "billplz": _billplz,
        "payu_india": _payu,
        "payu_europe": _payu,
        "payu_latam": _payu,
        "paynow": _scheme_bank("paynow", "https://api.paynow.abs.org.sg"),
        "vietqr": _scheme_bank("vietqr", "https://api.napas.com.vn"),
        "lankaqr": _scheme_bank("lankaqr", "https://api.lankapay.net.lk"),
        "zelle": _scheme_bank("zelle", "https://api.zellepay.com"),
        "interac_e_transfer": _scheme_bank("interac_e_transfer", "https://gateway.moneris.com"),
        "apple_pay": _stripe_wallet,
        "google_pay": _stripe_wallet,
    }
    for slug, fn in specials.items():
        creators[slug] = fn
        verifiers[slug] = _hosted_ok

    for slug, target in _ALIASES.items():
        if target.startswith("midtrans_"):
            creators[slug] = alias(target)
            verifiers[slug] = _midtrans_ok
        else:
            creators[slug] = alias(target)
            verifiers[slug] = base_verifiers.get(target, _mollie_ok if target == "mollie" else _hosted_ok)
        all_creators[slug] = creators[slug]

    for slug, (live, sandbox) in _WALLET_HOSTS.items():
        if slug in creators:
            continue
        creators[slug] = _wallet(live, sandbox)
        verifiers[slug] = _hosted_ok

    from integration_catalog import payment_plugin_slugs

    for slug in payment_plugin_slugs():
        if slug in ("stripe", "paypal"):
            continue
        if slug in base_creators or slug in creators:
            continue
        live, sandbox = _WALLET_HOSTS.get(slug, ("https://api.xendit.co", "https://api.xendit.co"))
        creators[slug] = _invoice_basic(live, sandbox)
        verifiers[slug] = _xendit_ok if "xendit" in live else _hosted_ok

    for slug in _MOLLIE_ALIASES:
        if slug in verifiers:
            verifiers[slug] = _mollie_ok

    return creators, verifiers
