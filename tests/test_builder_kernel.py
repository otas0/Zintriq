"""Kernel registry contracts for K1. Execution routes land in later steps."""

from __future__ import annotations

import unittest
from pathlib import Path

from builder_components import ACTION_REGISTRY, normalize_builder_action, registry_payload
from qr_experience_actions import normalize_action as normalize_qr_action
from builder_kernel.ids import IdentifierError, check_document_key, new_record_key
from builder_kernel.limits import COMPOSE_MAX_DEPTH, COMPOSE_MAX_STEPS
from builder_kernel.registry import KernelRegistry, kernel

ROOT = Path(__file__).resolve().parents[1]


class KernelRegistryTests(unittest.TestCase):
    def test_core_pack_registers_record_actions_and_editor_payload(self):
        kernel.ensure_core()
        self.assertTrue(kernel.known_action_id("create_record"))
        self.assertTrue(kernel.known_action_id("core/create_record"))
        self.assertTrue(kernel.known_action_id("update_record"))
        self.assertTrue(kernel.known_action_id("delete_record"))
        self.assertEqual(kernel.resolve_action_id("create_record"), "core/create_record")
        payload = registry_payload()
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["kernel_schema_version"], 1)
        self.assertEqual(set(payload["actions"]), set(ACTION_REGISTRY))
        self.assertIn("core/on_click", payload["triggers"])
        self.assertIn("core/record.created", payload["events"])

    def test_unknown_action_id_is_not_aliased(self):
        kernel.ensure_core()
        self.assertFalse(kernel.known_action_id("open"))
        self.assertIsNone(kernel.resolve_action_id("not_registered"))

    def test_official_seed_actions_are_registered(self):
        kernel.ensure_core()
        source = (ROOT / "universal_builder_core.py").read_text(encoding="utf-8")
        self.assertIn("'open_page'", source)
        self.assertTrue(kernel.known_action_id("open_page"))
        self.assertNotIn("action_type='open'", source.replace(" ", ""))

    def test_editor_posts_registry_action_type_values(self):
        text = (ROOT / "static" / "builder" / "universal-builder.js").read_text(encoding="utf-8")
        self.assertIn("action_type: typeSelect.value", text)
        payload = registry_payload()
        self.assertIn("create_record", payload["actions"])
        self.assertIn("start_workflow", payload["actions"])

    def test_reserved_document_key(self):
        with self.assertRaises(IdentifierError):
            check_document_key("records")
        with self.assertRaises(IdentifierError):
            check_document_key("Records")
        self.assertEqual(check_document_key("home"), "home")

    def test_record_keys_are_random_and_prefixed(self):
        keys = {new_record_key() for _ in range(20)}
        self.assertEqual(len(keys), 20)
        for key in keys:
            self.assertTrue(key.startswith("rec_"))
            self.assertRegex(key, r"^rec_[0-9a-f]{32}$")

    def test_builder_unknown_action_is_rejected_qr_still_coerces(self):
        with self.assertRaises(ValueError):
            normalize_builder_action({"type": "not_registered"})
        loose = normalize_qr_action({"type": "not_registered"})
        self.assertEqual(loose["type"], "show_information")

    def test_start_workflow_is_registered(self):
        kernel.ensure_core()
        self.assertTrue(kernel.known_action_id("start_workflow"))
        self.assertEqual(kernel.resolve_action_id("start_workflow"), "core/start_workflow")

    def test_compose_limits_reject_deep_and_long_pipelines(self):
        registry = KernelRegistry()
        too_long = [{"id": "core/create_record"} for _ in range(COMPOSE_MAX_STEPS + 1)]
        with self.assertRaises(ValueError):
            registry.register_action({"id": "pack/too-long", "compose": too_long})
        nested = {"id": "core/create_record"}
        for _ in range(COMPOSE_MAX_DEPTH + 1):
            nested = {"id": "pack/step", "compose": [nested]}
        with self.assertRaises(ValueError):
            registry.register_action({"id": "pack/too-deep", "compose": [nested]})

    def test_kernel_events_never_persist_payload_body(self):
        import sqlite3

        from builder_kernel.events import log_kernel_event, migrate_kernel_events

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE builder_projects (id INTEGER PRIMARY KEY)"
        )
        conn.execute("INSERT INTO builder_projects(id) VALUES (1)")
        migrate_kernel_events(conn)
        log_kernel_event(
            conn,
            project_id=1,
            event_id="core/record.created",
            action_id="core/create_record",
            record_key="rec_abc",
            status="ok",
            payload={"title": "secret body", "model_key": "notes"},
        )
        row = conn.execute(
            "SELECT id, event_id, status, payload FROM builder_kernel_events WHERE project_id=1"
        ).fetchone()
        self.assertIsInstance(row["id"], int)
        self.assertEqual(row["event_id"], "core/record.created")
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["payload"], "{}")
        self.assertNotIn("secret", row["payload"])

    def test_core_contributes_appear_in_editor_payload(self):
        payload = registry_payload()
        self.assertIn("contributes", payload)
        self.assertEqual(set(payload["contributes"]), {"editor", "sidebar", "commands"})
        self.assertIn(
            {"id": "core.open_publish", "title": "Publish"},
            payload["contributes"]["commands"],
        )
        package_ids = {item["package_id"] for item in payload["packages"]}
        self.assertIn("core", package_ids)

    def test_package_contributes_contract(self):
        from universal_builder_packages import (
            package_summary,
            validate_contributes,
            validate_package_manifest,
        )

        self.assertEqual(validate_contributes(None), [])
        self.assertEqual(
            validate_contributes({"editor": [], "sidebar": [], "commands": []}),
            [],
        )
        self.assertTrue(
            any("Unsupported contributes key" in item for item in validate_contributes({"workflows": []}))
        )
        self.assertTrue(
            any(".title is required" in item for item in validate_contributes({
                "commands": [{"id": "pack.demo"}],
            }))
        )
        manifest = {
            "id": "demo.notes",
            "name": "Notes",
            "publisher": "zintriq",
            "version": "1.0.0",
            "schema_version": 1,
            "package_type": "capability",
            "required_capabilities": ["core"],
            "permissions": ["builder.read"],
            "compatibility": {"builder_schema": 2},
            "contributes": {
                "editor": [{"id": "demo.notes.panel", "title": "Notes"}],
                "sidebar": [{"id": "demo.notes.nav", "title": "Notes"}],
                "commands": [{"id": "demo.notes.open", "title": "Open notes"}],
            },
        }
        self.assertEqual(validate_package_manifest(manifest), [])
        summary = package_summary(manifest)
        self.assertEqual(summary["contributes"]["commands"][0]["id"], "demo.notes.open")

        registry = KernelRegistry()
        registry.register_contributes(manifest["id"], manifest["contributes"])
        payload = registry.editor_payload()
        self.assertIn(
            {"id": "demo.notes.open", "title": "Open notes"},
            payload["contributes"]["commands"],
        )
        with self.assertRaises(ValueError):
            registry.register_contributes("bad.pack", {"workflows": []})


if __name__ == "__main__":
    unittest.main()
