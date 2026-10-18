"""Editor view plugin registry."""

from __future__ import annotations

import unittest

from meta.description import equivalent, from_json, to_json
from meta.simulation import machine_from_desc, step
from meta.uir import desc_to_visual, visual_to_desc
from meta.editor_views import (
    EDITOR_PLUGINS,
    EditorView,
    get_view,
    list_views,
    plugin_ids,
    register_view,
    reset_views_for_tests,
)

_SCENE = {
    "form": "struct",
    "fields": {
        "kind": {"form": "atom", "type": "string", "value": "scene"},
        "title": {"form": "atom", "type": "string", "value": "Scene"},
        "camera": {
            "form": "struct",
            "fields": {
                "x": {"form": "atom", "type": "float", "value": 0},
                "y": {"form": "atom", "type": "float", "value": 0},
                "z": {"form": "atom", "type": "float", "value": 8},
            },
        },
        "mesh": {"form": "atom", "type": "string", "value": "cube"},
    },
}

_LOGIC = {
    "form": "struct",
    "fields": {
        "kind": {"form": "atom", "type": "string", "value": "state_machine"},
        "state": {"form": "atom", "type": "string", "value": "idle"},
        "transitions": {
            "form": "sequence",
            "items": [
                {
                    "form": "struct",
                    "fields": {
                        "event": {"form": "atom", "type": "string", "value": "start"},
                        "source": {"form": "atom", "type": "string", "value": "idle"},
                        "target": {"form": "atom", "type": "string", "value": "run"},
                    },
                }
            ],
        },
    },
}


class EditorViewPluginTests(unittest.TestCase):
    def setUp(self):
        reset_views_for_tests()

    def tearDown(self):
        reset_views_for_tests()

    def test_builtins_cover_describe_simulate_instantiate(self):
        describe = {item["id"] for item in list_views("describe")}
        simulate = {item["id"] for item in list_views("simulate")}
        instantiate = {item["id"] for item in list_views("instantiate")}
        core = {"code", "visual", "graph", "diagram", "uir", "page"}
        self.assertTrue(core.issubset(describe))
        self.assertEqual(set(plugin_ids()) & describe, set(plugin_ids()))
        self.assertEqual(len(plugin_ids()), 27)
        self.assertEqual(len(EDITOR_PLUGINS), 27)
        self.assertEqual(simulate, {"simulation", "visual", "graph", "logic", "animation"})
        self.assertEqual(instantiate, {"page", "artifact"})
        space = {item["id"] for item in list_views("space")}
        self.assertEqual(space, {"space", "code", "graph", "uir"})
        self.assertEqual([item["id"] for item in list_views("space")], ["space", "code", "graph", "uir"])
        self.assertEqual([item["id"] for item in list_views("simulate")], ["simulation", "visual", "graph", "animation", "logic"])
        self.assertEqual(get_view("code").pane, "code")
        self.assertEqual(tuple(get_view("code").contract), ("activate",))
        self.assertEqual(tuple(get_view("diagram").contract), ("render", "hitTest", "edit"))
        self.assertEqual(get_view("scene").pane, "plugin")
        self.assertEqual(tuple(get_view("text").contract), ("render", "hitTest", "edit"))
        self.assertEqual(tuple(get_view("meta").contract), ("render", "hitTest", "edit"))
        self.assertEqual(tuple(get_view("meta-meta").contract), ("render", "hitTest", "edit"))

    def test_scene_and_logic_seeds_are_live_descriptions(self):
        import json

        scene = from_json(json.dumps(_SCENE))
        restored = visual_to_desc(desc_to_visual(scene))
        self.assertTrue(equivalent(scene, restored))
        self.assertEqual(to_json(scene), to_json(restored))
        logic = from_json(json.dumps(_LOGIC))
        machine = machine_from_desc(logic)
        self.assertEqual(machine.state, "idle")
        self.assertEqual(step(machine, "start").state, "run")

    def test_register_extra_view(self):
        register_view(EditorView("outline", "Outline", ("describe",), "visual", 9))
        ids = [item["id"] for item in list_views("describe")]
        self.assertIn("outline", ids)

    def test_invalid_view_rejected(self):
        with self.assertRaises(ValueError):
            register_view(EditorView("", "Nope", ("describe",), "code"))
        with self.assertRaises(ValueError):
            register_view(EditorView("empty", "Empty", ("describe",), "code", 0, ()))


if __name__ == "__main__":
    unittest.main()
