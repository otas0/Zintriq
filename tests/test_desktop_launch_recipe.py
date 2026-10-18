"""Launch recipe files are optional; missing launch.json keeps current host start."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DesktopLaunchRecipeTests(unittest.TestCase):
    def test_node_load_launch_recipe_missing_is_null(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        proc = subprocess.run(
            [
                "node",
                "-e",
                "const {loadLaunchRecipe}=require('./desktop/flask_host'); process.stdout.write(JSON.stringify(loadLaunchRecipe(process.argv[1])));",
                tmp.name,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "null")

    def test_node_load_launch_recipe_reads_studio_and_editors(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name) / "desktop" / "zintriq"
        folder.mkdir(parents=True)
        (folder / "launch.json").write_text(
            json.dumps(
                {
                    "bind": "127.0.0.1",
                    "studio": "/studio",
                    "loopback_only": True,
                    "editors": ["scene", "ai"],
                    "data_dir": str(folder),
                    "env": {"ZINTRIQ_DESKTOP": "1", "ZINTRIQ_DESKTOP_TOKEN": "do-not-copy"},
                }
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                "node",
                "-e",
                "const {loadLaunchRecipe,mergeLaunchEnv}=require('./desktop/flask_host'); const r=loadLaunchRecipe(process.argv[1]); const e=mergeLaunchEnv({}, r); process.stdout.write(JSON.stringify({studio:r.studio,editors:r.editors,token:e.ZINTRIQ_DESKTOP_TOKEN||null,host:e.ZINTRIQ_HOST}));",
                tmp.name,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["studio"], "/studio")
        self.assertEqual(body["editors"], ["scene", "ai"])
        self.assertIsNone(body["token"])
        self.assertEqual(body["host"], "127.0.0.1")

    def test_reject_non_loopback_bind(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name) / "desktop" / "zintriq"
        folder.mkdir(parents=True)
        (folder / "launch.json").write_text(json.dumps({"bind": "0.0.0.0", "studio": "/studio"}), encoding="utf-8")
        proc = subprocess.run(
            [
                "node",
                "-e",
                "const {loadLaunchRecipe}=require('./desktop/flask_host'); process.stdout.write(JSON.stringify(loadLaunchRecipe(process.argv[1])));",
                tmp.name,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "null")


if __name__ == "__main__":
    unittest.main()
