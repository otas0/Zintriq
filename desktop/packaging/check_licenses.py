#!/usr/bin/env python3
"""Fail the desktop build when a lockfile dependency license is unknown or needs review."""

from __future__ import annotations

import json
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "requirements-desktop.lock.txt"
EXCEPTIONS = Path(__file__).resolve().parent / "license-exceptions.json"

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


def _lock_names() -> set[str]:
    names = set()
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)==", line.rstrip(" \\"))
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


def _exceptions() -> dict[str, str]:
    if not EXCEPTIONS.is_file():
        return {}
    raw = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))
    found = {}
    for item in raw:
        name = str(item.get("name") or "").strip().lower().replace("_", "-")
        reason = str(item.get("reason") or "").strip()
        if name and not reason:
            raise SystemExit(f"license exception for {name} has no reason")
        if name:
            found[name] = reason
    return found


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
    wanted = _lock_names()
    exceptions = _exceptions()
    problems = []
    rows = []
    seen = set()
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        key = name.lower().replace("_", "-")
        if key not in wanted:
            continue
        seen.add(key)
        license_text = _license_of(dist)
        status = classify(license_text)
        rows.append({"name": name, "version": dist.version, "license": license_text, "status": status})
        if status == "ok":
            continue
        reason = exceptions.get(key)
        if reason:
            print(f"license exception used: {name}: {reason}")
            continue
        problems.append(f"{name} {dist.version}: {license_text or '(empty)'} [{status}]")
    missing = sorted(wanted - seen)
    for name in missing:
        reason = exceptions.get(name)
        if reason:
            print(f"license exception used for missing install: {name}: {reason}")
            continue
        problems.append(f"{name}: not installed in this environment [missing]")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("license-report.json")
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if problems:
        print("license review required:", file=sys.stderr)
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"wrote {out} ({len(rows)} lock packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
