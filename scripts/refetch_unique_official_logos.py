#!/usr/bin/env python3
"""Re-fetch unique official logos — strict matching, no fuzzy duplicates."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog import (  # noqa: E402
    BRAND_COLORS,
    PLUGIN_BRANDS,
    get_payment_plugin,
    get_reputation_plugin,
    payment_plugin_slugs,
    reputation_plugin_slugs,
)
from integration_catalog_batch2 import BATCH2_SIMPLE_ICONS  # noqa: E402
from integration_catalog_batch3 import BATCH3_SIMPLE_ICONS  # noqa: E402
from scripts.fetch_official_logos import OFFICIAL, fetch, kind, save  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"
SIMPLE_ICONS_JSON = "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/data/simple-icons.json"
JSdelivr_ICON = "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/{slug}.svg"

# Explicit slug -> simple-icons file slug (never fuzzy).
SLUG_ICON: dict[str, str] = {
    **BATCH2_SIMPLE_ICONS,
    **BATCH3_SIMPLE_ICONS,
    "stripe": "stripe", "paypal": "paypal", "paypay": "paypay", "square": "square",
    "adyen": "adyen", "mollie": "mollie", "klarna": "klarna", "line_pay": "line",
    "rakuten_pay": "rakuten", "grabpay": "grab", "shopeepay": "shopee",
    "xendit": "xendit", "omise": "omise", "midtrans": "midtrans", "gocardless": "gocardless",
    "sumup": "sumup", "worldpay": "worldpay", "authorize_net": "authorize", "braintree": "braintree",
    "afterpay": "afterpay", "zip": "zip", "eway": "eway", "paystack": "paystack",
    "flutterwave": "flutterwave", "mercado_pago": "mercadopago", "yookassa": "yookassa",
    "razorpay": "razorpay", "alipay_hk": "alipay", "wechat_pay_hk": "wechat",
    "payme": "hsbc", "unionpay": "unionpay", "atome": "atome", "twoc2p": "2c2p",
    "airwallex": "airwallex", "checkout_com": "checkout", "octopus": "octopus",
    "gcash": "gcash", "maya": "paymaya", "touch_n_go": "touchngo", "duitnow": "duitnow",
    "truemoney": "truemoney", "momo": "momo", "zalopay": "zalopay", "kakao_pay": "kakaopay",
    "toss": "toss", "naver_pay": "naver", "merpay": "merpay", "affirm": "affirm",
    "amazon_pay": "amazon", "openrice": "openrice", "tripadvisor": "tripadvisor",
    "yelp": "yelp", "trustpilot": "trustpilot", "google_reviews": "google",
    "google_customer_reviews": "google", "facebook_reviews": "facebook",
    "instagram_business": "instagram", "linkedin_company": "linkedin",
    "booking_com": "bookingdotcom", "agoda": "agoda", "expedia": "expedia",
    "hotels_com": "hotelsdotcom", "hostelworld": "hostelworld", "airbnb": "airbnb",
    "deliveroo": "deliveroo", "doordash": "doordash", "uber_eats": "ubereats",
    "swiggy": "swiggy", "zomato": "zomato", "opentable": "opentable", "thefork": "thefork",
    "foursquare": "foursquare", "g2": "g2", "capterra": "capterra", "feefo": "feefo",
    "holidaycheck": "holidaycheck", "michelin_guide": "michelin", "gurunavi": "gurunavi",
    "kakao_map": "kakao", "naver_place": "naver", "klook": "klook", "kayak": "kayak",
    "skyscanner": "skyscanner", "trivago": "trivago", "traveloka": "traveloka",
    "tiktok_business": "tiktok", "tiktok_shop": "tiktok", "whatsapp_business": "whatsapp",
    "youtube_brand": "youtube", "clearpay": "afterpay", "venmo": "venmo", "sofort": "klarna",
    "grab_paylater": "grab", "hoolah": "atome", "shopify_payments": "shopify", "shop_pay": "shopify",
    "ideal": "ideal", "bancontact": "bancontact", "giropay": "giropay", "eps": "eps",
    "blik": "blik", "mb_way": "mbway", "bizum": "bizum", "satispay": "satispay",
    "twint": "twint", "vipps": "vipps", "swish": "swish", "trustly": "trustly",
    "przelewy24": "przelewy24", "revolut": "revolut", "wise": "wise", "payoneer": "payoneer",
    "paddle": "paddle", "fastspring": "fastspring", "cybersource": "cybersource",
    "global_payments": "globalpayments", "nuvei": "nuvei", "paysafe": "paysafe",
    "worldline": "worldline", "sezzle": "sezzle", "splitit": "splitit", "tabby": "tabby",
    "tamara": "tamara", "scalapay": "scalapay", "phonepe": "phonepe", "paytm": "paytm",
    "dana": "dana", "boost": "boost", "favepay": "fave", "paidy": "paidy",
    "samsung_pay": "samsungpay", "apple_pay": "applepay", "google_pay": "googlepay",
    "clover": "clover", "lightspeed": "lightspeed", "toast": "toast", "fiserv": "fiserv",
    "pagarme": "pagarme", "pagseguro": "pagseguro", "dlocal": "dlocal", "ebanx": "ebanx",
    "conekta": "conekta", "openpay": "openpay", "kushki": "kushki", "mpesa": "mpesa",
    "hyperpay": "hyperpay", "tap_payments": "tap", "paytabs": "paytabs", "fawry": "fawry",
    "bluesnap": "bluesnap", "twocheckout": "verifone", "cash_app_pay": "cashapp",
    "zelle": "zelle", "nets": "nets", "hitpay": "hitpay", "ipay88": "ipay88",
    "curlec": "curlec", "senangpay": "senangpay", "billplz": "billplz", "paymongo": "paymongo",
    "dragonpay": "dragonpay", "coins_ph": "coinsph", "linkaja": "linkaja", "vnpay": "vnpay",
    "bkash": "bkash", "windcave": "windcave", "poli": "poli", "ccavenue": "ccavenue",
    "instamojo": "instamojo", "pine_labs": "pinelabs", "payu_india": "payu", "payu_europe": "payu",
    "payu_latam": "payu", "cashfree": "cashfree", "red_dot_payment": "reddotpayment",
    "revenue_monster": "revenuemonster", "paylah": "dbs", "wolt": "wolt", "ifood": "ifood",
    "menulog": "menulog", "just_eat": "justeat", "glovo": "glovo", "rappi": "rappi",
    "keeta": "keeta", "hungrypanda": "hungrypanda", "tablelog": "tabelog",
    "lazada_seller": "lazada", "shopee_seller": "shopee", "amazon_seller": "amazon",
    "ebay_seller": "ebay", "etsy_shop": "etsy", "woocommerce": "woocommerce",
    "magento": "adobe", "bigcommerce": "bigcommerce", "shopify": "shopify",
    "line_pay_tw": "line", "rabbit_line_pay": "line", "line_official": "line",
    "tap_and_go": "octopus", "grab_reviews": "grab", "foodpanda_reviews": "foodpanda",
    "interac": "interac", "interac_e_transfer": "interac", "moneris": "moneris",
    "payco": "payco", "ovo": "ovo", "gopay": "gojek", "qris": "qris",
    "macau_pass": "macaupass", "fps": "fps", "promptpay": "promptpay",
    "au_pay": "aupay", "d_barai": "dbarai", "mercado_pago": "mercadopago",
    "bolt_food": "bolt", "foodpanda_reviews": "foodpanda", "resy": "resy",
    "twoc2p": "2c2p", "paynow": "paynow", "vietqr": "vietqr", "lankaqr": "lankaqr",
    "esewa": "esewa", "khalti": "khalti", "maya": "paymaya", "jkopay": "jkopay",
    "easy_wallet": "easycard", "mpay": "mpay", "payfast": "payfast", "peach_payments": "peachpayments",
    "chipper_cash": "chippercash", "network_international": "networkinternational",
    "coinbase": "coinbase", "bitpay": "bitpay", "payconiq": "payconiq",
    "rakuten_ichiba": "rakuten", "yahoo_shopping_jp": "yahoo", "tokopedia": "tokopedia",
    "bukalapak": "bukalapak", "cleartrip": "cleartrip", "trip_com": "tripdotcom",
    "makemytrip": "makemytrip", "kkday": "kkday", "inline": "inline", "chope": "chope",
    "eatigo": "eatigo", "funnow": "funnow", "hot_pepper": "hotpepper", "bento": "bento",
}

# Verified Wikimedia only (no fabricated paths).
WIKIMEDIA: dict[str, list[str]] = {
    **{k: v for k, v in OFFICIAL.items()},
    "paynow": ["https://upload.wikimedia.org/wikipedia/commons/8/8e/PayNow_Logo.svg"],
    "dana": ["https://upload.wikimedia.org/wikipedia/commons/7/7e/Dana_%28company%29_logo.svg"],
    "ovo": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/OVO_%28digital_payment%29_logo.svg"],
    "phonepe": ["https://upload.wikimedia.org/wikipedia/commons/7/71/PhonePe_Logo.svg"],
    "paytm": ["https://upload.wikimedia.org/wikipedia/commons/2/24/Paytm_Logo_%28standalone%29.svg"],
    "wise": ["https://upload.wikimedia.org/wikipedia/commons/5/5c/Wise_%28formerly_TransferWise%29_logo.svg"],
    "revolut": ["https://upload.wikimedia.org/wikipedia/commons/6/6c/Revolut_logo.svg"],
    "ideal": ["https://upload.wikimedia.org/wikipedia/commons/e/e6/IDEAL_Logo.svg"],
    "boost": ["https://upload.wikimedia.org/wikipedia/commons/7/7a/Boost_%28Malaysia%29_logo.svg"],
    "bkash": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/BKash_Logo.svg"],
    "mpesa": ["https://upload.wikimedia.org/wikipedia/commons/1/15/M-PESA_LOGO-01.svg"],
    "venmo": ["https://upload.wikimedia.org/wikipedia/commons/7/7a/Venmo_logo.svg"],
    "macau_pass": ["https://upload.wikimedia.org/wikipedia/zh/4/4a/MacauPass.svg"],
    "octopus": ["https://upload.wikimedia.org/wikipedia/en/8/83/Octopus_Card.svg"],
    "fps": ["https://upload.wikimedia.org/wikipedia/zh/4/4c/FPS_Logo_TC.svg"],
    "duitnow": ["https://upload.wikimedia.org/wikipedia/commons/2/22/DuitNow_QR_Logo.png"],
    "promptpay": ["https://upload.wikimedia.org/wikipedia/commons/c/c5/PromptPay-logo.png"],
    "twoc2p": ["https://upload.wikimedia.org/wikipedia/commons/3/39/2C2P_Logo.png"],
    "payme": ["https://upload.wikimedia.org/wikipedia/commons/2/2a/PayMe_logo.svg"],
    "alipay_hk": ["https://upload.wikimedia.org/wikipedia/commons/7/7b/Alipay_logo.svg"],
    "wechat_pay_hk": ["https://upload.wikimedia.org/wikipedia/commons/7/7e/WeChat_logo.svg"],
    "unionpay": ["https://upload.wikimedia.org/wikipedia/commons/1/1b/UnionPay_logo.svg"],
    "jkopay": ["https://upload.wikimedia.org/wikipedia/commons/c/c5/JKOPay_logo.svg"],
    "easy_wallet": ["https://upload.wikimedia.org/wikipedia/commons/e/e0/EasyCard_logo.svg"],
    "truemoney": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/TrueMoney_Wallet_Logo.svg"],
    "openrice": ["https://upload.wikimedia.org/wikipedia/commons/0/0b/OpenRice_logo.svg"],
    "tripadvisor": ["https://upload.wikimedia.org/wikipedia/commons/0/02/TripAdvisor_Logo.svg"],
    "paypay": ["https://upload.wikimedia.org/wikipedia/commons/0/07/PayPay_logo.svg"],
    "line_pay": ["https://upload.wikimedia.org/wikipedia/commons/4/41/LINE_Pay_logo.svg"],
    "rakuten_pay": ["https://upload.wikimedia.org/wikipedia/commons/4/4c/Rakuten_Pay_logo.svg"],
    "grabpay": ["https://upload.wikimedia.org/wikipedia/commons/0/0a/Grab_logo.svg"],
    "shopeepay": ["https://upload.wikimedia.org/wikipedia/commons/f/fe/Shopee.svg"],
    "gcash": ["https://upload.wikimedia.org/wikipedia/commons/5/52/GCash_logo.svg"],
    "touch_n_go": ["https://upload.wikimedia.org/wikipedia/commons/f/fb/Touch_%27n_Go_eWallet_logo.svg"],
    "interac": ["https://upload.wikimedia.org/wikipedia/commons/4/4e/Interac_Logo.svg"],
    "interac_e_transfer": ["https://upload.wikimedia.org/wikipedia/commons/4/4e/Interac_Logo.svg"],
    "moneris": ["https://upload.wikimedia.org/wikipedia/commons/4/4a/Moneris_logo.svg"],
    "thefork": ["https://upload.wikimedia.org/wikipedia/commons/e/e4/The_fork_logo.png"],
    "hungrypanda": ["https://upload.wikimedia.org/wikipedia/commons/7/74/HungryPanda_logo.png"],
    "kkday": ["https://upload.wikimedia.org/wikipedia/commons/d/d7/KKday_Logo.svg"],
    "resy": ["https://upload.wikimedia.org/wikipedia/commons/4/43/Resy_logo.svg"],
    "windcave": ["https://upload.wikimedia.org/wikipedia/commons/8/8a/PaymentExpress_logo.svg"],
    "zelle": ["https://upload.wikimedia.org/wikipedia/commons/4/4c/Zelle_logo.svg"],
    "michelin_guide": ["https://upload.wikimedia.org/wikipedia/commons/6/6d/Michelin_star.svg"],
    "merpay": ["https://upload.wikimedia.org/wikipedia/commons/7/7f/Mercari_logo_2018.svg"],
    "au_pay": ["https://upload.wikimedia.org/wikipedia/commons/8/8e/Au_Pay_Logo.png"],
}

# Same logo OK for these slug groups (aliases).
ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"clearpay", "afterpay"}),
    frozenset({"interac", "interac_e_transfer"}),
    frozenset({"shop_pay", "shopify_payments", "shopify"}),
    frozenset({"grabpay", "grab_reviews", "grab_paylater"}),
    frozenset({"line_pay", "line_pay_tw", "rabbit_line_pay", "line_official"}),
    frozenset({"tap_and_go", "octopus"}),
    frozenset({"payu_india", "payu_europe", "payu_latam"}),
    frozenset({"shopeepay", "shopee_seller"}),
    frozenset({"google_reviews", "google_customer_reviews"}),
    frozenset({"sofort", "klarna"}),
    frozenset({"hoolah", "atome"}),
    frozenset({"venmo", "braintree"}),
    frozenset({"becs_direct_debit", "stripe"}),
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _load_index() -> dict[str, dict]:
    raw = fetch(SIMPLE_ICONS_JSON, timeout=30)
    if not raw:
        return {}
    index: dict[str, dict] = {}
    for item in json.loads(raw.decode("utf-8")):
        title = item.get("title") or ""
        if not title:
            continue
        file_slug = re.sub(r"[^a-z0-9]", "", title.lower())
        entry = {**item, "file_slug": file_slug}
        for key in {_norm(title)} | {_norm(a) for a in (item.get("aliases") or {}).get("aka") or []}:
            if key and key not in index:
                index[key] = entry
    return index


def _fetch_si(icon_slug: str) -> bytes | None:
    if len(icon_slug) < 3:
        return None
    url = JSdelivr_ICON.format(slug=urllib.parse.quote(icon_slug))
    data = fetch(url, timeout=10)
    if data and kind(data) == "svg" and b"/e/" not in data and b"<title>/e/" not in data:
        return data
    return None


def _fetch_si_colored(icon_slug: str, slug: str) -> bytes | None:
    color = BRAND_COLORS.get(slug, "")
    if color:
        data = fetch(f"https://cdn.simpleicons.org/{icon_slug}/{color}", timeout=10)
        if data and kind(data) == "svg":
            return data
    return _fetch_si(icon_slug)


def _fetch_wiki(slug: str) -> bytes | None:
    for url in WIKIMEDIA.get(slug, []):
        data = fetch(url, timeout=12)
        if data and kind(data):
            return data
    return None


def _fetch_google(domain: str) -> bytes | None:
    if not domain:
        return None
    return fetch(f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(domain)}&sz=128", timeout=12)


def _bad_logo(data: bytes) -> bool:
    text = data.decode("utf-8", errors="ignore").lower()
    return "<title>/e/</title>" in text or "ebay" in text[:200] and len(data) < 800


def _try_sources(slug: str, index: dict[str, dict]) -> tuple[bytes | None, str]:
    # 1) Explicit simple-icons map
    if slug in SLUG_ICON:
        data = _fetch_si_colored(SLUG_ICON[slug], slug)
        if data and not _bad_logo(data):
            return data, "simple-icons"

    # 2) Exact index match on plugin name / provider
    p = get_payment_plugin(slug) or get_reputation_plugin(slug)
    for key in filter(None, [_norm(p.get("name", "") if p else ""), _norm(p.get("provider", "") if p else "")]):
        if len(key) < 3:
            continue
        entry = index.get(key)
        if entry:
            data = _fetch_si_colored(entry["file_slug"], slug)
            if data and not _bad_logo(data):
                return data, "simple-icons-name"

    # 3) Domain base (min 4 chars)
    domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
    base = _norm(domain.split(".")[0])
    if len(base) >= 4:
        data = _fetch_si_colored(base, slug)
        if data and not _bad_logo(data):
            return data, "simple-icons-domain"

    # 4) Wikimedia verified
    data = _fetch_wiki(slug)
    if data and not _bad_logo(data):
        return data, "wikimedia"

    # 5) Google favicon (unique per domain)
    data = _fetch_google(domain)
    if data and kind(data):
        return data, "google-favicon"

    return None, "miss"


def _allowed_dup(a: str, b: str) -> bool:
    for group in ALIAS_GROUPS:
        if a in group and b in group:
            return True
    return False


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    slugs = sorted(set(payment_plugin_slugs()) | set(reputation_plugin_slugs()))
    index = _load_index()
    print(f"Refetching {len(slugs)} logos (strict, no fuzzy)…")

    saved: dict[str, str] = {}
    hash_to_slug: dict[str, str] = {}
    stats: dict[str, int] = {}

    for i, slug in enumerate(slugs, 1):
        data, source = _try_sources(slug, index)
        if not data:
            print(f"MISS [{i}] {slug}")
            stats["miss"] = stats.get("miss", 0) + 1
            continue

        h = hashlib.md5(data).hexdigest()
        if h in hash_to_slug and not _allowed_dup(slug, hash_to_slug[h]):
            # collision — force google favicon for uniqueness
            domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
            data2 = _fetch_google(domain)
            if data2 and kind(data2):
                data = data2
                source = "google-favicon-dedup"
                h = hashlib.md5(data).hexdigest()

        try:
            if save(slug, data):
                hash_to_slug[h] = slug
                saved[slug] = source
                stats[source] = stats.get(source, 0) + 1
                print(f"OK [{i}] {slug} ({source})")
        except (ValueError, OSError) as exc:
            print(f"FAIL [{i}] {slug}: {exc}")
            stats["fail"] = stats.get("fail", 0) + 1
        if i % 15 == 0:
            time.sleep(0.15)

    # audit
    by_hash: dict[str, list[str]] = {}
    for s in slugs:
        p = OUT / f"{s}.svg"
        if p.is_file():
            raw = p.read_text(encoding="utf-8", errors="ignore")
            by_hash[hashlib.md5(raw.encode()).hexdigest()].append(s)

    bad_dups = [g for g in by_hash.values() if len(g) > 1 and not all(
        any(_allowed_dup(g[0], x) for x in g[1:]) for _ in [0]
    )]
    # simpler: count dup groups where not all in same alias group
    dup_groups = 0
    for group in by_hash.values():
        if len(group) <= 1:
            continue
        ok = True
        for a in group[1:]:
            if not _allowed_dup(group[0], a):
                ok = False
                break
        if not ok:
            dup_groups += 1
            print("DUP?", group)

    print(f"\nSaved {len(saved)}/{len(slugs)} | stats={stats} | bad_dup_groups={dup_groups}")
    return 0 if dup_groups == 0 and stats.get("miss", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
