"""Acceptance gates: coverage scope, lint tooling, pack matrix, plugin unload contract."""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AcceptanceGateTests(unittest.TestCase):
    def test_expandable_builtin_boundaries(self):
        from meta.boundary import get, list_boundaries, reset_for_tests

        reset_for_tests()
        ids = {item.id for item in list_boundaries()}
        for key in ("vr.space", "robotics.cell", "print3d.job", "cnc.job", "chain.ledger", "chip"):
            self.assertIn(key, ids)
        self.assertEqual(get("vr.space").instantiation_target, "web_build")
        self.assertEqual(get("robotics.cell").instantiation_target, "device")
        self.assertEqual(get("print3d.job").kind, "hardware")
        self.assertEqual(get("chain.ledger").kind, "software")

    def test_editor_views_js_exposes_unregister_and_dispose(self):
        text = (ROOT / "static/studio/editor-views.js").read_text(encoding="utf-8")
        for needle in (
            "unregister:",
            "unload:",
            "dispose:",
            "clearHost",
            "destroySandbox",
            "unregisterOwner",
            'sandbox", "allow-scripts"',
        ):
            self.assertIn(needle, text)

    def test_engine_js_exposes_dispose_and_owner_commands(self):
        text = (ROOT / "static/studio/engine.js").read_text(encoding="utf-8")
        for needle in ("unregisterOwner:", "dispose:", "off:", "input.unbind"):
            self.assertIn(needle, text)

    def test_smoke_asserts_cold_start(self):
        text = (ROOT / "desktop/scripts/smoke.js").read_text(encoding="utf-8")
        self.assertIn("ZINTRIQ_SMOKE_COLD_MS", text)
        self.assertIn("cold start", text.lower())
        self.assertRegex(text, r"coldMs\s*[<>=]|COLD_MS|cold start")

    def test_pack_workflow_covers_three_platforms(self):
        text = (ROOT / ".github/workflows/desktop-pack.yml").read_text(encoding="utf-8")
        self.assertIn("macos-latest", text)
        self.assertIn("windows-latest", text)
        self.assertIn("ubuntu-24.04", text)
        self.assertIn("npm run dist", text)
        pkg = json.loads((ROOT / "desktop/package.json").read_text(encoding="utf-8"))
        scripts = pkg.get("scripts") or {}
        for key in ("dist:mac", "dist:win", "dist:linux"):
            self.assertIn(key, scripts)
        targets = pkg.get("build") or {}
        self.assertIn("dmg", str(targets.get("mac") or {}))
        self.assertIn("nsis", str(targets.get("win") or {}))
        self.assertIn("AppImage", str(targets.get("linux") or {}))

    def test_ruff_and_coverage_scripts_exist(self):
        self.assertTrue((ROOT / "ruff.toml").is_file())
        self.assertTrue((ROOT / "scripts/acceptance_coverage.py").is_file())
        self.assertTrue((ROOT / "scripts/acceptance_lint.py").is_file())
        self.assertTrue((ROOT / "scripts/acceptance_js_lint.js").is_file())
        self.assertTrue((ROOT / "scripts/acceptance_pack_check.py").is_file())
        cov = ast.parse((ROOT / "scripts/acceptance_coverage.py").read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(node, ast.FunctionDef) for node in cov.body))

    def test_desktop_workflow_runs_acceptance(self):
        text = (ROOT / ".github/workflows/desktop.yml").read_text(encoding="utf-8")
        self.assertIn("acceptance_coverage.py", text)
        self.assertIn("acceptance_lint.py", text)
        self.assertIn("acceptance_pack_check.py", text)


if __name__ == "__main__":
    unittest.main()
