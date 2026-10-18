"""Integration catalog — regional payment & review plugins with merchant setup guides."""

from __future__ import annotations

from typing import Any

# Not offered in these markets (merchant-facing note).
EXCLUDED_TERRITORIES = (
    "restricted territories",
)

REGION_LABELS: dict[str, str] = {
    "global": "Global",
    "cn": "China Mainland",
    "jp": "Japan",
    "kr": "Korea",
    "hk": "Hong Kong",
    "tw": "Taiwan",
    "mo": "Macau",
    "eu": "Europe",
    "us": "Americas",
    "ca": "Canada",
    "uk": "United Kingdom",
    "sea": "Southeast Asia",
    "au": "Australia & NZ",
    "af": "Africa",
    "ru": "Russia",
    "latam": "Latin America",
}

PRIMARY_REGIONS = ("global", "cn", "jp", "kr", "hk", "tw", "mo", "sea", "eu", "us", "ca", "uk", "au")

# Official brand sites — used for real color logos (local file, then Simple Icons / DuckDuckGo favicon).
PLUGIN_BRANDS: dict[str, dict[str, str]] = {
    "stripe": {"domain": "stripe.com"},
    "paypal": {"domain": "paypal.com"},
    "paypay": {"domain": "paypay.ne.jp"},
    "square": {"domain": "squareup.com"},
    "adyen": {"domain": "adyen.com"},
    "mollie": {"domain": "mollie.com"},
    "klarna": {"domain": "klarna.com"},
    "line_pay": {"domain": "line.me"},
    "rakuten_pay": {"domain": "rakuten.co.jp"},
    "grabpay": {"domain": "grab.com"},
    "shopeepay": {"domain": "shopee.com"},
    "xendit": {"domain": "xendit.co"},
    "omise": {"domain": "omise.co"},
    "midtrans": {"domain": "midtrans.com"},
    "gocardless": {"domain": "gocardless.com"},
    "sumup": {"domain": "sumup.com"},
    "worldpay": {"domain": "worldpay.com"},
    "authorize_net": {"domain": "authorize.net"},
    "braintree": {"domain": "braintreepayments.com"},
    "afterpay": {"domain": "afterpay.com"},
    "zip": {"domain": "zip.co"},
    "eway": {"domain": "eway.com.au"},
    "paystack": {"domain": "paystack.com"},
    "flutterwave": {"domain": "flutterwave.com"},
    "mercado_pago": {"domain": "mercadopago.com"},
    "yookassa": {"domain": "yookassa.ru"},
    "razorpay": {"domain": "razorpay.com"},
    "alipay_hk": {"domain": "alipay.com"},
    "wechat_pay_hk": {"domain": "pay.weixin.qq.com"},
    "payme": {"domain": "payme.hsbc.com.hk"},
    "unionpay": {"domain": "unionpayintl.com"},
    "jkopay": {"domain": "jkopay.com"},
    "easy_wallet": {"domain": "easycard.com.tw"},
    "mpay": {"domain": "mpay.com.mo"},
    "atome": {"domain": "atome.sg"},
    "twoc2p": {"domain": "2c2p.com"},
    "airwallex": {"domain": "airwallex.com"},
    "checkout_com": {"domain": "checkout.com"},
    "octopus": {"domain": "octopus.com.hk"},
    "fps": {"domain": "fps.hkicl.com.hk"},
    "gcash": {"domain": "gcash.com"},
    "maya": {"domain": "maya.ph"},
    "touch_n_go": {"domain": "touchngo.com.my"},
    "duitnow": {"domain": "duitnow.my"},
    "promptpay": {"domain": "promptpay.co.th"},
    "truemoney": {"domain": "truemoney.com"},
    "momo": {"domain": "momo.vn"},
    "zalopay": {"domain": "zalopay.vn"},
    "kakao_pay": {"domain": "kakaopay.com"},
    "toss": {"domain": "tosspayments.com"},
    "naver_pay": {"domain": "pay.naver.com"},
    "au_pay": {"domain": "aupay.wallet.auone.jp"},
    "d_barai": {"domain": "nttdocomo.co.jp"},
    "merpay": {"domain": "merpay.com"},
    "affirm": {"domain": "affirm.com"},
    "amazon_pay": {"domain": "pay.amazon.com"},
    "yelp": {"domain": "yelp.com"},
    "thefork": {"domain": "thefork.com"},
    "resy": {"domain": "resy.com"},
    "chope": {"domain": "chope.co"},
    "keeta": {"domain": "keeta-global.com"},
    "hungrypanda": {"domain": "hungrypanda.co"},
    "klook": {"domain": "klook.com"},
    "kkday": {"domain": "kkday.com"},
    "expedia": {"domain": "expedia.com"},
    "trip_com": {"domain": "trip.com"},
    "g2": {"domain": "g2.com"},
    "reviews_io": {"domain": "reviews.io"},
    "feefo": {"domain": "feefo.com"},
    "trusted_shops": {"domain": "trustedshops.com"},
    "tripadvisor": {"domain": "tripadvisor.com"},
    "tablelog": {"domain": "tabelog.com"},
    "opentable": {"domain": "opentable.com"},
    "trustpilot": {"domain": "trustpilot.com"},
    "gurunavi": {"domain": "gurunavi.com"},
    "hot_pepper": {"domain": "hotpepper.jp"},
    "booking_com": {"domain": "booking.com"},
    "agoda": {"domain": "agoda.com"},
    "uber_eats": {"domain": "ubereats.com"},
    "deliveroo": {"domain": "deliveroo.com"},
    "foursquare": {"domain": "foursquare.com"},
    "facebook_reviews": {"domain": "facebook.com"},
    "zomato": {"domain": "zomato.com"},
    "grab_reviews": {"domain": "grab.com"},
    "holidaycheck": {"domain": "holidaycheck.de"},
    "capterra": {"domain": "capterra.com"},
    "openrice": {"domain": "openrice.com"},
    "foodpanda_reviews": {"domain": "foodpanda.com"},
}

DEFAULT_LOGO_PATH = "/static/integrations/plugin-default.svg"

BRAND_COLORS: dict[str, str] = {
    "stripe": "635BFF", "paypal": "003087", "paypay": "FF0033", "square": "006AFF",
    "adyen": "0ABF53", "mollie": "000000", "klarna": "FFB3C7", "line_pay": "00C300",
    "rakuten_pay": "BF0000", "grabpay": "00B14F", "shopeepay": "EE4D2D", "xendit": "4573FF",
    "omise": "1A56DB", "midtrans": "002855", "gocardless": "161B21", "sumup": "000000",
    "worldpay": "E31C3D", "authorize_net": "1A3C6E", "braintree": "000000", "afterpay": "B2FCE4",
    "zip": "000000", "eway": "8DC63F", "paystack": "00C3F7", "flutterwave": "F5A623",
    "mercado_pago": "00B1EA", "yookassa": "8B3DFF", "razorpay": "072654",
    "alipay_hk": "1677FF", "wechat_pay_hk": "07C160", "payme": "E21B23",
    "unionpay": "E21836", "jkopay": "EF7F1A", "easy_wallet": "00A651",
    "mpay": "E31C3D",
    "atome": "F7C948", "twoc2p": "00A3E0", "airwallex": "612FFF", "checkout_com": "1A1A1A",
    "octopus": "F68B1F", "fps": "E60012", "gcash": "007DFF", "maya": "00D66F",
    "touch_n_go": "0056A6", "duitnow": "ED1C24", "promptpay": "1B4F9C", "truemoney": "F47321",
    "momo": "A50064", "zalopay": "0068FF", "kakao_pay": "FFEB00", "toss": "3182F6",
    "naver_pay": "03C75A", "au_pay": "EB5505", "d_barai": "CC0033", "merpay": "FF0211",
    "affirm": "0FA0EA", "amazon_pay": "FF9900",
    "yelp": "FF1A1A",
    "thefork": "548E3F", "resy": "E23744", "chope": "E31C23",
    "keeta": "FF6A00", "hungrypanda": "FF5A00", "klook": "FF5722", "kkday": "00B2A9",
    "expedia": "191E3B", "trip_com": "287DFA", "g2": "FF492C", "reviews_io": "23B574",
    "feefo": "00A0D2", "trusted_shops": "FFD200", "tripadvisor": "34E0A1", "tablelog": "FF6600", "opentable": "DA3743",
    "trustpilot": "00B67A", "gurunavi": "E60012", "hot_pepper": "E83929", "booking_com": "003580",
    "agoda": "E12B4A", "uber_eats": "06C167", "deliveroo": "00CCBC", "foursquare": "F94877",
    "facebook_reviews": "0866FF", "zomato": "E23744", "grab_reviews": "00B14F",
    "holidaycheck": "FF6600", "capterra": "FF9D28",
    "openrice": "E31C23", "foodpanda_reviews": "D70F64",
}

BRAND_INITIALS: dict[str, str] = {
    "stripe": "S", "paypal": "P", "paypay": "P", "square": "□", "adyen": "A",
    "mollie": "m", "klarna": "K", "line_pay": "L", "rakuten_pay": "R", "grabpay": "G",
    "shopeepay": "S", "xendit": "X", "omise": "O", "midtrans": "M", "gocardless": "GC",
    "sumup": "+", "worldpay": "W", "authorize_net": "A", "braintree": "B", "afterpay": "A",
    "zip": "Z", "eway": "e", "paystack": "P", "flutterwave": "F", "mercado_pago": "MP",
    "yookassa": "Y", "razorpay": "R", "yelp": "y", "tripadvisor": "T", "tablelog": "食",
    "opentable": "OT", "trustpilot": "★", "gurunavi": "ぐ", "hot_pepper": "HP",
    "booking_com": "B", "agoda": "A", "uber_eats": "UE", "deliveroo": "D",
    "foursquare": "4", "facebook_reviews": "f", "zomato": "Z", "grab_reviews": "G",
    "holidaycheck": "HC", "capterra": "C",
    "alipay_hk": "支", "wechat_pay_hk": "微", "payme": "PM", "unionpay": "UP",
    "jkopay": "街", "easy_wallet": "悠", "mpay": "M",
    "openrice": "OR", "foodpanda_reviews": "FP",
    "atome": "A", "twoc2p": "2C", "airwallex": "AW", "checkout_com": "CK",
    "octopus": "八", "fps": "FPS", "gcash": "G", "maya": "M",
    "touch_n_go": "TnG", "duitnow": "DN", "promptpay": "PP", "truemoney": "TM",
    "momo": "Mo", "zalopay": "Z", "kakao_pay": "K", "toss": "T",
    "naver_pay": "N", "au_pay": "au", "d_barai": "d", "merpay": "め",
    "affirm": "Af", "amazon_pay": "a",
    "thefork": "TF", "resy": "R", "chope": "C",
    "keeta": "K", "hungrypanda": "HP", "klook": "K", "kkday": "KK",
    "expedia": "E", "trip_com": "T", "g2": "G2", "reviews_io": "R",
    "feefo": "F", "trusted_shops": "TS", }


def _logo_svg(slug: str) -> str:
    color = BRAND_COLORS.get(slug, "67748E")
    initial = BRAND_INITIALS.get(slug) or slug[:2].upper()
    ink = "111111" if color.lower() in ("b2fce4", "ffb3c7", "00c3f7", "34e0a1") else "FFFFFF"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
        f'<rect width="64" height="64" rx="14" fill="#{color}"/>'
        f'<text x="32" y="40" text-anchor="middle" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="{18 if len(initial) > 1 else 26}" font-weight="700" fill="#{ink}">{initial}</text>'
        f"</svg>"
    )


def ensure_plugin_logos() -> None:
    from pathlib import Path

    folder = Path(__file__).resolve().parent / "static" / "integrations" / "logos"
    folder.mkdir(parents=True, exist_ok=True)
    slugs = [
        p["slug"]
        for p in list(PAYMENT_PLUGINS) + list(REPUTATION_PLUGINS)
        if p["slug"] not in REMOVED_CATALOG_SLUGS
    ]
    for slug in slugs:
        path = folder / f"{slug}.svg"
        if path.is_file():
            raw = path.read_text(encoding="utf-8", errors="ignore")
            if "official-brand" in raw or path.stat().st_size >= 200:
                continue
        path.write_text(_logo_svg(slug), encoding="utf-8")


def plugin_logo_url(slug: str) -> str:
    from pathlib import Path

    ensure_plugin_logos()
    local = Path(__file__).resolve().parent / "static" / "integrations" / "logos" / f"{slug}.svg"
    if local.is_file():
        return f"/static/integrations/logos/{slug}.svg?v=20260821c"
    return DEFAULT_LOGO_PATH

