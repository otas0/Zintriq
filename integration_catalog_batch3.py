"""Batch-3 payment plugins — wallet rails & regional SMB gateways."""

from __future__ import annotations

from typing import Any

_CRED_MERCHANT = [
    {"key": "merchant_id", "label": "Merchant ID", "required": True},
    {"key": "api_key", "label": "API Key", "required": True},
    {"key": "api_secret", "label": "API Secret", "type": "password", "required": True},
]

_SECURITY = [
    "Store API keys only in this encrypted vault — never in email, chat, or public repos.",
    "Use sandbox / test keys first; switch to live keys only after owner verification is complete.",
    "Restrict API keys to the minimum scopes (payments only).",
    "Rotate keys if a staff member with access leaves the business.",
]


def _pay_steps(name: str) -> list[str]:
    return [
        f"Open the official {name} merchant portal (link below) and apply as a business owner — not a personal account.",
        "Complete KYC / business verification required for live checkout.",
        "In the merchant or developer console, create API credentials with payment-only scopes.",
        "Copy Merchant ID, API Key, and API Secret (field names may differ by provider).",
        *_SECURITY,
        "Paste credentials below → Save & verify. Checkout charges your merchant account.",
    ]


def _wallet_steps(name: str, gateway: str) -> list[str]:
    return [
        f"Enable {name} in your {gateway} merchant dashboard (wallet rail is activated there).",
        f"Copy the same API credentials you use for {gateway} — Merchant ID + API keys.",
        *_SECURITY,
        f"Paste credentials below → Save & verify. Checkout presents {name} via {gateway}.",
    ]


