"""Engine Play, World Place, and local AI suite. Not Unity / Roblox / OpenAI."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta.boundary import reset_for_tests
from meta.collab.loopback import register_peer, replicate_place
from meta.description import atom, struct, to_json
from meta.instantiation import TARGET_DESKTOP_HOST, instantiate
from meta.runtime.ai_tools import ALLOWED_TOOLS, run_tool
from meta.runtime.engine import play_from_system, play_session, stop_session
from meta.runtime.kernels import kernel_spec
from meta.runtime.local_infer import embed_local, write_fixture_weights
from meta.runtime.structure_systems import (
    ai_suite_system,
    structure_flags,
    unity_structure_system,
    world_structure_system,
)
from meta.runtime.world import copy_object, place_spec, replicate_objects
from plugin_catalog import reset_reviews


class EngineWorldAiTests(unittest.TestCase):
    def setUp(self):
        reset_for_tests()
        reset_reviews()

    def tearDown(self):
        reset_for_tests()
        reset_reviews()

    def test_play_session_steps_dt_and_stop(self):
        scene = struct(
            kind=atom("string", value="scene", has_value=True),
            play=atom("bool", value=True, has_value=True),
            mesh=atom("string", value="cube", has_value=True),
        )
        physics = struct(
            kind=atom("string", value="physics.body", has_value=True),
            y=atom("float", value=1.0, has_value=True),
            vy=atom("float", value=0.0, has_value=True),
        )
        skeleton = struct(kind=atom("string", value="skeleton.rig", has_value=True))
        session = play_session(scene, physics=physics, skeleton=skeleton, frames=2, dt=1.0 / 60.0)
        self.assertTrue(session["engine"])
        self.assertFalse(session["unity"])
        self.assertEqual(len(session["frames"]), 2)
        self.assertGreater(session["t"], 0)
        self.assertTrue(session["frames"][0]["physics"])
        self.assertTrue(session["frames"][0]["skin"])
        stopped = stop_session(session["frames"][-1])
        self.assertFalse(stopped["playing"])
        compiled = kernel_spec(scene)
        self.assertTrue(compiled.get("engine") or compiled.get("hierarchy") is not None)

    def test_engine_system_play_and_instantiate(self):
        desc = unity_structure_system()
        flags = structure_flags(desc)
        self.assertEqual(flags["form"], "engine")
        played = play_from_system(desc, frames=2)
        self.assertEqual(len(played["frames"]), 2)
        art = instantiate(desc, target=TARGET_DESKTOP_HOST, slug="engine")
        self.assertFalse(art.payload_object()["unity"])

    def test_place_copy_and_loopback_replicate(self):
        desc = struct(
            kind=atom("string", value="world.place", has_value=True),
            title=atom("string", value="Yard", has_value=True),
        )
        spec = place_spec(desc)
        self.assertEqual(spec["kind"], "world.place")
        self.assertFalse(spec["wan"])
        self.assertFalse(spec["roblox"])
        self.assertEqual(spec["scripts"]["via"], "desc")
        copied = copy_object(spec["objects"][0])
        self.assertTrue(str(copied["id"]).endswith("-copy"))
        merged = replicate_objects(spec["objects"], [copied])
        self.assertGreaterEqual(len(merged), 2)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "a"
        peer = Path(tmp.name) / "b"
        root.mkdir()
        peer.mkdir()
        register_peer(root, str(peer))
        status = replicate_place(root, spec)
        self.assertEqual(status["copied"], 1)
        self.assertFalse(status["wan"])
        self.assertTrue((peer / "world" / "place.json").is_file())
        world = world_structure_system()
        self.assertEqual(structure_flags(world)["form"], "world")
        instantiate(world, target=TARGET_DESKTOP_HOST, slug="world")

    def test_local_ai_embed_and_tools(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        write_fixture_weights(root, "local.json")
        vec = embed_local("hello cube", data_root=root, name="local.json")
        self.assertFalse(vec["hosted"])
        self.assertFalse(vec["openai"])
        self.assertEqual(len(vec["vector"]), 8)
        self.assertEqual(ALLOWED_TOOLS, frozenset({"add_part", "submit_plugin", "explain"}))
        explained = run_tool("explain", {"prompt": "missing part"}, data_root=root)
        self.assertTrue(explained["ok"])
        self.assertTrue(explained["output"])
        suite = ai_suite_system()
        patched = run_tool("add_part", {"key": "extra", "title": "Extra", "kind": "scene"}, code=to_json(suite))
        self.assertTrue(patched["ok"])
        self.assertIn("extra", patched["code"])
        draft = run_tool("submit_plugin", {"id": "community-engine", "name": "Engine form", "form": "engine"})
        self.assertTrue(draft["ok"])
        self.assertEqual(draft["pack"]["form"], "engine")
        unknown = run_tool("shell", {})
        self.assertFalse(unknown["ok"])
        instantiate(suite, target=TARGET_DESKTOP_HOST, slug="ai-suite")

    def test_produce_without_model(self):
        from meta.runtime.produce import guess_kind, produce

        self.assertEqual(guess_kind("a cube on a table"), "scene")
        self.assertEqual(guess_kind("home page"), "page")
        made = produce(prompt="cube", slug="made-cube")
        self.assertFalse(made["model"])
        self.assertFalse(made["openai"])
        self.assertEqual(made["kind"], "scene")
        self.assertTrue(made["artifact"].checksum)
        self.assertTrue(made["code"].startswith("{"))
        page = produce(kind="page", slug="made-page", title="Hello")
        self.assertEqual(page["kind"], "page")
        self.assertTrue(page["artifact"].public_url)
        from plugin_catalog import reset_reviews

        reset_reviews()
        self.addCleanup(reset_reviews)
        plugin = produce(kind="plugin", title="My AI", prompt="AI")
        self.assertEqual(plugin["kind"], "plugin")
        self.assertIsNone(plugin["artifact"])
        self.assertEqual(plugin["pack"]["form"], "AI")
        self.assertTrue(plugin["pack"]["stamp"])
        app = produce(kind="app", slug="made-app", title="Host")
        self.assertEqual(app["kind"], "engine")


if __name__ == "__main__":
    unittest.main()
