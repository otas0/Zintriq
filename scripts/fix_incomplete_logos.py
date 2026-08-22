#!/usr/bin/env python3
"""Replace incomplete / broken / remote logos with complete official brand marks."""

from __future__ import annotations

import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog import PLUGIN_BRANDS  # noqa: E402
from scripts.fetch_official_logos import kind, wrap_raster, wrap_svg  # noqa: E402
from scripts.apply_official_logos import ADYEN_CDN_NAME, SLUG_ICON  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"
SI_DIR = ROOT / "scripts" / ".cache" / "simple-icons-11.14.0" / "icons"
ADYEN = "https://checkoutshopper-live.adyen.com/checkoutshopper/images/logos/{}.svg"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

# Must-fix targets: remote embeds + known wrong/tiny logos
FIX = [
    "blik", "bukalapak", "cybersource", "easy_wallet", "eat_app", "hyperpay",
    "khalti", "lightspeed", "linkaja", "magento", "moneris", "mpay",
    "naver_pay", "naver_place", "payconiq", "payfast", "pine_labs", "qris",
    "quandoo", "rappi", "revenue_monster", "satispay", "sezzle", "tock",
    "vietqr", "wave_money",
]

# Curated complete official logo URLs (full marks, not 16px favicons)
COMPLETE: dict[str, list[str]] = {
    "blik": [ADYEN.format("blik")],
    "payfast": [
        "https://payfast.io/wp-content/uploads/2022/09/Payfast-Logo.svg",
        "https://www.payfast.co.za/assets/images/payfast-logo.svg",
        ADYEN.format("payfast"),
    ],
    "rappi": [
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/rappi.svg",
    ],
    "bukalapak": [
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/bukalapak.svg",
    ],
    "hyperpay": [
        ADYEN.format("hyperpay"),
        "https://www.hyperpay.com/wp-content/uploads/2021/favicon.ico",
    ],
    "magento": [
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/adobe.svg",
    ],
    "naver_pay": [
        ADYEN.format("kcp_naverpay"),
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/naver.svg",
    ],
    "naver_place": [
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/naver.svg",
    ],
    "cybersource": [
        "https://www.cybersource.com/content/dam/cybersource/global/images/logos/cybersource-logo.svg",
        ADYEN.format("cybersource"),
    ],
    "easy_wallet": [
        "https://www.easycard.com.tw/easycard_web/Content/Images/logo.svg",
        ADYEN.format("easycard"),
    ],
    "eat_app": [
        "https://eat.app/assets/logo.svg",
        "https://eat.app/apple-touch-icon.png",
    ],
    "khalti": [
        "https://khalti.com/static/images/logo.png",
        "https://blog.khalti.com/wp-content/uploads/2019/07/khalti-logo.png",
    ],
    "lightspeed": [
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/lightspeed.svg",
        "https://www.lightspeedhq.com/favicon-196x196.png",
    ],
    "linkaja": [
        ADYEN.format("linkaja"),
        "https://www.linkaja.id/assets/img/logo-linkaja.png",
    ],
    "moneris": [
        ADYEN.format("moneris"),
        "https://www.moneris.com/favicon-196x196.png",
    ],
    "mpay": [
        ADYEN.format("mpay"),
        "https://www.mpay.com.mo/favicon.ico",
    ],
    "payconiq": [
        ADYEN.format("payconiq"),
        "https://www.payconiq.com/favicon-196x196.png",
    ],
    "pine_labs": [
        ADYEN.format("pinelabs"),
        "https://www.pinelabs.com/apple-touch-icon.png",
    ],
    "qris": [
        ADYEN.format("qris"),
        "https://qris.id/homepage/images/logo.png",
    ],
    "quandoo": [],  # extracted from corrupted file below
    "revenue_monster": [
        "https://www.revenuemonster.my/img/logo.png",
        "https://revenuemonster.my/favicon-196x196.png",
    ],
    "satispay": [
        ADYEN.format("satispay"),
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/satispay.svg",
    ],
    "sezzle": [
        ADYEN.format("sezzle"),
        "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/sezzle.svg",
    ],
    "tock": [
        "https://www.exploretock.com/apple-touch-icon.png",
        "https://www.exploretock.com/favicon-196x196.png",
    ],
    "vietqr": [
        ADYEN.format("vietqr"),
        "https://vietqr.net/favicon-196x196.png",
    ],
    "wave_money": [
        "https://www.wavemoney.com.mm/apple-touch-icon.png",
        ADYEN.format("wavemoney"),
    ],
}


def _curl(url: str, timeout: int = 12) -> bytes | None:
    import tempfile
    import os

    fd, path = tempfile.mkstemp(prefix="logo_", suffix=".bin")
    os.close(fd)
    try:
        r = subprocess.run(
            [
                "curl",
                "-4",
                "-sL",
                "--max-time",
                str(timeout),
                "-A",
                UA,
                "-o",
                path,
                "-w",
                "%{http_code}",
                url,
            ],
            capture_output=True,
        )
        code = r.stdout.decode().strip()
        p = Path(path)
        if code != "200" or not p.exists() or p.stat().st_size < 200:
            return None
        data = p.read_bytes()
        head = data[:200].lower()
        if head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<html" in head[:80]:
            return None
        return data
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _save(slug: str, data: bytes) -> bool:
    k = kind(data)
    if not k:
        return False
    if k == "svg":
        text = data.decode("utf-8", errors="ignore")
        if "<title>/e/</title>" in text or "tanuki" in text.lower():
            return False
        # reject huge HTML-contaminated svg
        if len(data) > 80_000 and ("</div>" in text or "<a href" in text):
            return False
        OUT.joinpath(f"{slug}.svg").write_text(wrap_svg(data), encoding="utf-8")
        return True
    if len(data) < 400:
        return False
    mime = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp", "ico": "image/x-icon"}.get(k)
    if not mime:
        return False
    OUT.joinpath(f"{slug}.svg").write_text(wrap_raster(data, mime), encoding="utf-8")
    return True