_CRED_API = [
    {"key": "api_key", "label": "API Key", "required": True},
    {"key": "api_secret", "label": "API Secret", "type": "password", "required": True},
]
_CRED_CLIENT = [
    {"key": "client_id", "label": "Client ID", "required": True},
    {"key": "client_secret", "label": "Client Secret", "type": "password", "required": True},
]
_CRED_MERCHANT = [
    {"key": "merchant_id", "label": "Merchant ID", "required": True},
    {"key": "api_key", "label": "API Key", "required": True},
    {"key": "api_secret", "label": "API Secret", "type": "password", "required": True},
]
_CRED_REVIEW = [
    {"key": "business_id", "label": "Business / listing ID", "required": True},
    {"key": "api_key", "label": "API Key (if required)", "type": "password"},
]

PAYMENT_PLUGINS: tuple[dict[str, Any], ...] = (
    {
        "slug": "stripe",
        "name": "Stripe",
        "provider": "stripe",
        "description": "Cards and Apple Pay — worldwide (except restricted regions)",
        "regions": ("global", "us", "eu", "uk", "au", "jp", "hk", "tw", "sea", "latam", "af"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "secret_key", "label": "Secret key", "type": "password", "placeholder": "sk_test_… or sk_live_…", "required": True},
            {"key": "publishable_key", "label": "Publishable key (optional)", "placeholder": "pk_test_…"},
        ],
        "setup_guide": {
            "summary": "Open a Stripe merchant account, copy the Secret key from the Dashboard, then paste it here. Checkout charges go to your Stripe balance.",
            "steps": [
                "Create a merchant account at the Stripe Dashboard (business owner, 18+).",
                "Complete identity / business verification so live charges can settle.",
                "In the Dashboard: Developers → API keys. Keep Test mode off.",
                "Reveal the Secret key (starts with sk_live_) and copy it. Publishable key (pk_live_) is optional.",
                "Paste the Secret key below → Save & verify. Checkout charges your real Stripe account.",
            ],
            "links": [
                {"label": "Stripe merchant signup", "url": "https://dashboard.stripe.com/register"},
                {"label": "Stripe Dashboard — API keys", "url": "https://dashboard.stripe.com/apikeys"},
            ],
        },
    },
    {
        "slug": "paypal",
        "name": "PayPal",
        "provider": "paypal",
        "description": "PayPal wallet & cards — Americas, Europe, UK, Australia, Japan, SEA, HK/TW/MO",
        "regions": ("global", "us", "eu", "uk", "au", "jp", "hk", "tw", "mo", "sea", "latam"),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_CLIENT,
        ],
        "setup_guide": {
            "summary": "Use your PayPal Business account to create a REST app, then paste Client ID and Secret.",
            "steps": [
                "Log in to the PayPal Developer Dashboard with the same email as your PayPal Business account.",
                "Apps & Credentials → Live tab → Create App. Name it (e.g. Zintriq).",
                "Open the app → copy Live Client ID and click Show to copy Secret.",
                "Paste both below → Save & verify. Customers pay on PayPal.",
            ],
            "links": [
                {"label": "PayPal Business signup", "url": "https://www.paypal.com/us/business"},
                {"label": "PayPal merchant apps & credentials (Live)", "url": "https://developer.paypal.com/dashboard/applications/live"},
            ],
        },
    },
    {
        "slug": "paypay",
        "name": "PayPay",
        "provider": "paypay",
        "description": "Japan's leading mobile wallet",
        "regions": ("jp",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Apply as a PayPay merchant, then copy Merchant ID + API keys from the merchant console.",
            "steps": [
                "Open PayPay for Business and apply with a Japanese business registration (法人 / 個人事業主).",
                "After approval, log in to the merchant console you receive by email.",
                "Open API / 開発者設定 and copy Merchant ID, API Key, and API Secret.",
                "Paste those three values below → Save & verify. Customers pay in the PayPay app.",
            ],
            "links": [
                {"label": "PayPay merchant apply (加盟店申込み)", "url": "https://merchant.paypay.ne.jp/entry"},
            ],
        },
    },
    {
        "slug": "square",
        "name": "Square",
        "provider": "square",
        "description": "In-person & online — US, UK, AU, JP, CA, EU",
        "regions": ("us", "uk", "au", "jp", "eu", "global"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "access_token", "label": "Access token", "type": "password", "required": True},
            {"key": "location_id", "label": "Location ID", "required": True},
        ],
        "setup_guide": {
            "summary": "Create a Square seller account, then copy the app Access token and Location ID.",
            "steps": [
                "Sign up as a Square seller, then open the Square Developer Dashboard and create an application.",
                "Open the app → Credentials. Copy the Sandbox Access token first (or Production when you go live).",
                "In the same Dashboard open Locations and copy the Location ID for the store that should receive funds.",
                "Paste Access token and Location ID below → Save & verify.",
            ],
            "links": [
                {"label": "Square seller signup", "url": "https://squareup.com/signup"},
                {"label": "Square merchant apps", "url": "https://developer.squareup.com/apps"},
            ],
        },
    },
    {
        "slug": "adyen",
        "name": "Adyen",
        "provider": "adyen",
        "description": "Enterprise payments — EU, UK, US, AU, SEA, Hong Kong, Taiwan",
        "regions": ("eu", "uk", "us", "au", "sea", "hk", "tw", "global"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "api_key", "label": "API Key", "type": "password", "required": True},
            {"key": "merchant_account", "label": "Merchant account code", "required": True},
            {"key": "client_key", "label": "Client key (optional)", "placeholder": "For Drop-in checkout"},
        ],
        "setup_guide": {
            "summary": "Complete Adyen merchant onboarding, then copy the API key and merchant account code from Customer Area.",
            "steps": [
                "Apply for an Adyen merchant account and finish KYC / company verification.",
                "Log in to Customer Area → Developers → API credentials → create a Web service user.",
                "Copy the API key. Then Account → Account settings → copy the Merchant account code.",
                "Optional: Developers → Client settings → copy Client key if you use Drop-in.",
                "Paste API key + merchant account code below → Save & verify.",
            ],
            "links": [
                {"label": "Adyen merchant signup", "url": "https://www.adyen.com/signup"},
                {"label": "Adyen Customer Area", "url": "https://ca-live.adyen.com/"},
            ],
        },
    },
    {
        "slug": "mollie",
        "name": "Mollie",
        "provider": "mollie",
        "description": "iDEAL, cards, SEPA — Netherlands & EU",
        "regions": ("eu", "uk"),
        "checkout_ready": True,
        "credential_fields": [{"key": "api_key", "label": "API Key", "type": "password", "required": True}],
        "setup_guide": {
            "summary": "Open a Mollie merchant account and copy the API key from Developers.",
            "steps": [
                "Create a Mollie merchant account and complete business verification.",
                "Dashboard → Developers → API keys.",
                "Copy the Test API key (starts with test_) first, or Live (live_) when you go live.",
                "Paste the API key below → Save & verify.",
            ],
            "links": [
                {"label": "Mollie merchant signup", "url": "https://www.mollie.com/dashboard/signup"},
                {"label": "Mollie Dashboard — API keys", "url": "https://my.mollie.com/dashboard/developers/api-keys"},
            ],
        },
    },
    {
        "slug": "klarna",
        "name": "Klarna",
        "provider": "klarna",
        "description": "Buy now, pay later — EU, UK, US, AU",
        "regions": ("eu", "uk", "us", "au"),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_CLIENT,
            {"key": "region", "label": "Region", "type": "select", "options": ["eu", "na", "oc"], "required": True},
        ],
        "setup_guide": {
            "summary": "Apply as a Klarna merchant, then copy API credentials from the Merchant Portal.",
            "steps": [
                "Apply for Klarna Payments as a retailer on the Klarna merchant site for your country.",
                "After approval, log in to the Klarna Merchant Portal.",
                "Settings → API credentials → copy Username / UID (Client ID) and Password (Client Secret).",
                "Set Region to eu, na, or oc to match your Klarna contract.",
                "Paste Client ID + Secret below → Save & verify.",
            ],
            "links": [
                {"label": "Klarna merchant / retailers", "url": "https://www.klarna.com/international/business/"},
                {"label": "Klarna Merchant Portal", "url": "https://portal.klarna.com/"},
            ],
        },
    },
    {
        "slug": "line_pay",
        "name": "LINE Pay",
        "provider": "line_pay",
        "description": "LINE wallet — Japan, Thailand, Taiwan",
        "regions": ("jp", "tw", "sea"),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Apply as a LINE Pay partner store, then copy Channel ID and Channel Secret from the store admin.",
            "steps": [
                "Apply as a LINE Pay partner store (Japan or Taiwan merchant pages below). Online and in-store accounts are separate — apply for online / website checkout.",
                "After approval, log in to the store admin with your Store ID.",
                "Developer tools / 開發者工具 → 管理連結金鑰 → copy Channel ID and Channel Secret. Also copy Store / Merchant ID from store info.",
                "Paste Merchant ID, API Key (Channel ID), and API Secret (Channel Secret) below → Save & verify.",
            ],
            "links": [
                {"label": "LINE Pay Japan — merchant apply", "url": "https://pay.line.me/"},
                {"label": "LINE Pay Taiwan — merchant apply", "url": "https://pay.line.me/"},
                {"label": "LINE Pay Taiwan — store admin login", "url": "https://pay.line.me/"},
            ],
        },
    },
    {
        "slug": "rakuten_pay",
        "name": "Rakuten Pay",
        "provider": "rakuten_pay",
        "description": "Rakuten wallet — Japan",
        "regions": ("jp",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Apply for Rakuten Pay for Business, then copy service ID and access keys from merchant admin.",
            "steps": [
                "Apply as a Rakuten Pay merchant (Japanese business registration required).",
                "After approval, log in to the merchant admin you receive by email.",
                "Open API / 加盟店設定 and copy Merchant ID (service ID), API Key, and API Secret.",
                "Paste those values below → Save & verify.",
            ],
            "links": [
                {"label": "Rakuten Pay for Business (merchant)", "url": "https://pay.rakuten.co.jp/"},
            ],
        },
    },
    {
        "slug": "grabpay",
        "name": "GrabPay",
        "provider": "grabpay",
        "description": "Grab wallet — Singapore, MY, PH, TH, VN, ID, Hong Kong",
        "regions": ("sea", "hk"),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Register on GrabMerchant, enable GrabPay, then copy Partner ID / secret and Merchant ID.",
            "steps": [
                "Sign up as a merchant on GrabMerchant (GrabFood / GrabPay).",
                "After the outlet is approved, open GrabMerchant Portal → Payments / Developer.",
                "Copy Partner ID, Partner Secret, and Merchant ID (outlet ID).",
                "Paste Merchant ID, API Key (Partner ID), and API Secret below → Save & verify.",
            ],
            "links": [
                {"label": "GrabMerchant signup", "url": "https://www.grab.com/sg/merchant/"},
                {"label": "GrabMerchant Portal login", "url": "https://merchant.grab.com/"},
            ],
        },
    },
    {
        "slug": "shopeepay",
        "name": "ShopeePay",
        "provider": "shopeepay",
        "description": "Shopee wallet — SEA markets",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": _CRED_MERCHANT,
        "setup_guide": {
            "summary": "Become a ShopeePay merchant via Shopee Partner, then paste the Merchant ID and API keys they issue.",
            "steps": [
                "Apply as a ShopeePay merchant through the Shopee Partner registration form for your country (SG, MY, PH, TH, VN, ID).",
                "Shopee emails login details for the Shopee Partner app / merchant console after review (usually within 7 working days).",
                "In the merchant console or the onboarding email, copy Merchant ID, API Key, and API Secret.",
                "Paste those values below → Save & verify.",
            ],
            "links": [
                {"label": "ShopeePay merchant — how to join", "url": "https://help.shopee.com.my/1/article/78391-%5BShopeePay-Merchant%5D-How-do-I-become-a-ShopeePay-merchant"},
            ],
        },
    },
    {
        "slug": "xendit",
        "name": "Xendit",
        "provider": "xendit",
        "description": "Indonesia, Philippines, Malaysia, Vietnam, Thailand",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [{"key": "secret_key", "label": "Secret API Key", "type": "password", "required": True}],
        "setup_guide": {
            "summary": "Open a Xendit merchant account and copy the Secret API key from Settings.",
            "steps": [
                "Create a Xendit merchant account and complete business verification.",
                "Dashboard → Settings → Developers → API Keys.",
                "Create or reveal the Secret API key (test first, then live).",
                "Paste the Secret API key below → Save & verify.",
            ],
            "links": [
                {"label": "Xendit merchant signup", "url": "https://dashboard.xendit.co/register/1"},
                {"label": "Xendit Dashboard", "url": "https://dashboard.xendit.co/"},
            ],
        },
    },
    {
        "slug": "omise",
        "name": "Omise",
        "provider": "omise",
        "description": "Thailand, Japan, Singapore, Malaysia",
        "regions": ("sea", "jp"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "public_key", "label": "Public key", "required": True},
            {"key": "secret_key", "label": "Secret key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open an Omise merchant account and copy public + secret keys from the Dashboard.",
            "steps": [
                "Create an Omise merchant account (Thailand / Japan / Singapore / Malaysia).",
                "Dashboard → Keys. Use Test keys first.",
                "Copy Public key (pkey_…) and Secret key (skey_…).",
                "Paste both below → Save & verify. Switch to Live keys when Omise activates your account.",
            ],
            "links": [
                {"label": "Omise merchant signup", "url": "https://dashboard.omise.co/signup"},
                {"label": "Omise Dashboard — keys", "url": "https://dashboard.omise.co/"},
            ],
        },
    },
    {
        "slug": "midtrans",
        "name": "Midtrans",
        "provider": "midtrans",
        "description": "Indonesia — cards, bank transfer, e-wallets",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "server_key", "label": "Server Key", "type": "password", "required": True},
            {"key": "client_key", "label": "Client Key", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Midtrans merchant account and copy Server Key + Client Key from Access Keys.",
            "steps": [
                "Create a Midtrans merchant account (Indonesia).",
                "Log in to the Dashboard → Settings → Access Keys.",
                "Copy Server Key and Client Key from the Sandbox tab first.",
                "Paste both below → Save & verify. Use Production keys when Midtrans activates live.",
            ],
            "links": [
                {"label": "Midtrans merchant signup", "url": "https://dashboard.midtrans.com/register"},
                {"label": "Midtrans Dashboard", "url": "https://dashboard.midtrans.com/"},
            ],
        },
    },
    {
        "slug": "gocardless",
        "name": "GoCardless",
        "provider": "gocardless",
        "description": "Direct debit — UK, EU",
        "regions": ("uk", "eu"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "access_token", "label": "Access token", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a GoCardless merchant account and create a read-write access token.",
            "steps": [
                "Create a GoCardless merchant account and complete verification.",
                "Dashboard → Developers → Create access token. Choose read-write.",
                "Copy the token immediately (it is shown once).",
                "Paste the Access token below, Save & verify.",
            ],
            "links": [
                {"label": "GoCardless merchant signup", "url": "https://manage.gocardless.com/sign-up"},
                {"label": "GoCardless merchant dashboard", "url": "https://manage.gocardless.com/"},
            ],
        },
    },
    {
        "slug": "sumup",
        "name": "SumUp",
        "provider": "sumup",
        "description": "Card terminals & online — EU, UK, US",
        "regions": ("eu", "uk", "us"),
        "checkout_ready": True,
        "credential_fields": [{"key": "api_key", "label": "API Key", "type": "password", "required": True}],
        "setup_guide": {
            "summary": "Create a SumUp merchant account, register an app, then paste the API key.",
            "steps": [
                "Create a SumUp merchant / business account.",
                "Open the SumUp merchant dashboard, then register an app under Developers.",
                "Copy the API key (or OAuth client credentials if that is what SumUp issued).",
                "Paste the API key below → Save & verify.",
            ],
            "links": [
                {"label": "SumUp — sign up", "url": "https://help.sumup.com/en-GB/articles/5V8xZtu56CPbJ2K7Hm0brt-sign-up"},
                {"label": "SumUp Support Centre", "url": "https://help.sumup.com/en-GB"},
            ],
        },
    },
    {
        "slug": "worldpay",
        "name": "Worldpay",
        "provider": "worldpay",
        "description": "Enterprise acquiring — UK, EU, US",
        "regions": ("uk", "eu", "us"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_code", "label": "Merchant code", "required": True},
            {"key": "installation_id", "label": "Installation ID", "required": True},
            {"key": "xml_password", "label": "XML password", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Apply for a Worldpay merchant account, then paste Merchant code, Installation ID, and XML password from the welcome pack.",
            "steps": [
                "Apply as a Worldpay merchant (or ask your acquiring bank for Worldpay Business Gateway).",
                "After boarding, open the welcome email / merchant pack.",
                "Copy Merchant code, Installation ID, and XML password.",
                "Paste those three values below → Save & verify.",
            ],
            "links": [
                {"label": "Worldpay merchant — get started", "url": "https://www.worldpay.com/en"},
                {"label": "Worldpay merchant login", "url": "https://www.worldpay.com/"},
            ],
        },
    },
    {
        "slug": "authorize_net",
        "name": "Authorize.net",
        "provider": "authorize_net",
        "description": "US & Canada card processing",
        "regions": ("us",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "api_login_id", "label": "API Login ID", "required": True},
            {"key": "transaction_key", "label": "Transaction Key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open an Authorize.net merchant account and copy API Login ID + Transaction Key.",
            "steps": [
                "Create an Authorize.net merchant account.",
                "Merchant Interface → Account → Settings → API Credentials & Keys.",
                "Copy API Login ID. Generate a new Transaction Key (it is shown once).",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "Authorize.net merchant signup", "url": "https://www.authorize.net/sign-up/"},
                {"label": "Authorize.net merchant login", "url": "https://account.authorize.net/"},
            ],
        },
    },
    {
        "slug": "braintree",
        "name": "Braintree",
        "provider": "braintree",
        "description": "PayPal-owned gateway — US, UK, EU, AU",
        "regions": ("us", "uk", "eu", "au"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Merchant ID", "required": True},
            {"key": "public_key", "label": "Public Key", "required": True},
            {"key": "private_key", "label": "Private Key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Braintree merchant account and copy Merchant ID, Public Key, and Private Key from the Control Panel.",
            "steps": [
                "Apply for Braintree (PayPal) and complete live merchant approval.",
                "Control Panel → Settings → API → API Keys.",
                "Copy Merchant ID, Public Key, and Private Key from the live account.",
                "Paste all three below → Save & verify.",
            ],
            "links": [
                {"label": "Braintree merchant signup", "url": "https://www.braintreepayments.com/get-started"},
                {"label": "Braintree Control Panel", "url": "https://www.braintreegateway.com/login"},
            ],
        },
    },
    {
        "slug": "afterpay",
        "name": "Afterpay / Clearpay",
        "provider": "afterpay",
        "description": "BNPL — AU, US, UK, EU",
        "regions": ("au", "us", "uk", "eu"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Merchant ID", "required": True},
            {"key": "secret_key", "label": "Secret Key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Apply as an Afterpay / Clearpay retailer, then copy Merchant ID and Secret from the Merchant Portal.",
            "steps": [
                "Apply as a retailer on Afterpay (AU/US) or Clearpay (UK/EU).",
                "After approval, log in to the Merchant Portal → Integration / API.",
                "Copy Merchant ID and Secret Key.",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "Afterpay merchant / retailers", "url": "https://www.afterpay.com/en-US/for-retailers"},
                {"label": "Clearpay merchant (UK/EU)", "url": "https://www.afterpay.com/"},
            ],
        },
    },
    {
        "slug": "zip",
        "name": "Zip (Quadpay)",
        "provider": "zip",
        "description": "BNPL — Australia, US",
        "regions": ("au", "us"),
        "checkout_ready": True,
        "credential_fields": _CRED_CLIENT,
        "setup_guide": {
            "summary": "Apply as a Zip merchant, then copy Client ID and Secret from the merchant portal.",
            "steps": [
                "Apply for Zip (Australia) or Zip / Quadpay (US) as a retailer.",
                "After approval, log in to the Zip Merchant Portal → API / Integration.",
                "Copy Client ID and Client Secret.",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "Zip merchant (Australia)", "url": "https://zip.co/au/business"},
            ],
        },
    },
    {
        "slug": "eway",
        "name": "eWAY",
        "provider": "eway",
        "description": "Australia & NZ payments",
        "regions": ("au",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "api_key", "label": "API Key", "required": True},
            {"key": "api_password", "label": "API Password", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open an eWAY merchant account and copy API Key + Password from MYeWAY.",
            "steps": [
                "Create an eWAY merchant account (Australia / NZ).",
                "Log in to MYeWAY → My Site → API Key.",
                "Copy API Key and API Password.",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "eWAY merchant signup", "url": "https://www.eway.com.au/sign-up"},
                {"label": "eWAY merchant tools / MyEway", "url": "https://www.eway.com.au/merchant-tools/"},
            ],
        },
    },
    {
        "slug": "paystack",
        "name": "Paystack",
        "provider": "paystack",
        "description": "Nigeria, Ghana, South Africa, Kenya",
        "regions": ("af",),
        "checkout_ready": True,
        "credential_fields": [{"key": "secret_key", "label": "Secret Key", "type": "password", "required": True}],
        "setup_guide": {
            "summary": "Open a Paystack merchant account and copy the Secret Key from Settings.",
            "steps": [
                "Create a Paystack merchant account and complete business verification.",
                "Dashboard → Settings → API Keys & Webhooks.",
                "Copy the Test Secret Key first (sk_test_…), or Live (sk_live_…) when you go live.",
                "Paste the Secret Key below → Save & verify.",
            ],
            "links": [
                {"label": "Paystack merchant signup", "url": "https://dashboard.paystack.com/#/signup"},
                {"label": "Paystack Dashboard", "url": "https://dashboard.paystack.com/"},
            ],
        },
    },
    {
        "slug": "flutterwave",
        "name": "Flutterwave",
        "provider": "flutterwave",
        "description": "Africa — cards, mobile money, bank transfer",
        "regions": ("af",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "public_key", "label": "Public Key", "required": True},
            {"key": "secret_key", "label": "Secret Key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Flutterwave merchant account and copy Public + Secret keys from Settings.",
            "steps": [
                "Create a Flutterwave merchant account and complete KYC.",
                "Dashboard → Settings → API Keys.",
                "Copy Public Key and Secret Key (test first, then live).",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "Flutterwave merchant signup", "url": "https://dashboard.flutterwave.com/signup"},
                {"label": "Flutterwave Dashboard", "url": "https://dashboard.flutterwave.com/"},
            ],
        },
    },
    {
        "slug": "mercado_pago",
        "name": "Mercado Pago",
        "provider": "mercado_pago",
        "description": "Latin America — Brazil, Mexico, Argentina, Chile, Colombia",
        "regions": ("latam", "us"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "access_token", "label": "Access Token", "type": "password", "required": True},
            {"key": "public_key", "label": "Public Key", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Mercado Pago seller account and copy Access Token + Public Key from Credentials.",
            "steps": [
                "Create a Mercado Pago seller account on your country site (BR, MX, AR, CL, CO, etc.).",
                "Your integrations → Credentials (or Developers → Credentials).",
                "Copy Test Access Token and Public Key first. Use Production keys when you go live.",
                "Paste Access Token and Public Key below → Save & verify.",
            ],
            "links": [
                {"label": "Mercado Pago seller / credentials", "url": "https://www.mercadopago.com/developers/panel/app"},
            ],
        },
    },
    {
        "slug": "yookassa",
        "name": "YooKassa",
        "provider": "yookassa",
        "description": "Russia — cards, YooMoney (subject to local regulations)",
        "regions": ("ru",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "shop_id", "label": "Shop ID", "required": True},
            {"key": "secret_key", "label": "Secret Key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a YooKassa merchant shop and copy shopId + secret key from Integration.",
            "steps": [
                "Register a business shop on YooKassa (ЮKassa) merchant onboarding.",
                "Merchant cabinet → Integration → API keys. Issue a secret key and note shopId.",
                "Paste Shop ID and Secret Key below → Save & verify.",
                "Only use this if you are allowed to accept these payments under local rules.",
            ],
            "links": [
                {"label": "YooKassa merchant apply", "url": "https://yookassa.ru/joinups"},
                {"label": "YooKassa merchant cabinet", "url": "https://yookassa.ru/my"},
            ],
        },
    },
    {
        "slug": "razorpay",
        "name": "Razorpay",
        "provider": "razorpay",
        "description": "India — cards, UPI, wallets",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "key_id", "label": "Key ID", "required": True},
            {"key": "key_secret", "label": "Key Secret", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Razorpay merchant account and generate API keys from Settings.",
            "steps": [
                "Create a Razorpay merchant account and complete KYC.",
                "Dashboard → Account & Settings → API Keys.",
                "Generate Test keys first. Copy Key ID and Key Secret (secret is shown once).",
                "Paste both below → Save & verify. Generate Live keys when you go live.",
            ],
            "links": [
                {"label": "Razorpay merchant signup", "url": "https://dashboard.razorpay.com/signup"},
                {"label": "Razorpay Dashboard", "url": "https://dashboard.razorpay.com/"},
            ],
        },
    },
    {
        "slug": "alipay_hk",
        "name": "AlipayHK",
        "provider": "alipay_hk",
        "description": "AlipayHK wallet — Hong Kong & Macau merchants",
        "regions": ("hk", "mo"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "app_id", "label": "App ID / Client ID", "required": True},
            {"key": "merchant_id", "label": "Merchant / Seller ID"},
            {"key": "private_key", "label": "RSA private key (PEM)", "type": "textarea", "required": True},
        ],
        "setup_guide": {
            "summary": "Register as an AlipayHK merchant, create an app, then paste App ID and the matching RSA private key.",
            "steps": [
                "Open AlipayHK Open Platform and register as a Hong Kong / Macau merchant (or use Antom / Alipay+ if that is your contract).",
                "Create an application. Copy App ID (or Client-Id if Antom issued that instead).",
                "Generate an RSA2 key pair. Upload the public key in the merchant console. Keep the private key as PEM.",
                "Optional: copy Merchant / Seller ID from the same app page.",
                "Paste App ID + PEM private key below, Save & verify. Checkout uses your live merchant account.",
            ],
            "links": [
                {"label": "AlipayHK merchant Open Platform", "url": "https://open.alipay.hk"},
            ],
        },
    },
    {
        "slug": "wechat_pay_hk",
        "name": "WeChat Pay HK",
        "provider": "wechat_pay_hk",
        "description": "WeChat Pay Hong Kong — HKD / MOP hosted checkout",
        "regions": ("hk", "mo"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Merchant ID (mchid)", "required": True},
            {"key": "appid", "label": "AppID", "required": True},
            {"key": "serial_no", "label": "API certificate serial no.", "required": True},
            {"key": "private_key", "label": "API certificate private key (PEM)", "type": "textarea", "required": True},
            {"key": "apiv3_key", "label": "APIv3 key", "type": "password", "required": True},
            {"key": "merchant_category_code", "label": "MCC (e.g. 5812 restaurants)"},
        ],
        "setup_guide": {
            "summary": "Apply as a WeChat Pay Global / HK merchant, then copy mchid, AppID, APIv3 cert, and APIv3 key. Not mainland WeChat Pay.",
            "steps": [
                "Open the WeChat Pay Global merchant site. Choose International Business if the mainland site appears. Join Us → Merchant → apply for Hong Kong.",
                "Upload BRC / company docs. After approval, WeChat emails mchid and the merchant login.",
                "Merchant platform → Account Center → API Security: apply for the APIv3 certificate and set an APIv3 key.",
                "Copy Merchant ID (mchid), AppID, certificate serial number, and the PEM private key. Optional: MCC (e.g. 5812 restaurants).",
                "Paste those values below → Save & verify.",
            ],
            "links": [
                {"label": "WeChat Pay Global — merchant apply", "url": "https://pay.weixin.qq.com/index.php/public/wechatpay/home"},
                {"label": "WeChat Pay — direct merchant application", "url": "https://pay.weixin.qq.com/index.php/public/wechatpay_en/application_direct_merchants"},
            ],
        },
    },
    {
        "slug": "payme",
        "name": "PayMe from HSBC",
        "provider": "payme",
        "description": "PayMe for Business — Hong Kong HKD checkout",
        "regions": ("hk",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Merchant ID", "required": True},
            {"key": "client_id", "label": "Client ID", "required": True},
            {"key": "client_secret", "label": "Client Secret", "type": "password", "required": True},
            {"key": "signing_key_id", "label": "Signing Key ID", "required": True},
            {"key": "signing_key", "label": "Signing Key", "type": "textarea", "required": True},
        ],
        "setup_guide": {
            "summary": "Open PayMe for Business, request Online Payments, then paste the five keys from HSBC’s merchant PDF.",
            "steps": [
                "Apply for PayMe for Business (HSBC Hong Kong merchant). Complete business verification in the app.",
                "In the PayMe for Business app: Help centre → Online Payments → request API access.",
                "HSBC emails a password-protected PDF. Open it and copy Merchant ID, Client ID, Client Secret, Signing Key ID, and Signing Key.",
                "Paste all five values below, Save & verify. Use the production keys HSBC issued.",
            ],
            "links": [
                {"label": "PayMe for Business (merchant)", "url": "https://payme.hsbc.com.hk/payme-for-business"},
            ],
        },
    },
    {
        "slug": "unionpay",
        "name": "UnionPay",
        "provider": "unionpay",
        "description": "UnionPay Online Payment — Hong Kong, Taiwan, Macau",
        "regions": ("hk", "tw", "mo"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Merchant ID (merId)", "required": True},
            {"key": "cert_id", "label": "Certificate ID (certId)", "required": True},
            {"key": "private_key", "label": "Signature private key (PEM)", "type": "textarea", "required": True},
        ],
        "setup_guide": {
            "summary": "Join UnionPay as a merchant (or via your acquirer), then paste merId, certId, and the signing private key.",
            "steps": [
                "Apply on the UnionPay merchant join site, or ask your acquiring bank to enable UnionPay Online Payment.",
                "After approval, log in to UnionPay Open Platform (merchant) and download the signing certificate.",
                "Note merId and certId from the certificate / merchant profile. Export the private key as PEM.",
                "Paste merId, certId, and PEM private key below → Save & verify.",
            ],
            "links": [
                {"label": "UnionPay merchant join", "url": "https://merchant.unionpay.com/join/"},
                {"label": "UnionPay merchant Open Platform", "url": "https://open.unionpay.com"},
            ],
        },
    },
    {
        "slug": "jkopay",
        "name": "JKOPAY",
        "provider": "jkopay",
        "description": "街口支付 — Taiwan mobile wallet checkout",
        "regions": ("tw",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Store ID", "required": True},
            {"key": "api_key", "label": "API Key", "required": True},
            {"key": "api_secret", "label": "API Secret", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Apply as a JKOPAY partner store, then copy Store ID and API Key from the store admin.",
            "steps": [
                "Open the JKOPAY store application page and apply as a partner store (網路平台 / online checkout).",
                "After approval, log in to 店家管理後台 (the store admin they email you).",
                "Open 線上收款 / API and copy Store ID and API Key (and API Secret if issued).",
                "Paste Store ID + API Key below → Save & verify.",
            ],
            "links": [
                {"label": "JKOPAY merchant apply (店家專區)", "url": "https://www.jkopay.com/application/store"},
            ],
        },
    },
    {
        "slug": "easy_wallet",
        "name": "Easy Wallet",
        "provider": "easy_wallet",
        "description": "悠遊付 — Taiwan EasyCard wallet checkout",
        "regions": ("tw",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_MERCHANT,
        ],
        "setup_guide": {
            "summary": "Apply as an Easy Wallet (悠遊付) store, then copy Merchant ID and API keys from the store console.",
            "steps": [
                "Submit the 悠遊付店家 form, or start 特店進件 with company / personal documents (登記、身分證、存摺、店面照片).",
                "After approval, log in to the store admin / 特店 APP they issue.",
                "Open API / 線上收款 and copy Merchant ID, API Key, and API Secret.",
                "Paste those three values below → Save & verify.",
            ],
            "links": [
                {"label": "悠遊付 — become a store", "url": "https://www.easycard.com.tw/"},
                {"label": "悠遊付 — merchant onboarding (特店進件)", "url": "https://masweb.easycard.com.tw/MAS/"},
            ],
        },
    },
    {
        "slug": "mpay",
        "name": "MPay",
        "provider": "mpay",
        "description": "澳門通 MPay — Macau wallet checkout",
        "regions": ("mo",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_MERCHANT,
        ],
        "setup_guide": {
            "summary": "Apply as a Macau Pass / MPay merchant, then copy online-payment API keys from the merchant platform.",
            "steps": [
                "Open 申請成為澳門通支付商戶 and select 商戶APP/網站收款 (website checkout).",
                "After approval, Macau Pass emails the Merchant Service Platform (MSP) login.",
                "MSP / merchant admin → online payment / API → copy Merchant ID, API Key, and API Secret.",
                "Paste those values below → Save & verify. Customers pay in the MPay app.",
            ],
            "links": [
                {"label": "Macau Pass — apply as merchant", "url": "https://www.macaupass.com/applymerchant"},
                {"label": "MPay merchant FAQ", "url": "https://www.macaupass.com/Merchantfaqs"},
            ],
        },
    },
    {
        "slug": "atome",
        "name": "Atome",
        "provider": "atome",
        "description": "APAC BNPL — Hong Kong, Singapore, Malaysia, Taiwan",
        "regions": ("hk", "sea", "tw"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "username", "label": "API username", "required": True},
            {"key": "password", "label": "API password", "type": "password", "required": True},
            {"key": "country", "label": "Country", "type": "select", "options": ["HK", "SG", "MY", "TW"], "required": True},
        ],
        "setup_guide": {
            "summary": "Apply as an Atome merchant, then copy API username and password from the Atome merchant / partner portal.",
            "steps": [
                "Open Atome for Business and apply for online checkout (BNPL) for Hong Kong, Singapore, Malaysia, or Taiwan.",
                "After approval, log in to the Atome merchant portal they email you.",
                "Open Developer / API and copy API username and password. Note the country of the contract.",
                "Paste username + password below and set Country → Save & verify.",
            ],
            "links": [
                {"label": "Atome for Business (merchant apply)", "url": "https://www.atome.sg/business"},
                {"label": "Atome merchant / partner portal", "url": "https://portal.atome.sg/"},
                {"label": "Atome developer portal", "url": "https://partner.apaylater.com/"},
            ],
        },
    },
    {
        "slug": "twoc2p",
        "name": "2C2P",
        "provider": "twoc2p",
        "description": "APAC acquiring — Hong Kong, Thailand, Singapore, SEA",
        "regions": ("hk", "sea"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Merchant ID", "required": True},
            {"key": "secret_key", "label": "Secret key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a 2C2P merchant account, then copy Merchant ID and Secret key from Merchant Portal. Checkout uses 2C2P’s hosted Payment Token page.",
            "steps": [
                "Apply as a 2C2P merchant (or ask your acquiring bank to issue a 2C2P MID).",
                "Log in to 2C2P Merchant Portal. Open Account / API.",
                "Copy the production Merchant ID and Secret key.",
                "Paste both below, Save & verify. Use the production Merchant ID 2C2P issued.",
            ],
            "links": [
                {"label": "2C2P — become a merchant", "url": "https://2c2p.com/contact-us"},
                {"label": "2C2P Merchant Portal", "url": "https://www.2c2p.com/"},
                {"label": "2C2P developer docs (Payment Token)", "url": "https://developer.2c2p.com/docs/api-payment-token"},
            ],
        },
    },
    {
        "slug": "airwallex",
        "name": "Airwallex",
        "provider": "airwallex",
        "description": "Global acquiring & payment links — common for Hong Kong companies",
        "regions": ("hk", "global", "au", "eu", "uk", "sea", "us"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "client_id", "label": "Client ID", "required": True},
            {"key": "api_key", "label": "API key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open an Airwallex Business account, then copy Client ID and API key from Developer settings. Checkout creates an Airwallex Payment Link.",
            "steps": [
                "Create an Airwallex Business account and complete KYC (Hong Kong companies are commonly accepted).",
                "Web app → Settings → Developer → API keys. Create a key. Copy Client ID and API key.",
                "Use the live API key from the Airwallex web app (not the Demo toggle).",
                "Paste Client ID + API key below → Save & verify. Customers pay on Airwallex’s hosted page.",
            ],
            "links": [
                {"label": "Airwallex — open a business account", "url": "https://www.airwallex.com/signup"},
                {"label": "Airwallex web app (merchant)", "url": "https://www.airwallex.com/app"},
                {"label": "Airwallex Payment Links API", "url": "https://www.airwallex.com/docs/api/payments/payment_links/create"},
            ],
        },
    },
    {
        "slug": "checkout_com",
        "name": "Checkout.com",
        "provider": "checkout_com",
        "description": "Enterprise hosted payments — global, Hong Kong, EU",
        "regions": ("global", "hk", "eu", "uk", "us"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "secret_key", "label": "Secret key", "type": "password", "placeholder": "sk_sbox_… or sk_…", "required": True},
            {"key": "processing_channel_id", "label": "Processing channel ID (optional)", "placeholder": "pc_…"},
        ],
        "setup_guide": {
            "summary": "Apply as a Checkout.com merchant, then copy the Secret key from Dashboard → Developers. Checkout uses Hosted Payments.",
            "steps": [
                "Apply for a Checkout.com merchant account (or ask your PSP to issue a Checkout.com entity).",
                "Log in to Dashboard / Hub. Developers → Keys. Copy the live Secret key (starts with sk_, not sk_sbox_).",
                "Optional: copy Processing channel ID (pc_…) from Settings → Channels if you have more than one.",
                "Paste the Secret key below, set Environment to match the key → Save & verify.",
            ],
            "links": [
                {"label": "Checkout.com — talk to sales / apply", "url": "https://www.checkout.com/contact-sales"},
                {"label": "Checkout.com Dashboard", "url": "https://dashboard.checkout.com/"},
                {"label": "Hosted Payments docs", "url": "https://www.checkout.com/docs/payments/accept-payments/accept-a-payment-on-a-hosted-page"},
            ],
        },
    },
    {
        "slug": "octopus",
        "name": "Octopus / 八达通",
        "provider": "octopus",
        "description": "Hong Kong Octopus Online Payment — issued after Octopus / acquirer approval",
        "regions": ("hk",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "Octopus merchant ID", "required": True},
            {"key": "api_key", "label": "API / hash key", "type": "password", "required": True},
            {"key": "api_secret", "label": "API secret (if issued)", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Apply for Octopus Online Payment (or ask your HK acquirer to enable Octopus). Paste the merchant ID and hash key they issue. Checkout is hosted by Octopus / your acquirer — not a consumer Octopus app login.",
            "steps": [
                "Open Octopus for Business and apply for Online Payment, or ask your existing HK acquirer (2C2P / bank) to enable Octopus as a channel.",
                "Octopus or the acquirer emails a merchant ID and hash / API key after underwriting. Keep the consumer Octopus app out of this — those keys will not work.",
                "If 2C2P issued the Octopus channel, connect 2C2P instead (same checkout, Octopus appears on their hosted page).",
                "Paste merchant ID + hash key below → Save & verify.",
            ],
            "links": [
                {"label": "Octopus for Business", "url": "https://www.octopus.com.hk/en/business/index.html"},
                {"label": "Octopus — become a merchant", "url": "https://www.octopus.com.hk/en/business/become-a-merchant/benefits/index.html"},
            ],
        },
    },
    {
        "slug": "fps",
        "name": "FPS 转数快",
        "provider": "fps",
        "description": "Hong Kong Faster Payment System — bank / acquirer hosted checkout",
        "regions": ("hk",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "fps_id", "label": "FPS identifier (mobile / email / FPS ID)", "required": True},
            {"key": "merchant_id", "label": "Bank / acquirer merchant ID", "required": True},
            {"key": "api_key", "label": "Bank / acquirer API key", "required": True},
            {"key": "api_secret", "label": "API secret", "type": "password", "required": True},
            {"key": "gateway_base", "label": "HTTPS API base from your bank", "placeholder": "https://…", "required": True},
        ],
        "setup_guide": {
            "summary": "FPS is not a standalone SaaS. Ask your HK bank or acquirer for FPS Online Payment API keys, then paste them here. A consumer FPS ID alone cannot take carded checkout.",
            "steps": [
                "In your HK business bank (or acquirer such as 2C2P / Airwallex), enable FPS Online / FPS QR for e-commerce.",
                "Copy the collecting FPS identifier plus the API key and secret the bank issues for payment requests.",
                "Optional: paste the HTTPS API base URL printed in the bank’s FPS Online PDF (must start with https://).",
                "Paste FPS ID, merchant ID, API key, and secret below → Save & verify. Customers pay on the bank / acquirer hosted page.",
            ],
            "links": [
                {"label": "HKICL Faster Payment System (scheme)", "url": "https://fps.hkicl.com.hk/"},
                {"label": "HKMA — FPS for businesses", "url": "https://www.hkma.gov.hk/eng/smart-consumers/faster-payment-system/"},
            ],
        },
    },
    {
        "slug": "gcash",
        "name": "GCash",
        "provider": "gcash",
        "description": "Philippines e-wallet checkout",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_MERCHANT,
        ],
        "setup_guide": {
            "summary": "Apply for GCash for Business online payments, then copy Merchant ID and API keys from the merchant dashboard.",
            "steps": [
                "Open GCash for Business and apply for Online Payment / GCash Checkout (not in-store QR only).",
                "After approval, log in to the GCash merchant dashboard they issue.",
                "Developer / API → copy Merchant ID, API Key, and API Secret (production / live keys).",
                "Paste those three values below → Save & verify. Customers pay in the GCash app.",
            ],
            "links": [
                {"label": "GCash for Business", "url": "https://business.gcash.com/"},
                {"label": "GCash merchant apply", "url": "https://business.gcash.com/registration"},
            ],
        },
    },
    {
        "slug": "maya",
        "name": "Maya",
        "provider": "maya",
        "description": "Philippines Maya Checkout (formerly PayMaya)",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "public_key", "label": "Public API key", "placeholder": "pk-…", "required": True},
            {"key": "secret_key", "label": "Secret API key", "type": "password", "placeholder": "sk-…", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Maya Business account, then copy Public and Secret API keys from Maya Manager. Checkout uses Maya Checkout v1.",
            "steps": [
                "Create a Maya Business / Maya Manager account and complete merchant verification.",
                "Maya Manager → Settings → API keys. Copy the live Public key (pk-) and Secret key (sk-).",
                "Paste both keys below, Save & verify. Use the live Secret key from Maya Manager.",
            ],
            "links": [
                {"label": "Maya Business (merchant)", "url": "https://www.maya.ph/business"},
                {"label": "Maya Manager login", "url": "https://manager.maya.ph/"},
                {"label": "Maya Checkout API", "url": "https://developers.maya.ph/docs/maya-checkout"},
            ],
        },
    },
    {
        "slug": "touch_n_go",
        "name": "Touch ’n Go eWallet",
        "provider": "touch_n_go",
        "description": "Malaysia Touch ’n Go eWallet checkout",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_MERCHANT,
        ],
        "setup_guide": {
            "summary": "Apply as a TNG eWallet online merchant, then copy Client ID / API keys from TNG Digital merchant portal.",
            "steps": [
                "Open Touch ’n Go eWallet for Business and apply for Online Payment (not in-store QR only).",
                "After approval, log in to the TNG Digital merchant portal.",
                "API / Developer → copy Merchant ID, API Key, and API Secret.",
                "Paste those values below → Save & verify. Customers pay in the TNG eWallet app.",
            ],
            "links": [
                {"label": "Touch ’n Go eWallet for Business", "url": "https://www.touchngo.com.my/"},
            ],
        },
    },
    {
        "slug": "duitnow",
        "name": "DuitNow",
        "provider": "duitnow",
        "description": "Malaysia DuitNow online / QR — via your bank or PayNet acquirer",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "merchant_id", "label": "DuitNow merchant / biller ID", "required": True},
            {"key": "api_key", "label": "Bank / acquirer API key", "required": True},
            {"key": "api_secret", "label": "API secret", "type": "password", "required": True},
            {"key": "gateway_base", "label": "HTTPS API base from your bank", "placeholder": "https://…", "required": True},
        ],
        "setup_guide": {
            "summary": "DuitNow is a PayNet scheme. Ask your Malaysian bank or acquirer for DuitNow Online / QR API keys, then paste them here.",
            "steps": [
                "Ask your MY business bank (or acquirer) to enable DuitNow Online / DuitNow QR for e-commerce.",
                "Copy Merchant / Biller ID plus API key and secret from the bank’s merchant portal or onboarding PDF.",
                "Optional: paste the HTTPS API base URL the bank printed (must start with https://).",
                "Paste those values below → Save & verify. Customers pay on the bank / PayNet hosted page.",
            ],
            "links": [
                {"label": "DuitNow (PayNet) — merchants", "url": "https://www.duitnow.my/"},
                {"label": "PayNet — DuitNow", "url": "https://www.paynet.my/"},
            ],
        },
    },
    {
        "slug": "promptpay",
        "name": "PromptPay",
        "provider": "promptpay",
        "description": "Thailand PromptPay — via your bank or Thai QR acquirer",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "promptpay_id", "label": "PromptPay ID (mobile / national ID / biller)", "required": True},
            {"key": "merchant_id", "label": "Acquirer merchant ID", "required": True},
            {"key": "api_key", "label": "Acquirer API key", "required": True},
            {"key": "api_secret", "label": "API secret", "type": "password", "required": True},
            {"key": "gateway_base", "label": "HTTPS API base from your bank", "placeholder": "https://…", "required": True},
        ],
        "setup_guide": {
            "summary": "PromptPay online checkout is issued by your Thai bank or acquirer (Omise / 2C2P / GB Prime). Paste those API keys — a consumer PromptPay ID alone is not enough.",
            "steps": [
                "Ask your Thai bank or acquirer to enable PromptPay / Thai QR for e-commerce.",
                "Copy PromptPay ID, merchant ID, API key, and secret from the merchant portal they issue.",
                "If you already have Omise or 2C2P, you can connect those plugins instead — PromptPay appears on their hosted page.",
                "Paste the acquirer keys below → Save & verify.",
            ],
            "links": [
                {"label": "Thai QR / PromptPay (Bank of Thailand)", "url": "https://www.bot.or.th/en/our-roles/payment-systems.html"},
            ],
        },
    },
    {
        "slug": "truemoney",
        "name": "TrueMoney",
        "provider": "truemoney",
        "description": "Thailand TrueMoney Wallet checkout",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_MERCHANT,
        ],
        "setup_guide": {
            "summary": "Apply as a TrueMoney merchant, then copy Merchant ID and API keys from the TrueMoney merchant console.",
            "steps": [
                "Open TrueMoney for Business / merchant apply and choose online wallet checkout.",
                "After approval, log in to the TrueMoney merchant console.",
                "API → copy Merchant ID, API Key, and API Secret (production / live keys).",
                "Paste those values below → Save & verify. Customers pay in TrueMoney Wallet.",
            ],
            "links": [
                {"label": "TrueMoney — online merchant apply", "url": "https://www.truemoney.com/"},
                {"label": "TrueMoney — True Smart Merchant FAQ", "url": "https://www.truemoney.com/"},
            ],
        },
    },
    {
        "slug": "momo",
        "name": "MoMo",
        "provider": "momo",
        "description": "Vietnam MoMo e-wallet checkout",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "partner_code", "label": "Partner code", "required": True},
            {"key": "access_key", "label": "Access key", "required": True},
            {"key": "secret_key", "label": "Secret key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Apply on MoMo for Business, then copy Partner code, Access key, and Secret key from the MoMo merchant dashboard.",
            "steps": [
                "Open MoMo for Business and apply for website / app payment (captureWallet).",
                "After approval, log in to the MoMo merchant dashboard / developer console.",
                "Copy Partner code, Access key, and Secret key. Use the test environment first.",
                "Paste all three below → Save & verify.",
            ],
            "links": [
                {"label": "MoMo for Business", "url": "https://business.momo.vn/"},
                {"label": "MoMo developer docs", "url": "https://developers.momo.vn/"},
            ],
        },
    },
    {
        "slug": "zalopay",
        "name": "ZaloPay",
        "provider": "zalopay",
        "description": "Vietnam ZaloPay wallet checkout",
        "regions": ("sea",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "app_id", "label": "App ID", "required": True},
            {"key": "key1", "label": "Key 1", "type": "password", "required": True},
            {"key": "key2", "label": "Key 2 (callback)", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Register as a ZaloPay merchant, then copy App ID, Key1, and Key2 from the ZaloPay merchant admin.",
            "steps": [
                "Apply as a ZaloPay merchant for website checkout.",
                "Log in to ZaloPay merchant admin after they issue an account.",
                "Open integration / API and copy App ID, Key1 (create order), and Key2 (callback).",
                "Paste App ID + Key1 below → Save & verify.",
            ],
            "links": [
                {"label": "ZaloPay for merchants", "url": "https://zalopay.vn/"},
                {"label": "ZaloPay developer docs", "url": "https://docs.zalopay.vn/"},
            ],
        },
    },
    {
        "slug": "kakao_pay",
        "name": "Kakao Pay",
        "provider": "kakao_pay",
        "description": "Korea Kakao Pay hosted checkout",
        "regions": ("kr",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "cid", "label": "CID (가맹점 코드)", "required": True},
            {"key": "admin_key", "label": "Admin key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Apply as a Kakao Pay merchant, then copy CID and Admin key from Kakao Pay merchants / developers.",
            "steps": [
                "Apply on Kakao Pay for merchants (온라인 결제). Complete business verification.",
                "Open Kakao developers / Kakao Pay merchant admin after approval.",
                "Copy CID (가맹점 코드) and Admin key. Use the test CID first if they issued one.",
                "Paste both below → Save & verify. Customers pay on Kakao Pay’s hosted page.",
            ],
            "links": [
                {"label": "Kakao Pay merchants", "url": "https://www.kakaopay.com/"},
                {"label": "Kakao Pay developers", "url": "https://developers.kakaopay.com/"},
            ],
        },
    },
    {
        "slug": "toss",
        "name": "Toss Payments",
        "provider": "toss",
        "description": "Korea Toss Payments hosted checkout",
        "regions": ("kr",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "client_key", "label": "Client key", "placeholder": "test_ck_… or live_ck_…", "required": True},
            {"key": "secret_key", "label": "Secret key", "type": "password", "placeholder": "test_sk_… or live_sk_…", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Toss Payments merchant account, then copy Client key and Secret key from the developer console.",
            "steps": [
                "Apply at Toss Payments (토스페이먼츠) as an online merchant.",
                "Developer console → API keys. Copy Client key (ck_) and Secret key (sk_). Use test_ keys first.",
                "Paste both below → Save & verify. Customers pay on Toss’s hosted checkout.",
            ],
            "links": [
                {"label": "Toss Payments — become a merchant", "url": "https://www.tosspayments.com/"},
                {"label": "Toss Payments developer console", "url": "https://developers.tosspayments.com/"},
            ],
        },
    },
    {
        "slug": "naver_pay",
        "name": "Naver Pay",
        "provider": "naver_pay",
        "description": "Korea Naver Pay checkout",
        "regions": ("kr",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "client_id", "label": "Client ID", "required": True},
            {"key": "client_secret", "label": "Client Secret", "type": "password", "required": True},
            {"key": "chain_id", "label": "Chain ID (가맹점)", "required": True},
        ],
        "setup_guide": {
            "summary": "Apply as a Naver Pay merchant, then copy Client ID, Client Secret, and Chain ID from Naver Pay Center.",
            "steps": [
                "Apply at Naver Pay Center (네이버페이 센터) for 온라인 결제.",
                "After approval, open 개발자센터 / API. Copy Client ID, Client Secret, and Chain ID.",
                "Copy the live Client ID, Client Secret, and Chain ID.",
                "Paste all three below → Save & verify. Customers pay on Naver Pay’s hosted page.",
            ],
            "links": [
                {"label": "Naver Pay Center (merchant)", "url": "https://admin.pay.naver.com/"},
                {"label": "Naver Pay developers", "url": "https://developer.pay.naver.com/"},
            ],
        },
    },
    {
        "slug": "au_pay",
        "name": "au PAY",
        "provider": "au_pay",
        "description": "Japan au PAY online checkout",
        "regions": ("jp",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_MERCHANT,
        ],
        "setup_guide": {
            "summary": "Apply as an au PAY online merchant (KDDI), then copy Merchant ID and API keys from the au PAY merchant console.",
            "steps": [
                "Apply for au PAY オンライン決済 on the KDDI / au PAY merchant site.",
                "After underwriting, log in to the au PAY merchant console they issue.",
                "API / 接続情報 → copy Merchant ID, API Key, and API Secret.",
                "Paste those values below → Save & verify.",
            ],
            "links": [
                {"label": "au PAY — merchant (加盟店)", "url": "https://www.au.com/payment/aupay/"},
            ],
        },
    },
    {
        "slug": "d_barai",
        "name": "d払い",
        "provider": "d_barai",
        "description": "Japan d払い (NTT docomo) online checkout",
        "regions": ("jp",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_MERCHANT,
        ],
        "setup_guide": {
            "summary": "Apply for d払い オンライン決済, then copy shop ID and API keys from the docomo merchant console.",
            "steps": [
                "Apply for d払い オンライン決済 on the NTT docomo merchant site.",
                "After approval, log in to the d払い merchant / 加盟店 console.",
                "Copy Merchant / Shop ID, API Key, and API Secret from 接続情報.",
                "Paste those values below → Save & verify. Customers pay in the d払い app.",
            ],
            "links": [
                {"label": "d払い — merchant apply (加盟店)", "url": "https://service.smt.docomo.ne.jp/keitai_payment/index.html"},
            ],
        },
    },
    {
        "slug": "merpay",
        "name": "Merpay",
        "provider": "merpay",
        "description": "Japan Merpay (Mercari) online checkout",
        "regions": ("jp",),
        "checkout_ready": True,
        "credential_fields": [
            *_CRED_CLIENT,
            {"key": "merchant_id", "label": "Merchant ID"},
        ],
        "setup_guide": {
            "summary": "Apply as a Merpay online merchant, then copy Client ID and Client Secret from the Merpay merchant console.",
            "steps": [
                "Apply for Merpay オンライン決済 on the Mercari / Merpay merchant site.",
                "After approval, open the Merpay merchant console.",
                "API → copy Client ID and Client Secret (and Merchant ID if shown).",
                "Paste those values below → Save & verify. Customers pay with Merpay.",
            ],
            "links": [
                {"label": "Merpay — merchants", "url": "https://merpay.com/"},
            ],
        },
    },
    {
        "slug": "affirm",
        "name": "Affirm",
        "provider": "affirm",
        "description": "US BNPL hosted checkout",
        "regions": ("us",),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "public_key", "label": "Public API key", "required": True},
            {"key": "private_key", "label": "Private API key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Apply as an Affirm merchant, then copy Public and Private API keys from the Affirm Merchant Dashboard.",
            "steps": [
                "Apply at Affirm for Business (US merchants).",
                "Merchant Dashboard → API keys. Copy the live Public key and Private key.",
                "Paste both below → Save & verify. Customers complete Affirm’s hosted checkout.",
            ],
            "links": [
                {"label": "Affirm for Business (merchant apply)", "url": "https://www.affirm.com/business"},
                {"label": "Affirm Merchant Dashboard", "url": "https://www.affirm.com/dashboard"},
                {"label": "Affirm Checkout API", "url": "https://docs.affirm.com/developers/reference/direct"},
            ],
        },
    },
    {
        "slug": "amazon_pay",
        "name": "Amazon Pay",
        "provider": "amazon_pay",
        "description": "Amazon Pay Checkout v2 — US, Japan, EU",
        "regions": ("us", "jp", "eu", "uk"),
        "checkout_ready": True,
        "credential_fields": [
            {"key": "store_id", "label": "Store ID", "placeholder": "amzn1.application-oa2-client.…", "required": True},
            {"key": "public_key_id", "label": "Public key ID", "required": True},
            {"key": "private_key", "label": "Private key (PEM)", "type": "textarea", "required": True},
            {"key": "merchant_id", "label": "Merchant ID"},
            {"key": "region", "label": "Region", "type": "select", "options": ["na", "eu", "jp"], "required": True},
        ],
        "setup_guide": {
            "summary": "Register Amazon Pay in Seller Central / Amazon Pay Console, create an API key pair, then paste Store ID, Public key ID, and the PEM private key.",
            "steps": [
                "Open Amazon Pay (Seller Central or Amazon Pay Console) and complete merchant registration for US, EU, or Japan.",
                "Integration / API keys → create a key pair. Download the private key (PEM). Copy Public key ID and Store ID.",
                "Use Sandbox first. Paste Store ID, Public key ID, and PEM private key below. Set Region (na / eu / jp) to match the account.",
                "Save & verify. Customers pay on Amazon Pay’s hosted checkout.",
            ],
            "links": [
                {"label": "Amazon Pay — get started (merchant)", "url": "https://pay.amazon.com/"},
                {"label": "Amazon Pay Console", "url": "https://pay.amazon.com/signup"},
                {"label": "Amazon Pay Checkout v2 docs", "url": "https://developer.amazon.com/docs/amazon-pay-api-v2/introduction.html"},
            ],
        },
    },
)

