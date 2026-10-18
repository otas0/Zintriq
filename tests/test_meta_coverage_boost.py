"""Targeted tests for meta package statement coverage gaps."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from meta.collab import (
    desc_to_plain,
    dump_state,
    empty_clock,
    integrate_plain,
    load_state,
    merge,
    merge_clocks,
    new_replica,
    plain_to_desc,
    stamp,
    tick,
    to_plain,
)
from meta.collab.ot import (
    apply_abs_ops,
    apply_ops_string,
    diff_ops,
    merge_from_base,
    to_abs_ops,
    transform_lists,
    transform_pair,
)
from meta.description import atom, depends_on, mapping, sequence, struct
from meta.instantiation.errors import InstantiationError
from meta.runtime.hardware import (
    device_artifact_body,
    esphome_venv_dir,
    esphome_venv_executable,
    list_devices,
    list_serial_ports,
    load_wifi,
    module_of,
    ota_key,
    persist_device_artifact,
    resolve_esphome_bin,
    save_wifi,
    validate_port,
    wifi_public,
    write_secrets_yaml,
)
from meta.runtime.world import (
    complete_local,
    is_world_kind,
    render_world,
    seed_desc,
    world_spec,
)
from meta.uir.errors import UIRError
from meta.uir.yaml_desc import dump_yaml, load_yaml


def _atom(value, typ="string"):
    return {"form": "atom", "type": typ, "value": value}


def _struct(**fields):
    return {"form": "struct", "fields": fields}


class YamlDescCoverageTests(unittest.TestCase):
    def test_dump_and_load_round_trip(self):
        data = {
            "name": "café",
            "count": 3,
            "on": True,
            "ratio": 1.5,
            "empty": "",
            "nested": {"a": 1},
            "items": ["x", "y"],
        }
        text = dump_yaml(data)
        self.assertIn("name:", text)
        restored = load_yaml(text)
        self.assertEqual(restored["name"], "café")
        self.assertEqual(restored["nested"]["a"], 1)
        self.assertEqual(restored["items"], ["x", "y"])

    def test_dump_empty_containers_and_scalar_edges(self):
        self.assertEqual(dump_yaml({}), "{}")
        self.assertEqual(dump_yaml([]), "[]")
        self.assertEqual(dump_yaml(None), "null")
        self.assertEqual(dump_yaml(True), "true")
        self.assertEqual(dump_yaml(42), "42")
        self.assertEqual(dump_yaml("plain"), "plain")
        self.assertIn('"', dump_yaml("has:colon"))

    def test_load_json_and_errors(self):
        self.assertEqual(load_yaml('{"a": 1}'), {"a": 1})
        self.assertEqual(load_yaml("[1, 2]"), [1, 2])
        with self.assertRaises(UIRError):
            load_yaml("")
        with self.assertRaises(UIRError):
            load_yaml("{not json")
        with self.assertRaises(UIRError):
            load_yaml("bad line without colon")

    def test_block_yaml_features(self):
        text = """
# comment
title: Demo
tags:
  - one
  - two
meta:
  count: 7
  flag: false
