#!/usr/bin/env python3
"""Merge/write marketing locale catalogs. Data lives in scripts/world_locales/*.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "i18n" / "locales"
DATA = Path(__file__).resolve().parent / "world_locales"

CORE = ("home.core.data", "home.core.interface", "home.core.logic", "home.core.connection", "home.core.publish")
CORE_VALS = ("Data", "Interface", "Logic", "Connection", "Publish")

NAV = {
    "primitives", "templates", "pricing", "security", "docs", "workspace",
    "signin", "signout", "create_account", "how_it_works", "compositions",
    "blog", "changelog", "about", "contact", "community",
}


def marketing_keys(en: dict[str, str]) -> list[str]:
    keys: list[str] = []
    for k in sorted(en):
        if k.startswith("region.") or k.startswith("group.") or k.startswith("page."):
            keys.append(k)
        elif k in ("lang.apply", "footer.rights", "footer.ops"):
            keys.append(k)
        elif k.startswith("nav.") and k[4:] in NAV:
            keys.append(k)
        elif k.startswith((
            "home.meta", "home.title", "home.lead", "home.cta_",
            "home.pos.", "home.flow.", "home.core.", "home.start.",
            "home.paths.", "home.price.", "home.trust.", "home.close.",
        )):
            keys.append(k)
    return keys


def write_locale(code: str, marketing: dict[str, str], required: list[str]) -> tuple[int, int]:
    path = LOCALES / f"{code}.json"
    existing: dict[str, str] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing = {str(k): str(v) for k, v in existing.items()}
    for k, v in marketing.items():
        existing[k] = v
    for k, v in zip(CORE, CORE_VALS):
        existing[k] = v
    missing = [k for k in required if k not in existing]
    if missing:
        raise SystemExit(f"{code}: missing {len(missing)} keys e.g. {missing[:5]}")
    # stable key order: existing non-marketing first (sorted), then marketing sorted
    mset = set(required)
    other = {k: v for k, v in existing.items() if k not in mset}
    out = {**{k: other[k] for k in sorted(other)}, **{k: existing[k] for k in required}}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(out), len(required)


def main() -> None:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    required = marketing_keys(en)
    if not DATA.is_dir():
        raise SystemExit(f"missing data dir {DATA}")
    results = []
    for path in sorted(DATA.glob("*.json")):
        code = path.stem
        marketing = json.loads(path.read_text(encoding="utf-8"))
        total, mcount = write_locale(code, marketing, required)
        results.append((code, total, mcount))
    for code, total, mcount in results:
        print(f"{code}.json written total={total} marketing={mcount}")
    print(f"done {len(results)} locales")


if __name__ == "__main__":
    main()
