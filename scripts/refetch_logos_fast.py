#!/usr/bin/env python3
"""Parallel logo refetch — Simple Icons, unavatar.io, favicons. Always overwrite."""

from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog import (  # noqa: E402
    BRAND_COLORS,
    BRAND_INITIALS,
    PLUGIN_BRANDS,
    payment_plugin_slugs,
    reputation_plugin_slugs,
)
from integration_catalog_batch2 import BATCH2_SIMPLE_ICONS  # noqa: E402
from integration_catalog_batch3 import BATCH3_SIMPLE_ICONS  # noqa: E402
from scripts.fetch_official_logos import fetch, kind, save, wrap_raster, wrap_svg  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"
JSdelivr = "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/{icon}.svg"

SLUG_ICON: dict[str, str] = {**BATCH2_SIMPLE_ICONS, **BATCH3_SIMPLE_ICONS}
_EXTRA = {
    "stripe": "stripe", "paypal": "paypal", "paypay": "paypay", "square": "square",
    "adyen": "adyen", "mollie": "mollie", "klarna": "klarna", "line_pay": "line",
    "rakuten_pay": "rakuten", "grabpay": "grab", "shopeepay": "shopee", "xendit": "xendit",
    "omise": "omise", "midtrans": "midtrans", "gocardless": "gocardless", "sumup": "sumup",
    "afterpay": "afterpay", "paystack": "paystack", "flutterwave": "flutterwave",
    "razorpay": "razorpay", "alipay_hk": "alipay", "wechat_pay_hk": "wechat",
    "atome": "atome", "gcash": "gcash", "maya": "paymaya", "touch_n_go": "touchngo",
    "truemoney": "truemoney", "momo": "momo", "kakao_pay": "kakaopay", "toss": "toss",
    "naver_pay": "naver", "merpay": "merpay", "affirm": "affirm", "amazon_pay": "amazon",
    "openrice": "openrice", "tripadvisor": "tripadvisor", "yelp": "yelp",
    "trustpilot": "trustpilot", "facebook_reviews": "facebook",
    "instagram_business": "instagram", "booking_com": "bookingdotcom", "agoda": "agoda",
    "expedia": "expedia", "airbnb": "airbnb", "deliveroo": "deliveroo", "doordash": "doordash",
    "uber_eats": "ubereats", "swiggy": "swiggy", "zomato": "zomato", "opentable": "opentable",
    "thefork": "thefork", "foursquare": "foursquare", "g2": "g2", "capterra": "capterra",
    "feefo": "feefo", "holidaycheck": "holidaycheck", "michelin_guide": "michelin",
    "klook": "klook", "kayak": "kayak", "skyscanner": "skyscanner", "traveloka": "traveloka",
    "tiktok_business": "tiktok", "whatsapp_business": "whatsapp",
    "clearpay": "afterpay", "venmo": "venmo", "sofort": "klarna", "grab_paylater": "grab",
    "hoolah": "atome", "shopify_payments": "shopify", "shop_pay": "shopify", "ideal": "ideal",
    "bancontact": "bancontact", "giropay": "giropay", "eps": "eps", "blik": "blik",
    "revolut": "revolut", "wise": "wise", "paddle": "paddle", "phonepe": "phonepe",
    "paytm": "paytm", "dana": "dana", "boost": "boost", "paidy": "paidy",
    "apple_pay": "applepay", "clover": "clover", "toast": "toast",
    "wolt": "wolt", "ifood": "ifood", "menulog": "menulog", "just_eat": "justeat",
    "glovo": "glovo", "interac": "interac", "moneris": "moneris", "zelle": "zelle",
    "line_pay_tw": "line", "rabbit_line_pay": "line", "line_official": "line",
    "tap_and_go": "octopus", "octopus": "octopus", "grab_reviews": "grab",
    "shopee_seller": "shopee",
    "payu_india": "payu", "payu_europe": "payu", "payu_latam": "payu",
    "interac_e_transfer": "interac", "foodpanda_reviews": "foodpanda", "worldpay": "worldpay",
    "checkout_com": "checkout", "braintree": "braintree", "mercado_pago": "mercadopago",
    "yookassa": "yookassa", "zip": "zip", "eway": "eway", "authorize_net": "authorize",
    "przelewy24": "przelewy24", "satispay": "satispay", "twint": "twint", "vipps": "vipps",
    "swish": "swish", "trustly": "trustly", "bizum": "bizum", "mb_way": "mbway",
    "payconiq": "payconiq", "sezzle": "sezzle", "tabby": "tabby", "tamara": "tamara",
    "scalapay": "scalapay", "splitit": "splitit", "nuvei": "nuvei", "paysafe": "paysafe",
    "worldline": "worldline", "cybersource": "cybersource", "global_payments": "globalpayments",
    "bluesnap": "bluesnap", "twocheckout": "verifone", "cash_app_pay": "cashapp",
    "pagarme": "pagarme", "pagseguro": "pagseguro", "dlocal": "dlocal", "ebanx": "ebanx",
    "conekta": "conekta", "openpay": "openpay", "kushki": "kushki", "mpesa": "mpesa",
    "hyperpay": "hyperpay", "tap_payments": "tap", "paytabs": "paytabs", "fawry": "fawry",
    "nets": "nets", "hitpay": "hitpay", "ipay88": "ipay88", "billplz": "billplz",
    "paymongo": "paymongo", "dragonpay": "dragonpay", "linkaja": "linkaja", "vnpay": "vnpay",
    "bkash": "bkash", "windcave": "windcave", "poli": "poli", "ccavenue": "ccavenue",
    "instamojo": "instamojo", "cashfree": "cashfree", "red_dot_payment": "reddotpayment",
    "revenue_monster": "revenuemonster", "paylah": "dbs", "curlec": "curlec",
    "senangpay": "senangpay", "gopay": "gojek", "ovo": "ovo", "favepay": "fave",
    "lazada_seller": "lazada", "amazon_seller": "amazon", "ebay_seller": "ebay",
    "etsy_shop": "etsy", "woocommerce": "woocommerce", "magento": "adobe",
    "bigcommerce": "bigcommerce", "shopify": "shopify", "bolt_food": "bolt",
    "rappi": "rappi", "keeta": "keeta", "hungrypanda": "hungrypanda", "tablelog": "tabelog",
    "rakuten_ichiba": "rakuten", "mercado_pago": "mercadopago", "fps": "fps",
    "duitnow": "duitnow", "promptpay": "promptpay", "au_pay": "aupay", "d_barai": "dbarai",
    "jkopay": "jkopay", "easy_wallet": "easycard", "mpay": "mpay", "unionpay": "unionpay",
    "payme": "hsbc", "twoc2p": "2c2p", "airwallex": "airwallex", "lightspeed": "lightspeed",
    "fiserv": "fiserv", "coinbase": "coinbase", "bitpay": "bitpay",
}
for k, v in _EXTRA.items():
    SLUG_ICON.setdefault(k, v)


