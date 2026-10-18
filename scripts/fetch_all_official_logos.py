#!/usr/bin/env python3
"""Fetch official brand logos for every integration plugin."""

from __future__ import annotations

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

# slug -> simple-icons file slug (explicit overrides)
SLUG_ICON: dict[str, str] = {
    **BATCH2_SIMPLE_ICONS,
    **BATCH3_SIMPLE_ICONS,
    "stripe": "stripe",
    "paypal": "paypal",
    "paypay": "paypay",
    "square": "square",
    "adyen": "adyen",
    "mollie": "mollie",
    "klarna": "klarna",
    "line_pay": "line",
    "line_pay_tw": "line",
    "rakuten_pay": "rakuten",
    "grabpay": "grab",
    "shopeepay": "shopee",
    "xendit": "xendit",
    "omise": "omise",
    "midtrans": "midtrans",
    "gocardless": "gocardless",
    "sumup": "sumup",
    "worldpay": "worldpay",
    "authorize_net": "authorize",
    "braintree": "braintree",
    "afterpay": "afterpay",
    "zip": "zip",
    "eway": "eway",
    "paystack": "paystack",
    "flutterwave": "flutterwave",
    "mercado_pago": "mercadopago",
    "yookassa": "yookassa",
    "razorpay": "razorpay",
    "alipay_hk": "alipay",
    "wechat_pay_hk": "wechat",
    "payme": "hsbc",
    "unionpay": "unionpay",
    "jkopay": "jkopay",
    "easy_wallet": "easycard",
    "mpay": "mpay",
    "atome": "atome",
    "twoc2p": "2c2p",
    "airwallex": "airwallex",
    "checkout_com": "checkout",
    "octopus": "octopus",
    "fps": "fps",
    "gcash": "gcash",
    "maya": "paymaya",
    "touch_n_go": "touchngo",
    "duitnow": "duitnow",
    "promptpay": "promptpay",
    "truemoney": "truemoney",
    "momo": "momo",
    "zalopay": "zalopay",
    "kakao_pay": "kakaopay",
    "toss": "toss",
    "naver_pay": "naver",
    "au_pay": "aupay",
    "d_barai": "dbarai",
    "merpay": "merpay",
    "affirm": "affirm",
    "amazon_pay": "amazon",
    "openrice": "openrice",
    "tripadvisor": "tripadvisor",
    "yelp": "yelp",
    "trustpilot": "trustpilot",
    "facebook_reviews": "facebook",
    "instagram_business": "instagram",
    "linkedin_company": "linkedin",
    "booking_com": "bookingdotcom",
    "agoda": "agoda",
    "expedia": "expedia",
    "hotels_com": "hotelsdotcom",
    "hostelworld": "hostelworld",
    "airbnb": "airbnb",
    "vrbo": "vrbo",
    "deliveroo": "deliveroo",
    "doordash": "doordash",
    "uber_eats": "ubereats",
    "grab_reviews": "grab",
    "foodpanda_reviews": "foodpanda",
    "swiggy": "swiggy",
    "zomato": "zomato",
    "opentable": "opentable",
    "thefork": "thefork",
    "foursquare": "foursquare",
    "g2": "g2",
    "capterra": "capterra",
    "feefo": "feefo",
    "holidaycheck": "holidaycheck",
    "michelin_guide": "michelin",
    "gurunavi": "gurunavi",
    "hot_pepper": "hotpepper",
    "kakao_map": "kakao",
    "naver_place": "naver",
    "inline": "inline",
    "chope": "chope",
    "eatigo": "eatigo",
    "funnow": "funnow",
    "klook": "klook",
    "kkday": "kkday",
    "makemytrip": "makemytrip",
    "kayak": "kayak",
    "skyscanner": "skyscanner",
    "trivago": "trivago",
    "traveloka": "traveloka",
    "tiktok_business": "tiktok",
    "tiktok_shop": "tiktok",
    "whatsapp_business": "whatsapp",
    "tap_and_go": "octopus",
    "line_official": "line",
    "rabbit_line_pay": "line",
    "gopay": "gojek",
    "clearpay": "afterpay",
    "venmo": "venmo",
    "sofort": "klarna",
    "becs_direct_debit": "stripe",
    "grab_paylater": "grab",
    "hoolah": "atome",
    "shopify_payments": "shopify",
    "shop_pay": "shopify",
    "interac": "interac",
    "interac_e_transfer": "interac",
    "moneris": "moneris",
    "ideal": "ideal",
    "bancontact": "bancontact",
    "giropay": "giropay",
    "eps": "eps",
    "blik": "blik",
    "mb_way": "mbway",
    "bizum": "bizum",
    "satispay": "satispay",
    "payconiq": "payconiq",
    "twint": "twint",
    "vipps": "vipps",
    "swish": "swish",
    "trustly": "trustly",
    "przelewy24": "przelewy24",
    "revolut": "revolut",
    "wise": "wise",
    "payoneer": "payoneer",
    "paddle": "paddle",
    "fastspring": "fastspring",
    "cybersource": "cybersource",
    "global_payments": "globalpayments",
    "nuvei": "nuvei",
    "paysafe": "paysafe",
    "worldline": "worldline",
    "sezzle": "sezzle",
    "splitit": "splitit",
    "tabby": "tabby",
    "tamara": "tamara",
    "scalapay": "scalapay",
    "phonepe": "phonepe",
    "paytm": "paytm",
    "dana": "dana",
    "ovo": "ovo",
    "boost": "boost",
    "favepay": "fave",
    "paidy": "paidy",
    "samsung_pay": "samsungpay",
    "apple_pay": "applepay",
    "coinbase": "coinbase",
    "bitpay": "bitpay",
    "clover": "clover",
    "lightspeed": "lightspeed",
    "toast": "toast",
    "fiserv": "fiserv",
    "pagarme": "pagarme",
    "pagseguro": "pagseguro",
    "dlocal": "dlocal",
    "ebanx": "ebanx",
    "conekta": "conekta",
    "openpay": "openpay",
    "kushki": "kushki",
    "mpesa": "mpesa",
    "hyperpay": "hyperpay",
    "tap_payments": "tap",
    "paytabs": "paytabs",
    "fawry": "fawry",
    "bluesnap": "bluesnap",
    "twocheckout": "verifone",
    "cash_app_pay": "cashapp",
    "venmo": "venmo",
    "zelle": "zelle",
    "nets": "nets",
    "hitpay": "hitpay",
    "ipay88": "ipay88",
    "curlec": "curlec",
    "senangpay": "senangpay",
    "billplz": "billplz",
    "paymongo": "paymongo",
    "dragonpay": "dragonpay",
    "coins_ph": "coinsph",
    "linkaja": "linkaja",
    "vnpay": "vnpay",
    "bkash": "bkash",
    "windcave": "windcave",
    "poli": "poli",
    "ccavenue": "ccavenue",
    "instamojo": "instamojo",
    "pine_labs": "pinelabs",
    "payu_india": "payu",
    "payu_europe": "payu",
    "payu_latam": "payu",
    "cashfree": "cashfree",
    "red_dot_payment": "reddotpayment",
    "revenue_monster": "revenuemonster",
    "paylah": "dbs",
    "shopify": "shopify",
    "woocommerce": "woocommerce",
    "magento": "adobe",
    "bigcommerce": "bigcommerce",
    "wolt": "wolt",
    "bolt_food": "bolt",
    "ifood": "ifood",
    "menulog": "menulog",
    "just_eat": "justeat",
    "glovo": "glovo",
    "rappi": "rappi",
    "keeta": "keeta",
    "hungrypanda": "hungrypanda",
    "tablelog": "tabelog",
    "hotels_com": "hotelsdotcom",
    "lazada_seller": "lazada",
    "shopee_seller": "shopee",
    "amazon_seller": "amazon",
    "ebay_seller": "ebay",
    "etsy_shop": "etsy",
}

