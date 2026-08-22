#!/usr/bin/env python3
"""Fetch official logos for batch-2 plugins from Simple Icons + Wikimedia."""

from __future__ import annotations

import ssl
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog_batch2 import BATCH2_SIMPLE_ICONS  # noqa: E402
from scripts.fetch_official_logos import fetch, save  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"
CTX = ssl.create_default_context()
UA = {
    "User-Agent": "ZintriqLogoFetch/1.2 (official brand marks)",
    "Accept": "image/svg+xml,image/png,*/*",
}

# Extra Wikimedia / official URLs for batch-2 slugs without Simple Icons match.
WIKI: dict[str, list[str]] = {
    "paynow": ["https://upload.wikimedia.org/wikipedia/commons/8/8e/PayNow_Logo.svg"],
    "dana": ["https://upload.wikimedia.org/wikipedia/commons/7/7e/Dana_%28company%29_logo.svg"],
    "ovo": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/OVO_%28digital_payment%29_logo.svg"],
    "phonepe": ["https://upload.wikimedia.org/wikipedia/commons/7/71/PhonePe_Logo.svg"],
    "paytm": ["https://upload.wikimedia.org/wikipedia/commons/2/24/Paytm_Logo_%28standalone%29.svg"],
    "wise": ["https://upload.wikimedia.org/wikipedia/commons/5/5c/Wise_%28formerly_TransferWise%29_logo.svg"],
    "revolut": ["https://upload.wikimedia.org/wikipedia/commons/6/6c/Revolut_logo.svg"],
    "ideal": ["https://upload.wikimedia.org/wikipedia/commons/e/e6/IDEAL_Logo.svg"],
    "doordash": ["https://upload.wikimedia.org/wikipedia/commons/6/6a/DoorDash_Logo.svg"],
    "airbnb": ["https://upload.wikimedia.org/wikipedia/commons/6/69/Airbnb_Logo_B%C3%A9lo.svg"],
    "shopify": ["https://upload.wikimedia.org/wikipedia/commons/0/0e/Shopify_logo_2018.svg"],
    "woocommerce": ["https://upload.wikimedia.org/wikipedia/commons/2/2a/WooCommerce_logo.svg"],
    "michelin_guide": ["https://upload.wikimedia.org/wikipedia/commons/6/6d/Michelin_star.svg"],
    "boost": ["https://upload.wikimedia.org/wikipedia/commons/7/7a/Boost_%28Malaysia%29_logo.svg"],
    "bkash": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/BKash_Logo.svg"],
    "mpesa": ["https://upload.wikimedia.org/wikipedia/commons/1/15/M-PESA_LOGO-01.svg"],
    "venmo": ["https://upload.wikimedia.org/wikipedia/commons/7/7a/Venmo_logo.svg"],
    "toast": ["https://upload.wikimedia.org/wikipedia/commons/5/5e/Toast_Inc._logo.svg"],
    "windcave": ["https://upload.wikimedia.org/wikipedia/commons/8/8a/PaymentExpress_logo.svg"],
    "macau_pass": ["https://upload.wikimedia.org/wikipedia/zh/4/4a/MacauPass.svg"],
}


def fetch_simple_icon(slug: str) -> bytes | None:
    return fetch(f"https://cdn.simpleicons.org/{slug}", timeout=5)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ok, missing = [], []

    targets = sorted(set(BATCH2_SIMPLE_ICONS) | set(WIKI))
    for slug in targets:
        path = OUT / f"{slug}.svg"
        if path.is_file():
            raw = path.read_text(encoding="utf-8", errors="ignore")
            if "official-brand" in raw and path.stat().st_size >= 200:
                ok.append(slug)
                continue

        data = None
        si = BATCH2_SIMPLE_ICONS.get(slug)
        if si:
            data = fetch_simple_icon(si)
        if not data and slug in WIKI:
            for url in WIKI[slug]:
                data = fetch(url, timeout=6)
                if data:
                    break
        if data and save(slug, data):
            ok.append(slug)
            print(f"OK {slug}")
        else:
            missing.append(slug)

    print(f"Done — official: {len(ok)}, missing: {len(missing)}")


if __name__ == "__main__":
    main()
