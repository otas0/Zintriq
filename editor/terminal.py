"""Permission-gated workspace terminal (no interactive TTY)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def run(
    workspace: Path,
    command: str,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    cmd = (command or "").strip()
    if not cmd:
        raise ValueError("empty command")
    if len(cmd) > 4000:
        raise ValueError("command too long")
    # Block obvious path escapes via shell cd tricks — still shell, so keep cwd fixed.
    root = workspace.resolve()
    root.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "ZINTRIQ_DESKTOP_TOKEN"}
    env["PWD"] = str(root)
    shell = os.environ.get("SHELL") or ("cmd.exe" if os.name == "nt" else "/bin/sh")
    if os.name == "nt":
        args = [shell, "/c", cmd]
    else:
        args = [shell, "-lc", cmd]
    proc = subprocess.run(
        args,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    out = (proc.stdout or "")[-80_000:]
    err = (proc.stderr or "")[-40_000:]
    return {
        "ok": True,
        "exitCode": proc.returncode,
        "stdout": out,
        "stderr": err,
        "cwd": str(root),
    }