# Wikimedia / official hosted marks (slug -> urls)
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
    "mpay": ["https://upload.wikimedia.org/wikipedia/commons/5/5a/MPay_logo.png"],
    "truemoney": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/TrueMoney_Wallet_Logo.svg"],
    "momo": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/MoMo_Logo.png"],
    "zalopay": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/ZaloPay_logo.svg"],
    "kakao_pay": ["https://upload.wikimedia.org/wikipedia/commons/e/e3/KakaoPay_logo.svg"],
    "openrice": ["https://upload.wikimedia.org/wikipedia/commons/0/0b/OpenRice_logo.svg"],
    "tripadvisor": ["https://upload.wikimedia.org/wikipedia/commons/0/02/TripAdvisor_Logo.svg"],
    "paypay": ["https://upload.wikimedia.org/wikipedia/commons/0/07/PayPay_logo.svg"],
    "line_pay": ["https://upload.wikimedia.org/wikipedia/commons/4/41/LINE_Pay_logo.svg"],
    "rakuten_pay": ["https://upload.wikimedia.org/wikipedia/commons/4/4c/Rakuten_Pay_logo.svg"],
    "grabpay": ["https://upload.wikimedia.org/wikipedia/commons/0/0a/Grab_logo.svg"],
    "shopeepay": ["https://upload.wikimedia.org/wikipedia/commons/f/fe/Shopee.svg"],
    "gcash": ["https://upload.wikimedia.org/wikipedia/commons/5/52/GCash_logo.svg"],
    "maya": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Maya_%28payment_platform%29_logo.svg"],
    "touch_n_go": ["https://upload.wikimedia.org/wikipedia/commons/f/fb/Touch_%27n_Go_eWallet_logo.svg"],
    "interac": ["https://upload.wikimedia.org/wikipedia/commons/4/4e/Interac_Logo.svg"],
    "interac_e_transfer": ["https://upload.wikimedia.org/wikipedia/commons/4/4e/Interac_Logo.svg"],
    "moneris": ["https://upload.wikimedia.org/wikipedia/commons/4/4a/Moneris_logo.svg"],
    "nets": ["https://upload.wikimedia.org/wikipedia/commons/1/1e/NETS_logo.svg"],
    "hitpay": ["https://upload.wikimedia.org/wikipedia/commons/8/8a/HitPay_logo.svg"],
    "ipay88": ["https://upload.wikimedia.org/wikipedia/commons/3/3e/IPay88_logo.png"],
    "senangpay": ["https://upload.wikimedia.org/wikipedia/commons/8/8c/SenangPay_logo.png"],
    "billplz": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Billplz_logo.svg"],
    "paymongo": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/PayMongo_logo.svg"],
    "dragonpay": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Dragonpay_logo.png"],
    "coins_ph": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Coins.ph_logo.svg"],
    "linkaja": ["https://upload.wikimedia.org/wikipedia/commons/2/2e/LinkAja_logo.svg"],
    "vnpay": ["https://upload.wikimedia.org/wikipedia/commons/7/77/VNPay_logo.svg"],
    "viettel_money": ["https://upload.wikimedia.org/wikipedia/commons/8/8e/Viettel_Money_logo.svg"],
    "vietqr": ["https://upload.wikimedia.org/wikipedia/commons/9/9e/VietQR_logo.svg"],
    "bakong": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Bakong_logo.svg"],
    "wave_money": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Wave_Money_logo.svg"],
    "payco": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/PAYCO_logo.svg"],
    "smilepay": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/SmilePay_logo.svg"],
    "icash_pay": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Icash_pay_logo.svg"],
    "pi_wallet": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Pi_Wallet_logo.svg"],
    "pxpay_plus": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/PXPay_Plus_logo.svg"],
    "boc_pay": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Bank_of_China_logo.svg"],
    "bnu_pay": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/BNU_logo.svg"],
    "macau_pass": ["https://upload.wikimedia.org/wikipedia/zh/4/4a/MacauPass.svg"],
    "tap_and_go": ["https://upload.wikimedia.org/wikipedia/en/8/83/Octopus_Card.svg"],
    "scb_easy": ["https://upload.wikimedia.org/wikipedia/commons/3/3e/Siam_Commercial_Bank_logo.svg"],
    "lankaqr": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/LankaQR_logo.svg"],
    "khalti": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Khalti_logo.svg"],
    "esewa": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/eSewa_logo.svg"],
    "pine_labs": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Pine_Labs_logo.svg"],
    "ccavenue": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/CCAvenue_logo.svg"],
    "instamojo": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Instamojo_logo.svg"],
    "cashfree": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Cashfree_logo.svg"],
    "curlec": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Curlec_logo.svg"],
    "revenue_monster": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Revenue_Monster_logo.svg"],
    "red_dot_payment": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Red_Dot_Payment_logo.svg"],
    "paylah": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/DBS_Bank_logo.svg"],
    "payto": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/PayTo_logo.svg"],
    "poli": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/POLi_Payments_logo.svg"],
    "windcave": ["https://upload.wikimedia.org/wikipedia/commons/8/8a/PaymentExpress_logo.svg"],
    "zelle": ["https://upload.wikimedia.org/wikipedia/commons/4/4c/Zelle_logo.svg"],
    "qris": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/QRIS_logo.svg"],
    "favepay": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Fave_logo.svg"],
    "gurunavi": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Gurunavi_logo.svg"],
    "hot_pepper": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Hot_Pepper_logo.svg"],
    "tablelog": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Tabelog_logo.svg"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _plugin_name(slug: str) -> str:
    p = get_payment_plugin(slug) or get_reputation_plugin(slug)
    return (p or {}).get("name") or slug.replace("_", " ").title()


