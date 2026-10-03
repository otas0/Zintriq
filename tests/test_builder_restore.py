"""Restore and .zintriq import must not bypass schema validation."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from universal_builder_core import init_universal_builder_tables, restore_project_snapshot

ROOT = Path(__file__).resolve().parents[1]


class RestoreAndImportBoundaryTests(unittest.TestCase):
    def test_restore_rejects_invalid_model_schema(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_universal_builder_tables(conn)
        conn.execute(
            "INSERT INTO builder_projects (workspace_id, name, slug, kind, status, settings) VALUES (1,'t','t','application','draft','{}')"
        )
        project_id = int(conn.execute("SELECT id FROM builder_projects").fetchone()[0])
        snapshot = {
            "surfaces": [],
            "documents": [],
            "data_models": [
                {
                    "model_key": "notes",
                    "name": "Notes",
                    "schema": {"$ref": "https://evil.example/schema.json"},
                    "adapter": "native",
                }
            ],
        }
        with self.assertRaises(ValueError):
            restore_project_snapshot(conn, project_id, snapshot)

    def test_zintriq_import_writes_the_parsed_dict_not_restore_snapshot(self):
        transfer = (ROOT / "desktop" / "transfer.py").read_text(encoding="utf-8")
        self.assertNotIn("restore_project_snapshot", transfer)
        self.assertIn("_insert_children(conn, parsed", transfer)
        self.assertIn("original zip bytes are not read again", transfer)
        core = (ROOT / "universal_builder_core.py").read_text(encoding="utf-8")
        self.assertIn("api_builder_core_restore_draft", core)
        marketplace = (ROOT / "universal_builder_marketplace.py").read_text(encoding="utf-8")
        self.assertIn("restore_project_snapshot", marketplace)


if __name__ == "__main__":
    unittest.main()