EXTRA_PAYMENT_PLUGINS: tuple[dict[str, Any], ...] = (
    {
        "slug": "apple_pay",
        "name": "Apple Pay",
        "provider": "apple",
        "description": "Apple Pay wallet checkout — enable via Stripe, Adyen, or your acquirer",
        "regions": ("global", "us", "eu", "uk", "au", "jp", "hk", "tw", "sea"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "secret_key", "label": "Gateway secret key (Stripe sk_…)", "type": "password", "required": True},
            {"key": "merchant_id", "label": "Merchant / account ID (optional for Stripe)"},
        ],
        "setup_guide": {
            "summary": "Enable Apple Pay on your payment gateway, then paste the gateway API secret used for wallet checkout.",
            "steps": _wallet_steps("Apple Pay", "Stripe or Adyen"),
            "links": [
                {"label": "Apple Pay — merchant setup", "url": "https://developer.apple.com/apple-pay/"},
                {"label": "Stripe — Apple Pay", "url": "https://stripe.com/docs/apple-pay"},
                {"label": "Adyen — Apple Pay", "url": "https://docs.adyen.com/payment-methods/apple-pay/"},
            ],
        },
    },
    {
        "slug": "google_pay",
        "name": "Google Pay",
        "provider": "google",
        "description": "Google Pay wallet checkout — enable via Stripe, Adyen, or your acquirer",
        "regions": ("global", "us", "eu", "uk", "au", "jp", "hk", "tw", "sea"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "secret_key", "label": "Gateway secret key (Stripe sk_…)", "type": "password", "required": True},
            {"key": "merchant_id", "label": "Google Pay merchant ID (from gateway console)"},
        ],
        "setup_guide": {
            "summary": "Enable Google Pay on your payment gateway, then paste the gateway API secret used for wallet checkout.",
            "steps": _wallet_steps("Google Pay", "Stripe or Adyen"),
            "links": [
                {"label": "Google Pay — web integration", "url": "https://developers.google.com/pay/api"},
                {"label": "Stripe — Google Pay", "url": "https://stripe.com/docs/google-pay"},
                {"label": "Adyen — Google Pay", "url": "https://docs.adyen.com/payment-methods/google-pay/"},
            ],
        },
    },
    {
        "slug": "nets",
        "name": "NETS",
        "provider": "nets",
        "description": "Singapore NETS — debit / QR online checkout",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Apply as a NETS merchant, then paste Terminal / API credentials from the NETS merchant portal.",
            "steps": _pay_steps("NETS"),
            "links": [
                {"label": "NETS — merchant services", "url": "https://www.nets.com.sg/merchants/ec/en.html"},
                {"label": "NETS merchant login", "url": "https://www.nets.com.sg/merchants/login"},
            ],
        },
    },
    {
        "slug": "paylah",
        "name": "PayLah!",
        "provider": "dbs",
        "description": "DBS PayLah! — Singapore mobile wallet for businesses",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Register for DBS PayLah! for Business, then copy merchant API credentials.",
            "steps": _pay_steps("PayLah!"),
            "links": [
                {"label": "DBS PayLah! for Business", "url": "https://www.dbs.com.sg/personal/deposits/pay-with-ease/dbs-paylah"},
                {"label": "PayLah! merchant support", "url": "https://www.dbs.com.sg/personal/support/bank-paylah"},
            ],
        },
    },
    {
        "slug": "hitpay",
        "name": "HitPay",
        "provider": "hitpay",
        "description": "HitPay — Singapore SMB payment links & QR checkout",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Create a HitPay business account, then copy API keys from Settings → API keys.",
            "steps": _pay_steps("HitPay"),
            "links": [
                {"label": "HitPay — sign up", "url": "https://hitpayapp.com/"},
                {"label": "HitPay API documentation", "url": "https://docs.hitpayapp.com/"},
            ],
        },
    },
    {
        "slug": "red_dot_payment",
        "name": "Red Dot Payment",
        "provider": "reddot",
        "description": "Red Dot Payment — Singapore online payment gateway for SMBs",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Apply as a Red Dot merchant, then copy MID and API credentials from the merchant portal.",
            "steps": _pay_steps("Red Dot Payment"),
            "links": [
                {"label": "Red Dot — merchant signup", "url": "https://reddotpayment.com/"},
                {"label": "Red Dot merchant portal", "url": "https://reddotpayment.com/"},
            ],
        },
    },
    {
        "slug": "ipay88",
        "name": "iPay88",
        "provider": "ipay88",
        "description": "iPay88 — Malaysia payment gateway (cards, FPX, e-wallets)",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Register as an iPay88 merchant, then copy Merchant Code and API keys from the merchant panel.",
            "steps": _pay_steps("iPay88"),
            "links": [
                {"label": "iPay88 — merchant registration", "url": "https://www.ipay88.com/"},
                {"label": "iPay88 merchant login", "url": "https://payment.ipay88.com.my/"},
            ],
        },
    },
    {
        "slug": "revenue_monster",
        "name": "Revenue Monster",
        "provider": "revenue_monster",
        "description": "Revenue Monster — Malaysia QR & e-wallet payment platform",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Sign up as a Revenue Monster merchant, then copy Store ID and API credentials.",
            "steps": _pay_steps("Revenue Monster"),
            "links": [
                {"label": "Revenue Monster — merchant", "url": "https://revenuemonster.my/"},
                {"label": "Revenue Monster developer docs", "url": "https://doc.revenuemonster.my/"},
            ],
        },
    },
    {
        "slug": "curlec",
        "name": "Curlec",
        "provider": "curlec",
        "description": "Curlec (Razorpay Malaysia) — FPX, cards & recurring payments",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Create a Curlec merchant account, then copy Key ID and Key Secret from the dashboard.",
            "steps": _pay_steps("Curlec"),
            "links": [
                {"label": "Curlec — get started", "url": "https://curlec.com/"},
                {"label": "Curlec API documentation", "url": "https://curlec.com/docs/"},
            ],
        },
    },
    {
        "slug": "senangpay",
        "name": "SenangPay",
        "provider": "senangpay",
        "description": "SenangPay — Malaysia payment gateway for online businesses",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Register on SenangPay, then copy Merchant ID and Secret Key from the dashboard.",
            "steps": _pay_steps("SenangPay"),
            "links": [
                {"label": "SenangPay — register", "url": "https://senangpay.my/"},
                {"label": "SenangPay merchant login", "url": "https://app.senangpay.my/"},
            ],
        },
    },
    {
        "slug": "shop_pay",
        "name": "Shop Pay",
        "provider": "shopify",
        "description": "Shop Pay — Shopify accelerated checkout for your store",
        "regions": ("global", "us", "eu", "uk", "au"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "shop_domain", "label": "Shopify store domain", "placeholder": "your-store.myshopify.com", "required": True},
            {"key": "api_key", "label": "Admin API access token", "type": "password", "required": True},
            {"key": "api_secret", "label": "API secret key (optional)", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Enable Shop Pay on your Shopify store, then paste the Admin API access token.",
            "steps": [
                "Log in to Shopify admin as the store owner.",
                "Settings → Apps and sales channels → Develop apps → Create an app.",
                "Configure Admin API scopes: read_checkouts, write_checkouts, read_payment_gateways.",
                "Install the app and reveal the Admin API access token once — copy it immediately.",
                *_SECURITY,
                "Paste store domain and access token below → Save & verify.",
            ],
            "links": [
                {"label": "Shop Pay — merchant", "url": "https://www.shopify.com/shop-pay"},
                {"label": "Shopify — custom app setup", "url": "https://www.shopify.com/payments"},
            ],
        },
    },
    {
        "slug": "zelle",
        "name": "Zelle",
        "provider": "zelle",
        "description": "Zelle — US bank-to-bank transfers (limited merchant API; via bank / gateway)",
        "regions": ("us",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Zelle business token / merchant ID", "required": True},
            {"key": "api_key", "label": "Bank or gateway API key", "required": True},
            {"key": "api_secret", "label": "API secret", "type": "password", "required": True},
            {"key": "gateway_base", "label": "Bank / gateway API base URL (from your acquirer)"},
        ],
        "setup_guide": {
            "summary": "Enroll in Zelle for business through your US bank or payment gateway, then paste integration credentials.",
            "steps": [
                "Contact your US bank or payment processor about Zelle for business / Zelle merchant tokens.",
                "Complete business enrollment — Zelle has no standalone public merchant API like card gateways.",
                "Obtain the merchant token and bank/gateway API credentials from your acquirer console.",
                *_SECURITY,
                "Paste credentials below → Save & verify. Checkout redirects via your bank integration.",
            ],
            "links": [
                {"label": "Zelle — for your business", "url": "https://www.zellepay.com/get-started"},
                {"label": "Early Warning — Zelle business", "url": "https://www.zellepay.com/get-started"},
            ],
        },
    },
    {
        "slug": "interac_e_transfer",
        "name": "Interac e-Transfer",
        "provider": "interac",
        "description": "Canada Interac e-Transfer — Request Money & business Autodeposit via bank or gateway",
        "regions": ("ca",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "deposit_email", "label": "Business Autodeposit email", "required": True},
            {"key": "merchant_id", "label": "Gateway merchant ID", "required": True},
            {"key": "api_key", "label": "Gateway API key", "required": True},
            {"key": "api_secret", "label": "Gateway API secret", "type": "password", "required": True},
            {"key": "gateway_base", "label": "Gateway API base URL (Moneris, Helcim, etc.)"},
        ],
        "setup_guide": {
            "summary": "Enroll in Interac e-Transfer for Business via your bank or gateway, then paste Autodeposit email and gateway credentials.",
            "steps": [
                "Register for Interac e-Transfer for Business with your Canadian bank or payment gateway (Moneris, Helcim, Square CA, etc.).",
                "Set up business Autodeposit and note the deposit email customers will send to.",
                "In your gateway console, enable e-Transfer Request Money / online e-Transfer and create API credentials.",
                "Interac does not offer a standalone public merchant checkout API — integration always goes through your bank or gateway.",
                *_SECURITY,
                "Paste Autodeposit email and gateway credentials below → Save & verify.",
            ],
            "links": [
                {"label": "Interac e-Transfer for Business", "url": "https://www.interac.ca/en/business/"},
                {"label": "Interac — Request Money", "url": "https://www.interac.ca/en/business/"},
                {"label": "Moneris merchant", "url": "https://www.moneris.com/"},
                {"label": "Helcim — Canadian payments", "url": "https://www.interac.ca/en/business/"},
            ],
        },
    },
)

