#!/usr/bin/env python3
"""Run meta package statement coverage; fail below 80% (branch optional)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = float(os.environ.get("ZINTRIQ_COVERAGE_MIN", "80"))


def main() -> int:
    python = sys.executable
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cov_file = ROOT / ".coverage.meta"
    if cov_file.exists():
        cov_file.unlink()
    env["COVERAGE_FILE"] = str(cov_file)
    cmd = [
        python,
        "-m",
        "coverage",
        "run",
        "--source=meta",
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_meta*.py",
    ]
    print("+", " ".join(cmd), flush=True)
    run = subprocess.run(cmd, cwd=ROOT, env=env)
    if run.returncode != 0:
        return run.returncode
    report = subprocess.run(
        [python, "-m", "coverage", "report", f"--fail-under={THRESHOLD:.0f}"],
        cwd=ROOT,
        env=env,
    )
    return report.returncode


if __name__ == "__main__":
    raise SystemExit(main())
