#!/usr/bin/env python3
"""Replace wordmark placeholders with official brand marks from Wikimedia / Simple Icons."""

from __future__ import annotations

import base64
import re
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "integrations" / "logos"
CTX = ssl.create_default_context()
UA = {
    "User-Agent": "ZintriqLogoFetch/1.1 (local catalog; official brand marks only)",
    "Accept": "image/svg+xml,image/png,image/jpeg,image/webp,*/*",
}

# Official files hosted by Wikimedia / Wikipedia (brand marks, not wordmark placeholders).
OFFICIAL: dict[str, list[str]] = {
    "affirm": ["https://upload.wikimedia.org/wikipedia/commons/f/ff/Affirm_logo.svg"],
    "gcash": ["https://upload.wikimedia.org/wikipedia/commons/5/52/GCash_logo.svg"],
    "toss": ["https://upload.wikimedia.org/wikipedia/commons/3/30/Toss-logo.svg"],
    "touch_n_go": [
        "https://upload.wikimedia.org/wikipedia/commons/f/fb/Touch_%27n_Go_eWallet_logo.svg"
    ],
    "trip_com": ["https://upload.wikimedia.org/wikipedia/commons/7/7a/Trip.com_logo.svg"],
    "airwallex": [
        "https://upload.wikimedia.org/wikipedia/commons/4/47/Airwallex_logo_%282025%29.png"
    ],
    "duitnow": ["https://upload.wikimedia.org/wikipedia/commons/2/22/DuitNow_QR_Logo.png"],
    "promptpay": ["https://upload.wikimedia.org/wikipedia/commons/c/c5/PromptPay-logo.png"],
    "twoc2p": ["https://upload.wikimedia.org/wikipedia/commons/3/39/2C2P_Logo.png"],
    "hungrypanda": ["https://upload.wikimedia.org/wikipedia/commons/7/74/HungryPanda_logo.png"],
    "kkday": ["https://upload.wikimedia.org/wikipedia/commons/d/d7/KKday_Logo.svg"],
    "resy": ["https://upload.wikimedia.org/wikipedia/commons/4/43/Resy_logo.svg"],
    "octopus": ["https://upload.wikimedia.org/wikipedia/en/8/83/Octopus_Card.svg"],
    "au_pay": ["https://upload.wikimedia.org/wikipedia/commons/8/8e/Au_Pay_Logo.png"],
    "thefork": ["https://upload.wikimedia.org/wikipedia/commons/e/e4/The_fork_logo.png"],
    "fps": ["https://upload.wikimedia.org/wikipedia/zh/4/4c/FPS_Logo_TC.svg"],
    "merpay": ["https://upload.wikimedia.org/wikipedia/commons/7/7f/Mercari_logo_2018.svg"],
}


def fetch(url: str, timeout: int = 20) -> bytes | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            data = resp.read()
            if not data or len(data) < 80:
                return None
            return data
    except Exception as exc:
        print(f"  fail {url}: {exc}")
        return None


def kind(data: bytes) -> str:
    head = data.lstrip()[:400]
    if b"<svg" in head[:800]:
        return "svg"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:4] == b"RIFF":
        return "webp"
    return ""


