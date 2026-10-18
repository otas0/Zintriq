"""Smoke checks for meta editor plugin pack, kit, and runtimes."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "static/studio/editors/pack.js"
KIT = ROOT / "static/studio/editors/plugin-kit.js"
RUNTIMES = ROOT / "static/studio/editors/runtimes.js"
SOLVERS = ROOT / "static/studio/editors/solvers.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _plugin_block(text: str, plugin_id: str) -> str:
    match = re.search(
        rf'id:\s*"{re.escape(plugin_id)}"[\s\S]*?\n    \}},\n(?:    \{{|  \];)',
        text,
    )
    if match is None:
        raise AssertionError(f"missing plugin block for {plugin_id}")
    return match.group(0)


class MetaPluginPackTests(unittest.TestCase):
    def test_pack_has_at_least_27_plugin_specs(self):
        text = _read(PACK)
        ids = re.findall(r'^\s+id:\s*"([^"]+)"', text, re.MULTILINE)
        registrations = len(re.findall(r"makePlugin\s*\(", text))
        self.assertGreaterEqual(len(ids), 27, f"expected >= 27 plugin ids, got {len(ids)}")
        self.assertGreaterEqual(registrations, 1)
        self.assertEqual(len(set(ids)), len(ids), "duplicate plugin ids in pack.js")

    def test_required_plugins_have_kind_value_and_seed(self):
        text = _read(PACK)
        for plugin_id in ("scene", "shader", "logic", "text", "chip", "map", "ai"):
            chunk = _plugin_block(text, plugin_id)
            self.assertRegex(chunk, r'kindValue:\s*"', msg=f"{plugin_id} missing kindValue")
            self.assertIn("seed:", chunk, msg=f"{plugin_id} missing seed")

    def test_plugin_kit_toolbar_and_table_marks(self):
        text = _read(KIT)
        self.assertIn("Paint", text)
        self.assertIn("View marks", text)
        self.assertIn("me-plugin-toolbar", text)
        self.assertIn('label: "Move"', text)
        self.assertIn('label: "Razor"', text)
        self.assertIn('label: "Route"', text)
        self.assertIn("data-tool", text)

    def test_runtimes_export_scene_and_chip(self):
        text = _read(RUNTIMES)
        self.assertRegex(text, r"\bscene\s*:\s*scene\b")
        self.assertRegex(text, r"\bchip\s*:\s*chip\b")
        for key in (
            "shader",
            "quantum",
            "map",
            "bitmap",
            "audio",
            "particle",
            "terrain",
            "model3d",
            "material",
            "circuit",
            "logic",
            "video",
            "font",
            "cad",
            "physics",
            "vector",
            "text",
            "ai",
            "film",
            "animation",
            "skeleton",
            "vr",
        ):
            self.assertRegex(text, rf"\b{re.escape(key)}\s*:\s*{re.escape(key)}\b", msg=f"missing runtime {key}")
        self.assertRegex(text, r"\bdocument\s*:")

    def test_scene_has_unity_inspector_groups(self):
        chunk = _plugin_block(_read(PACK), "scene")
        for needle in ("camera.fov", "light.intensity", "transform.px", "viewport: true", "objects", 'id: "move"'):
            self.assertIn(needle, chunk)
        kit = _read(KIT)
        for needle in ("Play", "Duplicate row", "me-timeline", "me-viewport", "data-outline-filter"):
            self.assertIn(needle, kit)

    def test_extra_domain_plugins_stay_plugins(self):
        text = _read(PACK)
        for plugin_id in ("vr", "robotics", "print3d", "cnc", "chain"):
            chunk = _plugin_block(text, plugin_id)
            self.assertIn("kindValue:", chunk)
            self.assertIn("seed:", chunk)

    def test_diagram_is_view_plugin_with_toolbar(self):
        text = (ROOT / "static/studio/editors/diagram.js").read_text(encoding="utf-8")
        self.assertIn('id: "diagram"', text)
        self.assertIn("me-plugin-toolbar", text)
        self.assertIn("properties.view", text)

    def test_solvers_and_nle_pack(self):
        solvers = _read(SOLVERS)
        for needle in ("ccdIk", "skinDeform", "manhattanRoute", "routeDrc", "assembleCut", "razorShot", "paintWeights", "mixAudio", "gradeFrame", "skinMesh", "rec709Encode", "skinCluster", "dcodeTable", "trsMatrix", "tokenizeLocal", "playKeys"):
            self.assertIn(needle, solvers)
        runtimes = _read(RUNTIMES)
        self.assertIn("ZintriqSolvers", runtimes)
        self.assertIn("ccdIk", runtimes)
        self.assertIn("razorShot", runtimes)
        film = _plugin_block(_read(PACK), "film")
        self.assertIn("track", film)
        self.assertIn("playhead", film)
        self.assertIn("Razor", film)
        self.assertIn("lift", film)
        skeleton = _plugin_block(_read(PACK), "skeleton")
        self.assertIn("weight", skeleton)
        self.assertIn("Paint", skeleton)
        circuit = _plugin_block(_read(PACK), "circuit")
        self.assertIn("table: \"nets\"", circuit)
        self.assertIn("clearance", circuit)
        self.assertIn("Route", circuit)
        workbench = (ROOT / "static/studio/workbench.js").read_text(encoding="utf-8")
        self.assertIn("workbench.palette", workbench)
        self.assertIn("bindDock", workbench)
        self.assertIn("data-dock-drop", workbench)
        self.assertIn("insertSplit", workbench)
        self.assertIn("pushStack", workbench)
        self.assertIn("toggleMax", workbench)
        self.assertIn("cycleMru", workbench)
        for editor in ("pack.js", "plugin-kit.js", "runtimes.js", "solvers.js", "diagram.js"):
            src = (ROOT / "static/studio/editors" / editor).read_text(encoding="utf-8")
            self.assertNotIn("createStore", src)
            self.assertNotIn("history.stack", src)
        css = (ROOT / "static/studio/workbench.css").read_text(encoding="utf-8")
        self.assertIn("wb-drop--left", css)
        self.assertIn("wb-split", css)
        self.assertIn("wb-tabs", css)
        runtimes = _read(RUNTIMES)
        self.assertIn("mesh brush", runtimes)
        self.assertIn("hierarchy · camera · lights", runtimes)
        self.assertIn("local session · hosted: false", runtimes)
        self.assertIn("zintriq.http", runtimes)
        self.assertIn("/api/builder-core/meta/ai/chat", runtimes)
        self.assertIn("play/stop · prefab", runtimes)
        self.assertIn("data-paint-bound", runtimes)
        self.assertIn("me-statusbar", workbench)
        self.assertIn("bindAssistant", workbench)
        self.assertIn('data-assistant-act="produce"', workbench)
        self.assertIn("/api/builder-core/meta/produce", workbench)
        self.assertIn("/api/builder-core/meta/ai/tools", workbench)

    def test_official_plugins_share_workbench_engine(self):
        from plugin_catalog import PACKS

        pack = _read(PACK)
        kit = _read(KIT)
        self.assertIn("jsView = false", pack)
        self.assertIn("engine = \"ZintriqEngine\"", pack)
        self.assertIn("spec.industry", kit)
        self.assertNotIn("ZintriqEngine.store =", pack)
        self.assertNotIn("history.stack", pack)
        ids = re.findall(r'^\s+id:\s*"([^"]+)"', pack, re.MULTILINE)
        official = [str(row["id"])[9:] for row in PACKS]
        for view in official:
            self.assertIn(view, ids, view)


if __name__ == "__main__":
    unittest.main()
