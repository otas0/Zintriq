"""Fail the CI job when desktop logs contain the smoke run's startup token.

The token file is deleted here and is not part of the uploaded paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FORBIDDEN_NAMES = {
    "smoke-session.json",
    "secret_key",
    "zintriq.db",
    "zintriq.db-wal",
    "zintriq.db-shm",
}


def _files() -> list[Path]:
    found = []
    log_dir = Path(os.environ.get("ZINTRIQ_SMOKE_LOG_DIR") or "")
    if log_dir.is_dir():
        found.extend(path for path in log_dir.rglob("*") if path.is_file())
    for name in ("unittest.txt", "smoke.txt"):
        path = Path(name)
        if path.is_file():
            found.append(path)
    extra = os.environ.get("ZINTRIQ_ARTIFACT_FILES") or ""
    for piece in extra.split(","):
        piece = piece.strip()
        if not piece:
            continue
        path = Path(piece)
        if path.is_file():
            found.append(path)
    return found


def _token() -> str:
    raw = os.environ.get("ZINTRIQ_SMOKE_TOKEN_FILE") or ""
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_file():
        return ""
    token = path.read_text(encoding="utf-8").strip()
    path.unlink()
    return token


def main() -> int:
    token = _token()
    for path in _files():
        if path.name in FORBIDDEN_NAMES:
            print(f"refusing artifact file name {path.name}", file=sys.stderr)
            return 1
        if token and token in path.read_text(encoding="utf-8", errors="replace"):
            print(f"desktop token found in {path.name}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