EXTRA_PLUGIN_BRANDS: dict[str, dict[str, str]] = {
    "apple_pay": {"domain": "apple.com"},
    "google_pay": {"domain": "google.com"},
    "nets": {"domain": "nets.com.sg"},
    "paylah": {"domain": "dbs.com.sg"},
    "hitpay": {"domain": "hitpayapp.com"},
    "red_dot_payment": {"domain": "reddotpayment.com"},
    "ipay88": {"domain": "ipay88.com"},
    "revenue_monster": {"domain": "revenuemonster.my"},
    "curlec": {"domain": "curlec.com"},
    "senangpay": {"domain": "senangpay.my"},
    "shop_pay": {"domain": "shopify.com"},
    "zelle": {"domain": "zellepay.com"},
    "interac_e_transfer": {"domain": "interac.ca"},
}

EXTRA_BRAND_COLORS: dict[str, str] = {
    "apple_pay": "000000",
    "google_pay": "4285F4",
    "nets": "ED1C24",
    "paylah": "C41230",
    "hitpay": "0066FF",
    "red_dot_payment": "E31837",
    "ipay88": "005BAC",
    "revenue_monster": "00A651",
    "curlec": "072654",
    "senangpay": "FF6600",
    "shop_pay": "5A31F4",
    "zelle": "6D1ED4",
    "interac_e_transfer": "FFCC00",
}

EXTRA_BRAND_INITIALS: dict[str, str] = {
    "apple_pay": "",
    "google_pay": "G",
    "nets": "N",
    "paylah": "PL",
    "hitpay": "H",
    "red_dot_payment": "RD",
    "ipay88": "88",
    "revenue_monster": "RM",
    "curlec": "C",
    "senangpay": "SP",
    "shop_pay": "SP",
    "zelle": "Z",
    "interac_e_transfer": "eT",
}

BATCH3_SIMPLE_ICONS: dict[str, str] = {
    "apple_pay": "applepay",
    "google_pay": "googlepay",
    "shop_pay": "shopify",
    "ipay88": "ipay88",
}
