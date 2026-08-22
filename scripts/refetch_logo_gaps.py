#!/usr/bin/env python3
"""Second pass — retry unavatar.io for slugs still on branded tiles."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration_catalog import PLUGIN_BRANDS, payment_plugin_slugs, reputation_plugin_slugs  # noqa: E402
from scripts.fetch_official_logos import fetch, kind  # noqa: E402
from scripts.refetch_logos_fast import _save_bytes, _write_branded  # noqa: E402

OUT = ROOT / "static" / "integrations" / "logos"


def _is_branded_tile(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return "viewBox=\"0 0 64 64\"" in raw and "<text" in raw


def main() -> None:
    slugs = sorted(set(payment_plugin_slugs()) | set(reputation_plugin_slugs()))
    targets = [s for s in slugs if _is_branded_tile(OUT / f"{s}.svg")]
    print(f"Retrying {len(targets)} branded tiles via unavatar…")
    ok = 0
    for i, slug in enumerate(targets, 1):
        domain = (PLUGIN_BRANDS.get(slug) or {}).get("domain") or ""
        if not domain:
            continue
        data = fetch(f"https://unavatar.io/{domain}?fallback=false", timeout=20)
        if data and kind(data) and _save_bytes(slug, data):
            ok += 1
            print(f"OK [{i}] {slug}")
        else:
            _write_branded(slug)  # refresh unique initials
    print(f"Upgraded {ok}/{len(targets)}")


if __name__ == "__main__":
    main()