REPUTATION_PLUGINS: tuple[dict[str, Any], ...] = (
    {
        "slug": "yelp",
        "name": "Yelp",
        "provider": "yelp",
        "description": "US, UK, AU local reviews",
        "regions": ("us", "uk", "au"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Claim the business on Yelp for Business Owners, then paste the listing ID (and Fusion API key if you have one).",
            "steps": [
                "Open Yelp for Business Owners and claim or create your listing.",
                "After you own the page, copy the Business ID from the listing URL (the number after /biz/) or from Business information.",
                "If Yelp issued Fusion API access, copy the API key from the owner tools they gave you. Listing ID alone is enough to connect.",
                "Paste Business ID (and API key if you have it) below → Save & verify.",
            ],
            "links": [
                {"label": "Yelp for Business Owners", "url": "https://biz.yelp.com/"},
            ],
        },
    },
    {
        "slug": "tripadvisor",
        "name": "Tripadvisor",
        "provider": "tripadvisor",
        "description": "Global travel & hospitality reviews",
        "regions": ("global", "us", "eu", "uk", "au", "sea", "hk", "tw", "mo"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Claim the property on Tripadvisor for owners, then paste the location ID from your listing.",
            "steps": [
                "Open Tripadvisor for business owners and claim or list your property.",
                "After you have access, open your listing. The location ID is the number in the URL (e.g. -d123456).",
                "Paste that ID as Business ID. Add an API key only if Tripadvisor issued one to your owner account.",
                "Save & verify.",
            ],
            "links": [
                {"label": "Tripadvisor for Business — restaurants", "url": "https://www.tripadvisor.com/business/restaurants"},
                {"label": "Tripadvisor — claim restaurant listing", "url": "https://www.tripadvisor.com/business/claim-restaurant-listing-free"},
            ],
        },
    },
    {
        "slug": "tablelog",
        "name": "Tabelog",
        "provider": "tablelog",
        "description": "Japan restaurant reviews",
        "regions": ("jp",),
        "capabilities": ("read_reviews", "reservation_feedback"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Register as a Tabelog 店舗会員, then copy the restaurant ID from the owner console.",
            "steps": [
                "Confirm the shop is already listed on Tabelog, then apply for 店舗会員 (free) with a business license photo.",
                "After review, open the email and complete first login on the owner console.",
                "Copy the restaurant ID from the owner dashboard or from the shop URL (rcd=…).",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Tabelog owner console login", "url": "https://owner.tabelog.com/"},
                {"label": "Tabelog — register as store member", "url": "https://owner.tabelog.com/home/registration/"},
            ],
        },
    },
    {
        "slug": "opentable",
        "name": "OpenTable",
        "provider": "opentable",
        "description": "US, UK, AU, EU, Hong Kong restaurant reviews",
        "regions": ("us", "uk", "au", "eu", "hk"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join OpenTable as a restaurant, then copy the Restaurant ID from GuestCenter.",
            "steps": [
                "Apply as an OpenTable restaurant partner.",
                "Log in to GuestCenter / restaurant admin.",
                "Open Restaurant settings and copy the Restaurant ID.",
                "Paste as Business ID. Add an API key only if OpenTable issued partner API access.",
                "Save & verify.",
            ],
            "links": [
                {"label": "OpenTable for restaurants", "url": "https://restaurant.opentable.com/"},
                {"label": "OpenTable GuestCenter login", "url": "https://restaurant.opentable.com/"},
            ],
        },
    },
    {
        "slug": "trustpilot",
        "name": "Trustpilot",
        "provider": "trustpilot",
        "description": "EU, UK, US, AU consumer reviews",
        "regions": ("eu", "uk", "us", "au"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "business_unit_id", "label": "Business Unit ID", "required": True},
            {"key": "api_key", "label": "API Key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Claim the profile on Trustpilot Business, then copy Business Unit ID and API key.",
            "steps": [
                "Create or claim your company profile on Trustpilot Business.",
                "Integrations → API → create an application.",
                "Copy Business Unit ID and API key.",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "Trustpilot Business (merchant)", "url": "https://business.trustpilot.com/"},
            ],
        },
    },
    {
        "slug": "gurunavi",
        "name": "Gurunavi",
        "provider": "gurunavi",
        "description": "Japan dining guide reviews",
        "regions": ("jp",),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Register the restaurant with Gurunavi for shops, then copy the Shop ID from shop admin.",
            "steps": [
                "Apply to list / manage the restaurant on Gurunavi’s shop (店舗) programme.",
                "Log in to shop management after they issue an account.",
                "Copy Shop ID from the admin header or from the shop URL.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Gurunavi for restaurants (店舗)", "url": "https://pro.gnavi.co.jp/"},
            ],
        },
    },
    {
        "slug": "hot_pepper",
        "name": "Hot Pepper Gourmet",
        "provider": "hot_pepper",
        "description": "Japan (Recruit) restaurant reviews",
        "regions": ("jp",),
        "capabilities": ("read_reviews",),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Register on Hot Pepper Gourmet 店舗管理, then copy the store code from the admin.",
            "steps": [
                "Apply for a Hot Pepper Gourmet store (店舗) account with Recruit.",
                "Log in to 店舗管理画面 after they issue an ID.",
                "Copy the store code from the admin home or from the shop URL.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Hot Pepper Gourmet — store admin login", "url": "https://www.cms.hotpepper.jp/CLN/login/"},
            ],
        },
    },
    {
        "slug": "booking_com",
        "name": "Booking.com",
        "provider": "booking_com",
        "description": "Global hospitality reviews",
        "regions": ("global", "eu", "uk", "us", "au", "sea", "hk", "tw", "mo"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "hotel_id", "label": "Property ID", "required": True},
            {"key": "api_key", "label": "Connectivity API key", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Join Booking.com as a property partner, then copy the Property ID from the extranet.",
            "steps": [
                "Create or log in to a Booking.com partner (extranet) account.",
                "Open the property in the extranet. Property ID is in the URL and on the property home.",
                "Paste Property ID. Add a Connectivity API key only if Booking issued one.",
                "Save & verify.",
            ],
            "links": [
                {"label": "Booking.com partner extranet", "url": "https://admin.booking.com/"},
                {"label": "Booking.com — list your property", "url": "https://join.booking.com/"},
            ],
        },
    },
    {
        "slug": "agoda",
        "name": "Agoda",
        "provider": "agoda",
        "description": "SEA & APAC hospitality reviews",
        "regions": ("sea", "au", "hk", "tw", "mo", "global"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Register the property on Agoda YCS, then copy the Property ID from the extranet.",
            "steps": [
                "Sign in to Agoda YCS (Yield Control System) as a property partner.",
                "Open the property. Copy Property ID from the extranet header or property settings.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Agoda YCS (property partner)", "url": "https://ycs.agoda.com/"},
            ],
        },
    },
    {
        "slug": "uber_eats",
        "name": "Uber Eats",
        "provider": "uber_eats",
        "description": "Delivery reviews — US, UK, AU, JP, EU, Hong Kong, Taiwan",
        "regions": ("us", "uk", "au", "jp", "eu", "hk", "tw"),
        "capabilities": ("read_reviews",),
        "credential_fields": [
            {"key": "store_id", "label": "Store UUID", "required": True},
            {"key": "client_id", "label": "API Client ID", "required": True},
            {"key": "client_secret", "label": "Client Secret", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open Uber Eats Manager, copy the Store UUID, then add API Client ID and Secret if Uber issued them.",
            "steps": [
                "Log in to Uber Eats Manager for the restaurant.",
                "Store settings → copy Store UUID.",
                "If you have Uber API access: create an app and copy Client ID and Client Secret.",
                "Paste Store UUID, Client ID, and Client Secret below → Save & verify.",
            ],
            "links": [
                {"label": "Uber Eats Manager (merchant)", "url": "https://www.uber.com/us/en/deliver/"},
            ],
        },
    },
    {
        "slug": "deliveroo",
        "name": "Deliveroo",
        "provider": "deliveroo",
        "description": "UK, EU, AU, Hong Kong delivery reviews",
        "regions": ("uk", "eu", "au", "hk"),
        "capabilities": ("read_reviews",),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join Deliveroo as a restaurant partner, then copy the Site ID from Partner Hub.",
            "steps": [
                "Register or log in at Deliveroo Partner Hub.",
                "Open the restaurant. Copy Site ID from store settings.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Deliveroo Partner Hub", "url": "https://restaurants.deliveroo.com/en"},
            ],
        },
    },
    {
        "slug": "foursquare",
        "name": "Foursquare",
        "provider": "foursquare",
        "description": "Global location reviews & tips",
        "regions": ("global", "us", "eu", "uk", "au", "hk", "tw", "mo"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "venue_id", "label": "Venue ID", "required": True},
            {"key": "api_key", "label": "API Key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Claim the venue on Foursquare for business, then paste Venue ID (and API key if issued).",
            "steps": [
                "Open Foursquare for Business and claim or create the venue.",
                "Copy Venue ID from the venue page or owner tools.",
                "If Foursquare issued an API key for your business project, add it. Venue ID alone can connect.",
                "Paste Venue ID (and API key if you have it) below → Save & verify.",
            ],
            "links": [
                {"label": "Foursquare for Business", "url": "https://location.foursquare.com/"},
            ],
        },
    },
    {
        "slug": "facebook_reviews",
        "name": "Facebook Reviews",
        "provider": "facebook",
        "description": "Meta business page recommendations",
        "regions": ("global", "us", "eu", "uk", "au", "sea", "latam", "hk", "tw", "mo"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "page_id", "label": "Facebook Page ID", "required": True},
            {"key": "access_token", "label": "Page Access Token", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Claim the Page in Meta Business Suite, then paste Page ID and a Page access token.",
            "steps": [
                "Log in to Meta Business Suite and claim or create the Facebook Page.",
                "Page settings → Page info → copy Page ID.",
                "In Meta Business / Events Manager (or the token tool Meta gives business users), create a Page access token with pages_read_engagement / pages_read_user_content.",
                "Paste Page ID and the token below → Save & verify.",
            ],
            "links": [
                {"label": "Meta Business Suite", "url": "https://www.facebook.com/business"},
            ],
        },
    },
    {
        "slug": "zomato",
        "name": "Zomato",
        "provider": "zomato",
        "description": "India, UAE, SEA restaurant reviews",
        "regions": ("sea", "global"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join Zomato as a restaurant partner, then copy the Restaurant ID from the partner dashboard.",
            "steps": [
                "Apply to partner with Zomato for your outlet.",
                "After approval, log in to the partner dashboard.",
                "Copy Restaurant ID from outlet settings.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Zomato — partner with us (merchant)", "url": "https://www.zomato.com/partner-with-us"},
            ],
        },
    },
    {
        "slug": "grab_reviews",
        "name": "GrabFood Reviews",
        "provider": "grab",
        "description": "SEA & Hong Kong delivery platform ratings",
        "regions": ("sea", "hk"),
        "capabilities": ("read_reviews",),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Register the outlet on GrabMerchant, then copy Outlet ID from the store profile.",
            "steps": [
                "Sign up or log in on GrabMerchant.",
                "Open the outlet → Store profile. Copy Outlet ID.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "GrabMerchant signup", "url": "https://www.grab.com/sg/merchant/"},
                {"label": "GrabMerchant Portal login", "url": "https://merchant.grab.com/"},
            ],
        },
    },
    {
        "slug": "holidaycheck",
        "name": "HolidayCheck",
        "provider": "holidaycheck",
        "description": "EU travel reviews (DACH focus)",
        "regions": ("eu",),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Register the property on HolidayCheck hotel admin, then copy the Property ID.",
            "steps": [
                "Log in to HolidayCheck hotel admin as the property owner.",
                "Open the property and copy Property ID from settings.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "HolidayCheck Business Center (merchant)", "url": "https://www.holidaycheck.com/"},
            ],
        },
    },
    {
        "slug": "capterra",
        "name": "Capterra",
        "provider": "capterra",
        "description": "B2B software reviews — US, global",
        "regions": ("us", "global", "eu", "uk", "au"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "List the product on Capterra for vendors, then copy the product / listing ID.",
            "steps": [
                "Sign up as a Capterra vendor and claim or create the product listing.",
                "Vendor portal → copy Product / listing ID.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Capterra vendor signup", "url": "https://www.capterra.com/vendors/"},
            ],
        },
    },
    {
        "slug": "openrice",
        "name": "OpenRice",
        "provider": "openrice",
        "description": "OpenRice restaurant reviews — Hong Kong, Taiwan, Macau",
        "regions": ("hk", "tw", "mo"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Log in to OpenRice Biz, then copy the restaurant ID from the merchant dashboard.",
            "steps": [
                "Open OpenRice Biz and create a free merchant account, or log in with the email OpenRice issued.",
                "Select Hong Kong / Taiwan / Macau, then pick the restaurant.",
                "Copy the restaurant ID from the dashboard or from the listing URL (the number after /restaurant/).",
                "Paste as Business ID. Add an API key only if OpenRice issued one. Save & verify.",
            ],
            "links": [
                {"label": "OpenRice Biz (merchant login)", "url": "https://merchant.openrice.com/en/hongkong"},
            ],
        },
    },
    {
        "slug": "foodpanda_reviews",
        "name": "foodpanda Reviews",
        "provider": "foodpanda",
        "description": "foodpanda store ratings — Hong Kong & Taiwan",
        "regions": ("hk", "tw"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "business_id", "label": "Vendor / store ID", "required": True},
            {"key": "api_key", "label": "Partner API key", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Log in to Panda Partner, then copy the vendor / store ID from store settings.",
            "steps": [
                "Log in to Panda Partner (foodpanda restaurant / shop portal) with the email they issued at onboarding.",
                "Open the Hong Kong or Taiwan outlet → Store settings.",
                "Copy Vendor / store ID (Vendor Identifier).",
                "If Delivery Hero issued a partner API key, add it. Otherwise the store ID is enough.",
                "Paste below → Save & verify.",
            ],
            "links": [
                {"label": "Panda Partner (merchant login)", "url": "https://partner.foodpanda.com/login"},
            ],
        },
    },

    {
        "slug": "thefork",
        "name": "TheFork",
        "provider": "thefork",
        "description": "Europe & Hong Kong restaurant reservations + reviews",
        "regions": ("eu", "hk"),
        "capabilities": ("read_reviews", "read_rating", "reservation_feedback"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join TheFork as a restaurant, then copy the restaurant ID from TheFork Manager.",
            "steps": [
                "Apply as a TheFork restaurant partner (Europe or Hong Kong).",
                "Log in to TheFork Manager after they issue an account.",
                "Copy Restaurant ID from settings or from the listing URL.",
                "Paste as Business ID. Add an API key only if TheFork issued partner API access. Save & verify.",
            ],
            "links": [
                {"label": "TheFork Manager — for restaurants", "url": "https://www.theforkmanager.com/en/get-started"},
                {"label": "TheFork Manager", "url": "https://www.theforkmanager.com/en/"},
            ],
        },
    },
    {
        "slug": "resy",
        "name": "Resy",
        "provider": "resy",
        "description": "US restaurant reservations + guest reviews",
        "regions": ("us",),
        "capabilities": ("read_reviews", "reservation_feedback"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join Resy as a restaurant, then copy the venue ID from Resy OS.",
            "steps": [
                "Apply to join Resy as a restaurant partner.",
                "Log in to Resy OS after they issue access.",
                "Copy Venue / restaurant ID from venue settings.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Resy — join as a restaurant", "url": "https://resy.com/join"},
                {"label": "Resy OS (merchant)", "url": "https://os.resy.com/"},
            ],
        },
    },
    {
        "slug": "chope",
        "name": "Chope",
        "provider": "chope",
        "description": "Singapore & Hong Kong reservations + reviews",
        "regions": ("sea", "hk"),
        "capabilities": ("read_reviews", "reservation_feedback"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join Chope as a restaurant partner, then copy the outlet ID from Chope Merchant.",
            "steps": [
                "Apply as a Chope restaurant partner (Singapore / Hong Kong).",
                "Log in to Chope Merchant after they issue an account.",
                "Copy Outlet / restaurant ID from store settings.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Chope — for restaurants", "url": "https://www.chope.co/singapore-restaurants/pages/for-restaurants"},
                {"label": "Chope Merchant login", "url": "https://merchant.chope.co/"},
            ],
        },
    },
    {
        "slug": "keeta",
        "name": "KeeTa",
        "provider": "keeta",
        "description": "Hong Kong KeeTa (Keeta) delivery store ratings",
        "regions": ("hk",),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "business_id", "label": "Store / vendor ID", "required": True},
            {"key": "api_key", "label": "Partner API key", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Join KeeTa as a restaurant partner, then copy the store ID from the KeeTa merchant app / portal.",
            "steps": [
                "Apply as a KeeTa (Keeta) restaurant partner in Hong Kong.",
                "Log in to the KeeTa merchant app or merchant portal they issue.",
                "Store settings → copy Store / vendor ID.",
                "Paste as Store ID. Add a partner API key only if KeeTa issued one. Save & verify.",
            ],
            "links": [
                {"label": "KeeTa — merchants (Hong Kong)", "url": "https://www.keeta-global.com/"},
            ],
        },
    },
    {
        "slug": "hungrypanda",
        "name": "HungryPanda",
        "provider": "hungrypanda",
        "description": "Global Chinese delivery platform ratings",
        "regions": ("global", "uk", "us", "au", "eu", "hk"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join HungryPanda as a restaurant partner, then copy the shop ID from the merchant portal.",
            "steps": [
                "Apply as a HungryPanda restaurant partner.",
                "Log in to the HungryPanda merchant portal after onboarding.",
                "Copy Shop / restaurant ID from outlet settings.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "HungryPanda — partner with us", "url": "https://www.hungrypanda.co/merchants/"},
                {"label": "HungryPanda merchant portal", "url": "https://merchant.hungrypanda.co/"},
            ],
        },
    },
    {
        "slug": "klook",
        "name": "Klook",
        "provider": "klook",
        "description": "Experiences & dining reviews — Hong Kong, Taiwan, SEA",
        "regions": ("hk", "tw", "sea"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join Klook as an activity / dining merchant, then copy the product or merchant ID from Klook Partner.",
            "steps": [
                "Apply on Klook Partner (experiences or dining).",
                "Log in to Klook Partner after approval.",
                "Copy Merchant / product ID from the listing.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "Klook Partner (merchant)", "url": "https://merchant.klook.com/introduction"},
                {"label": "Klook Merchant Portal login", "url": "https://merchant.klook.com/"},
            ],
        },
    },
    {
        "slug": "kkday",
        "name": "KKday",
        "provider": "kkday",
        "description": "Experiences & dining reviews — Taiwan, Hong Kong, SEA",
        "regions": ("tw", "hk", "sea"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Join KKday as a supplier, then copy the product / supplier ID from KKday Supplier Center.",
            "steps": [
                "Apply on KKday Supplier Center.",
                "After approval, open the product in Supplier Center.",
                "Copy Product / supplier ID.",
                "Paste as Business ID → Save & verify.",
            ],
            "links": [
                {"label": "KKday Supplier Center", "url": "https://scm.kkday.com/"},
            ],
        },
    },
    {
        "slug": "expedia",
        "name": "Expedia",
        "provider": "expedia",
        "description": "Global hotel guest reviews (Expedia Partner Central)",
        "regions": ("global", "us", "eu", "uk", "au", "sea", "hk", "tw", "jp"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "property_id", "label": "Property ID", "required": True},
            {"key": "api_key", "label": "Partner API key", "type": "password"},
        ],
        "setup_guide": {
            "summary": "List the property on Expedia Partner Central, then copy the Property ID from the extranet.",
            "steps": [
                "Create or log in to Expedia Partner Central.",
                "Open the property. Property ID is on the property home and in the URL.",
                "Paste Property ID. Add a Connectivity API key only if Expedia issued one.",
                "Save & verify.",
            ],
            "links": [
                {"label": "Expedia Partner Central", "url": "https://www.expediapartnercentral.com/"},
                {"label": "Expedia — list your property", "url": "https://apps.expediapartnercentral.com/en_US/list"},
            ],
        },
    },
    {
        "slug": "trip_com",
        "name": "Trip.com",
        "provider": "trip_com",
        "description": "Global hotel guest reviews (Trip.com eBooking)",
        "regions": ("global", "hk", "tw", "sea", "jp", "us", "eu"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "property_id", "label": "Hotel / property ID", "required": True},
            {"key": "api_key", "label": "Partner API key", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Join Trip.com as a property partner, then copy the Hotel ID from eBooking.",
            "steps": [
                "Create or log in to Trip.com eBooking (property extranet).",
                "Open the property. Copy Hotel / property ID from the header or property settings.",
                "Paste as Hotel ID. Add a partner API key only if Trip.com issued one.",
                "Save & verify.",
            ],
            "links": [
                {"label": "Trip.com eBooking (merchant)", "url": "https://ebooking.trip.com/"},
            ],
        },
    },
    {
        "slug": "g2",
        "name": "G2",
        "provider": "g2",
        "description": "B2B software reviews — global",
        "regions": ("global", "us", "eu", "uk"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": _CRED_REVIEW,
        "setup_guide": {
            "summary": "Claim the product on G2 as a vendor, then copy the product ID from G2 Seller.",
            "steps": [
                "Sign up as a G2 vendor and claim or create the product listing.",
                "G2 Seller / vendor portal → copy Product ID.",
                "Paste as Business ID. Add an API key only if G2 issued one.",
                "Save & verify.",
            ],
            "links": [
                {"label": "G2 Seller (vendor)", "url": "https://sell.g2.com/"},
            ],
        },
    },
    {
        "slug": "reviews_io",
        "name": "Reviews.io",
        "provider": "reviews_io",
        "description": "UK & EU independent review platform",
        "regions": ("uk", "eu"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "store_id", "label": "Store ID", "required": True},
            {"key": "api_key", "label": "API key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Create a Reviews.io merchant account, then copy Store ID and API key from Integrations.",
            "steps": [
                "Sign up at Reviews.io as the business owner.",
                "Integrations → API. Copy Store ID and API key.",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "Reviews.io — merchant signup", "url": "https://www.reviews.io/"},
                {"label": "Reviews.io dashboard", "url": "https://dash.reviews.io/"},
            ],
        },
    },
    {
        "slug": "feefo",
        "name": "Feefo",
        "provider": "feefo",
        "description": "UK & EU verified reviews",
        "regions": ("uk", "eu"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "merchant_identifier", "label": "Merchant identifier", "required": True},
            {"key": "api_key", "label": "API key", "type": "password", "required": True},
        ],
        "setup_guide": {
            "summary": "Open a Feefo merchant account, then copy Merchant identifier and API key from Feefo Hub.",
            "steps": [
                "Sign up as a Feefo merchant (UK / EU businesses).",
                "Feefo Hub → Integrations / API. Copy Merchant identifier and API key.",
                "Paste both below → Save & verify.",
            ],
            "links": [
                {"label": "Feefo — for businesses", "url": "https://business.feefo.com/"},
                {"label": "Feefo Hub login", "url": "https://www.feefo.com/"},
            ],
        },
    },
    {
        "slug": "trusted_shops",
        "name": "Trusted Shops",
        "provider": "trusted_shops",
        "description": "EU / UK Trusted Shops buyer reviews",
        "regions": ("eu", "uk"),
        "capabilities": ("read_reviews", "read_rating"),
        "credential_fields": [
            {"key": "tsid", "label": "Trusted Shops ID (TSID)", "required": True},
            {"key": "api_key", "label": "API client secret", "type": "password"},
        ],
        "setup_guide": {
            "summary": "Join Trusted Shops as a member shop, then copy the TSID from eTrusted / my.trustedshops.",
            "steps": [
                "Apply as a Trusted Shops member (EU / UK webshop).",
                "Log in to eTrusted / my.trustedshops after membership is active.",
                "Copy Trusted Shops ID (TSID) from shop settings.",
                "Paste TSID. Add an API client secret only if Trusted Shops issued one. Save & verify.",
            ],
            "links": [
                {"label": "Trusted Shops — for businesses", "url": "https://www.trustedshops.com/"},
                {"label": "eTrusted / member login", "url": "https://my.trustedshops.com/"},
            ],
        },
    },

)

