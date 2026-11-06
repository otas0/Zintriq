"""Workspace text search (rg when available, else Python walk)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".editor",
    "dist",
    "build",
    ".tox",
}


def search(workspace: Path, query: str, *, max_hits: int = 200) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        raise ValueError("empty query")
    if len(q) > 200:
        raise ValueError("query too long")
    root = workspace.resolve()
    if shutil.which("rg"):
        return _rg(root, q, max_hits=max_hits)
    return _walk(root, q, max_hits=max_hits)


def _rg(root: Path, query: str, *, max_hits: int) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "rg",
            "--json",
            "--max-count",
            "20",
            "-g",
            "!node_modules",
            "-g",
            "!.git",
            "-g",
            "!.venv",
            query,
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    hits: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        try:
            obj = __import__("json").loads(line)
        except Exception:
            continue
        if obj.get("type") != "match":
            continue
        data = obj.get("data") or {}
        path = data.get("path", {}).get("text") or ""
        try:
            rel = str(Path(path).resolve().relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        lines = data.get("lines", {}).get("text") or ""
        num = int((data.get("line_number") or 1))
        hits.append({"path": rel, "line": num, "text": lines.rstrip("\n")[:300]})
        if len(hits) >= max_hits:
            break
    return {"ok": True, "engine": "rg", "query": query, "hits": hits}


def _walk(root: Path, query: str, *, max_hits: int) -> dict[str, Any]:
    try:
        pattern = re.compile(re.escape(query))
    except re.error:
        pattern = re.compile(re.escape(query), re.I)
    hits: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = str(path.relative_to(root)).replace("\\", "/")
                hits.append({"path": rel, "line": i, "text": line[:300]})
                if len(hits) >= max_hits:
                    return {"ok": True, "engine": "walk", "query": query, "hits": hits}
    return {"ok": True, "engine": "walk", "query": query, "hits": hits}
