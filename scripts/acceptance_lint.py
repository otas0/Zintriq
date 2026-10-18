#!/usr/bin/env python3
"""Product-body lint: ruff on meta/desktop host + offline JS acceptance checks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Product body: meta core + acceptance tooling + meta/desktop test modules.
# Merchant Flask modules stay out of this gate (not meta core).
RUFF_PATHS = (
    "meta",
    "desktop/server_mode.py",
    "desktop/meta_store.py",
    "desktop/meta_routes.py",
    "tests/test_meta_description.py",
    "tests/test_meta_simulation.py",
    "tests/test_meta_uir.py",
    "tests/test_meta_uir_marks.py",
    "tests/test_meta_coverage_boost.py",
    "tests/test_meta_instantiation.py",
    "tests/test_meta_runtime.py",
    "tests/test_meta_kernels.py",
    "tests/test_meta_collab.py",
    "tests/test_meta_editor_views.py",
    "tests/test_meta_plugin_pack.py",
    "tests/test_acceptance_gates.py",
    "tests/test_desktop_meta_apply.py",
    "tests/test_desktop_mode.py",
    "tests/test_desktop_packaging.py",
    "scripts/acceptance_coverage.py",
    "scripts/acceptance_lint.py",
    "scripts/acceptance_pack_check.py",
)


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd or ROOT).returncode


def lint_python() -> int:
    ruff = shutil.which("ruff")
    if not ruff:
        candidate = Path(sys.executable).resolve().parent / ("ruff.exe" if os.name == "nt" else "ruff")
        ruff = str(candidate) if candidate.is_file() else None
    if not ruff:
        return _run([sys.executable, "-m", "ruff", "check", *RUFF_PATHS])
    return _run([ruff, "check", *RUFF_PATHS])


def lint_js() -> int:
    node = shutil.which("node")
    if not node:
        print("node missing; skip JS lint", flush=True)
        return 0 if os.environ.get("CI") != "true" else 1
    script = ROOT / "scripts" / "acceptance_js_lint.js"
    return _run([node, str(script)])


def main() -> int:
    py = lint_python()
    if py != 0:
        return py
    js = lint_js()
    if js != 0:
        return js
    print("acceptance lint ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