from integration_catalog_batch2 import (
    BATCH2_SIMPLE_ICONS,
    EXTRA_BRAND_COLORS,
    EXTRA_BRAND_INITIALS,
    EXTRA_PAYMENT_PLUGINS,
    EXTRA_PLUGIN_BRANDS,
    EXTRA_REPUTATION_PLUGINS,
)
from integration_catalog_batch3 import (
    BATCH3_SIMPLE_ICONS,
    EXTRA_BRAND_COLORS as BATCH3_BRAND_COLORS,
    EXTRA_BRAND_INITIALS as BATCH3_BRAND_INITIALS,
    EXTRA_PAYMENT_PLUGINS as BATCH3_PAYMENT_PLUGINS,
    EXTRA_PLUGIN_BRANDS as BATCH3_PLUGIN_BRANDS,
)
from integration_catalog_china import (
    EXTRA_BRAND_COLORS as CHINA_BRAND_COLORS,
    EXTRA_BRAND_INITIALS as CHINA_BRAND_INITIALS,
    EXTRA_PAYMENT_PLUGINS as CHINA_PAYMENT_PLUGINS,
    EXTRA_PLUGIN_BRANDS as CHINA_PLUGIN_BRANDS,
    EXTRA_REPUTATION_PLUGINS as CHINA_REPUTATION_PLUGINS,
)

