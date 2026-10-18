"""USB/BLE/GPIO/I2C/SPI/camera buses — fake env, no vendor SDK."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from meta.runtime.buses import KINDS, BusError, close_session, list_all, list_bus, open_session, session_read, session_write, transfer


class BusTests(unittest.TestCase):
    def test_fake_list_and_transfer(self):
        for kind in KINDS:
            os.environ["ZINTRIQ_FAKE_" + kind.upper()] = f"fake-{kind}-0"
            self.addCleanup(lambda k=kind: os.environ.pop("ZINTRIQ_FAKE_" + k.upper(), None))
        buses = list_all()
        self.assertEqual(set(buses), set(KINDS))
        usb = list_bus("usb")
        self.assertEqual(usb[0]["id"], "fake-usb-0")
        ping = transfer("usb", "fake-usb-0", "ping")
        self.assertTrue(ping["ok"])
        opened = open_session("usb", "fake-usb-0")
        self.assertTrue(opened["session"])
        session_write(opened["session"], "hello")
        got = session_read(opened["session"], 16)
        self.assertIn("hello", got["data"])
        close_session(opened["session"])
        with self.assertRaises(BusError):
            session_read(opened["session"])
        self.assertEqual(ping["kind"], "usb")
        with self.assertRaises(BusError):
            list_bus("firewire")
        with self.assertRaises(BusError):
            transfer("usb", "missing-device", "x")

    def test_search_index_covers_drafts_artifacts_plugins(self):
        from desktop.meta_store import load_layout, rebuild_search_index, save_draft, save_layout, search_all

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        save_draft("needle-box", code='{"kind":"scene","title":"ZXSEARCHMARK"}', base=root)
        plugins = root / "plugins"
        plugins.mkdir()
        (plugins / "official-film.json").write_text('{"id":"official-film","hint":"ZXPLUGINMARK"}', encoding="utf-8")
        rebuild_search_index(base=root)
        hits = search_all("ZXSEARCHMARK", base=root)
        self.assertTrue(any(hit.get("kind") == "draft" and hit.get("slug") == "needle-box" for hit in hits))
        plugin_hits = search_all("ZXPLUGINMARK", base=root)
        self.assertTrue(any(hit.get("kind") == "plugin" for hit in plugin_hits))
        self.assertTrue((root / "search-index.json").is_file())
        index = json.loads((root / "search-index.json").read_text(encoding="utf-8"))
        self.assertIn("inv", index)
        self.assertTrue(index["inv"])
        save_draft("pinyin-box", code='{"title":"场景搜索"}', base=root)
        self.assertTrue(any(hit.get("slug") == "pinyin-box" for hit in search_all("chang", base=root)))
        save_draft("brush-box", code='{"title":"笔刷三维"}', base=root)
        self.assertTrue(any(hit.get("slug") == "brush-box" for hit in search_all("shua", base=root)))
        self.assertTrue(any(hit.get("slug") == "brush-box" for hit in search_all("bi", base=root)))
        save_draft("fuzzy-box", code='{"kind":"scene"}', base=root)
        self.assertTrue(any(hit.get("slug") == "fuzzy-box" for hit in search_all("scne", base=root)))
        layout = save_layout(
            {"activeGroup": 1, "groups": [{"tree": {"id": "code", "type": "leaf"}}, {"tree": {"id": "graph", "type": "leaf"}}]},
            base=root,
        )
        self.assertEqual(load_layout(base=root)["activeGroup"], 1)
        self.assertEqual(len(layout["groups"]), 2)
        self.assertEqual(layout["version"], 8)
        from desktop.layout import (
            apply_profile,
            close_group,
            close_tab,
            cycle_mru,
            focus_group,
            maximize_editor,
            move_editor,
            pin_editor,
            remember_editor,
            reset_layout,
            resize_group,
            save_profile,
            set_chrome,
            split_group,
            stick_editor,
            swap_groups,
        )

        split = split_group(layout, direction="right")
        self.assertGreaterEqual(len(split["groups"]), 2)
        moved = move_editor(split, "graph", 0)
        self.assertTrue(any(ed.get("id") == "graph" for ed in moved["groups"][0]["editors"]))
        closed = close_group(moved, 0)
        self.assertGreaterEqual(len(closed["groups"]), 1)
        pinned = pin_editor(closed, "code")
        self.assertIn("code", pinned["pinned"])
        sized = resize_group(pinned, 0, 1.5)
        self.assertGreaterEqual(sized["groups"][0]["size"], 1.5)
        chrome = set_chrome(sized, sidebar=False, panel=0.4, zen=True, activity="search")
        self.assertFalse(chrome["sidebar"])
        self.assertTrue(chrome["zen"])
        closed_tab = close_tab(chrome, "missing")
        self.assertTrue(closed_tab["groups"][0]["editors"])
        named = save_profile(set_chrome(closed_tab, panel_tab="problems", columns=2), "edit")
        self.assertIn("edit", named["profiles"])
        restored = apply_profile(named, "edit")
        self.assertEqual(restored["workspace"], "edit")
        recent = remember_editor(restored, "graph")
        self.assertIn("graph", recent["mru"])
        stuck = stick_editor(recent, "code")
        self.assertIn("code", stuck["sticky"])
        maxed = maximize_editor(stuck, "code")
        self.assertEqual(maxed["max"], "code")
        swapped = swap_groups(split_group(maxed, direction="right"), 0, 1)
        self.assertGreaterEqual(len(swapped["groups"]), 2)
        focused = focus_group(swapped, 1)
        self.assertEqual(focused["activeGroup"], 1)
        cycled = cycle_mru(remember_editor(focused, "code"), offset=1)
        self.assertTrue(cycled["mru"])
        self.assertEqual(reset_layout(recent)["workspace"], "default")
        save_draft("zh-box", code='{"title":"中"}', base=root)
        self.assertTrue(any(hit.get("slug") == "zh-box" for hit in search_all("zh", base=root)))
        save_draft("pair-box", code='{"title":"搜索"}', base=root)
        self.assertTrue(any(hit.get("slug") == "pair-box" for hit in search_all("sousuo", base=root)))
        save_draft("trad-box", code='{"title":"場"}', base=root)
        self.assertTrue(any(hit.get("slug") == "trad-box" for hit in search_all("chang", base=root)))
        self.assertTrue(any(hit.get("slug") == "pinyin-box" for hit in search_all("chang2", base=root)))
        layout = save_layout({"queries": [{"id": "unstamped", "stamped": "0", "slug": "needle-box"}]}, base=root)
        self.assertEqual(layout["queries"][0]["slug"], "needle-box")
