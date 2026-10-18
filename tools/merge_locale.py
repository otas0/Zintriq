#!/usr/bin/env python3
"""Merge translated catalogs into i18n/locales/{code}.json.

Usage:
  python3 tools/merge_locale.py CODE <<'JSON'
  { "nav.home": "...", ... }
  JSON

Or:
  python3 tools/merge_locale.py CODE path/to/partial.json

Ensures every key from i18n/_active_en.json is present after merge
(missing keys stay absent so callers can detect gaps — pass --fill-en to copy EN).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "i18n" / "locales"
ACTIVE = ROOT / "i18n" / "_active_en.json"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: merge_locale.py CODE [partial.json] [--fill-en]", file=sys.stderr)
        return 2
    code = sys.argv[1]
    fill_en = "--fill-en" in sys.argv
    args = [a for a in sys.argv[2:] if a != "--fill-en"]
    if args:
        incoming = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    else:
        incoming = json.loads(sys.stdin.read())
    if not isinstance(incoming, dict):
        print("incoming must be a JSON object", file=sys.stderr)
        return 2
    path = LOCALES / f"{code}.json"
    existing = {}
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
    active = json.loads(ACTIVE.read_text(encoding="utf-8")) if ACTIVE.is_file() else {}
    merged = dict(existing)
    for k, v in incoming.items():
        if v is None:
            continue
        merged[str(k)] = str(v)
    if fill_en:
        for k, v in active.items():
            merged.setdefault(k, v)
    # Prefer keeping only active + any legacy already present
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    have = sum(1 for k in active if k in merged)
    print(f"{code}: {have}/{len(active)} active keys ({len(merged)} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