PLUGIN_BRANDS.update(EXTRA_PLUGIN_BRANDS)
PLUGIN_BRANDS.update(BATCH3_PLUGIN_BRANDS)
PLUGIN_BRANDS.update(CHINA_PLUGIN_BRANDS)
BRAND_COLORS.update(EXTRA_BRAND_COLORS)
BRAND_COLORS.update(BATCH3_BRAND_COLORS)
BRAND_COLORS.update(CHINA_BRAND_COLORS)
BRAND_INITIALS.update(EXTRA_BRAND_INITIALS)
BRAND_INITIALS.update(BATCH3_BRAND_INITIALS)
BRAND_INITIALS.update(CHINA_BRAND_INITIALS)

PAYMENT_PLUGINS = PAYMENT_PLUGINS + EXTRA_PAYMENT_PLUGINS + BATCH3_PAYMENT_PLUGINS + CHINA_PAYMENT_PLUGINS
REPUTATION_PLUGINS = REPUTATION_PLUGINS + EXTRA_REPUTATION_PLUGINS + CHINA_REPUTATION_PLUGINS

# Google-owned integrations are retired from the product surface.
REMOVED_CATALOG_SLUGS = frozenset({
    "google_calendar",
    "google_business",
    "google_reviews",
    "google_customer_reviews",
    "google_pay",
    "youtube_brand",
})


