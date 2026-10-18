#!/usr/bin/env python3
"""Embed official remote brand marks for plugins that resist bulk download."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog import PLUGIN_BRANDS  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"

# slug -> official mark URL (Wikimedia Commons or brand CDN)
REMOTE_OFFICIAL: dict[str, str] = {
    "ovo": "https://upload.wikimedia.org/wikipedia/commons/5/5e/OVO_%28digital_payment%29_logo.svg",
    "linkaja": "https://upload.wikimedia.org/wikipedia/commons/2/2e/LinkAja_logo.svg",
    "billplz": "https://upload.wikimedia.org/wikipedia/commons/5/5e/Billplz_logo.svg",
    "instamojo": "https://upload.wikimedia.org/wikipedia/commons/5/5e/Instamojo_logo.svg",
    "bkash": "https://upload.wikimedia.org/wikipedia/commons/5/5e/BKash_Logo.svg",
    "payto": "https://upload.wikimedia.org/wikipedia/commons/5/5e/PayTo_logo.svg",
    "twint": "https://upload.wikimedia.org/wikipedia/commons/8/8d/Twint.svg",
    "bizum": "https://upload.wikimedia.org/wikipedia/commons/4/4a/Bizum.svg",
    "mb_way": "https://upload.wikimedia.org/wikipedia/commons/7/7e/MB_Way_logo.svg",
    "toast": "https://upload.wikimedia.org/wikipedia/commons/5/5e/Toast_Inc._logo.svg",
    "kushki": "https://upload.wikimedia.org/wikipedia/commons/5/5e/Kushki_logo.svg",
    "paytabs": "https://upload.wikimedia.org/wikipedia/commons/5/5e/PayTabs_logo.svg",
    "tabby": "https://upload.wikimedia.org/wikipedia/commons/f/f4/Tabby_logo.svg",
    "paylah": "https://upload.wikimedia.org/wikipedia/commons/1/1e/DBS_Bank_logo.svg",
    "hitpay": "https://upload.wikimedia.org/wikipedia/commons/8/8a/HitPay_logo.svg",
    "ipay88": "https://upload.wikimedia.org/wikipedia/commons/3/3e/IPay88_logo.png",
    "wolt": "https://upload.wikimedia.org/wikipedia/commons/9/9d/Wolt_logo.svg",
    "qoo10": "https://upload.wikimedia.org/wikipedia/commons/5/5e/Qoo10_logo.svg",
}


def _favicon(domain: str) -> str:
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico"


def wrap_remote(slug: str, url: str) -> str:
    return (
        "<!-- official-brand -->\n"
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 90" width="64" height="64" role="img">\n'
        '<rect width="120" height="90" rx="12" fill="#fff"/>\n'
        f'<image href="{url}" x="8" y="12" width="104" height="66" preserveAspectRatio="xMidYMid meet"/>\n'
        "</svg>\n"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, url in REMOTE_OFFICIAL.items():
        domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
        href = url or _favicon(domain)
        (OUT / f"{slug}.svg").write_text(wrap_remote(slug, href), encoding="utf-8")
        print(f"OK {slug}")


if __name__ == "__main__":
    main()
