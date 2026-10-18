"""Structure systems instantiate onto desktop_host. Not brand clones."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meta.boundary import reset_for_tests
from meta.description import atom, sequence, struct
from meta.instantiation import TARGET_DESKTOP_HOST, instantiate
from meta.runtime.desktop_host import apply_desktop_host, editor_plugin_ids, zintriq_system_desc
from meta.runtime.kernels import assemble_film, kernel_spec, scene_compile
from meta.runtime.structure_systems import structure_catalog, structure_flags
from plugin_catalog import catalog, loop_cycle, reset_reviews


class StructureSystemTests(unittest.TestCase):
    def setUp(self):
        reset_for_tests()
        reset_reviews()

    def tearDown(self):
        reset_for_tests()
        reset_reviews()

    def test_all_structure_systems_instantiate_desktop_host(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        catalog = structure_catalog()
        self.assertEqual(
            set(catalog),
            {"cam", "cjk", "grade", "layout", "mirror", "skin", "sync", "unity", "world", "ai-suite", "zintriq"},
        )
        for key, factory in catalog.items():
            desc = factory()
            flags = structure_flags(desc)
            self.assertFalse(flags["unity"], msg=key)
            self.assertFalse(flags["wan"], msg=key)
            self.assertFalse(flags["cdn"], msg=key)
            art = instantiate(desc, target=TARGET_DESKTOP_HOST, slug=key)
            again = instantiate(desc, target=TARGET_DESKTOP_HOST, slug=key)
            self.assertEqual(art.checksum, again.checksum, msg=key)
            body = art.payload_object()
            self.assertFalse(body["unity"], msg=key)
            self.assertFalse(body["wan"], msg=key)
            self.assertEqual(body["launch"]["bind"], "127.0.0.1", msg=key)
            stored = apply_desktop_host(desc, slug=key, data_root=root, parts=body.get("parts"))
            folder = root / "desktop" / key
            self.assertTrue((folder / "launch.json").is_file(), msg=key)
            launch = json.loads((folder / "launch.json").read_text(encoding="utf-8"))
            self.assertTrue(launch["loopback_only"], msg=key)
            self.assertFalse(launch["wan"], msg=key)
            editor_keys = [item["key"] for item in body.get("parts") or [] if item.get("key") not in {"workbench", "flask"}]
            self.assertEqual(editor_keys, stored["host"]["editors"], msg=key)
            self.assertEqual(editor_keys, launch["editors"], msg=key)

    def test_skin_cam_grade_structure_fields(self):
        skin = kernel_spec(struct(kind=atom("string", value="skeleton.rig", has_value=True)))
        self.assertIn("weights", skin)
        self.assertIn("cluster", skin)
        self.assertIn("blend", skin)
        cam = kernel_spec(
            struct(
                kind=atom("string", value="circuit", has_value=True),
                nets=sequence(struct(name=atom("string", value="n1", has_value=True))),
                vias=sequence(struct(x=atom("float", value=1, has_value=True), y=atom("float", value=1, has_value=True))),
            )
        )
        for field in ("netlist", "apertures", "stencil", "plated", "keepout"):
            self.assertIn(field, cam)
        grade = assemble_film(
            struct(
                kind=atom("string", value="film.cut", has_value=True),
                playhead=atom("float", value=0.4, has_value=True),
                razor_at=atom("float", value=0.4, has_value=True),
                shots=sequence(
                    struct(
                        clip=atom("string", value="a", has_value=True),
                        duration=atom("float", value=1, has_value=True),
                        **{"in": atom("float", value=0, has_value=True)},
                    )
                ),
            )
        )
        self.assertTrue(grade["playhead_cache"])
        self.assertGreaterEqual(len(grade["razored"]), 2)
        self.assertIn("rec709", grade)
        self.assertIn("dag", grade)

    def test_layout_cjk_mirror_sync_player(self):
        from desktop.layout import cycle_mru, maximize_editor, normalize_layout, remember_editor
        from desktop.search_text import tokens
        from meta.collab.loopback import exchange_peers
        from plugin_catalog import hosted_catalog

        layout = remember_editor(normalize_layout({}), "scene")
        layout = maximize_editor(layout, "scene")
        layout = cycle_mru(layout)
        self.assertEqual(layout["version"], 8)
        self.assertTrue(layout["mru"])
        self.assertTrue(tokens("汉字测试"))
        doc = hosted_catalog()
        self.assertEqual(doc["protocol"], 7)
        self.assertTrue(doc["digest"])
        self.assertTrue(doc.get("mirror"))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        status = exchange_peers(Path(tmp.name))
        self.assertFalse(status["wan"])
        scene = scene_compile(
            struct(
                kind=atom("string", value="scene", has_value=True),
                instances=sequence(struct(name=atom("string", value="Dup", has_value=True))),
                keys=sequence(
                    struct(t=atom("float", value=0, has_value=True), px=atom("float", value=0, has_value=True)),
                    struct(t=atom("float", value=1, has_value=True), px=atom("float", value=2, has_value=True)),
                ),
                time=atom("float", value=0.5, has_value=True),
            )
        )
        self.assertFalse(scene["unity"])
        self.assertTrue(scene["instances"])
        self.assertAlmostEqual(scene["play"]["px"], 1.0)

    def test_plugin_loop_any_form_then_project(self):
        pending = loop_cycle({"id": "community-loop", "name": "Loop", "form": "ai"})
        self.assertEqual(pending["status"], "pending")
        self.assertFalse(pending["project"])
        self.assertEqual(pending["form"], "ai")
        self.assertFalse(pending["wan"])
        approved = loop_cycle({"id": "community-loop-ok", "name": "Loop ok", "form": "layout"}, approved=True)
        self.assertTrue(approved["project"])
        self.assertEqual(approved["loop"], "plugin-project-plugin")
        from plugin_catalog import stamp_plugin

        stamped = stamp_plugin(name="Typed form", form="IoT")
        self.assertEqual(stamped["pack"]["form"], "IoT")
        self.assertTrue(stamped["pack"]["stamp"])
        self.assertEqual(stamped["pack"]["view"], "circuit")
        self.assertIn(stamped["pack"]["id"], {row["id"] for row in catalog()})
        from meta.description import to_json
        from plugin_catalog import project_from_packs

        again = stamp_plugin(
            name="Loop doc",
            form="Scene",
            document={"form": "atom", "type": "string", "value": "kept", "has_value": True},
        )
        desc = project_from_packs([again["pack"]], title="again")
        self.assertIn("kept", to_json(desc))

    def test_zintriq_parts_match_pack_plugin_ids(self):
        zin = instantiate(zintriq_system_desc(), target=TARGET_DESKTOP_HOST, slug="zintriq")
        keys = [item["key"] for item in zin.payload_object()["parts"] if item["key"] not in {"workbench", "flask"}]
        self.assertEqual(keys, editor_plugin_ids())

    def test_official_pack_sha256_and_stamp_timeline(self):
        from plugin_catalog import official_pack_file, pack_sha256, record_stamp_timeline, stamp_timeline

        pack = official_pack_file("scene.zintriq-plugin.json")
        self.assertTrue(pack and pack.get("sha256"))
        self.assertEqual(pack["sha256"], pack_sha256(pack))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        record_stamp_timeline(
            root,
            slug="scene-draft",
            fingerprint="abc123",
            pack_id="official-scene",
            document={"form": "atom", "type": "string", "value": "kept-desc", "has_value": True},
        )
        rows = stamp_timeline(root, "scene-draft")
        self.assertEqual(rows[-1]["fingerprint"], "abc123")
        from plugin_catalog import restore_stamp_document
        from desktop.meta_store import load_draft

        restore_stamp_document(root, slug="scene-draft", fingerprint="abc123")
        draft = load_draft("scene-draft", base=root)
        self.assertIn("kept-desc", str(draft.get("code") or ""))
        self.assertEqual(draft.get("slug") or "scene-draft", "scene-draft")
        for i in range(26):
            record_stamp_timeline(
                root,
                slug="scene-draft",
                fingerprint=f"fp{i:02d}",
                pack_id="official-scene",
                document={"form": "atom", "type": "string", "value": f"v{i}", "has_value": True},
            )
        record_stamp_timeline(
            root,
            slug="scene-draft",
            fingerprint="fp00",
            pack_id="official-scene",
            document={"form": "atom", "type": "string", "value": "latest-fp00", "has_value": True},
        )
        capped = stamp_timeline(root, "scene-draft")
        fps = [item["fingerprint"] for item in capped]
        self.assertLessEqual(len(fps), 24)
        self.assertEqual(len(set(fps)), len(fps))
        self.assertIn("fp00", fps)
        self.assertNotIn("fp01", fps)
        restore_stamp_document(root, slug="scene-draft", fingerprint="fp00")
        again = load_draft("scene-draft", base=root)
        self.assertIn("latest-fp00", str(again.get("code") or ""))
        self.assertEqual(again.get("slug") or "scene-draft", "scene-draft")


if __name__ == "__main__":
    unittest.main()
