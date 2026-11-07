#!/usr/bin/env python3
"""Write / verify SHA256SUMS for installer artifacts (not unpacked directories)."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

META_NAMES = {
    "SHA256SUMS",
    "sbom.cdx.json",
    "license-report.json",
    "OFL.txt",
    "THIRD_PARTY_NOTICES.md",
    "builder-debug.yml",
    "release-body.md",
}
SKIP_SUFFIX = {".blockmap", ".yml", ".yaml"}
INSTALLER_SUFFIX = {".dmg", ".zip", ".exe", ".deb"}


def is_installer(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name
    if name in META_NAMES or name.startswith("SHA256SUMS"):
        return False
    lower = name.lower()
    if path.suffix.lower() in SKIP_SUFFIX:
        return False
    if path.suffix.lower() in INSTALLER_SUFFIX:
        return True
    return lower.endswith(".appimage")


def installer_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and is_installer(path):
            files.append(path)
    return files


def write_sums(root: Path) -> Path:
    lines = []
    for path in installer_files(root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    dest = root / "SHA256SUMS"
    dest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"wrote {dest} ({len(lines)} files)")
    return dest


def parse_sums(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise SystemExit(f"bad SHA256SUMS line: {raw!r}")
        digest, name = parts
        out[name] = digest
    return out


def verify_coverage(root: Path, sums_path: Path) -> None:
    listed = parse_sums(sums_path)
    expected = {path.name for path in installer_files(root)}
    missing = sorted(expected - set(listed))
    extra = sorted(set(listed) - expected)
    if missing or extra:
        print("SHA256SUMS coverage mismatch", file=sys.stderr)
        if missing:
            print("  missing from SUMS:", ", ".join(missing), file=sys.stderr)
        if extra:
            print("  extra in SUMS:", ", ".join(extra), file=sys.stderr)
        raise SystemExit(1)
    # Re-hash to confirm digests
    for path in installer_files(root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if listed[path.name] != digest:
            print(f"digest mismatch for {path.name}", file=sys.stderr)
            raise SystemExit(1)
    print(f"SHA256SUMS covers {len(expected)} installers")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="artifact directory")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="require SHA256SUMS to list every non-blockmap installer under root",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite SHA256SUMS from installers under root (default if not --verify-only)",
    )
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1

    do_write = args.write or not args.verify
    if do_write:
        # Drop stale per-OS SUMS that would confuse merge-multiple publishes.
        for stale in root.glob("SHA256SUMS*"):
            stale.unlink()
        write_sums(root)
    if args.verify:
        verify_coverage(root, root / "SHA256SUMS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