def payment_plugin_slugs() -> tuple[str, ...]:
    return tuple(p["slug"] for p in PAYMENT_PLUGINS if p["slug"] not in REMOVED_CATALOG_SLUGS)


def reputation_plugin_slugs() -> tuple[str, ...]:
    return tuple(p["slug"] for p in REPUTATION_PLUGINS if p["slug"] not in REMOVED_CATALOG_SLUGS)


def get_payment_plugin(slug: str) -> dict[str, Any] | None:
    return next((p for p in PAYMENT_PLUGINS if p["slug"] == slug), None)


def get_reputation_plugin(slug: str) -> dict[str, Any] | None:
    return next((p for p in REPUTATION_PLUGINS if p["slug"] == slug), None)


def all_plugin_seeds() -> tuple[dict[str, Any], ...]:
    seeds = []
    for p in PAYMENT_PLUGINS:
        if p["slug"] in REMOVED_CATALOG_SLUGS:
            continue
        seeds.append({
            "slug": p["slug"],
            "name": p["name"],
            "provider": p["provider"],
            "description": p["description"],
            "category": "payments",
        })
    for p in REPUTATION_PLUGINS:
        if p["slug"] in REMOVED_CATALOG_SLUGS:
            continue
        seeds.append({
            "slug": p["slug"],
            "name": p["name"],
            "provider": p["provider"],
            "description": p["description"],
            "category": "reputation",
        })
    return tuple(seeds)