def _load_simple_icon_index() -> dict[str, dict]:
    """normalized name/alias -> simple-icons metadata."""
    raw = fetch(SIMPLE_ICONS_JSON, timeout=30)
    if not raw:
        return {}
    icons = json.loads(raw.decode("utf-8"))
    index: dict[str, dict] = {}
    for item in icons:
        title = item.get("title") or ""
        if not title:
            continue
        keys = {_norm(title)}
        for aka in (item.get("aliases") or {}).get("aka") or []:
            keys.add(_norm(str(aka)))
        file_slug = re.sub(r"[^a-z0-9]", "", title.lower())
        entry = {**item, "file_slug": file_slug}
        for key in keys:
            if key and key not in index:
                index[key] = entry
    return index


def _fetch_icon_entry(entry: dict) -> bytes | None:
    file_slug = entry.get("file_slug") or ""
    if file_slug:
        data = _fetch_simple_icon(file_slug)
        if data:
            return data
    source = entry.get("source") or ""
    if source:
        data = fetch(source, timeout=12)
        if data and kind(data):
            return data
    return None


def _icon_candidates(slug: str) -> list[str]:
    out: list[str] = []
    if slug in SLUG_ICON:
        out.append(SLUG_ICON[slug])
    brand = PLUGIN_BRANDS.get(slug) or {}
    domain = brand.get("domain") or ""
    if domain:
        base = domain.split(".")[0]
        out.extend([base, base.replace("-", ""), _norm(base)])
    p = get_payment_plugin(slug) or get_reputation_plugin(slug)
    if p:
        out.append(p.get("provider") or "")
        out.append(_norm(p.get("name") or ""))
        for part in re.split(r"[\s/&]+", p.get("name") or ""):
            if part:
                out.append(_norm(part))
    out.extend([slug, slug.replace("_", ""), _norm(slug)])
    seen: set[str] = set()
    uniq: list[str] = []
    for c in out:
        c = _norm(c)
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _fetch_simple_icon(icon_slug: str) -> bytes | None:
    url = JSdelivr_ICON.format(slug=urllib.parse.quote(icon_slug))
    data = fetch(url, timeout=8)
    if data and kind(data) == "svg":
        return data
    return None


