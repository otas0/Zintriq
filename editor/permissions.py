"""Tool permission model — deny by default for AI/network/terminal."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, bool] = {
    "fs.read": True,
    "fs.write": True,  # user Save
    "changes.apply": True,  # accept/reject tool diffs
    "git.read": True,
    "git.write": False,
    "ai.run": False,
    "terminal": False,
    "debug": False,
    "debug.write": True,  # setVariable / writeMemory / hot reload (attach may force off)
    "network": False,
}

KNOWN = frozenset(DEFAULTS)


def permissions_path(data_dir: Path) -> Path:
    return Path(data_dir) / "permissions.json"


def load(data_dir: Path) -> dict[str, bool]:
    path = permissions_path(data_dir)
    merged = dict(DEFAULTS)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in KNOWN:
                    merged[key] = bool(value)
    return merged


def save(data_dir: Path, perms: dict[str, Any]) -> dict[str, bool]:
    merged = dict(DEFAULTS)
    for key, value in (perms or {}).items():
        if key in KNOWN:
            merged[key] = bool(value)
    path = permissions_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged


class PermissionDenied(PermissionError):
    pass


def require(data_dir: Path, *keys: str) -> None:
    perms = load(data_dir)
    missing = [k for k in keys if not perms.get(k)]
    if missing:
        raise PermissionDenied(f"permission denied: {', '.join(missing)}")
