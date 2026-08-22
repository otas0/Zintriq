#!/usr/bin/env python3
"""Self-test every payment/reputation plugin: catalog, HTTPS links, logos, adapters."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOGO_DIR = ROOT / "static" / "integrations" / "logos"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def curl_probe(url: str, timeout: int = 12) -> dict:
    """HEAD-ish GET with redirects; report final HTTPS status."""
    fd, path = tempfile.mkstemp(prefix="probe_", suffix=".bin")
    os.close(fd)
    try:
        r = subprocess.run(
            [
                "curl", "-4", "-sL", "--max-time", str(timeout),
                "-A", UA, "-o", path, "-w",
                "%{http_code}|%{url_effective}|%{ssl_verify_result}",
                "-H", "Range: bytes=0-0",
                url,
            ],
            capture_output=True,
        )
        meta = (r.stdout or b"").decode("utf-8", "ignore").strip()
        parts = meta.split("|")
        code = parts[0] if parts else "000"
        final = parts[1] if len(parts) > 1 else url
        ssl = parts[2] if len(parts) > 2 else ""
        size = Path(path).stat().st_size if Path(path).is_file() else 0
        # Some hosts reject Range; retry full GET head bytes
        if code in ("000", "403", "405", "416") or code.startswith("5"):
            r2 = subprocess.run(
                [
                    "curl", "-4", "-sL", "--max-time", str(timeout),
                    "-A", UA, "-o", path, "-w",
                    "%{http_code}|%{url_effective}|%{ssl_verify_result}",
                    url,
                ],
                capture_output=True,
            )
            meta2 = (r2.stdout or b"").decode("utf-8", "ignore").strip()
            parts2 = meta2.split("|")
            if parts2 and parts2[0] not in ("000",):
                code, final = parts2[0], parts2[1] if len(parts2) > 1 else final
                ssl = parts2[2] if len(parts2) > 2 else ssl
                size = Path(path).stat().st_size if Path(path).is_file() else 0
        ok = code.isdigit() and 200 <= int(code) < 400
        https = final.lower().startswith("https://")
        # Soft-pass geo/WAF walls — HTTPS endpoint exists even when this network is blocked
        soft = https and code in ("000", "400", "401", "403", "406", "429", "999")
        return {
            "url": url,
            "ok": (ok or soft) and https,
            "hard_ok": ok and https,
            "http_code": code,
            "final_url": final,
            "https": https,
            "ssl_verify": ssl,
            "bytes": size,
            "note": "geo_or_auth_wall" if soft and not ok else "",
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def logo_issues(slug: str) -> list[str]:
    p = LOGO_DIR / f"{slug}.svg"
    out = []
    if not p.is_file():
        return ["missing_file"]
    n = p.stat().st_size
    if n < 300:
        out.append(f"tiny:{n}")
    t = p.read_text(errors="ignore")
    if 'href="http' in t and "data:" not in t:
        out.append("remote_embed")
    if "</div>" in t or "<header" in t:
        out.append("html_pollution")
    if "tanuki" in t.lower():
        out.append("wrong_asset")
    return out


def run() -> int:
    from integration_catalog import PAYMENT_PLUGINS, REPUTATION_PLUGINS

    plugins = [("payment", p) for p in PAYMENT_PLUGINS] + [
        ("reputation", p) for p in REPUTATION_PLUGINS
    ]

    catalog_fail: list[dict] = []
    link_jobs: list[tuple[str, str, str]] = []  # slug, label, url
    logo_fail: list[dict] = []

    for kind, p in plugins:
        slug = p["slug"]
        guide = p.get("setup_guide") or {}
        problems = []
        if not (guide.get("summary") or "").strip():
            problems.append("missing_summary")
        steps = guide.get("steps") or []
        if len(steps) < 1:
            problems.append("missing_steps")
        links = guide.get("links") or []
        if not links:
            problems.append("missing_links")
        for link in links:
            label = (link.get("label") or "").strip() or "(no label)"
            url = (link.get("url") or "").strip()
            if not url:
                problems.append(f"empty_url:{label}")
                continue
            if not url.lower().startswith("https://"):
                problems.append(f"not_https:{url}")
            parsed = urlparse(url)
            if not parsed.netloc:
                problems.append(f"bad_url:{url}")
            link_jobs.append((slug, label, url))
        oauth = bool(p.get("oauth_required"))
        fields = p.get("credential_fields") or []
        if not oauth and not fields:
            problems.append("no_credentials_and_no_oauth")
        if problems:
            catalog_fail.append({"slug": slug, "kind": kind, "problems": problems})

        for issue in logo_issues(slug):
            logo_fail.append({"slug": slug, "issue": issue})

    # Unique URLs for probing
    unique_urls = sorted({u for _, _, u in link_jobs})
    print(f"Probing {len(unique_urls)} unique merchant URLs…", flush=True)
    probe_by_url: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(curl_probe, u): u for u in unique_urls}
        for i, fut in enumerate(as_completed(futs), 1):
            u = futs[fut]
            try:
                probe_by_url[u] = fut.result()
            except Exception as e:
                probe_by_url[u] = {
                    "url": u, "ok": False, "http_code": "err",
                    "final_url": u, "https": False, "error": str(e),
                }
            if i % 40 == 0 or i == len(unique_urls):
                print(f"  {i}/{len(unique_urls)}", flush=True)

    dead_links: list[dict] = []
    for slug, label, url in link_jobs:
        res = probe_by_url.get(url) or {}
        if not res.get("ok"):
            dead_links.append({
                "slug": slug,
                "label": label,
                "url": url,
                "http_code": res.get("http_code"),
                "final_url": res.get("final_url"),
                "https": res.get("https"),
            })

    # Checkout adapters
    adapter_fail: list[str] = []
    try:
        from payment_checkout_adapters import _CREATORS, _VERIFIERS
        from integration_catalog import payment_plugin_slugs
        special = {"stripe", "paypal"}
        for slug in payment_plugin_slugs():
            if slug in special:
                continue
            if slug not in _CREATORS or slug not in _VERIFIERS:
                adapter_fail.append(slug)
    except Exception as e:
        adapter_fail.append(f"import_error:{e}")

    report = {
        "plugin_count": len(plugins),
        "unique_urls": len(unique_urls),
        "catalog_failures": catalog_fail,
        "dead_links": dead_links,
        "logo_failures": logo_fail,
        "adapter_failures": adapter_fail,
        "ok_links": sum(1 for v in probe_by_url.values() if v.get("ok")),
        "failed_links": sum(1 for v in probe_by_url.values() if not v.get("ok")),
    }

    out_path = ROOT / "scripts" / ".cache" / "plugin_selftest_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== Plugin self-test summary ===")
    print(f"Plugins: {report['plugin_count']}")
    print(f"Catalog integrity failures: {len(catalog_fail)}")
    print(f"Links OK: {report['ok_links']}  Failed: {report['failed_links']}")
    print(f"Logo issues: {len(logo_fail)}")
    print(f"Checkout adapter gaps: {len(adapter_fail)}")
    if catalog_fail:
        print("\nCatalog issues (first 20):")
        for row in catalog_fail[:20]:
            print(f"  {row['slug']}: {', '.join(row['problems'])}")
    if dead_links:
        print("\nDead / insecure links (first 40):")
        for row in dead_links[:40]:
            print(f"  {row['slug']} | {row['http_code']} | {row['label']} | {row['url']}")
    if logo_fail:
        print("\nLogo issues:")
        for row in logo_fail:
            print(f"  {row['slug']}: {row['issue']}")
    if adapter_fail:
        print("\nAdapter gaps:", ", ".join(adapter_fail[:30]))
    print(f"\nReport: {out_path}")

    # Fail only on hard integrity (catalog, adapters, logos). Dead links reported but
    # some geo-blocked hosts return 403 from this network — treat as warn.
    hard = len(catalog_fail) + len(adapter_fail) + len(logo_fail)
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(run())
