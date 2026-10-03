"""Desktop schema version and waitress packaging constants."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DesktopSchemaTests(unittest.TestCase):
    def test_newer_database_is_rejected(self):
        from desktop.server_mode import DESKTOP_SCHEMA_VERSION, ensure_desktop_schema

        temp = Path(tempfile.mkdtemp(prefix="zintriq-schema-new-"))
        db = temp / "zintriq.db"
        conn = sqlite3.connect(db)
        conn.execute(f"PRAGMA user_version={DESKTOP_SCHEMA_VERSION + 1}")
        conn.commit()
        conn.close()
        with self.assertRaises(SystemExit) as caught:
            ensure_desktop_schema(db)
        self.assertEqual(caught.exception.code, 1)

    def test_older_database_is_stamped(self):
        from desktop.server_mode import DESKTOP_SCHEMA_VERSION, ensure_desktop_schema, stamp_desktop_schema

        temp = Path(tempfile.mkdtemp(prefix="zintriq-schema-old-"))
        db = temp / "zintriq.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE dummy (id INTEGER)")
        conn.execute("PRAGMA user_version=0")
        conn.commit()
        conn.close()
        ensure_desktop_schema(db)
        stamp_desktop_schema(db)
        conn = sqlite3.connect(db)
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        conn.close()
        self.assertEqual(version, DESKTOP_SCHEMA_VERSION)

    def test_missing_database_is_allowed(self):
        from desktop.server_mode import ensure_desktop_schema

        ensure_desktop_schema(Path(tempfile.mkdtemp()) / "missing.db")


class DesktopPackagingGuardTests(unittest.TestCase):
    def test_freeze_support_at_entry(self):
        text = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("multiprocessing.freeze_support()", text)

    def test_frozen_host_does_not_pass_app_py(self):
        text = (ROOT / "desktop" / "flask_host.js").read_text(encoding="utf-8")
        self.assertIn("packaged ? [] : [path.join(repoRoot(), \"app.py\")]", text)
        self.assertNotRegex(text, r"spawn\(pythonPath,\s*\[path\.join\(repoRoot\(\),\s*\"app\.py\"\)")

    def test_waitress_body_limit_exceeds_package_cap(self):
        from desktop.server_mode import WAITRESS_IDENT, WAITRESS_MAX_REQUEST_BODY
        from desktop.transfer import LIMITS

        self.assertGreater(WAITRESS_MAX_REQUEST_BODY, LIMITS.max_uncompressed)
        self.assertEqual(WAITRESS_MAX_REQUEST_BODY, 40 * 1024 * 1024)
        self.assertEqual(WAITRESS_IDENT, "")

    def test_waitress_create_server_accepts_hardening_kwargs(self):
        from waitress.adjustments import Adjustments

        names = set(Adjustments._param_map) if hasattr(Adjustments, "_param_map") else set()
        if not names:
            names = {item for item in dir(Adjustments) if not item.startswith("_")}
        for name in (
            "ident",
            "expose_tracebacks",
            "clear_untrusted_proxy_headers",
            "max_request_body_size",
        ):
            self.assertTrue(
                hasattr(Adjustments, name) or name in names,
                f"waitress Adjustments missing {name}",
            )

    def test_app_id_is_placeholder(self):
        text = (ROOT / "desktop" / "package.json").read_text(encoding="utf-8")
        self.assertIn("com.example.zintriq.unreleased", text)

    def test_check_bundle_rejects_secrets_and_requires_licenses(self):
        script = ROOT / "desktop" / "packaging" / "check_bundle.py"
        temp = Path(tempfile.mkdtemp(prefix="zintriq-bundle-"))
        bad = temp / "bad"
        bad.mkdir()
        (bad / "leak.db").write_bytes(b"sqlite")
        env = os.environ.copy()
        proc = __import__("subprocess").run(
            [sys.executable, str(script), str(bad)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("database", proc.stderr.lower())
        self.assertIn("OFL", proc.stderr)

        good = temp / "good"
        (good / "static" / "fonts" / "geist-sans").mkdir(parents=True)
        (good / "docs").mkdir()
        (good / "static" / "fonts" / "geist-sans" / "OFL.txt").write_text("OFL", encoding="utf-8")
        (good / "docs" / "THIRD_PARTY_NOTICES.md").write_text("notices", encoding="utf-8")
        (good / "ok.txt").write_text("hello", encoding="utf-8")
        proc = __import__("subprocess").run(
            [sys.executable, str(script), str(good)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        (good / "home.txt").write_text("/Users/someone/secret", encoding="utf-8")
        proc = __import__("subprocess").run(
            [sys.executable, str(script), str(good)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("absolute developer path", proc.stderr)

    def test_license_classifier_fails_gpl(self):
        import importlib.util

        path = ROOT / "desktop" / "packaging" / "check_licenses.py"
        spec = importlib.util.spec_from_file_location("zintriq_check_licenses", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.classify("MIT"), "ok")
        self.assertEqual(mod.classify("GNU GPL"), "review")
        self.assertEqual(mod.classify("AGPL-3.0"), "review")
        self.assertEqual(mod.classify(""), "unknown")
        self.assertEqual(mod.classify("UNKNOWN"), "unknown")