ratio: 3.14
empty: null
"""
        data = load_yaml(text)
        self.assertEqual(data["title"], "Demo")
        self.assertEqual(data["tags"], ["one", "two"])
        self.assertEqual(data["meta"]["count"], 7)
        self.assertFalse(data["meta"]["flag"])
        self.assertAlmostEqual(data["ratio"], 3.14)
        self.assertIsNone(data["empty"])

    def test_dump_nested_list_and_scalar_tokens(self):
        nested = dump_yaml([{"name": "nested"}, "plain"], indent=1)
        self.assertIn("- name:", nested)
        self.assertEqual(load_yaml("x: {}"), {"x": {}})
        self.assertEqual(load_yaml("x: []"), {"x": []})
        self.assertEqual(load_yaml('x: "quoted"'), {"x": "quoted"})
        with self.assertRaises(UIRError):
            load_yaml("outer:\n  inner: 1\n    bad: 2")


class WorldRuntimeCoverageTests(unittest.TestCase):
    def test_is_world_kind_and_complete_local(self):
        self.assertTrue(is_world_kind("scene"))
        self.assertFalse(is_world_kind("nope"))
        self.assertEqual(complete_local("", "m"), "m: empty prompt")
        long_words = " ".join(f"w{i}" for i in range(60))
        self.assertTrue(complete_local(long_words, "local").endswith(" …"))

    def test_world_spec_kind_branches(self):
        level = struct(
            kind=atom("string", value="level", has_value=True),
            room=atom("string", value="hall", has_value=True),
            spawn=struct(x=atom("float", value=1, has_value=True), y=atom("float", value=2, has_value=True)),
            title=atom("string", value="L", has_value=True),
        )
        self.assertEqual(world_spec(level)["room"], "hall")
        material = struct(
            kind=atom("string", value="material", has_value=True),
            albedo=atom("string", value="#ff0000", has_value=True),
            metal=atom("float", value=0.5, has_value=True),
            rough=atom("float", value=0.1, has_value=True),
            title=atom("string", value="M", has_value=True),
        )
        self.assertEqual(world_spec(material)["albedo"], "#ff0000")
        anim = struct(
            kind=atom("string", value="animation", has_value=True),
            duration=atom("float", value=2, has_value=True),
            keyframes=sequence(
                struct(time=atom("float", value=0, has_value=True), value=atom("float", value=1, has_value=True)),
            ),
            title=atom("string", value="A", has_value=True),
        )
        self.assertEqual(world_spec(anim)["duration"], 2.0)
        video = struct(
            kind=atom("string", value="video", has_value=True),
            clip=atom("string", value="c1", has_value=True),
            frame=atom("int", value=12, has_value=True),
            title=atom("string", value="V", has_value=True),
        )
        self.assertEqual(world_spec(video)["frame"], 12)
        audio = struct(
            kind=atom("string", value="audio", has_value=True),
            hz=atom("int", value=880, has_value=True),
            gain=atom("float", value=0.5, has_value=True),
            title=atom("string", value="Au", has_value=True),
        )
        self.assertEqual(world_spec(audio)["hz"], 880)
        media = struct(
            kind=atom("string", value="media.channel", has_value=True),
            name=atom("string", value="TV", has_value=True),
            clips=sequence(atom("string", value="ep1", has_value=True)),
            title=atom("string", value="TV", has_value=True),
        )
        self.assertEqual(world_spec(media)["clips"], ["ep1"])
        checkout = struct(
            kind=atom("string", value="commerce.checkout", has_value=True),
            currency=atom("string", value="eur", has_value=True),
            items=sequence(),
            title=atom("string", value="Shop", has_value=True),
        )
        self.assertEqual(world_spec(checkout)["items"][0]["name"], "Item")
        table = struct(
            kind=atom("string", value="spreadsheet", has_value=True),
            rows=sequence(
                struct(col=atom("string", value="a", has_value=True), val=atom("int", value=1, has_value=True)),
            ),
            title=atom("string", value="S", has_value=True),
        )
        self.assertEqual(world_spec(table)["rows"][0]["col"], "a")
        shader = struct(
            kind=atom("string", value="shader", has_value=True),
            glsl=atom("string", value="main();", has_value=True),
            title=atom("string", value="Sh", has_value=True),
        )
        self.assertIn("main", world_spec(shader)["glsl"])
        particle = struct(
            kind=atom("string", value="particle", has_value=True),
            emit=atom("int", value=64, has_value=True),
            burst=atom("int", value=8, has_value=True),
            title=atom("string", value="P", has_value=True),
        )
        self.assertEqual(world_spec(particle)["emit"], 64)
        terrain = struct(
            kind=atom("string", value="terrain", has_value=True),
            height=atom("float", value=20, has_value=True),
            noise=atom("float", value=0.2, has_value=True),
            title=atom("string", value="T", has_value=True),
        )
        self.assertEqual(world_spec(terrain)["height"], 20.0)
        geo = struct(
            kind=atom("string", value="map", has_value=True),
            lat=atom("float", value=1.0, has_value=True),
            lng=atom("float", value=2.0, has_value=True),
            title=atom("string", value="Map", has_value=True),
        )
        self.assertEqual(world_spec(geo)["lat"], 1.0)
        quantum = struct(
            kind=atom("string", value="quantum", has_value=True),
            qubit=atom("int", value=4, has_value=True),
            hadamard=atom("string", value="q1", has_value=True),
            title=atom("string", value="Q", has_value=True),
        )
        self.assertEqual(world_spec(quantum)["qubit"], 4)
        vector = struct(
            kind=atom("string", value="vector", has_value=True),
            path=atom("string", value="M0 0", has_value=True),
            title=atom("string", value="Vec", has_value=True),
        )
        self.assertEqual(world_spec(vector)["path"], "M0 0")
        text = struct(
            kind=atom("string", value="text", has_value=True),
            body=sequence(atom("string", value="line", has_value=True)),
            title=atom("string", value="Txt", has_value=True),
        )
        self.assertEqual(world_spec(text)["body"], ["line"])
        doc = struct(
            kind=atom("string", value="document", has_value=True),
            heading=atom("string", value="H", has_value=True),
            paragraph=atom("string", value="P", has_value=True),
            title=atom("string", value="Doc", has_value=True),
        )
        self.assertEqual(world_spec(doc)["paragraph"], "P")
        graph = struct(
            kind=atom("string", value="node.graph", has_value=True),
            a=struct(label=atom("string", value="Left", has_value=True)),
            b=struct(label=atom("string", value="Right", has_value=True)),
            title=atom("string", value="G", has_value=True),
        )
        self.assertEqual(world_spec(graph)["a"], "Left")
        font = struct(
            kind=atom("string", value="font", has_value=True),
            title=atom("string", value="F", has_value=True),
        )
        self.assertEqual(world_spec(font)["label"], "F")
        kernel = seed_desc("physics.body", "Body")
        spec = world_spec(kernel)
        self.assertEqual(spec["family"], "game")
        self.assertIn("mass", spec)

    def test_seed_desc_variants_and_render(self):
        for kind in (
            "scene",
            "cad.solid",
            "commerce.checkout",
            "social.channel",
            "media.channel",
            "ai",
            "physics.body",
            "skeleton.rig",
            "film.cut",
            "cad.brep",
            "commerce.settle",
            "social.federate",
            "llm.weights",
            "bitmap",
        ):
            desc = seed_desc(kind, title=kind)
            self.assertIsNotNone(desc)
        scene = seed_desc("scene")
        html = render_world(scene)
        self.assertIn("data-world=", html)
        self.assertIn("zw-spec", html)
        self.assertEqual(world_spec(atom("int", value=1, has_value=True))["kind"], "")


class CollabCoverageTests(unittest.TestCase):
    def test_merge_and_state_helpers(self):
        self.assertIsNone(merge(None, None))
        left = stamp(_struct(title=_atom("L")), "aaa", 1)
        self.assertEqual(to_plain(merge(None, left))["fields"]["title"]["value"], "L")
        self.assertEqual(to_plain(merge(left, None))["fields"]["title"]["value"], "L")
        rep = new_replica()
        self.assertTrue(rep)
        clock, lamport = tick(empty_clock(), "aaa")
        self.assertEqual(lamport, 1)
        merged_clock = merge_clocks(clock, {"bbb": 3})
        self.assertEqual(merged_clock["bbb"], 3)
        raw = dump_state(replica="aaa", clock=clock, doc=left)
        loaded = load_state(raw)
        self.assertEqual(loaded["replica"], "aaa")
        with self.assertRaises(ValueError):
            load_state("[]")

    def test_mapping_raw_and_plain_round_trip(self):
        plain = {
            "form": "mapping",
            "entries": {"k": _atom("v")},
        }
        wrapped = stamp(plain, "aaa", 1)
        self.assertEqual(to_plain(wrapped)["entries"]["k"]["value"], "v")
        node = struct(x=atom("int", value=1, has_value=True))
        self.assertEqual(desc_to_plain(node)["form"], "struct")
        self.assertEqual(plain_to_desc(desc_to_plain(node)).fields[0][0], "x")

    def test_merge_form_mismatch_and_lww(self):
        left = stamp(_atom("old"), "aaa", 1)
        right = stamp(_struct(x=_atom(1, "int")), "bbb", 2)
        merged = merge(left, right)
        self.assertIn(merged["form"], {"atom", "struct"})
        int_left = stamp(_atom(1, "int"), "aaa", 5)
        int_right = stamp(_atom(2, "int"), "bbb", 4)
        self.assertEqual(to_plain(merge(int_left, int_right))["value"], 1)

    def test_integrate_sequence_tombstones_and_atoms(self):
        seq_plain = {"form": "sequence", "items": [_atom("a"), _atom("b")]}
        base = integrate_plain(None, seq_plain, "aaa", 1)
        shrunk = integrate_plain(base, {"form": "sequence", "items": [_atom("a")]}, "aaa", 2)
        plain = to_plain(shrunk)
        self.assertEqual([item["value"] for item in plain["items"]], ["a"])
        int_base = integrate_plain(None, _atom(1, "int"), "aaa", 1)
        same = integrate_plain(int_base, _atom(1, "int"), "aaa", 2)
        self.assertIs(same, int_base)
        changed = integrate_plain(int_base, _atom(9, "int"), "aaa", 3)
        self.assertEqual(to_plain(changed)["value"], 9)
        str_base = integrate_plain(None, _struct(title=_atom("hi")), "aaa", 1)
        non_string = integrate_plain(str_base, _struct(title=_atom(42, "int")), "aaa", 2)
        self.assertEqual(to_plain(non_string)["fields"]["title"]["value"], 42)

    def test_wrap_non_desc_and_merge_mapping(self):
        raw = stamp({"note": "x"}, "aaa", 1)
        self.assertEqual(to_plain(raw), {"note": "x"})
        left = stamp({"form": "mapping", "entries": {"a": _atom("1")}}, "aaa", 1)
        right = stamp({"form": "mapping", "entries": {"b": _atom("2")}}, "bbb", 2)
        merged = to_plain(merge(left, right))
        self.assertEqual(merged["entries"]["a"]["value"], "1")
        self.assertEqual(merged["entries"]["b"]["value"], "2")


class OtCoverageTests(unittest.TestCase):
    def test_diff_replace_and_apply_edges(self):
        ops = diff_ops("abc", "axc")
        self.assertTrue(any(op.get("op") == "replace" for op in ops) or len(ops) >= 2)
        self.assertEqual(apply_ops_string("abc", [{"op": "insert_abs", "s": "x"}]), "abc")
        abs_ops = to_abs_ops(diff_ops("hi", "hiya"), replica="aaa")
        self.assertTrue(abs_ops)
        self.assertEqual(apply_abs_ops("hello", [{"op": "insert", "pos": 99, "s": "!"}]), "hello!")

    def test_transform_pairs(self):
        ins_a = {"op": "insert", "pos": 2, "s": "X", "replica": "aaa"}
        ins_b = {"op": "insert", "pos": 2, "s": "Y", "replica": "bbb"}
        ta, tb = transform_pair(dict(ins_a), dict(ins_b))
        self.assertNotEqual(ta["pos"], tb["pos"])
        del_ins = {"op": "delete", "pos": 0, "n": 2, "replica": "aaa"}
        del_del = {"op": "delete", "pos": 1, "n": 2, "replica": "bbb"}
        transform_pair(dict(del_ins), dict(del_del))
        ins = {"op": "insert", "pos": 1, "s": "Z", "replica": "aaa"}
        delete = {"op": "delete", "pos": 0, "n": 3, "replica": "bbb"}
        transform_pair(dict(ins), dict(delete))
        transform_pair(dict(delete), dict(ins))
        left = [dict(ins_a)]
        right = [dict(ins_b)]
        transform_lists(left, right)
        merged = merge_from_base("ab", "aXb", "aYb", "aaa", "bbb")
        self.assertIn("X", merged)
        self.assertIn("Y", merged)
        self.assertEqual(len(merged), 4)


class RelationCoverageTests(unittest.TestCase):
    def test_depends_on_sequence_and_mapping(self):
        node = struct(
            items=sequence(atom("string", ref="$.a")),
            props=mapping(x=atom("int", ref="$.b")),
        )
        self.assertEqual(depends_on(node), frozenset({"$.a", "$.b"}))


class HardwareCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ota_key_and_devices(self):
        k1 = ota_key(self.root)
        k2 = ota_key(self.root)
        self.assertEqual(k1, k2)
        self.assertEqual(list_devices(self.root), [])
        folder = self.root / "hardware" / "dev1"
        folder.mkdir(parents=True)
        (folder / "device.json").write_text("not json", encoding="utf-8")
        (folder / "device.json").write_text(json.dumps({"id": "dev1", "module": "relay"}), encoding="utf-8")
        rows = list_devices(self.root)
        self.assertEqual(rows[0]["id"], "dev1")

    def test_persist_and_device_artifact(self):
        body = device_artifact_body(
            struct(
                kind=atom("string", value="hardware.module", has_value=True),
                sense=atom("string", value="relay", has_value=True),
            ),
            slug="r1",
        )
        path = persist_device_artifact(body, data_root=self.root)
        self.assertTrue((path / "module.yaml").is_file())
        with self.assertRaises(InstantiationError):
            persist_device_artifact({}, data_root=self.root)

    def test_wifi_store_and_secrets(self):
        self.assertEqual(load_wifi(self.root), {"password": "", "ssid": ""})
        bad = self.root / "hardware" / "wifi.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{", encoding="utf-8")
        self.assertEqual(load_wifi(self.root)["ssid"], "")
        bad.write_text("[]", encoding="utf-8")
        self.assertEqual(load_wifi(self.root)["ssid"], "")
        save_wifi(self.root, ssid="lab", password="secret")
        save_wifi(self.root, ssid="lab2", password=None)
        self.assertEqual(load_wifi(self.root)["ssid"], "lab2")
        self.assertEqual(load_wifi(self.root)["password"], "secret")
        pub = wifi_public(self.root)
        self.assertTrue(pub["has_password"])
        write_secrets_yaml(self.root / "hw", ssid="s", password="p")
        self.assertIn("wifi_ssid", (self.root / "hw" / "secrets.yaml").read_text(encoding="utf-8"))

    def test_validate_port_and_esphome_resolve(self):
        with self.assertRaises(InstantiationError):
            validate_port("")
        os.environ["ZINTRIQ_FAKE_SERIAL"] = "/dev/cu.ZINTRIQAKE"
        self.addCleanup(lambda: os.environ.pop("ZINTRIQ_FAKE_SERIAL", None))
        self.assertEqual(validate_port("/dev/cu.ZINTRIQAKE"), "/dev/cu.ZINTRIQAKE")
        with self.assertRaises(InstantiationError):
            validate_port("/dev/not-listed")
        os.environ["ZINTRIQ_SKIP_ESPHOME_INSTALL"] = "1"
        self.addCleanup(lambda: os.environ.pop("ZINTRIQ_SKIP_ESPHOME_INSTALL", None))
        with self.assertRaises(InstantiationError):
            resolve_esphome_bin(self.root)
        _ = esphome_venv_dir(self.root)
        _ = esphome_venv_executable(self.root)

    def test_module_of_non_struct(self):
        with self.assertRaises(InstantiationError):
            module_of(atom("string", value="x", has_value=True))

    def test_list_serial_ports_glob_branch(self):
        os.environ.pop("ZINTRIQ_FAKE_SERIAL", None)
        ports = list_serial_ports()
        self.assertTrue(isinstance(ports, list))


if __name__ == "__main__":
    unittest.main()
