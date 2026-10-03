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


if __name__ == "__main__":
    unittest.main()