def _fetch_wikimedia(slug: str) -> bytes | None:
    for url in WIKIMEDIA.get(slug, []):
        data = fetch(url, timeout=10)
        if data and kind(data):
            return data
    return None


def _fetch_ddg_favicon(domain: str) -> bytes | None:
    if not domain:
        return None
    url = f"https://icons.duckduckgo.com/ip3/{urllib.parse.quote(domain)}.ico"
    return fetch(url, timeout=12)


def _fetch_domain_favicon(domain: str) -> bytes | None:
    if not domain:
        return None
    for path in ("/favicon.svg", "/favicon.ico", "/apple-touch-icon.png"):
        data = fetch(f"https://{domain}{path}", timeout=8)
        if data and kind(data):
            return data
    return None


def _match_simple_icon(slug: str, index: dict[str, dict]) -> tuple[bytes | None, str]:
    if slug in SLUG_ICON:
        data = _fetch_simple_icon(SLUG_ICON[slug])
        if data:
            return data, "simple-icons"
        entry = index.get(_norm(SLUG_ICON[slug]))
        if entry:
            data = _fetch_icon_entry(entry)
            if data:
                return data, "simple-icons-source"

    for cand in _icon_candidates(slug):
        entry = index.get(cand)
        if entry:
            data = _fetch_icon_entry(entry)
            if data:
                return data, "simple-icons"
        data = _fetch_simple_icon(cand)
        if data:
            return data, "simple-icons"

    return None, ""


