#!/usr/bin/env python3
"""Write SHA256SUMS and an SBOM after electron-builder finishes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "release")
    dest.mkdir(parents=True, exist_ok=True)
    sums = subprocess.call([sys.executable, str(HERE / "sha256sums.py"), str(dest)])
    if sums:
        return sums
    sbom = subprocess.call([sys.executable, str(HERE / "sbom.py"), str(dest / "sbom.cdx.json")])
    if sbom:
        return sbom
    if not (dest / "SHA256SUMS").is_file() or not (dest / "sbom.cdx.json").is_file():
        print("SHA256SUMS or sbom.cdx.json missing after dist", file=sys.stderr)
        return 1
    print(f"dist artifacts ready in {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
