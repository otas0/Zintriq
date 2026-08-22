#!/usr/bin/env python3
"""Fetch official logos from each brand's website — parallel, short timeouts."""

from __future__ import annotations

import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog import (  # noqa: E402
    PLUGIN_BRANDS,
    payment_plugin_slugs,
    reputation_plugin_slugs,
)
from scripts.fetch_official_logos import kind, wrap_raster, wrap_svg  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

DIRECT: dict[str, list[str]] = {
    "gocardless": ["https://framerusercontent.com/images/HGclCakwkjXTJWerSl9H76gCo.svg"],
    "mollie": ["https://framerusercontent.com/images/SeL6IJlQ4Ae7noV1fXjkTlqvo.png"],
    "wolt": [
        "https://wolt-com-static-assets.wolt.com/apple-icon-180x180.png",
        "https://wolt-com-static-assets.wolt.com/apple-icon-152x152.png",
    ],
    "worldpay": [
        "https://images.ctfassets.net/zhwqbd2ar3b8/4tjJgF1mlLT9by5OhXTrK8/"
        "c94fc8972817ed7193fc86401fbe6544/wpisnowgp-main-red.png"
    ],
    "omise": [
        "https://cdn.prod.website-files.com/67481ca1f2e8301c5e5e3895/"
        "67b31dccf355a66a3924d211_favicon-256.png"
    ],
    "midtrans": ["https://midtrans.com/assets/img/ico.png"],
    "fiserv": ["https://fiserv.com/content/dam/fiserv-com/favicon-med.ico"],
    "paystack": ["https://paystack.com/favicon.ico", "https://www.paystack.com/favicon.ico"],
    "opentable": ["https://www.opentable.com/favicon.ico"],
    "sumup": ["https://sumup.com/favicon.ico", "https://www.sumup.com/favicon.ico"],
    "worldline": ["https://worldline.com/favicon.ico"],
    "lightspeed": ["https://www.lightspeedhq.com/favicon.ico"],
    "twocheckout": ["https://www.2checkout.com/favicon.ico"],
    "paytabs": ["https://www.paytabs.com/favicon.ico"],
    "payu_europe": ["https://payu.com/favicon.ico", "https://corporate.payu.com/favicon.ico"],
    "payu_latam": ["https://payu.com/favicon.ico"],
    "nuvei": ["https://nuvei.com/favicon.ico"],
    "cybersource": ["https://www.cybersource.com/favicon.ico"],
    "global_payments": ["https://www.globalpayments.com/favicon.ico"],
    "dlocal": ["https://dlocal.com/favicon.ico"],
    "moneris": ["https://www.moneris.com/favicon.ico"],
    "mpesa": ["https://www.safaricom.co.ke/favicon.ico"],
    "peach_payments": ["https://www.peachpayments.com/favicon.ico"],
    "network_international": ["https://www.network.ae/favicon.ico"],
    "pine_labs": ["https://www.pinelabs.com/favicon.ico"],
    "windcave": ["https://www.windcave.com/favicon.ico"],
    "tamara": ["https://tamara.co/favicon.ico"],
    "payconiq": ["https://www.payconiq.com/favicon.ico"],
    "paidy": ["https://paidy.com/favicon.ico"],
    "toss": ["https://static.toss.im/icons/png/4x/icon-toss-logo.png", "https://toss.im/favicon.ico"],
    "merpay": ["https://jp.mercari.com/favicon.ico", "https://www.mercari.com/favicon.ico"],
    "jkopay": ["https://www.jkopay.com/favicon.ico"],
    "easy_wallet": ["https://www.easycard.com.tw/favicon.ico"],
    "fps": ["https://www.hkicl.com.hk/favicon.ico"],
    "d_barai": ["https://www.nttdocomo.co.jp/favicon.ico"],
    "twoc2p": ["https://2c2p.com/favicon.ico"],
    "ovo": ["https://www.ovo.id/favicon.ico"],
    "linkaja": ["https://www.linkaja.id/favicon.ico"],
    "favepay": ["https://myfave.com/favicon.ico"],
    "qris": ["https://www.bi.go.id/favicon.ico"],
    "lazada_seller": ["https://www.lazada.com/favicon.ico"],
    "kkday": ["https://www.kkday.com/favicon.ico"],
    "hungrypanda": ["https://www.hungrypanda.co/favicon.ico"],
    "holidaycheck": ["https://www.holidaycheck.de/favicon.ico"],
    "menulog": ["https://www.menulog.com.au/favicon.ico"],
    "skipthedishes": ["https://www.skipthedishes.com/favicon.ico"],
    "keeta": ["https://www.keeta.com/favicon.ico"],
    "bentobox": ["https://getbento.com/favicon.ico"],
    "eat_app": ["https://eatapp.co/favicon.ico"],
    "funnow": ["https://www.funnow.com/favicon.ico"],
    "inline": ["https://inline.app/favicon.ico"],
    "tock": ["https://www.exploretock.com/favicon.ico"],
    "zenchef": ["https://www.zenchef.com/favicon.ico"],
    "qoo10": ["https://www.qoo10.com/favicon.ico"],
    "macau_pass": ["https://www.macau-pass.com/favicon.ico"],
    "mpay": ["https://www.mpay.com.mo/favicon.ico"],
    "bnu_pay": ["https://www.bnucard.com/favicon.ico"],
    "icash_pay": ["https://www.icashpay.com.tw/favicon.ico"],
    "pi_wallet": ["https://www.piwallet.com.tw/favicon.ico"],
    "pxpay_plus": ["https://www.pxpayplus.com/favicon.ico"],
    "smilepay": ["https://www.mysmilepay.com/favicon.ico"],
    "bakong": ["https://bakong.nbc.gov.kh/favicon.ico"],
    "wave_money": ["https://www.wavemoney.com.mm/favicon.ico"],
    "khalti": ["https://khalti.com/favicon.ico"],
    "lankaqr": ["https://www.lankapay.net/favicon.ico"],
}