def _extract_quandoo() -> bytes | None:
    """Pull clean Quandoo wordmark out of previously scraped HTML blob."""
    p = OUT / "quandoo.svg"
    if not p.is_file():
        return None
    t = p.read_text(errors="ignore")
    m = re.search(
        r'(<svg[^>]*viewBox="0 0 165 37"[^>]*>.*?</svg>)',
        t,
        re.I | re.S,
    )
    if not m:
        return None
    svg = m.group(1)
    # keep only first clean mark
    svg = re.sub(r"</svg>.*", "</svg>", svg, count=1, flags=re.S)
    if "F8B333" not in svg and "quandoo" not in svg.lower():
        # still ok if path present
        if "M17.885" not in svg:
            return None
    return svg.encode("utf-8")


def _local_si(slug: str) -> bytes | None:
    icon = SLUG_ICON.get(slug)
    if not icon:
        return None
    p = SI_DIR / f"{icon}.svg"
    if p.is_file() and p.stat().st_size > 200:
        return p.read_bytes()
    return None


def _adyen(slug: str) -> bytes | None:
    name = ADYEN_CDN_NAME.get(slug) or COMPLETE.get(slug, [None])[0]
    if isinstance(name, str) and "adyen.com" in name:
        name = name.rsplit("/", 1)[-1].replace(".svg", "")
    elif slug in ADYEN_CDN_NAME:
        name = ADYEN_CDN_NAME[slug]
    else:
        # try from COMPLETE list
        for u in COMPLETE.get(slug, []):
            if "adyen.com" in u:
                name = u.rsplit("/", 1)[-1].replace(".svg", "")
                break
        else:
            return None
    data = _curl(ADYEN.format(name))
    if data and b"<svg" in data[:300] and b"html" not in data[:80].lower():
        return data
    return None


def _site_logo(slug: str) -> bytes | None:
    domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
    if not domain:
        return None
    hosts = [domain, f"www.{domain}"]
    for host in hosts:
        html_bytes = _curl(f"https://{host}/", timeout=10)
        if not html_bytes:
            continue
        html = html_bytes.decode("utf-8", errors="ignore")
        urls: list[str] = []
        for m in re.finditer(
            r"<link[^>]+rel=[\"'][^\"']*(?:apple-touch-icon|icon)[^\"']*[\"'][^>]*>",
            html,
            re.I,
        ):
            hm = re.search(r"href=[\"']([^\"']+)", m.group(0), re.I)
            if hm:
                href = hm.group(1)
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = f"https://{host}{href}"
                urls.append(href)
        for m in re.finditer(
            r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)",
            html,
            re.I,
        ):
            href = m.group(1)
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = f"https://{host}{href}"
            urls.append(href)
        # prefer larger apple-touch / png / svg
        urls.sort(
            key=lambda u: (
                50 if "apple-touch" in u else 0
                + (40 if u.endswith(".svg") else 0)
                + (20 if u.endswith(".png") else 0)
                + (30 if "logo" in u.lower() else 0)
            ),
            reverse=True,
        )
        for url in urls[:8]:
            data = _curl(url, timeout=8)
            if data and _ok_size(data) and kind(data):
                return data
        for path in (
            "/apple-touch-icon.png",
            "/apple-touch-icon-precomposed.png",
            "/android-chrome-192x192.png",
            "/logo.svg",
            "/logo.png",
        ):
            data = _curl(f"https://{host}{path}", timeout=6)
            if data and _ok_size(data) and kind(data):
                return data
    return None


def _ok_size(data: bytes) -> bool:
    k = kind(data)
    if k == "svg":
        return len(data) >= 300 and b"<path" in data
    return len(data) >= 800  # complete raster marks, not 16px favicons


def fix_one(slug: str) -> tuple[str, str]:
    if slug == "quandoo":
        data = _extract_quandoo()
        if data and _save(slug, data):
            return slug, "extract-quandoo"

    for url in COMPLETE.get(slug, []):
        if not url:
            continue
        data = _curl(url)
        if data and _ok_size(data) and _save(slug, data):
            return slug, f"complete:{url.split('/')[2]}"

    data = _local_si(slug)
    if data and _save(slug, data):
        return slug, "simple-icons"

    data = _adyen(slug)
    if data and _save(slug, data):
        return slug, "adyen"

    data = _site_logo(slug)
    if data and _save(slug, data):
        return slug, "site"

    return slug, "miss"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Fixing {len(FIX)} incomplete logos…", flush=True)
    ok = miss = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(fix_one, s) for s in FIX]
        for fut in as_completed(futs):
            slug, src = fut.result()
            if src == "miss":
                miss += 1
                print(f"MISS {slug}", flush=True)
            else:
                ok += 1
                print(f"OK {slug} ({src})", flush=True)
    print(f"\nDone ok={ok} miss={miss}", flush=True)
    return 1 if miss else 0


if __name__ == "__main__":
    raise SystemExit(main())