def _is_placeholder(path: Path) -> bool:
    if not path.is_file():
        return True
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if "official-brand" in raw:
        return False
    return '<rect width="64" height="64"' in raw or "<text" in raw


def _is_official(path: Path) -> bool:
    if not path.is_file():
        return False
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return "official-brand" in raw and path.stat().st_size >= 200


def fetch_logo(slug: str, index: dict[str, dict], *, force: bool) -> str:
    path = OUT / f"{slug}.svg"
    if not force and not _is_placeholder(path):
        return "skip"

    data, source = _match_simple_icon(slug, index)
    if not data:
        data = _fetch_wikimedia(slug)
        source = "wikimedia"
    if not data:
        domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
        data = _fetch_domain_favicon(domain)
        source = "domain-favicon"
    if not data:
        domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
        data = _fetch_ddg_favicon(domain)
        source = "ddg-favicon"
    if data:
        try:
            if save(slug, data):
                return source
        except (ValueError, OSError):
            pass
    return "miss"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch official logos for all integration plugins")
    parser.add_argument("--force", action="store_true", help="Replace existing official logos too")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    slugs = sorted(set(payment_plugin_slugs()) | set(reputation_plugin_slugs()))
    print(f"Loading Simple Icons index…")
    index = _load_simple_icon_index()
    print(f"Index: {len(index)} aliases")

    stats: dict[str, list[str]] = {
        "skip": [],
        "simple-icons": [],
        "simple-icons-source": [],
        "simple-icons-fuzzy": [],
        "wikimedia": [],
        "domain-favicon": [],
        "ddg-favicon": [],
        "miss": [],
    }
    for i, slug in enumerate(slugs, 1):
        result = fetch_logo(slug, index, force=args.force)
        stats[result].append(slug)
        if result in ("simple-icons", "simple-icons-source", "simple-icons-fuzzy", "wikimedia", "domain-favicon", "ddg-favicon"):
            print(f"OK [{i}/{len(slugs)}] {slug} ({result})")
        elif result == "miss":
            print(f"MISS [{i}/{len(slugs)}] {slug}")
        if i % 20 == 0:
            time.sleep(0.2)

    got = (
        len(stats["simple-icons"])
        + len(stats["simple-icons-source"])
        + len(stats["simple-icons-fuzzy"])
        + len(stats["wikimedia"])
        + len(stats["domain-favicon"])
        + len(stats["ddg-favicon"])
    )
    print(
        f"\nDone — skip={len(stats['skip'])} fetched={got} missing={len(stats['miss'])}"
    )
    if stats["miss"]:
        print("Missing:", ", ".join(stats["miss"]))
        from scripts.embed_official_logo_gaps import REMOTE_OFFICIAL, wrap_remote
        from integration_catalog import PLUGIN_BRANDS

        for slug in stats["miss"]:
            if slug not in REMOTE_OFFICIAL:
                domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
                if domain:
                    REMOTE_OFFICIAL[slug] = f"https://icons.duckduckgo.com/ip3/{domain}.ico"
            url = REMOTE_OFFICIAL.get(slug)
            if url:
                (OUT / f"{slug}.svg").write_text(wrap_remote(slug, url), encoding="utf-8")
                print(f"EMBED {slug}")
                stats["miss"].remove(slug)
    return 1 if stats["miss"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
