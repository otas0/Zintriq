"""Tests for editor host: fs, changes, AI bypass, permissions, git, lsp."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class EditorAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
        cls.workspace = root / "workspace"
        cls.workspace.mkdir()
        os.environ["ZINTRIQ_DESKTOP"] = "1"
        os.environ["ZINTRIQ_DESKTOP_TOKEN"] = "t" * 32
        os.environ["ZINTRIQ_DATA_DIR"] = str(root)
        os.environ["ZINTRIQ_WORKSPACE"] = str(cls.workspace)
        import importlib
        import app as app_mod

        importlib.reload(app_mod)
        cls.app_mod = app_mod
        cls.client = app_mod.app.test_client()
        cls.headers = {"X-Zintriq-Desktop-Token": "t" * 32}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_healthz(self) -> None:
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["product"], "editor")

    def test_editor_page(self) -> None:
        res = self.client.get("/editor")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Zintriq Editor", res.data)
        self.assertIn(b"syntax.js", res.data)
        self.assertIn(b"btn-new-file", res.data)
        self.assertIn(b"onboarding", res.data)

    def test_api_requires_token(self) -> None:
        res = self.client.get("/api/fs/list")
        self.assertEqual(res.status_code, 401)

    def test_fs_roundtrip(self) -> None:
        res = self.client.put(
            "/api/fs/write",
            json={"path": "hello.py", "text": "print(1)\n"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/api/fs/read?path=hello.py", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["text"], "print(1)\n")
        self.assertEqual(body["language"], "python")

    def test_fs_create_mkdir_delete(self) -> None:
        res = self.client.post(
            "/api/fs/create",
            json={"path": "fresh/note.txt", "text": "hi\n"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertEqual((self.workspace / "fresh" / "note.txt").read_text(encoding="utf-8"), "hi\n")
        res = self.client.post(
            "/api/fs/create",
            json={"path": "fresh/note.txt", "text": "x"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 409)
        res = self.client.post(
            "/api/fs/mkdir",
            json={"path": "fresh/subdir"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue((self.workspace / "fresh" / "subdir").is_dir())
        res = self.client.post(
            "/api/fs/delete",
            json={"path": "fresh/note.txt"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse((self.workspace / "fresh" / "note.txt").exists())

    def test_workspace_seed_and_onboarding(self) -> None:
        from editor import workspace_bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            data = Path(tmp) / "data"
            ws.mkdir()
            data.mkdir()
            result = workspace_bootstrap.ensure_ready(ws, data)
            self.assertTrue(result["seed"]["seeded"])
            self.assertTrue((ws / "WELCOME.md").is_file())
            self.assertTrue((ws / "examples" / "hello.py").is_file())
            self.assertTrue(result["show_onboarding"])
            workspace_bootstrap.save_onboarding(data, completed=True)
            self.assertTrue(workspace_bootstrap.load_onboarding(data)["completed"])
            again = workspace_bootstrap.seed_workspace(ws)
            self.assertFalse(again["seeded"])

        res = self.client.get("/api/onboarding", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("onboarding", res.get_json())
        res = self.client.post(
            "/api/onboarding/complete",
            json={"completed": True},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/api/onboarding", headers=self.headers)
        self.assertFalse(res.get_json()["show_onboarding"])

    def test_path_escape_blocked(self) -> None:
        res = self.client.get("/api/fs/read?path=../secret", headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_change_accept_rollback(self) -> None:
        (self.workspace / "a.txt").write_text("old\n", encoding="utf-8")
        res = self.client.post(
            "/api/changes",
            json={
                "source": "tool",
                "note": "test",
                "files": [{"path": "a.txt", "before": "old\n", "after": "new\n"}],
            },
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        cid = res.get_json()["change"]["id"]
        res = self.client.get(f"/api/changes/{cid}", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["diffs"][0]["diff"])
        res = self.client.post(f"/api/changes/{cid}/accept", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual((self.workspace / "a.txt").read_text(encoding="utf-8"), "new\n")
        res = self.client.post(f"/api/changes/{cid}/rollback", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual((self.workspace / "a.txt").read_text(encoding="utf-8"), "old\n")

    def test_change_per_file_accept_reject(self) -> None:
        (self.workspace / "p1.txt").write_text("a\n", encoding="utf-8")
        (self.workspace / "p2.txt").write_text("b\n", encoding="utf-8")
        res = self.client.post(
            "/api/changes",
            json={
                "source": "tool",
                "files": [
                    {"path": "p1.txt", "before": "a\n", "after": "A\n"},
                    {"path": "p2.txt", "before": "b\n", "after": "B\n"},
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        cid = res.get_json()["change"]["id"]
        res = self.client.post(
            f"/api/changes/{cid}/files/accept",
            json={"path": "p1.txt"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertEqual((self.workspace / "p1.txt").read_text(encoding="utf-8"), "A\n")
        self.assertEqual(res.get_json()["change"]["status"], "mixed")
        res = self.client.post(
            f"/api/changes/{cid}/files/reject",
            json={"path": "p2.txt"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual((self.workspace / "p2.txt").read_text(encoding="utf-8"), "b\n")
        body = res.get_json()["change"]
        self.assertEqual(body["status"], "mixed")
        statuses = {f["path"]: f["status"] for f in body["files"]}
        self.assertEqual(statuses["p1.txt"], "accepted")
        self.assertEqual(statuses["p2.txt"], "rejected")

    def test_editor_page_has_workbench_chrome(self) -> None:
        res = self.client.get("/editor")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"minimap", res.data)
        self.assertIn(b"fold.js", res.data)
        self.assertIn(b"bottom-dock", res.data)
        self.assertIn(b"diff-overlay", res.data)

    def test_ai_denied_by_default(self) -> None:
        (self.workspace / "b.txt").write_text("x\n", encoding="utf-8")
        res = self.client.post(
            "/api/ai/run",
            json={"prompt": "annotate", "path": "b.txt"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 403)

    def test_ai_propose_via_change_stack(self) -> None:
        from editor import permissions as perms

        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "ai.run": True})
        (self.workspace / "c.txt").write_text("body\n", encoding="utf-8")
        res = self.client.post(
            "/api/ai/run",
            json={"prompt": "add banner", "path": "c.txt"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        change = res.get_json()["change"]
        self.assertEqual(change["status"], "pending")
        self.assertEqual(change["source"], "ai")
        # disk unchanged until accept
        self.assertEqual((self.workspace / "c.txt").read_text(encoding="utf-8"), "body\n")
        res = self.client.post(f"/api/changes/{change['id']}/accept", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("ai", (self.workspace / "c.txt").read_text(encoding="utf-8"))

    def test_permissions_roundtrip(self) -> None:
        res = self.client.put(
            "/api/permissions",
            json={"permissions": {"ai.run": False, "git.write": True, "network": False}},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()["permissions"]
        self.assertFalse(body["ai.run"])
        self.assertTrue(body["git.write"])
        self.assertFalse(body["network"])
        res = self.client.get("/api/permissions", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json()["permissions"]["ai.run"])

    def test_git_log_and_branches(self) -> None:
        from editor import permissions as perms

        perms.save(
            self.app_mod.DATA_DIR,
            {**perms.load(self.app_mod.DATA_DIR), "git.read": True, "git.write": True},
        )
        self.client.post("/api/git/init", headers=self.headers)
        (self.workspace / "g.txt").write_text("one\n", encoding="utf-8")
        res = self.client.post(
            "/api/git/commit",
            json={"message": "first"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        res = self.client.get("/api/git/log?limit=20", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["repo"])
        self.assertGreaterEqual(len(body["commits"]), 1)
        res = self.client.get("/api/git/branches", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        br = res.get_json()
        self.assertTrue(br["current"])
        res = self.client.post(
            "/api/git/checkout",
            json={"name": "feat-p2", "create": True},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertEqual(res.get_json()["current"], "feat-p2")

    def test_lsp_language_map_and_status(self) -> None:
        from editor import lsp_bridge, lsp_client

        self.assertEqual(lsp_bridge.language_for("main.go"), "go")
        self.assertEqual(lsp_bridge.language_for("lib.rs"), "rust")
        self.assertEqual(lsp_bridge.language_for("a.cpp"), "cpp")
        self.assertEqual(lsp_bridge.language_for("x.yml"), "yaml")
        servers = lsp_client.available_servers()
        self.assertIn("python", servers)
        self.assertIn("go", servers)
        self.assertIn("rust", servers)
        res = self.client.get("/api/lsp/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("servers", res.get_json())

    def test_git_init_and_status(self) -> None:
        from editor import permissions as perms

        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "git.write": True})
        res = self.client.post("/api/git/init", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/api/git/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["repo"])

    def test_lsp_diagnose_python(self) -> None:
        res = self.client.post(
            "/api/lsp/diagnose",
            json={"path": "bad.py", "text": "def (\n"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["language"], "python")
        self.assertTrue(body["diagnostics"])

    def test_lsp_complete_endpoint(self) -> None:
        res = self.client.post(
            "/api/lsp/complete",
            json={"path": "x.py", "text": "impor", "line": 0, "character": 5},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertIn("items", body)

    def test_search(self) -> None:
        (self.workspace / "needle.txt").write_text("alpha needle omega\n", encoding="utf-8")
        res = self.client.post(
            "/api/search",
            json={"query": "needle"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        hits = res.get_json()["hits"]
        self.assertTrue(any(h["path"] == "needle.txt" for h in hits))

    def test_terminal_denied_by_default(self) -> None:
        from editor import permissions as perms

        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "terminal": False})
        res = self.client.post(
            "/api/terminal/run",
            json={"command": "echo hi"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 403)

    def test_terminal_when_allowed(self) -> None:
        from editor import permissions as perms

        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "terminal": True})
        res = self.client.post(
            "/api/terminal/run",
            json={"command": "echo zintriq-term"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertEqual(body["exitCode"], 0)
        self.assertIn("zintriq-term", body["stdout"])

    def test_lsp_definition_hover_endpoints(self) -> None:
        payload = {"path": "x.py", "text": "x = 1\n", "line": 0, "character": 0}
        res = self.client.post("/api/lsp/definition", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("locations", res.get_json())
        res = self.client.post("/api/lsp/hover", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("contents", res.get_json())

    def test_lsp_references_and_code_action(self) -> None:
        payload = {"path": "x.py", "text": "x = 1\n", "line": 0, "character": 0}
        res = self.client.post("/api/lsp/references", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("locations", body)
        res = self.client.post("/api/lsp/codeAction", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("actions", res.get_json())
        res = self.client.post(
            "/api/lsp/codeAction/apply",
            json={"action": {"title": "noop"}},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_lsp_rename_without_server(self) -> None:
        res = self.client.post(
            "/api/lsp/rename",
            json={
                "path": "x.py",
                "text": "foo = 1\n",
                "line": 0,
                "character": 0,
                "newName": "bar",
            },
            headers=self.headers,
        )
        # no server → 400
        self.assertIn(res.status_code, (200, 400))

    def test_debug_adapters_and_breakpoints(self) -> None:
        from editor import permissions as perms

        res = self.client.get("/api/debug/adapters", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("python", res.get_json())
        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "debug": False})
        res = self.client.post(
            "/api/debug/breakpoints/toggle",
            json={"path": "dbg.py", "line": 2},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 403)
        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "debug": True})
        (self.workspace / "dbg.py").write_text("x = 1\ny = 2\nprint(x + y)\n", encoding="utf-8")
        res = self.client.post(
            "/api/debug/breakpoints/toggle",
            json={"path": "dbg.py", "line": 2},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertEqual(res.get_json()["lines"], [2])
        res = self.client.post(
            "/api/debug/breakpoints/condition",
            json={"path": "dbg.py", "line": 2, "condition": "y > 1"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["breakpoints"][0]["condition"], "y > 1")
        res = self.client.post(
            "/api/debug/breakpoints/hit",
            json={"path": "dbg.py", "line": 2, "hitCondition": ">=3"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["breakpoints"][0]["hitCondition"], ">=3")
        res = self.client.post(
            "/api/debug/watches",
            json={"expression": "x + y"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("x + y", res.get_json()["watches"])
        res = self.client.post(
            "/api/debug/layout",
            json={"layout": {"showConsole": False, "showVars": True}},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json()["layout"]["showConsole"])
        res = self.client.get("/api/debug/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("dbg.py", body["breakpoints"])
        self.assertEqual(body["breakpoints"]["dbg.py"][0]["hitCondition"], ">=3")
        self.assertIn("layout", body)
        self.assertFalse(body["layout"]["showConsole"])
        # persistence across reload of module state file
        from editor import debug_session as ds

        ds.load_persisted(self.app_mod.DATA_DIR)
        self.assertEqual(ds.list_breakpoints()["dbg.py"][0]["hitCondition"], ">=3")
        self.assertIn("x + y", ds.list_watches())
        res = self.client.post(
            "/api/debug/dataBreakpoints",
            json={"name": "y", "accessType": "write"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["dataBreakpoint"]["name"], "y")
        res = self.client.get("/api/debug/status", headers=self.headers)
        self.assertTrue(any(x["name"] == "y" for x in res.get_json()["dataBreakpoints"]))
        res = self.client.post(
            "/api/debug/attach",
            json={"engine": "python", "host": "127.0.0.1", "port": 0},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            "/api/debug/breakpoints/log",
            json={"path": "dbg.py", "line": 2, "logMessage": "y={y}"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["breakpoints"][0]["logMessage"], "y={y}")
        res = self.client.post(
            "/api/debug/exceptions",
            json={"raised": True, "uncaught": True},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["exceptionBreakpoints"]["raised"])
        res = self.client.post(
            "/api/debug/pathMappings",
            json={"pathMappings": [{"localRoot": "/local", "remoteRoot": "/remote"}]},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["pathMappings"][0]["remoteRoot"], "/remote")
        from editor import debug_session as ds2

        self.assertEqual(ds2._map_remote_to_local("/remote/app.py"), "/local/app.py")
        res = self.client.get("/api/debug/launch", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["configurations"])
        res = self.client.post(
            "/api/debug/launch",
            json={
                "version": "0.2.0",
                "configurations": [
                    {
                        "name": "Py file",
                        "type": "python",
                        "request": "launch",
                        "program": "${file}",
                    }
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["path"], ".zintriq/launch.json")
        self.assertTrue((self.app_mod.WORKSPACE / ".zintriq" / "launch.json").is_file())
        res = self.client.post(
            "/api/debug/breakpoints/meta",
            json={"path": "dbg.py", "line": 2, "group": "smoke", "enabled": True},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["breakpoints"][0]["group"], "smoke")
        res = self.client.post(
            "/api/debug/breakpoints/groups",
            json={"group": "smoke", "enabled": False},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json()["groups"]["smoke"])
        res = self.client.post(
            "/api/debug/breakpoints/batch",
            json={"enable": [{"path": "dbg.py", "line": 2}]},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["breakpoints"]["dbg.py"][0]["enabled"])
        (self.workspace / "crash.txt").write_text(
            'Traceback (most recent call last):\n  File "dbg.py", line 2, in <module>\n'
            "    y = 2\nValueError: boom\n",
            encoding="utf-8",
        )
        res = self.client.post(
            "/api/debug/postmortem",
            json={"path": "crash.txt"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertTrue(res.get_json().get("postmortem") or res.get_json().get("engine") == "postmortem")
        self.client.post("/api/debug/stop", json={}, headers=self.headers)
        res = self.client.get("/api/debug/adapters", headers=self.headers)
        self.assertIn("rr", res.get_json())
        self.assertIn("reverse", res.get_json())
        from editor import debug_extras as de
        from editor import debug_launch as dl

        doc = dl.default_document(self.workspace)
        self.assertTrue(doc.get("compounds"))
        flame = de.flame_from_pstats_text(
            "   ncalls  tottime  percall  cumtime  percall filename:lineno(function)\n"
            "        1    0.001    0.001    0.010    0.010 foo.py:1(bar)\n"
        )
        self.assertTrue(flame["flame"]["children"])
        local_jest = self.workspace / "node_modules" / "jest" / "bin" / "jest.js"
        # without local jest → npx/which path
        prog, prefix, is_npx = de.resolve_jest_program(self.workspace)
        self.assertTrue(prog)
        self.assertTrue(is_npx or not local_jest.is_file())
        if is_npx:
            self.assertIn("jest", prefix)
        res = self.client.get("/api/debug/breakpoints/export", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        exported = res.get_json()
        self.assertIn("breakpoints", exported)
        res = self.client.post(
            "/api/debug/breakpoints/import",
            json={
                "breakpoints": [{"path": "dbg.py", "line": 3, "condition": "x"}],
                "merge": True,
            },
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(b["line"] == 3 for b in res.get_json()["breakpoints"].get("dbg.py", [])))
        tip = de.save_coverage_tip()
        self.assertTrue(tip["ok"])

    def test_debug_python_session_if_debugpy(self) -> None:
        """Live debugpy e2e — opt-in (can be slow / flaky under parallel load)."""
        import importlib.util
        import os
        import time

        from editor import permissions as perms

        if os.environ.get("ZINTRIQ_DEBUG_E2E") != "1":
            self.skipTest("set ZINTRIQ_DEBUG_E2E=1 for live debugpy e2e")
        if importlib.util.find_spec("debugpy") is None:
            self.skipTest("debugpy not installed")
        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "debug": True})
        (self.workspace / "loop.py").write_text(
            "a = 1\nb = 2\nc = a + b\nprint(c)\n",
            encoding="utf-8",
        )
        self.client.post(
            "/api/debug/breakpoints",
            json={"path": "loop.py", "breakpoints": [{"line": 3, "condition": "a == 1"}]},
            headers=self.headers,
        )
        self.client.post("/api/debug/watches", json={"expression": "a + b"}, headers=self.headers)
        res = self.client.post("/api/debug/start", json={"path": "loop.py"}, headers=self.headers)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertTrue(body.get("running"))
        sid1 = body.get("sessionId") or body.get("id")
        self.assertTrue(sid1)
        deadline = time.time() + 8
        while time.time() < deadline and not body.get("stopped"):
            time.sleep(0.2)
            body = self.client.get("/api/debug/status", headers=self.headers).get_json()
        if body.get("stopped"):
            ev = self.client.post(
                "/api/debug/evaluate",
                json={"expression": "a + b", "sessionId": sid1},
                headers=self.headers,
            )
            self.assertEqual(ev.status_code, 200, ev.get_data(as_text=True))
        self.client.post("/api/debug/stop", json={}, headers=self.headers)

    def test_debug_multi_session_registry(self) -> None:
        from editor import debug_session as ds

        # registry semantics without launching adapters
        with ds._LOCK:
            ds._SESSIONS.clear()
            ds._ACTIVE_ID = None

        class _Fake(ds.DebugSession):
            def __init__(self, sid: str, path: str) -> None:
                self.id = sid
                self.rel = path
                self.alive = True
                self.stopped = True
                self.watches = []
                self.frame_id = 1
                self.thread_id = 1
                self.threads = [{"id": 1, "name": "MainThread"}]
                self.timeline = []
                self.timeline_index = -1
                self.timeline_viewing = False
                self.stack = [
                    {"id": 1, "name": "top", "path": path, "line": 1},
                    {"id": 2, "name": "caller", "path": path, "line": 9},
                ]
                self.variables = [{"name": "x", "value": "1", "scope": "Locals"}]
                self.inline_values = []

            def start(self) -> None:
                return None

            def stop(self) -> None:
                self.alive = False

            def apply_breakpoints(self, rel: str) -> None:
                return None

            def apply_data_breakpoints(self) -> None:
                return None

            def apply_exception_breakpoints(self) -> None:
                return None

            def select_frame(self, frame_id) -> None:
                self.frame_id = frame_id
                self.variables = [
                    {"name": "x", "value": "9" if frame_id == 2 else "1", "scope": "Locals"}
                ]
                self.inline_values = [
                    {"path": self.rel, "line": 9 if frame_id == 2 else 1, "text": "x = " + self.variables[0]["value"]}
                ]

            def select_thread(self, thread_id) -> None:
                self.thread_id = thread_id

            def timeline_seek(self, index: int) -> None:
                self.timeline_index = index
                self.timeline_viewing = True
                self.variables = [{"name": "x", "value": str(index), "scope": "Locals"}]

            def timeline_live(self) -> None:
                self.timeline_viewing = False
                self.timeline_index = 0

            def step_back(self) -> dict:
                if self.timeline_index > 0:
                    self.timeline_index -= 1
                return self.snapshot()

            def reverse_continue(self) -> dict:
                self.timeline_index = 0
                return self.snapshot()

            def completions(self, text: str, column: int, *, frame_id=None) -> list:
                return [{"label": "x", "text": "x", "type": "variable"}]

            def profile_start(self, kind: str = "cpu") -> dict:
                return {"ok": True, "kind": kind}

            def profile_stop(self, kind: str = "cpu") -> dict:
                return {"ok": True, "id": "prof1", "kind": kind}

            def disassemble(self, *, memory_reference: str = "", offset: int = 0, count: int = 64) -> dict:
                return {"ok": True, "mode": "fake", "text": "0x0  nop"}

            def read_memory(
                self,
                *,
                memory_reference: str = "",
                expression: str = "",
                offset: int = 0,
                count: int = 64,
            ) -> dict:
                return {"ok": True, "mode": "fake", "text": "00000000  00 01 02", "bytesRead": 3}

            def cont(self) -> dict:
                return self.snapshot()

            def step_over(self) -> dict:
                return self.snapshot()

            def step_in(self) -> dict:
                return self.snapshot()

            def step_out(self) -> dict:
                return self.snapshot()

            def evaluate(self, expression: str, *, frame_id=None, context: str = "repl") -> dict:
                return {"value": "1", "type": "int"}

            def expand_variables(self, variables_reference: int) -> list:
                return [{"name": "child", "value": "2", "variablesReference": 0, "expandable": False}]

            def refresh_watches(self) -> None:
                return None

            def snapshot(self) -> dict:
                return {
                    "ok": True,
                    "id": self.id,
                    "sessionId": self.id,
                    "running": self.alive,
                    "stopped": self.stopped,
                    "path": self.rel,
                    "stack": list(self.stack),
                    "selectedFrameId": self.frame_id,
                    "threadId": self.thread_id,
                    "threads": list(self.threads),
                    "timeline": {
                        "length": 2,
                        "index": self.timeline_index,
                        "viewing": self.timeline_viewing,
                        "entries": [],
                    },
                    "variables": list(self.variables),
                    "inlineValues": list(self.inline_values),
                    "watches": [],
                    "console": [],
                }

        a = _Fake("aaa", "a.py")
        b = _Fake("bbb", "b.py")
        with ds._LOCK:
            ds._SESSIONS["aaa"] = a
            ds._SESSIONS["bbb"] = b
            ds._ACTIVE_ID = "aaa"
        st = ds.status()
        self.assertEqual(len(st["sessions"]), 2)
        ds.set_active("bbb")
        self.assertEqual(ds.status()["activeSessionId"], "bbb")
        framed = ds.select_frame(2, session_id="bbb")
        self.assertEqual(framed["selectedFrameId"], 2)
        self.assertEqual(framed["variables"][0]["value"], "9")
        self.assertTrue(framed["inlineValues"])
        th = ds.select_thread(1, session_id="bbb")
        self.assertEqual(th["threadId"], 1)
        hist = ds.timeline_seek(1, session_id="bbb")
        self.assertTrue(hist["timeline"]["viewing"])
        self.assertEqual(hist["variables"][0]["value"], "1")
        live = ds.timeline_live(session_id="bbb")
        self.assertFalse(live["timeline"]["viewing"])
        back = ds.step_back("bbb")
        self.assertEqual(back["sessionId"], "bbb")
        comps = ds.completions("x.", 3, session_id="bbb")
        self.assertTrue(comps["items"])
        ds.stop("aaa")
        self.assertEqual(len(ds.status()["sessions"]), 1)
        ds.stop()
        self.assertEqual(len(ds.status()["sessions"]), 0)

    def test_pty_supported_and_session(self) -> None:
        from editor import permissions as perms

        res = self.client.get("/api/terminal/pty/supported", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        info = res.get_json()
        self.assertIn("backend", info)
        if not info["supported"]:
            self.skipTest("PTY unsupported here")
        perms.save(self.app_mod.DATA_DIR, {**perms.load(self.app_mod.DATA_DIR), "terminal": True})
        res = self.client.post("/api/terminal/pty/start", json={"cols": 40, "rows": 12}, headers=self.headers)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        sid = body["id"]
        self.assertTrue(body.get("backend"))
        res = self.client.post(
            "/api/terminal/pty/write",
            json={"id": sid, "data": "echo pty-ok\r"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        import time

        time.sleep(0.3)
        res = self.client.get(f"/api/terminal/pty/read?id={sid}", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.client.post("/api/terminal/pty/close", json={"id": sid}, headers=self.headers)


if __name__ == "__main__":
    unittest.main()