def plugin_public_meta(slug: str) -> dict[str, Any] | None:
    p = get_payment_plugin(slug) or get_reputation_plugin(slug)
    if not p:
        return None
    return {
        "slug": p["slug"],
        "name": p["name"],
        "category": "payments" if "checkout_ready" in p else "reputation",
        "description": p["description"],
        "regions": list(p.get("regions", ())),
        "region_labels": [REGION_LABELS.get(r, r) for r in p.get("regions", ())],
        "checkout_ready": True if "checkout_ready" in p else False,
        "oauth_required": bool(p.get("oauth_required")),
        "capabilities": list(p.get("capabilities", ())),
        "credential_fields": p.get("credential_fields", []),
        "setup_guide": p.get("setup_guide", {}),
        "excluded_territories": list(EXCLUDED_TERRITORIES),
        "logo_url": plugin_logo_url(p["slug"]),
    }


def catalog_api_payload() -> dict[str, Any]:
    return {
        "excluded_territories": list(EXCLUDED_TERRITORIES),
        "regions": [{"id": k, "label": v} for k, v in REGION_LABELS.items()],
        "primary_regions": list(PRIMARY_REGIONS),
        "payments": [
            plugin_public_meta(p["slug"])
            for p in PAYMENT_PLUGINS
            if p["slug"] not in REMOVED_CATALOG_SLUGS
        ],
        "reputation": [
            plugin_public_meta(p["slug"])
            for p in REPUTATION_PLUGINS
            if p["slug"] not in REMOVED_CATALOG_SLUGS
        ],
    }


ensure_plugin_logos()
