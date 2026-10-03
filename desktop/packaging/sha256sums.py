#!/usr/bin/env python3
"""Write SHA256SUMS for installer artifacts (not unpacked directories)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

SKIP_DIR_NAMES = {"mac", "mac-arm64", "mac-universal", "linux-unpacked", "linux-arm64-unpacked", "win-unpacked", "win-ia32-unpacked"}
SKIP_SUFFIX = {".blockmap"}


def files_for(root: Path):
    for path in sorted(root.iterdir()):
        if path.is_dir():
            continue
        if path.name in {"SHA256SUMS", "sbom.cdx.json", "license-report.json"}:
            continue
        if path.suffix.lower() in SKIP_SUFFIX:
            continue
        yield path


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    lines = []
    for path in files_for(root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    dest = root / "SHA256SUMS"
    dest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"wrote {dest} ({len(lines)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
