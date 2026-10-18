"""View marks are a UIR projection overlay — Desc stays pure."""

from __future__ import annotations

import unittest

from meta.description import atom, equivalent, struct
from meta.uir import (
    UIRError,
    attach_view,
    desc_to_visual,
    from_visual,
    merge_visual_views,
    normalize_view,
    strip_view,
    to_desc,
    to_visual,
    visual_to_desc,
)


class MetaUIRMarksTests(unittest.TestCase):
    def test_normalize_view_transform_pivot_marks(self):
        view = normalize_view(
            {
                "transform": {"x": 10, "y": 20, "sx": 2},
                "pivot": {"x": 0, "y": 1},
                "marks": ["selected", "pivot", "selected"],
                "type": "frame",
                "selected": True,
            }
        )
        self.assertEqual(view["transform"]["x"], 10.0)
        self.assertEqual(view["transform"]["sx"], 2.0)
        self.assertEqual(view["pivot"]["y"], 1.0)
        self.assertEqual(view["marks"], ["selected", "pivot"])
        self.assertEqual(view["type"], "frame")
        self.assertTrue(view["selected"])

    def test_invalid_transform_rejected(self):
        with self.assertRaises(UIRError):
            normalize_view({"transform": "nope"})

    def test_visual_keeps_marks_uir_keeps_marks_desc_strips(self):
        node = struct(title=atom("string", value="Room", has_value=True))
        visual = desc_to_visual(node)
        root_id = visual["root"]
        for item in visual["nodes"]:
            if item["id"] == root_id:
                item["properties"] = attach_view(
                    item["properties"],
                    {"transform": {"x": 3}, "marks": ["anchor"], "pivot": {"x": 0.25}},
                )
        uir = from_visual(visual)
        again = to_visual(uir)
        marked = next(item for item in again["nodes"] if item["id"] == root_id)
        self.assertEqual(marked["properties"]["view"]["marks"], ["anchor"])
        self.assertEqual(marked["properties"]["view"]["transform"]["x"], 3.0)
        restored = to_desc(uir)
        self.assertTrue(equivalent(node, restored))
        stripped = visual_to_desc(again)
        self.assertTrue(equivalent(node, stripped))
        for item in desc_to_visual(stripped)["nodes"]:
            self.assertNotIn("view", item.get("properties") or {})

    def test_merge_visual_views_preserves_overlay(self):
        node = struct(a=atom("int", value=1, has_value=True))
        base = desc_to_visual(node)
        overlay = desc_to_visual(node)
        rid = overlay["root"]
        for item in overlay["nodes"]:
            if item["id"] == rid:
                item["properties"] = attach_view(item["properties"], {"marks": ["hot"]})
        merged = merge_visual_views(base, overlay)
        marked = next(item for item in merged["nodes"] if item["id"] == rid)
        self.assertEqual(marked["properties"]["view"]["marks"], ["hot"])
        self.assertTrue(equivalent(node, visual_to_desc(merged)))

    def test_strip_view_removes_projection_only(self):
        props = attach_view({"type": "string", "has_value": True, "value": "x"}, {"marks": ["a"]})
        self.assertIn("view", props)
        clean = strip_view(props)
        self.assertNotIn("view", clean)
        self.assertEqual(clean["value"], "x")


if __name__ == "__main__":
    unittest.main()
