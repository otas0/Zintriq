#!/usr/bin/env python3
"""Wrap already-downloaded official brand files into catalog logo tiles."""

from __future__ import annotations

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "integrations" / "logos"


def kind(data: bytes) -> str:
    head = data.lstrip()[:400]
    if head.startswith(b"<") or b"<svg" in head:
        return "svg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:4] == b"RIFF":
        return "webp"
    return ""


def wrap_svg(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    if text.startswith("<?xml"):
        text = text.split("?>", 1)[-1]
    start = text.find("<svg")
    end = text.rfind("</svg>")
    if start == -1 or end == -1:
        raise ValueError("svg missing")
    inner = text[start : end + 6]
    inner = re.sub(r"\swidth='[^']*'|\swidth=\"[^\"]*\"", "", inner, count=1)
    inner = re.sub(r"\sheight='[^']*'|\sheight=\"[^\"]*\"", "", inner, count=1)
    if "xmlns=" not in inner[:280]:
        inner = inner.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    inner = inner.replace(
        "<svg",
        '<svg x="8" y="10" width="104" height="70" preserveAspectRatio="xMidYMid meet"',
        1,
    )
    return (
        "<!-- official-brand -->\n"
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 90" width="64" height="64" role="img">\n'
        '<rect width="120" height="90" rx="12" fill="#fff"/>\n'
        f"{inner}\n"
        "</svg>\n"
    )


def wrap_raster(data: bytes, mime: str) -> str:
    b64 = base64.b64encode(data).decode()
    return (
        "<!-- official-brand -->\n"
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 90" width="64" height="64" role="img">\n'
        '<rect width="120" height="90" rx="12" fill="#fff"/>\n'
        f'<image href="data:{mime};base64,{b64}" x="8" y="12" width="104" height="66" '
        'preserveAspectRatio="xMidYMid meet"/>\n'
        "</svg>\n"
    )


def save(slug: str, data: bytes) -> None:
    k = kind(data)
    if k == "svg":
        (OUT / f"{slug}.svg").write_text(wrap_svg(data), encoding="utf-8")
        return
    mime = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}.get(k)
    if not mime:
        raise ValueError(f"{slug}: unknown file type")
    (OUT / f"{slug}.svg").write_text(wrap_raster(data, mime), encoding="utf-8")


def main() -> None:
    mapping = {
        "atome": Path("/tmp/adyen-atome.svg"),
        "gcash": Path("/tmp/adyen-gcash.svg"),
        "touch_n_go": Path("/tmp/adyen-touchngo.svg"),
        "promptpay": Path("/tmp/adyen-promptpay.svg"),
        "duitnow": Path("/tmp/adyen-duitnow.svg"),
        "truemoney": Path("/tmp/adyen-truemoney.svg"),
        "au_pay": Path("/tmp/adyen-aupay.svg"),
        "momo": Path("/tmp/adyen-momo_wallet.svg"),
        "maya": Path("/tmp/adyen-paymaya_wallet.svg"),
        "kakao_pay": Path("/tmp/adyen-kakaopay.svg"),
        "naver_pay": Path("/tmp/adyen-kcp_naverpay.svg"),
        "affirm": Path("/tmp/adyen-affirm.svg"),
    }
    for slug, src in mapping.items():
        if not src.is_file() or src.stat().st_size < 200:
            print(f"SKIP {slug} missing {src}")
            continue
        save(slug, src.read_bytes())
        print(f"OK {slug} from {src.name} ({src.stat().st_size}b)")


if __name__ == "__main__":
    main()
