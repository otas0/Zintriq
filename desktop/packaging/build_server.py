#!/usr/bin/env python3
"""Freeze the desktop Flask server with the pinned PyInstaller spec (no UPX)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = Path(__file__).resolve().parent / "server.spec"
DIST = ROOT / "desktop" / "resources" / "server"


def main() -> int:
    os.chdir(ROOT)
    DIST.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST.parent),
        "--workpath",
        str(ROOT / "desktop" / "packaging" / "build"),
        str(SPEC),
    ]
    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