def _svg_viewbox(open_tag: str, body: str) -> str:
    """Resolve a viewBox so nested SVGs scale with preserveAspectRatio instead of clipping."""
    m = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', open_tag, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    wm = re.search(r'\bwidth\s*=\s*["\']([0-9.]+)', open_tag, re.I)
    hm = re.search(r'\bheight\s*=\s*["\']([0-9.]+)', open_tag, re.I)
    if wm and hm:
        return f"0 0 {wm.group(1)} {hm.group(1)}"
    # Last resort: crude numeric extents from path-ish content
    nums = [float(x) for x in re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", body[:12000])]
    xs = [n for n in nums if 0 <= n <= 4000]
    if len(xs) >= 4:
        lo, hi = min(xs), max(xs)
        if hi > lo:
            pad = max(1.0, (hi - lo) * 0.02)
            return f"{lo - pad:.2f} {lo - pad:.2f} {hi - lo + 2 * pad:.2f} {hi - lo + 2 * pad:.2f}"
    return "0 0 100 100"


def wrap_svg(raw: bytes, bg: str = "#fff") -> str:
    text = raw.decode("utf-8", errors="ignore")
    if text.startswith("<?xml"):
        text = text.split("?>", 1)[-1]
    # Unwrap prior official-brand shells so re-wrap stays single-level
    if "<!-- official-brand -->" in text[:80]:
        img = re.search(
            r'<image[^>]+href="(data:image/[^"]+)"[^>]*/?>',
            text,
            re.I,
        )
        if img:
            href = img.group(1)
            return (
                "<!-- official-brand -->\n"
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 96" width="104" height="64" role="img">\n'
                f'<rect width="160" height="96" rx="12" fill="{bg}"/>\n'
                f'<image href="{href}" x="8" y="10" width="144" height="76" '
                'preserveAspectRatio="xMidYMid meet"/>\n'
                "</svg>\n"
            )
        nested = re.search(
            r'<svg[^>]*x="\d+"[^>]*>([\s\S]*)</svg>\s*</svg>\s*$',
            text,
            re.I,
        )
        if nested:
            # Prefer the brand payload: find first inner <svg …>…</svg>
            m2 = re.search(r"(<svg\b[\s\S]*</svg>)\s*$", text.strip(), re.I)
            if m2:
                # Extract innermost brand svg if double-wrapped
                pass
        # Pull first real brand svg after the shell rect
        m3 = re.search(r"<rect[^/]*/>\s*(<svg\b[\s\S]*)</svg>\s*$", text, re.I)
        if m3:
            text = m3.group(1)
            if not text.rstrip().endswith("</svg>"):
                text = text + "</svg>"

    start = text.find("<svg")
    end = text.rfind("</svg>")
    if start == -1 or end == -1:
        raise ValueError("svg missing")
    open_end = text.find(">", start)
    if open_end == -1:
        raise ValueError("svg open tag broken")
    open_tag = text[start : open_end + 1]
    body = text[open_end + 1 : end]
    # Drop non-geometry chrome that blocks peel / pollutes badges
    body = re.sub(r"<script\b[\s\S]*?</script>", "", body, flags=re.I)
    body = re.sub(r"<style\b[\s\S]*?</style>", "", body, flags=re.I)
    # Peel empty sizing wrappers: <svg width/height> <svg viewBox>…</svg> </svg>
    for _ in range(6):
        stripped = body.strip()
        if not stripped.lower().startswith("<svg"):
            break
        child_start = stripped.find("<svg")
        child_open_end = stripped.find(">", child_start)
        if child_open_end == -1:
            break
        depth = 0
        i = child_start
        child_end = None
        while i < len(stripped):
            o = stripped.find("<svg", i)
            c = stripped.find("</svg>", i)
            if c == -1:
                break
            if o != -1 and o < c:
                depth += 1
                i = o + 4
            else:
                depth -= 1
                i = c + 6
                if depth == 0:
                    child_end = i
                    break
        if child_end is None:
            break
        after = stripped[child_end:].strip()
        if after and not after.startswith("<!--"):
            break
        open_tag = stripped[child_start : child_open_end + 1]
        body = stripped[child_open_end + 1 : child_end - 6]
    vb = _svg_viewbox(open_tag, body)
    # Old wrap slots used as fake viewBoxes — rebuild from path `d` extents only
    slot_vbs = {"0 0 104 70", "0 0 104 50", "0 0 112 60", "0 0 100 100"}
    if vb in slot_vbs and "<svg" not in body.lower():
        d_chunks = re.findall(r'\bd="([^"]+)"', body) + re.findall(r"\bd='([^']+)'", body)
        nums = [float(x) for chunk in d_chunks for x in re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", chunk)]
        pos = [n for n in nums if n >= 0]
        if pos:
            side = max(pos)
            # Prefer square icon artboards (Simple Icons etc.)
            if side <= 128:
                vb = f"0 0 {side:.2f} {side:.2f}"
            else:
                pad = side * 0.04
                vb = f"0 0 {side + pad:.2f} {side + pad:.2f}"
        else:
            vb = "0 0 64 64"
    return (
        "<!-- official-brand -->\n"
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 96" width="104" height="64" role="img">\n'
        f'<rect width="160" height="96" rx="12" fill="{bg}"/>\n'
        f'<svg x="8" y="10" width="144" height="76" viewBox="{vb}" '
        f'preserveAspectRatio="xMidYMid meet" overflow="visible" '
        f'xmlns="http://www.w3.org/2000/svg">{body}</svg>\n'
        "</svg>\n"
    )


def wrap_raster(data: bytes, mime: str, bg: str = "#fff") -> str:
    b64 = base64.b64encode(data).decode()
    return (
        "<!-- official-brand -->\n"
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 96" width="104" height="64" role="img">\n'
        f'<rect width="160" height="96" rx="12" fill="{bg}"/>\n'
        f'<image href="data:{mime};base64,{b64}" x="8" y="10" width="144" height="76" '
        'preserveAspectRatio="xMidYMid meet"/>\n'
        "</svg>\n"
    )


def save(slug: str, data: bytes) -> bool:
    k = kind(data)
    if k == "svg":
        (OUT / f"{slug}.svg").write_text(wrap_svg(data), encoding="utf-8")
        return True
    mime = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp", "ico": "image/x-icon"}.get(k)
    if mime:
        (OUT / f"{slug}.svg").write_text(wrap_raster(data, mime), encoding="utf-8")
        return True
    return False


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ok, missing = [], []
    for slug, urls in OFFICIAL.items():
        got = None
        for url in urls:
            got = fetch(url)
            if got and kind(got):
                break
            got = None
        if got and save(slug, got):
            ok.append(slug)
            print(f"OK {slug} ({kind(got)} {len(got)}b)")
        else:
            missing.append(slug)
            print(f"MISSING {slug}")
    print("OK", ok)
    print("MISSING", missing)


if __name__ == "__main__":
    main()
