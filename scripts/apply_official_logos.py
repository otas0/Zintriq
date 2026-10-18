#!/usr/bin/env python3
"""Apply unique official brand logos — local Simple Icons, Adyen marks, verified Wikimedia."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog import (  # noqa: E402
    PLUGIN_BRANDS,
    payment_plugin_slugs,
    reputation_plugin_slugs,
)
from integration_catalog_batch2 import BATCH2_SIMPLE_ICONS  # noqa: E402
from integration_catalog_batch3 import BATCH3_SIMPLE_ICONS  # noqa: E402
from scripts.fetch_official_logos import OFFICIAL, kind, save, wrap_raster, wrap_svg  # noqa: E402
from scripts.refetch_logos_fast import SLUG_ICON as _EXTRA_ICONS  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"
SI_DIR = ROOT / "scripts" / ".cache" / "simple-icons-11.14.0" / "icons"
ADYEN_DIR = ROOT / "scripts" / ".cache" / "adyen-logos"
ADYEN_CDN = "https://checkoutshopper-live.adyen.com/checkoutshopper/images/logos/{}.svg"
JSdelivr = "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/{}.svg"

SLUG_ICON: dict[str, str] = {**BATCH2_SIMPLE_ICONS, **BATCH3_SIMPLE_ICONS, **_EXTRA_ICONS}

# slug -> Adyen CDN logo filename (verified 200 OK)
ADYEN_CDN_NAME: dict[str, str] = {
    "affirm": "affirm",
    "atome": "atome",
    "au_pay": "aupay",
    "bancontact": "bancontact",
    "blik": "blik",
    "bizum": "bizum",
    "ccavenue": "ccavenue",
    "dana": "dana",
    "dragonpay": "dragonpay",
    "duitnow": "duitnow",
    "eps": "eps",
    "fawry": "fawry",
    "gcash": "gcash",
    "giropay": "giropay",
    "grabpay": "grabpay",
    "ideal": "ideal",
    "interac": "interac",
    "interac_e_transfer": "interac",
    "ipay88": "ipay88",
    "kakao_pay": "kakaopay",
    "mb_way": "mbway",
    "maya": "paymaya_wallet",
    "momo": "momo_wallet",
    "nets": "nets",
    "payco": "payco",
    "paynow": "paynow",
    "paypay": "paypay",
    "payto": "payto",
    "poli": "poli",
    "promptpay": "promptpay",
    "przelewy24": "dotpay",
    "rakuten_pay": "rakutenpay",
    "scalapay": "scalapay",
    "swish": "swish",
    "touch_n_go": "touchngo",
    "truemoney": "truemoney",
    "trustly": "trustly",
    "twint": "twint",
    "unionpay": "unionpay",
    "vipps": "vipps",
    "zip": "zip",
}

# slug -> local Adyen SVG basename (without adyen- prefix)
ADYEN_LOCAL: dict[str, str] = {
    "affirm": "affirm",
    "afterpay": "afterpaytouch",
    "airwallex": "airwallex",
    "alipay_hk": "alipay_hk",
    "atome": "atome",
    "au_pay": "aupay",
    "checkout_com": "checkoutcom",
    "d_barai": "dbarai",
    "duitnow": "duitnow",
    "fps": "fps",
    "gcash": "gcash",
    "grabpay": "grabpay",
    "kakao_pay": "kakaopay",
    "maya": "paymaya_wallet",
    "merpay": "merpay",
    "momo": "momo_wallet",
    "naver_pay": "kcp_naverpay",
    "octopus": "octopus",
    "payme": "payme",
    "paypay": "paypay",
    "promptpay": "promptpay",
    "rakuten_pay": "rakutenpay",
    "tap_and_go": "octopus",
    "toss": "tosspay",
    "touch_n_go": "touchngo",
    "truemoney": "truemoney",
    "twoc2p": "2c2p",
    "unionpay": "unionpay",
    "wechat_pay_hk": "wechatpay",
    "zalopay": "zalopay",
    "zip": "zip",
}

ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"clearpay", "afterpay"}),
    frozenset({"interac", "interac_e_transfer"}),
    frozenset({"shop_pay", "shopify_payments", "shopify"}),
    frozenset({"grabpay", "grab_reviews", "grab_paylater"}),
    frozenset({"line_pay", "line_pay_tw", "rabbit_line_pay", "line_official"}),
    frozenset({"tap_and_go", "octopus"}),
    frozenset({"payu_india", "payu_europe", "payu_latam"}),
    frozenset({"shopeepay", "shopee_seller"}),
    frozenset(),  # retired Google plug-ins
    frozenset({"sofort", "klarna"}),
    frozenset({"hoolah", "atome"}),
    frozenset({"becs_direct_debit", "stripe"}),
    frozenset({"amazon_pay", "amazon_seller"}),
    frozenset({"naver_pay", "naver_place"}),
    frozenset({"rakuten_ichiba", "rakuten_pay"}),
    frozenset({"tiktok_business", "tiktok_shop"}),
)


def _curl(url: str, timeout: int = 12) -> bytes | None:
    r = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), "-w", "%{http_code}", url],
        capture_output=True,
    )
    body = r.stdout
    if len(body) < 5:
        return None
    code = body[-3:].decode(errors="ignore")
    data = body[:-3]
    if code != "200" or len(data) < 80:
        return None
    return data


def _bad(data: bytes) -> bool:
    t = data.decode("utf-8", errors="ignore").lower()
    return "<title>/e/</title>" in t or ("/e/" in t[:120] and len(data) < 900)


def _is_branded(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return 'viewBox="0 0 64 64"' in raw and "<text" in raw


def _is_official(path: Path) -> bool:
    if not path.is_file():
        return False
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return "official-brand" in raw and not _is_branded(path)


def _save_bytes(slug: str, data: bytes) -> bool:
    if _bad(data):
        return False
    k = kind(data)
    try:
        if k == "svg":
            OUT.joinpath(f"{slug}.svg").write_text(wrap_svg(data), encoding="utf-8")
        elif k in ("png", "jpeg", "webp", "ico"):
            mime = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp", "ico": "image/x-icon"}[k]
            OUT.joinpath(f"{slug}.svg").write_text(wrap_raster(data, mime), encoding="utf-8")
        else:
            return False
        return True
    except (ValueError, OSError):
        return False


def _local_si(icon: str) -> bytes | None:
    p = SI_DIR / f"{icon}.svg"
    if p.is_file() and p.stat().st_size > 80:
        data = p.read_bytes()
        return data if not _bad(data) else None
    return None


def _local_adyen(name: str) -> bytes | None:
    for stem in (name, name.replace("_", "")):
        p = ADYEN_DIR / f"adyen-{stem}.svg"
        if p.is_file() and p.stat().st_size > 80:
            data = p.read_bytes()
            return data if b"<svg" in data[:300] else None
    return None


def _domain_favicon(domain: str) -> bytes | None:
    if not domain:
        return None
    for path in ("/favicon.svg", "/favicon.ico", "/apple-touch-icon.png"):
        data = _curl(f"https://{domain}{path}", timeout=10)
        if data and kind(data) and len(data) >= 200:
            return data
    return None


def _try_sources(slug: str) -> tuple[bytes | None, str]:
    if slug in ADYEN_LOCAL:
        data = _local_adyen(ADYEN_LOCAL[slug])
        if data:
            return data, "adyen-local"

    if slug in ADYEN_CDN_NAME:
        data = _curl(ADYEN_CDN.format(ADYEN_CDN_NAME[slug]))
        if data and kind(data) == "svg" and not _bad(data):
            return data, "adyen-cdn"

    icon = SLUG_ICON.get(slug)
    if icon:
        data = _local_si(icon)
        if data:
            return data, "simple-icons-local"
        data = _curl(JSdelivr.format(icon))
        if data and kind(data) == "svg" and not _bad(data):
            return data, "simple-icons-cdn"

    for url in OFFICIAL.get(slug, []):
        data = _curl(url, timeout=20)
        if data and kind(data) and not _bad(data):
            return data, "wikimedia"

    domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
    data = _domain_favicon(domain)
    if data:
        return data, "domain-favicon"
    return None, "miss"


def _allowed_dup(a: str, b: str) -> bool:
    for group in ALIAS_GROUPS:
        if a in group and b in group:
            return True
    return False


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    slugs = sorted(set(payment_plugin_slugs()) | set(reputation_plugin_slugs()))
    stats: dict[str, int] = defaultdict(int)
    hash_to_slug: dict[str, str] = {}

    for slug in slugs:
        path = OUT / f"{slug}.svg"
        if _is_official(path) and not _is_branded(path):
            stats["kept"] += 1
            raw = path.read_text(encoding="utf-8", errors="ignore")
            hash_to_slug[hashlib.md5(raw.encode()).hexdigest()] = slug
            continue

        data, source = _try_sources(slug)
        if not data:
            stats["miss"] += 1
            print(f"MISS {slug}")
            continue

        h = hashlib.md5(data).hexdigest()
        if h in hash_to_slug and not _allowed_dup(slug, hash_to_slug[h]):
            domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
            data2 = _domain_favicon(domain)
            if data2 and kind(data2):
                data = data2
                source = "domain-favicon-dedup"
                h = hashlib.md5(data).hexdigest()

        if _save_bytes(slug, data):
            hash_to_slug[h] = slug
            stats[source] += 1
            print(f"OK {slug} ({source})")
        else:
            stats["fail"] += 1
            print(f"FAIL {slug}")

    by_hash: dict[str, list[str]] = defaultdict(list)
    branded = []
    for s in slugs:
        p = OUT / f"{s}.svg"
        if not p.is_file():
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        by_hash[hashlib.md5(raw.encode()).hexdigest()].append(s)
        if _is_branded(p):
            branded.append(s)

    bad_dups = []
    for group in by_hash.values():
        if len(group) <= 1:
            continue
        if not all(_allowed_dup(group[0], x) for x in group[1:]):
            bad_dups.append(group)

    print(f"\nStats: {dict(stats)}")
    print(f"Branded tiles left: {len(branded)}")
    print(f"Bad duplicate groups: {len(bad_dups)}")
    for g in bad_dups:
        print(f"  DUP: {', '.join(g)}")
    if branded:
        print("Still branded:", ", ".join(branded[:30]), ("..." if len(branded) > 30 else ""))
    return 1 if branded or bad_dups else 0


if __name__ == "__main__":
    raise SystemExit(main())