def _bad(data: bytes) -> bool:
    t = data.decode("utf-8", errors="ignore")
    return "<title>/e/</title>" in t


def _unique_initial(slug: str) -> str:
    custom = BRAND_INITIALS.get(slug)
    if custom and len(custom) >= 2:
        return custom
    parts = slug.split("_")
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    if len(slug) >= 3:
        return (slug[0] + slug[2]).upper()
    return slug[:2].upper()


def _write_branded(slug: str) -> bool:
    """Unique per-slug colored tile — last resort."""
    color = BRAND_COLORS.get(slug, "67748E")
    initial = _unique_initial(slug)
    ink = "111111" if color.lower() in ("b2fce4", "ffb3c7", "00c3f7", "34e0a1", "ffcc00") else "FFFFFF"
    svg = (
        "<!-- official-brand -->\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" role="img">\n'
        f'<rect width="64" height="64" rx="14" fill="#{color}"/>\n'
        f'<text x="32" y="40" text-anchor="middle" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="{18 if len(initial) > 1 else 26}" font-weight="700" fill="#{ink}">{initial}</text>\n'
        "</svg>\n"
    )
    (OUT / f"{slug}.svg").write_text(svg, encoding="utf-8")
    return True


def _save_bytes(slug: str, data: bytes) -> bool:
    if _bad(data):
        return False
    k = kind(data)
    try:
        if k == "svg":
            (OUT / f"{slug}.svg").write_text(wrap_svg(data), encoding="utf-8")
        elif k in ("png", "jpeg", "webp"):
            mime = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}[k]
            (OUT / f"{slug}.svg").write_text(wrap_raster(data, mime), encoding="utf-8")
        else:
            return False
        return True
    except (ValueError, OSError):
        return False


def _fetch_one(slug: str) -> tuple[str, str]:
    domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
    icon = SLUG_ICON.get(slug)

    if icon:
        color = BRAND_COLORS.get(slug, "")
        urls = []
        if color:
            urls.append(f"https://cdn.simpleicons.org/{icon}/{color}")
        urls.append(JSdelivr.format(icon=icon))
        for url in urls:
            data = fetch(url, timeout=10)
            if data and kind(data) and _save_bytes(slug, data):
                return slug, "simple-icons"

    if domain:
        for url in (
            f"https://unavatar.io/{domain}?fallback=false",
            f"https://icons.duckduckgo.com/ip3/{domain}.ico",
            f"https://icons.duckduckgo.com/ip3/{domain}.ico",
        ):
            data = fetch(url, timeout=12)
            if data and kind(data) and _save_bytes(slug, data):
                return slug, "unavatar" if "unavatar" in url else "favicon"

    _write_branded(slug)
    return slug, "branded-fallback"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    slugs = sorted(set(payment_plugin_slugs()) | set(reputation_plugin_slugs()))
    results: dict[str, str] = {}
    print(f"Refetching {len(slugs)} logos…")
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_fetch_one, s): s for s in slugs}
        for fut in as_completed(futs):
            slug, src = fut.result()
            results[slug] = src
            print(f"{src:16} {slug}")

    by_hash: dict[str, list[str]] = defaultdict(list)
    ebay = []
    for s in slugs:
        raw = (OUT / f"{s}.svg").read_text(encoding="utf-8", errors="ignore")
        by_hash[hashlib.md5(raw.encode()).hexdigest()].append(s)
        if "/e/" in raw:
            ebay.append(s)

    from collections import Counter
    c = Counter(results.values())
    bad_dups = sum(1 for g in by_hash.values() if len(g) > 1)
    print(f"\nSources: {dict(c)}")
    print(f"Duplicate groups: {bad_dups} | ebay logos: {len(ebay)}")
    return 1 if ebay else 0


if __name__ == "__main__":
    raise SystemExit(main())
