"""Explicit AI bypass — subprocess only, results go to change stack."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from editor import changes
from editor import permissions as perms


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"ZINTRIQ_DESKTOP_TOKEN"}}
    env["PYTHONUNBUFFERED"] = "1"
    return env


def run_ai(
    *,
    data_dir: Path,
    workspace: Path,
    prompt: str,
    path: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    rel = (path or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError("invalid path")
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())
    before = target.read_text(encoding="utf-8") if target.is_file() else ""
    allow_network = bool(perms.load(data_dir).get("network"))
    payload = json.dumps(
        {
            "prompt": prompt,
            "path": rel,
            "text": before,
            "allow_network": allow_network,
        }
    )
    proc = subprocess.run(
        [sys.executable, "-m", "editor.ai_worker"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=_child_env(),
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(proc.stderr.strip() or f"ai worker exit {proc.returncode}")
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f"ai worker bad output: {exc}") from exc
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or "ai failed")
    after = str(out.get("after") or "")
    if after == before:
        raise RuntimeError("ai produced no change")
    proposed = changes.propose(
        data_dir,
        source="ai",
        files=[{"path": rel, "before": before, "after": after}],
        note=str(out.get("note") or prompt[:200]),
    )
    return {
        "ok": True,
        "change": proposed,
        "provider": out.get("provider") or "unknown",
    }
