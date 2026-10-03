#!/usr/bin/env python3
"""Refuse a desktop bundle that ships secrets, home paths, or missing licenses."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SECRET_NAMES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
}

ENV_NAME = re.compile(r"^\.env.*$", re.IGNORECASE)
HOME_PATH = re.compile(
    rb"(?:/Users/|/home/|[A-Za-z]:\\Users\\|/opt/homebrew/)",
    re.IGNORECASE,
)
KEY_BLOB = re.compile(
    rb"(-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----)|"
    rb"(AKIA[0-9A-Z]{16})|"
    rb"(sk_live_[0-9A-Za-z]{16,})|"
    rb"(ghp_[0-9A-Za-z]{20,})|"
    rb"(xox[baprs]-[0-9A-Za-z-]{20,})",
)

SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__"}
TEXT_SUFFIX = {
    ".js",
    ".json",
    ".html",
    ".css",
    ".txt",
    ".md",
    ".py",
    ".map",
    ".yml",
    ".yaml",
    ".xml",
    ".plist",
    ".spec",
    ".cfg",
    ".ini",
    ".toml",
    ".csv",
}
BINARY_SUFFIX = {
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".pyc",
    ".pyo",
    ".zip",
    ".whl",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".icns",
    ".ico",
    ".node",
    ".pak",
    ".dat",
}


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def _require(path: Path, label: str, errors: list) -> None:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")


def scan(root: Path) -> list:
    errors = []
    ofl = list(root.rglob("OFL.txt"))
    notices = list(root.rglob("THIRD_PARTY_NOTICES.md"))
    if not ofl:
        errors.append("OFL license file is missing from the bundle")
    if not notices:
        errors.append("third-party license list is missing from the bundle")
    for path in _iter_files(root):
        name = path.name
        suffix = path.suffix.lower()
        if suffix in SECRET_NAMES or name.lower().endswith(".sqlite"):
            errors.append(f"database or key file packed: {path}")
            continue
        if ENV_NAME.match(name) or suffix == ".env":
            errors.append(f"env file packed: {path}")
            continue
        if name.endswith(".pem") or name.endswith(".key"):
            errors.append(f"key file packed: {path}")
            continue
        if suffix in BINARY_SUFFIX:
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"unreadable {path}: {exc}")
            continue
        if suffix not in TEXT_SUFFIX and b"\0" in data[:1024]:
            continue
        sample = data[: 1024 * 1024]
        if HOME_PATH.search(sample):
            errors.append(f"absolute developer path in {path}")
        if KEY_BLOB.search(sample):
            errors.append(f"possible secret material in {path}")
    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_bundle.py <dir> [dir...]", file=sys.stderr)
        return 2
    errors = []
    for raw in sys.argv[1:]:
        root = Path(raw)
        if not root.exists():
            errors.append(f"missing path {root}")
            continue
        errors.extend(scan(root))
    if errors:
        for item in errors:
            print(item, file=sys.stderr)
        return 1
    print("bundle checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
