"""Hardware, OS host, and canvas runtimes over Desc."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meta.boundary import HARDWARE_MODULE_ID, OS_SURFACE_ID, reset_for_tests
from meta.description import atom, equivalent, struct
from meta.instantiation import (
    TARGET_CANVAS,
    TARGET_DEVICE,
    TARGET_OS_HOST,
    description_from_artifact,
    instantiate,
    software_page,
)
from meta.runtime.canvas import canvas_from_artifact, canvas_from_desc
from meta.runtime.hardware import MODULES, esphome_yaml, flash_plan, module_of, pair, verify_ota
from meta.uir.errors import UIRError
from meta.runtime.os_surface import apply_host, host_spec
from meta.uir import code_to_desc, from_desc, to_code


class MetaRuntimeTests(unittest.TestCase):
    def setUp(self):
        reset_for_tests()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        reset_for_tests()

    def test_three_modules_pair_and_sign_ota(self):
        for sense, expected in (("climate", "climate"), ("relay", "relay"), ("presence", "presence")):
            desc = struct(
                kind=atom("string", value=HARDWARE_MODULE_ID, has_value=True),
                sense=atom("string", value=sense, has_value=True),
                title=atom("string", value=sense, has_value=True),
            )
            self.assertEqual(module_of(desc), expected)
            device = pair(desc, port="/dev/ttyUSB0", data_root=self.root)
            yaml_text = esphome_yaml(desc, device)
            self.assertIn("esp32:", yaml_text)
            if expected == "climate":
                self.assertIn("dht", yaml_text)
            elif expected == "relay":
                self.assertIn("gpio", yaml_text)
            else:
                self.assertIn("occupancy", yaml_text)
            plan = flash_plan(device, yaml_text, data_root=self.root)
            self.assertTrue(plan["commands"])
            self.assertTrue(verify_ota(yaml_text.encode("utf-8"), plan["ota"]["signature"], self.root))
            self.assertFalse(verify_ota(b"nope", plan["ota"]["signature"], self.root))
        self.assertEqual(set(MODULES), {"climate", "relay", "presence"})
        art = instantiate(
            struct(
                kind=atom("string", value=HARDWARE_MODULE_ID, has_value=True),
                sense=atom("string", value="dht22", has_value=True),
            ),
            slug="mod-a",
        )
        self.assertEqual(art.target, TARGET_DEVICE)
        self.assertEqual(art.payload_object()["module"], "climate")

    def test_os_surface_writes_host(self):
        desc = struct(
            kind=atom("string", value=OS_SURFACE_ID, has_value=True),
            title=atom("string", value="Desk", has_value=True),
        )
        spec = host_spec(desc)
        self.assertEqual(spec["windows"][0]["title"], "Desk")
        apply_host(desc, slug="desk", data_root=self.root)
        self.assertTrue((self.root / "os" / "desk" / "surface.json").is_file())
        art = instantiate(desc, slug="desk-os")
        self.assertEqual(art.target, TARGET_OS_HOST)
        self.assertTrue(equivalent(desc, description_from_artifact(art)))

    def test_canvas_from_software_page(self):
        page = software_page(title="Cafe", body=("Hello.",))
        tree = canvas_from_desc(page)
        self.assertEqual(tree["form"], "canvas")
        self.assertEqual(tree["pages"][0]["type"], "page")
        self.assertTrue(tree["pages"][0]["children"])
        art = instantiate(page, slug="cafe-page")
        synced = canvas_from_artifact(art)
        self.assertEqual(synced["pages"][0]["props"]["title"], "Cafe")
        canvas_art = instantiate(page, target=TARGET_CANVAS, slug="cafe-canvas")
        self.assertEqual(canvas_art.target, TARGET_CANVAS)
        self.assertEqual(canvas_art.payload_object()["canvas"]["form"], "canvas")

    def test_yaml_code_round_trip(self):
        node = struct(kind=atom("string", value="scene", has_value=True), title=atom("string", value="A", has_value=True))
        yaml_text = to_code(from_desc(node), language="yaml")
        self.assertIn("form:", yaml_text)
        restored = code_to_desc(yaml_text, language="yaml")
        self.assertTrue(equivalent(node, restored))
        with self.assertRaises(UIRError):
            to_code(from_desc(node), language="python")

    def test_serial_ports_and_flash_job(self):
        import os
        import time

        from meta.runtime.hardware import job_status, list_serial_ports, start_flash

        os.environ["ZINTRIQ_FAKE_SERIAL"] = "/dev/cu.ZINTRIQAKE"
        self.addCleanup(lambda: os.environ.pop("ZINTRIQ_FAKE_SERIAL", None))
        ports = list_serial_ports()
        self.assertEqual(ports[0]["path"], "/dev/cu.ZINTRIQAKE")
        wrapper = self.root / "esphome"
        if os.name == "nt":
            wrapper = self.root / "esphome.bat"
            wrapper.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
        else:
            wrapper.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n", encoding="utf-8")
            os.chmod(wrapper, 0o755)
        os.environ["ESPHOME_BIN"] = str(wrapper)
        self.addCleanup(lambda: os.environ.pop("ESPHOME_BIN", None))
        yaml_path = self.root / "hardware" / "mod" / "module.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text("esphome:\n  name: t\n", encoding="utf-8")
        job = start_flash(
            port="/dev/cu.ZINTRIQAKE",
            yaml_path=str(yaml_path),
            data_root=self.root,
            ssid="lab",
            password="secret-wifi",
        )
        for _ in range(80):
            row = job_status(job["id"])
            if row and row["status"] in {"ok", "error"}:
                break
            time.sleep(0.05)
        self.assertEqual(job_status(job["id"])["status"], "ok", job_status(job["id"]))
        secrets = (yaml_path.parent / "secrets.yaml").read_text(encoding="utf-8")
        self.assertIn("lab", secrets)
        self.assertIn("secret-wifi", secrets)

    def test_flash_requires_wifi_ssid(self):
        import os

        from meta.instantiation.errors import InstantiationError
        from meta.runtime.hardware import start_flash

        os.environ["ZINTRIQ_FAKE_SERIAL"] = "/dev/cu.ZINTRIQAKE"
        self.addCleanup(lambda: os.environ.pop("ZINTRIQ_FAKE_SERIAL", None))
        yaml_path = self.root / "hardware" / "mod" / "module.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text("esphome:\n  name: t\n", encoding="utf-8")
        with self.assertRaises(InstantiationError):
            start_flash(port="/dev/cu.ZINTRIQAKE", yaml_path=str(yaml_path), data_root=self.root)


if __name__ == "__main__":
    unittest.main()