STATIC = (
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/android-chrome-192x192.png",
    "/favicon.svg",
    "/favicon-96x96.png",
    "/favicon.ico",
)

ALT_HOSTS: dict[str, list[str]] = {
    "favepay": ["myfave.com"],
    "bentobox": ["getbento.com"],
    "eat_app": ["eatapp.co"],
    "tock": ["exploretock.com"],
    "payu_europe": ["payu.com", "corporate.payu.com"],
    "payu_latam": ["payu.com"],
    "toss": ["toss.im", "tosspayments.com"],
    "merpay": ["jp.mercari.com", "mercari.com"],
    "mpesa": ["safaricom.co.ke"],
    "lankaqr": ["lankapay.net"],
    "bakong": ["bakong.nbc.gov.kh"],
    "twocheckout": ["2checkout.com"],
    "global_payments": ["globalpayments.com"],
}


def _is_branded(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return 'viewBox="0 0 64 64"' in raw and "<text" in raw


def _curl(url: str, timeout: int = 6) -> bytes | None:
    r = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), "-A", UA, "-w", "%{http_code}", url],
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


def _curl_html(url: str, timeout: int = 8) -> str:
    r = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), "-A", UA, url],
        capture_output=True,
    )
    return r.stdout.decode("utf-8", errors="ignore")


def _extract(html: str, base: str) -> list[str]:
    urls: list[str] = []
    for m in re.finditer(r"<link[^>]+rel=[\"']([^\"']*)[\"'][^>]*>", html, re.I):
        tag, rel = m.group(0), m.group(1).lower()
        if not any(x in rel for x in ("icon", "apple-touch", "shortcut")):
            continue
        hm = re.search(r"href=[\"']([^\"']+)", tag, re.I)
        if hm:
            urls.append(urljoin(base, hm.group(1)))
    for prop in ("og:image", "twitter:image"):
        for m in re.finditer(
            rf"<meta[^>]+(?:property|name)=[\"']{re.escape(prop)}[\"'][^>]+content=[\"']([^\"']+)",
            html,
            re.I,
        ):
            urls.append(urljoin(base, m.group(1)))
    for m in re.finditer(
        r"<img[^>]+(?:class|id|alt)=[\"'][^\"']*logo[^\"']*[\"'][^>]*>", html, re.I
    ):
        sm = re.search(r"src=[\"']([^\"']+)", m.group(0), re.I)
        if sm:
            urls.append(urljoin(base, sm.group(1)))
    return list(dict.fromkeys(urls))


def _save(slug: str, data: bytes) -> bool:
    k = kind(data)
    if not k:
        return False
    if k == "svg":
        if b"html" in data[:160].lower() or b"<title>/e/</title>" in data:
            return False
        OUT.joinpath(f"{slug}.svg").write_text(wrap_svg(data), encoding="utf-8")
        return True
    mime = {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "ico": "image/x-icon",
    }.get(k)
    if not mime or len(data) < 100:
        return False
    OUT.joinpath(f"{slug}.svg").write_text(wrap_raster(data, mime), encoding="utf-8")
    return True


def _hosts(slug: str) -> list[str]:
    domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
    hosts: list[str] = []
    for h in ALT_HOSTS.get(slug, []):
        hosts.append(h)
    if domain:
        hosts.extend([domain, f"www.{domain}"])
    return list(dict.fromkeys(hosts))


def fetch_one(slug: str) -> tuple[str, str]:
    for url in DIRECT.get(slug, []):
        data = _curl(url)
        if data and _save(slug, data):
            return slug, url

    for host in _hosts(slug):
        for path in STATIC:
            url = f"https://{host}{path}"
            data = _curl(url, timeout=5)
            if data and _save(slug, data):
                return slug, url

    for host in _hosts(slug)[:2]:
        html = _curl_html(f"https://{host}/")
        if len(html) < 400:
            continue
        for url in _extract(html, f"https://{host}/")[:10]:
            data = _curl(url)
            if data and _save(slug, data):
                return slug, url
        break
    return slug, ""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = set(payment_plugin_slugs()) | set(reputation_plugin_slugs())
    for orphan in ("taiwan_pay", "ipeen"):
        p = OUT / f"{orphan}.svg"
        if orphan not in catalog and p.is_file():
            p.unlink()
            print(f"REMOVED orphan {orphan}", flush=True)

    targets = sorted(
        s for s in catalog if not (OUT / f"{s}.svg").is_file() or _is_branded(OUT / f"{s}.svg")
    )
    print(f"Fetching official site logos for {len(targets)}…", flush=True)
    ok = miss = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch_one, s): s for s in targets}
        for fut in as_completed(futs):
            slug, url = fut.result()
            if url:
                ok += 1
                p = urlparse(url)
                print(f"OK {slug} <- {p.netloc}{p.path[:70]}", flush=True)
            else:
                miss += 1
                print(f"MISS {slug}", flush=True)
    print(f"\nDone: ok={ok} miss={miss}", flush=True)
    return 1 if miss else 0


if __name__ == "__main__":
    raise SystemExit(main())
