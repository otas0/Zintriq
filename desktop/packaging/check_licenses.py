#!/usr/bin/env python3
"""Fail the desktop build when a dependency license is unknown or needs review."""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path

ALLOWED_MARKERS = (
    "MIT",
    "BSD",
    "APACHE",
    "ISC",
    "PSF",
    "PYTHON SOFTWARE",
    "PYTHON-2.0",
    "MPL-2.0",
    "MOZILLA PUBLIC",
    "ZPL",
    "ZOPE PUBLIC",
    "HPND",
    "UNLICENSE",
    "CC0",
    "OFL",
    "SIL OPEN FONT",
    "HISTORICAL PERMISSION",
    "0BSD",
)

REVIEW_MARKERS = (
    "GPL",
    "AGPL",
    "AFFERO",
    "LGPL",
    "SLEEPYCAT",
    "SSPL",
    "COMMERCIAL",
)

SKIP_NAMES = {
    "zintriq-studio",
    "pip",
    "setuptools",
    "wheel",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "macholib",
}


def _license_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    for key in ("License-Expression", "License"):
        value = (meta.get(key) or "").strip()
        if value:
            return value
    classifiers = meta.get_all("Classifier") or []
    licenses = [row.split(" :: ")[-1] for row in classifiers if row.startswith("License ::")]
    return "; ".join(licenses)


def classify(text: str) -> str:
    raw = (text or "").strip()
    if not raw or raw.upper() in {"UNKNOWN", "UNLICENSED"}:
        return "unknown"
    upper = raw.upper()
    if any(marker in upper for marker in REVIEW_MARKERS):
        return "review"
    if any(marker in upper for marker in ALLOWED_MARKERS):
        return "ok"
    return "unknown"


def main() -> int:
    problems = []
    rows = []
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        if name.lower() in SKIP_NAMES:
            continue
        license_text = _license_of(dist)
        status = classify(license_text)
        rows.append({"name": name, "version": dist.version, "license": license_text, "status": status})
        if status != "ok":
            problems.append(f"{name} {dist.version}: {license_text or '(empty)'} [{status}]")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("license-report.json")
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if problems:
        print("license review required:", file=sys.stderr)
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"wrote {out} ({len(rows)} packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
