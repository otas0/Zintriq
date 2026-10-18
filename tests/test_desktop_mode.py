"""Desktop mode: subprocess server, loopback bind, token, auth routes, data dir."""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
if not (ROOT / "app.py").is_file():
    raise RuntimeError("expected app.py next to tests")


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _snapshot_paths(paths: list) -> dict:
    found = {}
    for path in paths:
        if path.is_dir():
            found[str(path)] = sorted(
                str(item.relative_to(path)) for item in path.rglob("*") if item.is_file()
            )
        elif path.exists():
            found[str(path)] = "present"
        else:
            found[str(path)] = None
    return found


def _added_files(before: dict, after: dict) -> list:
    created = []
    for key, old in before.items():
        new = after.get(key)
        if old is None and new not in (None, "present") and new != old:
            created.append(key)
        elif old is None and new == "present":
            created.append(key)
        elif isinstance(old, list) and isinstance(new, list):
            extra = sorted(set(new) - set(old))
            if extra:
                created.append(f"{key}: {extra}")
    return created


class DesktopServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from desktop.server_mode import TOKEN_HEADER

        cls.header = TOKEN_HEADER
        cls.token = "d" * 32 + "esktop-test-token"
        cls.temp = Path(tempfile.mkdtemp(prefix="zintriq-desktop-"))
        cls.data_dir = cls.temp / "data"
        cls.log_path = cls.temp / "server.log"
        cls.port = _free_port()
        cls.watched = [
            ROOT / "marketqr.db",
            ROOT / "marketqr.db-wal",
            ROOT / "marketqr.db-shm",
            ROOT / ".dev_secret_key",
            ROOT / "zintriq.db",
            ROOT / "static" / "uploads",
            Path.home() / "marketqr.db",
            Path.home() / "zintriq.db",
            Path.home() / ".dev_secret_key",
            Path.cwd() / "marketqr.db",
        ]
        cls.before_files = _snapshot_paths(cls.watched)
        cls.before_status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        )
        env = os.environ.copy()
        env["ZINTRIQ_DESKTOP"] = "1"
        env["ZINTRIQ_DATA_DIR"] = str(cls.data_dir)
        env["ZINTRIQ_DESKTOP_TOKEN"] = cls.token
        env["PORT"] = str(cls.port)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env.pop("HOST", None)
        cls.log_handle = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [str(PYTHON), str(ROOT / "app.py")],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=cls.log_handle,
            stderr=subprocess.STDOUT,
        )
        try:
            cls._wait_until_ready()
        except Exception:
            if cls.proc.poll() is None:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
            cls.log_handle.close()
            raise

    @classmethod
    def _scrub(cls, text: str) -> str:
        return text.replace(cls.token, "<token>")

    @classmethod
    def _wait_until_ready(cls):
        deadline = time.time() + 120
        last = "server did not become ready"
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                cls.log_handle.flush()
                log = cls.log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
                raise RuntimeError(cls._scrub(log))
            try:
                status, _headers, _body = cls._exchange("GET", "/healthz")
                if status == 200:
                    return
                last = f"healthz status {status}"
            except OSError as exc:
                last = str(exc)
            time.sleep(0.25)
        cls.log_handle.flush()
        log = cls.log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError(cls._scrub(last + "\n" + log))

    @classmethod
    def _exchange(cls, method: str, path: str, headers: dict | None = None, body: bytes | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=30)
        try:
            merged = {"Host": f"127.0.0.1:{cls.port}", cls.header: cls.token}
            if headers:
                merged.update(headers)
            if body is not None:
                merged["Content-Length"] = str(len(body))
            conn.putrequest(method, path, skip_host=True)
            for key, value in merged.items():
                conn.putheader(key, value)
            conn.endheaders(body)
            response = conn.getresponse()
            payload = response.read()
            pairs = response.getheaders()
            return response.status, pairs, payload
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "proc", None) and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        if getattr(cls, "proc", None) and cls.proc.stdin:
            cls.proc.stdin.close()
        if getattr(cls, "log_handle", None):
            cls.log_handle.close()
        log = ""
        if cls.log_path.is_file():
            log = cls.log_path.read_text(encoding="utf-8", errors="replace")
        shutil.rmtree(cls.temp, ignore_errors=True)
        if cls.token in log:
            raise AssertionError("server log contained the desktop token")

    def _headers(self, pairs):
        return {key.lower(): value for key, value in pairs}

    def test_listens_on_loopback_only(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.settimeout(2)
            probe.connect(("127.0.0.1", self.port))
        finally:
            probe.close()
        if os.name == "nt":
            output = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                text=True,
                errors="replace",
            )
            listening = [
                line
                for line in output.splitlines()
                if "LISTENING" in line.upper() and f":{self.port}" in line
            ]
            self.assertTrue(listening, f"no LISTENING row for port {self.port}\n{output[-1500:]}")
            joined = "\n".join(listening)
            self.assertIn(f"127.0.0.1:{self.port}", joined)
            self.assertNotRegex(joined, rf"(?m)^\s*TCP\s+0\.0\.0\.0:{self.port}\b")
            self.assertNotRegex(joined, rf"(?m)^\s*TCP\s+\*:{self.port}\b")
        else:
            output = subprocess.check_output(
                ["lsof", "-nP", f"-iTCP:{self.port}", "-sTCP:LISTEN"],
                text=True,
                errors="replace",
            )
            self.assertIn(f"127.0.0.1:{self.port}", output)
            self.assertNotIn(f"*:{self.port}", output)
            self.assertNotIn(f"0.0.0.0:{self.port}", output)
        for _family, _, _, _, address in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = address[0]
            if ip.startswith("127."):
                continue
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.4)
            try:
                sock.connect((ip, self.port))
            except OSError:
                continue
            else:
                self.fail(f"desktop server accepted a connection on {ip}")
            finally:
                sock.close()

    def test_token_host_options_and_healthz(self):
        status, pairs, body = self._exchange("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertIn(b"ok", body)
        headers = self._headers(pairs)
        server = headers.get("server") or ""
        self.assertNotIn("waitress", server.lower())
        self.assertNotIn("werkzeug", server.lower())
        self.assertNotIn("location", headers)
        self.assertFalse(any(key.lower().startswith("access-control-") for key, _value in pairs))

        status, pairs, _body = self._exchange(
            "GET", "/healthz", headers={self.header: ""}
        )
        self.assertEqual(status, 401)
        self.assertNotIn("location", self._headers(pairs))
        self.assertFalse(any(key.lower().startswith("access-control-") for key, _value in pairs))

        status, pairs, _body = self._exchange(
            "GET", "/healthz", headers={self.header: "f" * 32}
        )
        self.assertEqual(status, 401)
        self.assertNotIn("location", self._headers(pairs))
        self.assertFalse(any(key.lower().startswith("access-control-") for key, _value in pairs))

        status, pairs, _body = self._exchange("OPTIONS", "/healthz", headers={self.header: ""})
        self.assertEqual(status, 401)
        self.assertNotIn("location", self._headers(pairs))
        self.assertFalse(any(key.lower().startswith("access-control-") for key, _value in pairs))

        status, pairs, _body = self._exchange("OPTIONS", "/healthz")
        self.assertNotEqual(status, 401)
        self.assertFalse(any(key.lower().startswith("access-control-") for key, _value in pairs))

        for host in (
            f"evil.example:{self.port}",
            "127.0.0.1",
            "localhost",
            f"0.0.0.0:{self.port}",
            f"127.0.0.1:{self.port + 1}",
        ):
            status, pairs, _body = self._exchange(
                "GET",
                "/healthz",
                headers={"Host": host},
            )
            self.assertEqual(status, 400, host)
            self.assertNotIn("location", self._headers(pairs))
            self.assertFalse(any(key.lower().startswith("access-control-") for key, _value in pairs))

        status, pairs, _body = self._exchange(
            "GET",
            "/healthz",
            headers={"Host": f"localhost:{self.port}"},
        )
        self.assertEqual(status, 200)
        self.assertFalse(any(key.lower().startswith("access-control-") for key, _value in pairs))

        status, _pairs, body = self._exchange("GET", "/sw.js")
        self.assertEqual(status, 404)
        self.assertNotIn(b"addEventListener", body)

    def test_ready_line_names_this_process(self):
        self.log_handle.flush()
        text = self.log_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^ZINTRIQ_READY pid=(\d+) port=(\d+)$", text, re.M)
        self.assertIsNotNone(match, text[-500:])
        ready_pid = int(match.group(1))
        if os.name != "nt":
            self.assertEqual(ready_pid, self.proc.pid)
        self.assertTrue(_pid_alive(ready_pid))
        self.assertEqual(int(match.group(2)), self.port)
        self.assertNotIn(self.token, match.group(0))

    def test_auth_routes_redirect_to_studio(self):
        if os.environ.get("ZINTRIQ_DESKTOP") == "1":
            self.skipTest("parent environment enables desktop mode")
        import app as app_module
        from desktop.server_mode import AUTH_RULES, concrete_path, rule_looks_like_auth

        rules = [rule.rule for rule in app_module.app.url_map.iter_rules()]
        missing = sorted(AUTH_RULES - set(rules))
        self.assertEqual(missing, [], "auth rules missing from the url map")
        unexpected = sorted(rule for rule in rules if rule_looks_like_auth(rule) and rule not in AUTH_RULES)
        self.assertEqual(unexpected, [], "url map has auth routes that desktop mode does not close")
        for rule in sorted(AUTH_RULES):
            path = concrete_path(rule)
            status, pairs, _body = self._exchange("GET", path)
            location = self._headers(pairs).get("location", "")
            self.assertEqual(status, 302, f"{rule} -> {path} returned {status}")
            self.assertTrue(
                location.endswith("/studio") or location.endswith("/studio/"),
                f"{rule} redirected to {location}",
            )

    def test_desktop_pages_open(self):
        status, pairs, body = self._exchange("GET", "/studio")
        self.assertEqual(status, 200)
        studio_html = body.decode("utf-8", "replace")
        # Phase-2 desktop shell: Community is in-app; still no team / account chrome.
        self.assertIn('href="/app/community"', studio_html)
        self.assertIn('data-page="community"', studio_html)
        self.assertNotIn("from-community", studio_html)
        self.assertNotIn("/account/workspaces", studio_html)
        self.assertTrue(
            ("Personal · Local" in studio_html) or ("个人 · 本地" in studio_html),
            "desktop studio should show the personal workspace hint",
        )
        # Community lives in the desktop shell.
        for path in ("/app/community", "/account/workspaces"):
            c_status, _pairs, c_body = self._exchange("GET", path)
            self.assertEqual(
                c_status,
                200,
                f"{path} {self._scrub(c_body.decode('utf-8', 'replace')[:240])}",
            )
        community = self._exchange("GET", "/app/community")[2].decode("utf-8", "replace")
        main = community.split("<main", 1)[1].split("</main>", 1)[0]
        self.assertNotIn("page.community", main)
        self.assertNotRegex(
            main,
            r"(?<![A-Za-z0-9_-])(?:community|item|share|profile)\.[a-z0-9_.]+",
        )
        self.assertIn("Your published descriptions", main)
        self.assertIn("da-community", community)
        status, _pairs, body = self._exchange("GET", "/app/settings")
        self.assertIn(status, (302, 303))
        self.assertIn("da-factory", studio_html)
        self.assertNotIn("universal-builder.js", studio_html)
        match = re.search(r'csrf-token" content="([^"]+)"', studio_html)
        self.assertIsNotNone(match)
        csrf = match.group(1)
        cookie = "; ".join(
            value.split(";", 1)[0] for key, value in pairs if key.lower() == "set-cookie"
        )
        meta_status, _meta_pairs, meta_body = self._exchange(
            "GET",
            "/studio/meta",
            headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        )
        meta_html = meta_body.decode("utf-8", "replace")
        self.assertEqual(meta_status, 200, self._scrub(meta_html[:300]))
        self.assertIn("me-code", meta_html)
        self.assertNotIn("universal-builder.js", meta_html)
        retired_status, retired_pairs, _retired_body = self._exchange(
            "GET",
            "/studio/p/1",
            headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        )
        self.assertIn(retired_status, (301, 302, 303))
        location = self._headers(retired_pairs).get("location", "")
        self.assertTrue(location.endswith("/studio") or "/studio" in location)

    def test_desktop_navigation_allowlist(self):
        """Electron shell may open Community; not merchant / account / marketing."""
        script = ROOT / "desktop" / "navigation.js"
        result = subprocess.run(
            [
                "node",
                "-e",
                "const n=require('./desktop/navigation');"
                "const port=4123;"
                "const ok=(p)=>n.navigationAllowed('http://127.0.0.1:'+port+p, port);"
                "const assert=(c,m)=>{if(!c){console.error(m);process.exit(1);}};"
                "assert(ok('/studio'),'studio');"
                "assert(ok('/'),'root');"
                "assert(ok('/studio/meta'),'meta');"
                "assert(ok('/build/demo'),'build');"
                "assert(ok('/static/x.js'),'static');"
                "assert(ok('/api/builder-core/meta/index'),'api');"
                "assert(!ok('/pricing'),'pricing');"
                "assert(!ok('/product'),'product');"
                "assert(ok('/app/community'),'community');"
                "assert(!ok('/app/settings'),'settings');"
                "assert(!ok('/manage/demo'),'manage');"
                "assert(!ok('/account'),'account');"
                "assert(!ok('/login'),'login');"
                "console.log('ok');",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout)
        self.assertTrue(script.is_file())

    def test_production_desktop_refuses_public_bind(self):
        env = os.environ.copy()
        env["ZINTRIQ_DESKTOP"] = "1"
        env["ENV"] = "production"
        env["HOST"] = "0.0.0.0"
        env["ZINTRIQ_DESKTOP_TOKEN"] = "p" * 32
        env["ZINTRIQ_DATA_DIR"] = str(self.temp / "unused-prod")
        proc = subprocess.run(
            [
                str(PYTHON),
                "-c",
                "from desktop.server_mode import prepare_desktop_paths; prepare_desktop_paths()",
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("non-loopback", proc.stderr)

    def test_create_project_stays_inside_data_dir(self):
        from meta.description import to_json
        from meta.instantiation import default_site_desc

        status, pairs, body = self._exchange("GET", "/studio")
        self.assertEqual(status, 200, self._scrub(body.decode("utf-8", "replace")[:400]))
        match = re.search(r'csrf-token" content="([^"]+)"', body.decode("utf-8", "replace"))
        self.assertIsNotNone(match)
        csrf = match.group(1)
        cookie = "; ".join(
            value.split(";", 1)[0] for key, value in pairs if key.lower() == "set-cookie"
        )
        before = _snapshot_paths(self.watched)
        status_before = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        payload = json.dumps({
            "csrf_token": csrf,
            "slug": "desktop-smoke",
            "description": json.loads(to_json(default_site_desc())),
        }).encode()
        status, _pairs, body = self._exchange(
            "POST",
            "/api/builder-core/meta/instantiate",
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
                "Cookie": cookie,
            },
            body=payload,
        )
        self.assertEqual(status, 201, self._scrub(body.decode("utf-8", "replace")[:400]))
        after = _snapshot_paths(self.watched)
        status_after = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        changed = _added_files(self.before_files, after)
        self.assertEqual(before, after)
        self.assertEqual(status_before, status_after)
        self.assertEqual(changed, [])
        database = self.data_dir / "zintriq.db"
        self.assertTrue(database.is_file())
        self.assertTrue((self.data_dir / "artifacts" / "desktop-smoke.json").is_file())
        self.assertTrue((self.data_dir / "sites" / "desktop-smoke" / "home.html").is_file())
        if os.name == "posix":
            self.assertEqual(self.data_dir.stat().st_mode & 0o777, 0o700)
        conn = sqlite3.connect(database)
        try:
            user = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                ("local@desktop.zintriq",),
            ).fetchone()
            member = conn.execute(
                """SELECT wm.role FROM workspace_members wm
                   JOIN users u ON u.id = wm.user_id
                   WHERE u.email = ?""",
                ("local@desktop.zintriq",),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(user)
        self.assertEqual(member[0], "owner")

    def test_web_mode_still_requires_login(self):
        if os.environ.get("ZINTRIQ_DESKTOP") == "1":
            self.skipTest("parent environment enables desktop mode")
        import app as app_module

        client = app_module.app.test_client()
        studio = client.get("/studio", follow_redirects=False)
        self.assertEqual(studio.status_code, 404)
        health = client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        for path in ("/studio/p/1", "/app/community"):
            retired = client.get(path, follow_redirects=False)
            self.assertEqual(retired.status_code, 404, path)
        runtime = client.get("/static/builder/universal-runtime.css")
        self.assertEqual(runtime.status_code, 404)
        built = client.get("/build/demo/home")
        self.assertEqual(built.status_code, 404)
        api = client.get("/api/builder-core/projects")
        self.assertEqual(api.status_code, 404)

    def test_web_does_not_provide_studio(self):
        if os.environ.get("ZINTRIQ_DESKTOP") == "1":
            self.skipTest("parent environment enables desktop mode")
        import app as app_module

        client = app_module.app.test_client()
        for path in ("/studio", "/studio/", "/studio/p/1", "/studio/simulate", "/studio/instantiate", "/studio/space"):
            response = client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 404, path)
            self.assertNotIn("/login", response.headers.get("Location") or "")


class DesktopShellFileTests(unittest.TestCase):
    def test_electron_shell_has_no_composition_transfer(self):
        preload = (ROOT / "desktop" / "preload.js").read_text(encoding="utf-8")
        self.assertIn("studio:http", preload)
        self.assertIn("studio:probe", preload)
        self.assertIn("studio:plugin-publish", preload)
        self.assertIn("studio:plugin-disable", preload)
        self.assertIn("studio:plugin-remove", preload)
        self.assertIn("disablePlugin", preload)
        self.assertIn("removePlugin", preload)
        self.assertIn("publishPlugin", preload)
        error_page = (ROOT / "desktop" / "error.html").read_text(encoding="utf-8")
        self.assertIn("did not start", error_page)
        self.assertIn("local host", error_page.lower())
        self.assertIn("studio:notify", preload)
        self.assertIn("studio:unpublish", preload)
        self.assertIn("studio:sync", preload)
        self.assertIn("studio:plugin-catalog", preload)
        self.assertIn("listPlugins", preload)
        self.assertIn("studio:open-pack", preload)
        self.assertIn("pathForFile", preload)
        self.assertIn("openPack", preload)
        self.assertNotIn("export-project", preload)
        self.assertNotIn("preview-import", preload)
        self.assertNotIn("commit-import", preload)
        self.assertNotIn("exportProject", preload)
        menu = (ROOT / "desktop" / "app_menu.js").read_text(encoding="utf-8")
        self.assertIn('label: "Open…"', menu)
        self.assertIn("Export webpage", menu)
        self.assertIn("Community", menu)
        self.assertIn('label: "Home"', menu)
        self.assertIn('label: "New"', menu)
        self.assertIn('label: "Community"', menu)
        self.assertNotIn('label: "Describe"', menu)
        self.assertNotIn('label: "Simulate"', menu)
        self.assertNotIn('label: "Instantiate"', menu)
        self.assertIn('label: "Pane"', menu)
        self.assertIn('activateEditorView("uir")', menu)
        self.assertIn('activateEditorView("diagram")', menu)
        self.assertIn("Add plugin", menu)
        self.assertIn("Check for updates", menu)
        self.assertIn("Sign up", menu)
        login_page = (ROOT / "desktop" / "login.html").read_text(encoding="utf-8")
        self.assertIn("Sign in to continue", login_page)
        self.assertIn("id=\"signup\"", login_page)
        self.assertIn("does not need an account", login_page)
        self.assertIn("openPack", login_page)
        self.assertIn("dragover", login_page)
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8")
        self.assertIn("showLoginGate", main)
        self.assertIn("verifySession", main)
        self.assertNotIn(".zintriq", menu)
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8")
        self.assertIn("meta_zip_host", main)
        self.assertIn("meta_http", main)
        self.assertIn("studio:http", main)
        self.assertIn("studio:plugin-disable", main)
        self.assertIn("studio:plugin-remove", main)
        self.assertIn("host_prefs", main)
        self.assertIn("Unsaved work", main)
        self.assertIn("studio:unpublish", main)
        self.assertIn("studio:sync", main)
        self.assertIn("accountOrigin", main)
        self.assertIn("studio/meta?new=1", main)
        self.assertIn("/studio/space", main)
        self.assertIn("/api/builder-core/meta/index", main)
        self.assertIn("open-file", main)
        self.assertIn("packPathsFromArgv", main)
        self.assertIn("flushPendingPacks", main)
        self.assertIn("studio:open-pack", main)
        self.assertNotIn("sign in required", main)
        self.assertIn("importSite: () => {", main)
        self.assertNotIn("You cannot describe", login_page)
        self.assertIn("/studio/instantiate", main)
        self.assertNotIn("studio/meta?slug=", main)
        community_js = (ROOT / "static" / "studio" / "community.js").read_text(encoding="utf-8")
        self.assertIn('openShare(item.id, "describe")', community_js)
        self.assertIn("listPlugins", community_js)
        self.assertIn("goHomeAfterInstall", community_js)
        self.assertIn("Install this plugin first", community_js)
        self.assertIn("requireAccountToPublish", community_js)
        self.assertIn("Sign in to publish to your account", community_js)
        self.assertIn('textContent = "Install"', community_js)
        self.assertIn("addInstallButton", community_js)
        self.assertIn("goHomeAfterInstall", community_js)
        self.assertIn('textContent = "Use"', community_js)
        self.assertIn('textContent = "Disable"', community_js)
        self.assertIn('textContent = "Remove"', community_js)
        self.assertIn("/api/plugin/disable", community_js)
        self.assertIn("/api/plugin/remove", community_js)
        self.assertIn("/api/plugin/stamp", community_js)
        self.assertIn("data.replaced", community_js)
        self.assertIn("delete_draft", community_js)
        self.assertIn("Bound draft:", community_js)
        self.assertIn("draft_slug", community_js)
        editor_js = (ROOT / "static" / "studio" / "meta-editor.js").read_text(encoding="utf-8")
        self.assertIn("未盖章", editor_js)
        self.assertIn("草稿不是这份包", editor_js)
        self.assertIn("draft refreshed", editor_js)
        self.assertIn("stampConsistency", editor_js)
        self.assertIn("keymapConflicts", (ROOT / "desktop" / "host_prefs.js").read_text(encoding="utf-8"))
        self.assertIn("gitStatus", main)
        self.assertIn("gitDiff", (ROOT / "desktop" / "host_prefs.js").read_text(encoding="utf-8"))
        self.assertIn("gitLog", (ROOT / "desktop" / "host_prefs.js").read_text(encoding="utf-8"))
        self.assertIn("gitIgnore", (ROOT / "desktop" / "host_prefs.js").read_text(encoding="utf-8"))
        self.assertIn("lastFlaskLaunch", (ROOT / "desktop" / "flask_host.js").read_text(encoding="utf-8"))
        self.assertIn("importKeymap", (ROOT / "desktop" / "preload.js").read_text(encoding="utf-8"))
        self.assertIn("togglePin", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("wb-q-form", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("data-stamp", (ROOT / "static" / "studio" / "meta-editor.js").read_text(encoding="utf-8"))
        self.assertIn("label: \"Git\"", (ROOT / "desktop" / "app_menu.js").read_text(encoding="utf-8"))
        plugins_html = (ROOT / "templates" / "marketing" / "plugins.html").read_text(encoding="utf-8")
        self.assertIn("page.plugins.kicker", plugins_html)
        self.assertIn("page.plugins.lead", plugins_html)
        self.assertIn("page.plugins.title", plugins_html)
        self.assertIn("page.plugins.open_studio", plugins_html)
        self.assertIn("data-pack-id", plugins_html)
        en_json = (ROOT / "i18n" / "locales" / "en.json").read_text(encoding="utf-8")
        self.assertIn("no public CDN", en_json)
        self.assertIn("no ratings", en_json.lower())
        self.assertIn("desktop Community", en_json)
        self.assertIn("overflow-x: auto", (ROOT / "static" / "studio" / "workbench.css").read_text(encoding="utf-8"))
        self.assertIn('window.location.href = "/studio"', (ROOT / "static" / "studio" / "community.js").read_text(encoding="utf-8"))
        community_html = (ROOT / "templates" / "studio" / "community.html").read_text(encoding="utf-8")
        self.assertIn("Install, Use, Disable, and Remove stay on this machine", community_html)
        self.assertNotIn("hasCachedAccount", main)
        factory_js = (ROOT / "static" / "studio" / "factory.js").read_text(encoding="utf-8")
        self.assertIn("/studio/meta/", factory_js)
        self.assertIn("isPluginFile", factory_js)
        self.assertIn("looksLikePluginPack", factory_js)
        self.assertIn("refreshInstalledPacks", factory_js)
        self.assertIn("refreshCurrentDrafts", factory_js)
        self.assertIn("data-pack-disable", factory_js)
        self.assertIn("zintriq-plugin", factory_js)
        self.assertIn("data.studio", factory_js)
        self.assertIn('kind === "webpage" && data.studio', factory_js)
        self.assertNotIn("/studio/instantiate/", factory_js)
        factory_html = (ROOT / "templates" / "studio" / "factory.html").read_text(encoding="utf-8")
        self.assertIn("zintriq-app.zip", factory_html)
        self.assertIn("data-pack-disable", factory_html)
        self.assertIn("data-pack-remove", factory_html)
        self.assertIn("da-draft-empty", factory_html)
        self.assertIn("Right-click for Fill", factory_html)
        self.assertIn("data-fill-pack", factory_html)
        self.assertIn("is-current-empty", factory_html)
        self.assertIn("multiple", factory_html)
        self.assertIn("da-diag", factory_html)
        self.assertIn("da-relaunch", factory_html)
        self.assertIn("da-copy-log", factory_html)
        self.assertIn("/studio/settings", factory_html)
        community_js = (ROOT / "static" / "studio" / "community.js").read_text(encoding="utf-8")
        self.assertIn("/api/plugin/use", community_js)
        self.assertIn("applyPackFocus", community_js)
        self.assertIn("stamp-target", community_js)
        self.assertIn("prefillStampName", community_js)
        self.assertIn("zintriq-community-kind", community_js)
        self.assertIn("zintriq-community-q", community_js)
        self.assertIn("syncCommunityUrl", community_js)
        self.assertIn('syncCommunityUrl("push")', community_js)
        self.assertIn("communityPushMax", community_js)
        self.assertIn("popstate", community_js)
        self.assertIn("bound to draft", community_js)
        self.assertIn("rebind: true", community_js)
        self.assertIn("binding_cleared", community_js)
        self.assertIn("zintriq-binding-cleared", community_js)
        self.assertIn("zintriq-binding", community_js)
        self.assertIn("da-stamp-id", community_html)
        self.assertIn("da-reload", community_html)
        editor_views_js = (ROOT / "static" / "studio" / "editor-views.js").read_text(encoding="utf-8")
        self.assertIn("BroadcastChannel", editor_views_js)
        self.assertIn("ESP32 hidden", editor_views_js)
        self.assertIn("Reinstall Robotics", editor_views_js)
        self.assertIn("me-hw", editor_views_js)
        self.assertIn("#me-hw missing", editor_views_js)
        self.assertIn("Open Instantiate", editor_views_js)
        self.assertIn("zintriq-focus-hw", editor_views_js)
        workbench_js = (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8")
        self.assertIn("zintriq-draft-slug", workbench_js)
        self.assertIn("modesScroll", workbench_js)
        self.assertIn("rebind-timeline", workbench_js)
        self.assertIn("openRebindDrawer", workbench_js)
        self.assertIn("wb-rebind-group", workbench_js)
        self.assertIn("zintriq-rebind-open-pack", workbench_js)
        self.assertIn("refreshRebinds", workbench_js)
        self.assertIn("__zintriqLayoutTimer", workbench_js)
        self.assertIn("layoutDebounceMs", workbench_js)
        self.assertIn("__zintriqWindowId", workbench_js)
        self.assertIn("zintriq-layout", workbench_js)
        self.assertIn("openLocalFiles", factory_js)
        self.assertIn("skippedQueue", factory_js)
        self.assertIn("Retry all", factory_js)
        self.assertIn("Retrying ", factory_js)
        self.assertIn("data-retry-cancel", factory_js)
        self.assertIn("Confirm cancel?", factory_js)
        self.assertIn("Install UI & Fill", factory_js)
        self.assertIn("Retry install & Fill", factory_js)
        self.assertIn("data-fill-draft-link", factory_js)
        self.assertIn("Occupied:", factory_js)
        self.assertIn("Rename to ", factory_js)
        self.assertIn("data-rename-slot", factory_js)
        self.assertIn("Other name", factory_js)
        self.assertIn("is-occupied", factory_js)
        self.assertIn("da-draft-menu", factory_js)
        self.assertIn("pointerdown", factory_js)
        self.assertIn("holdMs", factory_js)
        self.assertIn("zintriq-hold-touch-ms", factory_js)
        self.assertIn("navigator.vibrate", factory_js)
        self.assertIn("Bound draft:", factory_js)
        self.assertIn("data-copy-sha256", plugins_html)
        self.assertIn("page.plugins.copy_sha256", plugins_html)
        site_chrome = (ROOT / "static" / "js" / "site-chrome.js").read_text(encoding="utf-8")
        self.assertIn("showCopyToast", site_chrome)
        self.assertIn("prefersReducedMotion", site_chrome)
        self.assertIn("dismissCopyToast", site_chrome)
        self.assertIn("pointerup", site_chrome)
        self.assertIn("mq-toast__secs", site_chrome)
        settings_html = (ROOT / "templates" / "studio" / "settings.html").read_text(encoding="utf-8")
        self.assertIn("da-settings-push-max", settings_html)
        self.assertIn("da-settings-prefs-export", settings_html)
        self.assertIn("da-settings-hold-touch", settings_html)
        self.assertIn("is-current-empty", (ROOT / "static" / "desktop-app.css").read_text(encoding="utf-8"))
        self.assertIn("assertModesScrollLayout", (ROOT / "desktop" / "scripts" / "smoke.js").read_text(encoding="utf-8"))
        settings_html = (ROOT / "templates" / "studio" / "settings.html").read_text(encoding="utf-8")
        self.assertIn("da-keymap-conflicts", settings_html)
        self.assertIn("not uploaded", settings_html)
        self.assertIn("da-git-ignore", settings_html)
        self.assertIn("writeDotted", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("edlText", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("zintriq-plugins-changed", (ROOT / "static" / "studio" / "editor-views.js").read_text(encoding="utf-8"))
        self.assertIn("wb-q-level", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("wb-q-save", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("wb-q-level-min", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("parseEdl", (ROOT / "static" / "studio" / "editors" / "solvers.js").read_text(encoding="utf-8"))
        self.assertIn("T(\\d+)", (ROOT / "static" / "studio" / "editors" / "solvers.js").read_text(encoding="utf-8"))
        self.assertIn("A(\\d+)", (ROOT / "static" / "studio" / "editors" / "solvers.js").read_text(encoding="utf-8"))
        self.assertIn("shots.audio", (ROOT / "static" / "studio" / "editors" / "solvers.js").read_text(encoding="utf-8"))
        self.assertIn("dopesheet", (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn("insert-key", (ROOT / "static" / "studio" / "editors" / "plugin-kit.js").read_text(encoding="utf-8"))
        self.assertIn("from_layer", (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn("to_layer", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("  A", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("wb-fav-drag", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("_paletteQ", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("dest === slug", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertNotIn("studio/meta?new=1", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("ease-in-out", (ROOT / "static" / "studio" / "editors" / "plugin-kit.js").read_text(encoding="utf-8"))
        self.assertIn("cubic", (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn('"c1x"', (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn('"c2y"', (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn("keepout", (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn("holes", (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn("inSolidKeepout", (ROOT / "static" / "studio" / "editors" / "solvers.js").read_text(encoding="utf-8"))
        self.assertIn("shot.edl", (ROOT / "static" / "studio" / "editors" / "solvers.js").read_text(encoding="utf-8"))
        self.assertIn("drafts/", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("/cut", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("wb-q-export", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("mergeQueries", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("restoreStamp", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("toISOString", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("ArrowLeft", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("paintRecent", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("recentCommands", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("command._recent", (ROOT / "static" / "studio" / "engine.js").read_text(encoding="utf-8"))
        self.assertIn("data-ease-handles", (ROOT / "static" / "studio" / "editors" / "plugin-kit.js").read_text(encoding="utf-8"))
        self.assertIn("fill(\"evenodd\")", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("thisDescAudio", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("mergeQueries(root.ZintriqWorkbench._queries", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("fp8", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("recentByWorkspace", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("recentByWorkspace", (ROOT / "desktop" / "layout.py").read_text(encoding="utf-8"))
        self.assertIn("data-ease-row", (ROOT / "static" / "studio" / "editors" / "plugin-kit.js").read_text(encoding="utf-8"))
        self.assertIn("draw_l0", (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn("Ignore child Desc audio sequence", (ROOT / "desktop" / "meta_store.py").read_text(encoding="utf-8"))
        self.assertIn("row.id", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("pack_id", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("switchWorkspace", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("page.plugins.origin.", plugins_html)
        self.assertIn("copy-ease", (ROOT / "static" / "studio" / "editors" / "plugin-kit.js").read_text(encoding="utf-8"))
        self.assertIn("data-keepout-counts", (ROOT / "static" / "studio" / "editors" / "plugin-kit.js").read_text(encoding="utf-8"))
        self.assertIn("track: shot.track", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn('String(item.id || "").trim()', (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("da-installed-packs", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("renameWorkspace", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("page.plugins.origin.official", (ROOT / "i18n" / "locales" / "de.json").read_text(encoding="utf-8"))
        self.assertIn("page.plugins.origin.third", (ROOT / "i18n" / "locales" / "fr.json").read_text(encoding="utf-8"))
        self.assertIn("page.plugins.origin.official", (ROOT / "i18n" / "locales" / "es.json").read_text(encoding="utf-8"))
        self.assertIn("page.plugins.name.", plugins_html)
        self.assertIn("workbench-layout.json", (ROOT / "desktop" / "meta_store.py").read_text(encoding="utf-8"))
        self.assertIn("easeUnit", (ROOT / "static" / "studio" / "editors" / "solvers.js").read_text(encoding="utf-8"))
        self.assertIn("easing", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn('writeMerge(ctx, "drc"', (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("layer:", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("  T", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("palette.repaint", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("Rename favorite", (ROOT / "static" / "studio" / "workbench.js").read_text(encoding="utf-8"))
        self.assertIn("No external PCB", (ROOT / "static" / "studio" / "editors" / "pack.js").read_text(encoding="utf-8"))
        self.assertIn("keyframes", (ROOT / "static" / "studio" / "editors" / "runtimes.js").read_text(encoding="utf-8"))
        self.assertIn("syncCommands", (ROOT / "static" / "studio" / "editor-views.js").read_text(encoding="utf-8"))
        self.assertIn("portInUse", (ROOT / "static" / "studio" / "factory.js").read_text(encoding="utf-8"))
        self.assertIn("assertAssocOpen", (ROOT / "desktop" / "scripts" / "smoke.js").read_text(encoding="utf-8"))
        self.assertIn("probeInstalledAssocs", (ROOT / "desktop" / "scripts" / "smoke.js").read_text(encoding="utf-8"))
        self.assertIn("mdls", (ROOT / "desktop" / "scripts" / "assoc-os.js").read_text(encoding="utf-8"))
        self.assertIn("xdg-mime", (ROOT / "desktop" / "scripts" / "assoc-os.js").read_text(encoding="utf-8"))
        self.assertIn("HKCU", (ROOT / "desktop" / "scripts" / "assoc-os.js").read_text(encoding="utf-8"))
        self.assertIn("OpenWithProgids", (ROOT / "desktop" / "scripts" / "assoc-os.js").read_text(encoding="utf-8"))
        self.assertIn("Archive Utility", (ROOT / "desktop" / "scripts" / "assoc-os.js").read_text(encoding="utf-8"))
        self.assertIn("打开方式", (ROOT / "docs" / "desktop-packaging.md").read_text(encoding="utf-8"))
        self.assertIn("page.plugins.verify_open", plugins_html)
        self.assertIn("page.plugins.kicker", plugins_html)
        self.assertIn("page.plugins.sandbox", plugins_html)
        self.assertIn("page.plugins.status.", plugins_html)
        self.assertIn("page.plugins.summary.", plugins_html)
        self.assertIn("page.plugins.name.", plugins_html)
        pack_doc = (ROOT / "docs" / "desktop-packaging.md").read_text(encoding="utf-8")
        self.assertIn("手测录像核对", pack_doc)
        self.assertIn("手测补", pack_doc)
        self.assertIn("访达核对", pack_doc)
        self.assertIn("访达补 content type", pack_doc)
        self.assertIn("mime 核对", pack_doc)
        self.assertIn("mime 补", pack_doc)
        zh_hans = (ROOT / "i18n" / "locales" / "zh-Hans.json").read_text(encoding="utf-8")
        self.assertIn("Studio Open 时核对该值", zh_hans)
        pkg = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))
        exts = []
        for item in (pkg.get("build") or {}).get("fileAssociations") or []:
            ext = item.get("ext")
            if isinstance(ext, list):
                exts.extend(ext)
            else:
                exts.append(ext)
        self.assertIn("json", exts)
        self.assertIn("zip", exts)
        self.assertIn("zintriq-app", exts)
        zip_assoc = next(item for item in pkg["build"]["fileAssociations"] if item.get("ext") == "zip")
        self.assertEqual(zip_assoc.get("rank"), "Alternate")
        self.assertIn("not default unzip", zip_assoc.get("description", "").lower())
        plugin_assoc = next(item for item in pkg["build"]["fileAssociations"] if item.get("ext") == "zintriq-plugin.json")
        self.assertEqual(plugin_assoc.get("rank"), "Alternate")
        self.assertEqual(pkg["build"]["mac"]["target"][0], "dmg")
        self.assertIn("nsis", pkg["build"]["win"]["target"])
        self.assertIn("AppImage", pkg["build"]["linux"]["target"])
        self.assertNotIn("transfer_host", main)

    def test_meta_http_allowlist(self):
        script = r"""
const { allowedRoute } = require('./meta_http');
const cases = [
  ['GET', '/api/builder-core/meta/index', true],
  ['GET', '/api/builder-core/meta/views', true],
  ['GET', '/api/builder-core/meta/boundaries', true],
  ['GET', '/api/builder-core/meta/space', true],
  ['POST', '/api/builder-core/meta/preview', true],
  ['PUT', '/api/builder-core/meta/preview', false],
  ['POST', '/api/builder-core/projects', false],
  ['GET', '/api/builder-core/meta/../secrets', false],
  ['POST', 'http://127.0.0.1/api/builder-core/meta/preview', false],
  ['GET', '/api/builder-core/meta/index?x=1', false],
];
const failed = cases.filter(([m, p, want]) => allowedRoute(m, p) !== want);
if (failed.length) {
  console.error(JSON.stringify(failed));
  process.exit(1);
}
"""
        proc = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT / "desktop"),
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_pack_paths_from_argv(self):
        script = r"""
const path = require('path');
const { isPackPath, packPathsFromArgv } = require('./meta_zip_host');
if (!isPackPath('a.zip') || !isPackPath('b.zintriq-app.zip') || !isPackPath('c.zintriq-app') || !isPackPath('d.zintriq-plugin.json')) process.exit(2);
if (isPackPath('notes.txt') || isPackPath('app.exe')) process.exit(3);
const rows = packPathsFromArgv(['electron', '.', '/tmp/site.zip', 'zintriq://x', '--dev', 'keep.zintriq-app.zip']);
if (rows.length !== 2) { console.error(rows); process.exit(4); }
if (!rows[0].endsWith('site.zip') || !rows[1].endsWith('keep.zintriq-app.zip')) process.exit(5);
"""
        proc = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT / "desktop"),
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class DesktopProcessGuardTests(unittest.TestCase):
    def test_short_token_exits_without_echoing_it(self):
        token = "too-short-token-value"
        self.assertLess(len(token), 32)
        data_dir = Path(tempfile.mkdtemp(prefix="zintriq-short-")) / "data"
        env = os.environ.copy()
        env["ZINTRIQ_DESKTOP"] = "1"
        env["ZINTRIQ_DATA_DIR"] = str(data_dir)
        env["ZINTRIQ_DESKTOP_TOKEN"] = token
        env["PORT"] = "5123"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [str(PYTHON), str(ROOT / "app.py")],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertNotIn(token, combined)
        self.assertIn("32", combined)
        self.assertFalse(data_dir.exists())
        shutil.rmtree(data_dir.parent, ignore_errors=True)

    def test_secret_file_is_owner_only(self):
        data_dir = Path(tempfile.mkdtemp(prefix="zintriq-secret-"))
        token = "s" * 40
        env = os.environ.copy()
        env.pop("SECRET_KEY", None)
        env["ZINTRIQ_DESKTOP"] = "1"
        env["ZINTRIQ_DATA_DIR"] = str(data_dir)
        env["ZINTRIQ_DESKTOP_TOKEN"] = token
        env["PORT"] = "5124"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [
                str(PYTHON),
                "-c",
                "from desktop.server_mode import prepare_desktop_paths; prepare_desktop_paths()",
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.replace(token, "<token>"))
        self.assertNotIn(token, proc.stdout + proc.stderr)
        secret = data_dir / "secret_key"
        self.assertTrue(secret.is_file())
        if os.name == "posix":
            self.assertEqual(data_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(secret.stat().st_mode & 0o777, stat.S_IRUSR | stat.S_IWUSR)
        shutil.rmtree(data_dir, ignore_errors=True)

    def test_special_data_dir_wal_and_uri(self):
        base = Path(tempfile.mkdtemp(prefix="zintriq-path-"))
        # Windows forbids '?' in path components; keep the URI-encoding coverage.
        suffix = "a%b#c_d" if os.name == "nt" else "a%b#c?d"
        data_dir = base / "工作室 数据" / suffix
        token = "p" * 40
        env = os.environ.copy()
        env.pop("SECRET_KEY", None)
        env.pop("DATABASE_URL", None)
        env["ZINTRIQ_DESKTOP"] = "1"
        env["ZINTRIQ_DATA_DIR"] = str(data_dir)
        env["ZINTRIQ_DESKTOP_TOKEN"] = token
        env["PORT"] = "5125"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [str(PYTHON), "-c", _PATH_PROBE],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = (proc.stdout + proc.stderr).replace(token, "<token>")
        self.assertEqual(proc.returncode, 0, combined)
        self.assertIn("PATH_OK", proc.stdout)
        self.assertNotIn(token, proc.stdout + proc.stderr)
        uri_line = next(line for line in proc.stdout.splitlines() if line.startswith("URI="))
        uri = uri_line.split("=", 1)[1]
        self.assertIn("%25", uri)
        self.assertIn("%23", uri)
        if os.name != "nt":
            self.assertIn("%3F", uri)
        self.assertNotIn("#", uri.split("file://", 1)[-1])
        self.assertTrue((data_dir / "zintriq.db").is_file())
        self.assertEqual((data_dir / "uploads" / "note.txt").read_text(encoding="utf-8"), "hello")
        secret = data_dir / "secret_key"
        self.assertTrue(secret.is_file())
        if os.name == "posix":
            self.assertEqual(secret.stat().st_mode & 0o777, stat.S_IRUSR | stat.S_IWUSR)
        shutil.rmtree(base, ignore_errors=True)

    def test_second_process_reports_holder_pid(self):
        token = "k" * 40
        temp = Path(tempfile.mkdtemp(prefix="zintriq-lock-"))
        data_dir = temp / "data"
        log_path = temp / "server.log"
        port = _free_port()
        env = _desktop_env(data_dir, port, token)
        log_handle = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(PYTHON), str(ROOT / "app.py")],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        try:
            pid, ready_port = _wait_for_ready(log_path, proc)
            if os.name != "nt":
                self.assertEqual(pid, proc.pid)
            self.assertTrue(_pid_alive(pid))
            self.assertEqual(ready_port, port)
            pid_text = (data_dir / "zintriq.pid").read_text(encoding="utf-8")
            self.assertRegex(pid_text, rf"(?m)^pid={pid}$")
            self.assertNotIn(token, pid_text)
            self.assertNotIn(token, (data_dir / "zintriq.lock").read_bytes().decode("utf-8", "replace"))
            second_port = _free_port()
            second_env = _desktop_env(data_dir, second_port, token)
            second = subprocess.run(
                [str(PYTHON), str(ROOT / "app.py")],
                cwd=str(ROOT),
                env=second_env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            combined = second.stdout + second.stderr
            self.assertNotEqual(second.returncode, 0)
            self.assertIn(str(pid), combined)
            self.assertNotIn(token, combined)
            status, _pairs, body = _http_get(port, "/healthz", token)
            self.assertEqual(status, 200)
            self.assertIn(b"ok", body)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            if proc.stdin:
                proc.stdin.close()
            log_handle.close()
            shutil.rmtree(temp, ignore_errors=True)

    @unittest.skipIf(
        os.name == "nt",
        "Windows TerminateProcess does not close the child stdin pipe that Flask watches",
    )
    def test_parent_death_releases_data_dir(self):
        token = "q" * 40
        temp = Path(tempfile.mkdtemp(prefix="zintriq-parent-"))
        data_dir = temp / "data"
        log_path = temp / "server.log"
        port = _free_port()
        env = _desktop_env(data_dir, port, token)
        wrapper = subprocess.Popen(
            [str(PYTHON), "-c", _PARENT_WRAPPER, str(log_path), str(ROOT / "app.py"), str(ROOT)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        flask_pid = None
        try:
            line = wrapper.stdout.readline()
            self.assertTrue(line.startswith("PARENT_OK "), wrapper.stderr.read() if wrapper.poll() else line)
            flask_pid = int(line.split("pid=", 1)[1].split()[0])
            self.assertNotEqual(flask_pid, wrapper.pid)
            wrapper.kill()
            wrapper.wait(timeout=5)
            deadline = time.time() + 8
            while time.time() < deadline and _pid_alive(flask_pid):
                time.sleep(0.2)
            self.assertFalse(_pid_alive(flask_pid), "flask kept running after its parent was killed")
            restart_port = _free_port()
            restart_log = temp / "restart.log"
            restart_env = _desktop_env(data_dir, restart_port, token)
            handle = open(restart_log, "w", encoding="utf-8")
            restart = subprocess.Popen(
                [str(PYTHON), str(ROOT / "app.py")],
                cwd=str(ROOT),
                env=restart_env,
                stdin=subprocess.PIPE,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
            try:
                _wait_for_ready(restart_log, restart)
                status, _pairs, body = _http_get(restart_port, "/healthz", token)
                self.assertEqual(status, 200)
                self.assertIn(b"ok", body)
                restart.stdin.close()
                restart.wait(timeout=8)
            finally:
                if restart.poll() is None:
                    restart.kill()
                    restart.wait(timeout=5)
                handle.close()
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait(timeout=5)
            if wrapper.stdout:
                wrapper.stdout.close()
            if wrapper.stderr:
                wrapper.stderr.close()
            if flask_pid and _pid_alive(flask_pid):
                os.kill(flask_pid, 9)
            shutil.rmtree(temp, ignore_errors=True)

    def test_stale_pid_from_dead_process_does_not_block_start(self):
        gone = subprocess.Popen([str(PYTHON), "-c", "pass"])
        gone.wait(timeout=10)
        self._assert_pid_file_does_not_block_start(gone.pid)

    def test_live_unrelated_pid_does_not_block_start(self):
        self._assert_pid_file_does_not_block_start(os.getpid())

    def _assert_pid_file_does_not_block_start(self, stale_pid: int):
        token = "z" * 40
        temp = Path(tempfile.mkdtemp(prefix="zintriq-stale-pid-"))
        data_dir = temp / "data"
        data_dir.mkdir()
        # Stale pid file only — leave the lock free so a new process can acquire it.
        (data_dir / "zintriq.pid").write_text(f"pid={stale_pid}\nport=1\n", encoding="utf-8")
        log_path = temp / "server.log"
        port = _free_port()
        env = _desktop_env(data_dir, port, token)
        handle = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(PYTHON), str(ROOT / "app.py")],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        try:
            ready_pid, ready_port = _wait_for_ready(log_path, proc)
            # On Windows the READY line can name a worker while Popen tracks the
            # launcher pid; require the announced pid to own the port/lock instead.
            if os.name != "nt":
                self.assertEqual(ready_pid, proc.pid)
            self.assertEqual(ready_port, port)
            self.assertNotEqual(ready_pid, stale_pid)
            self.assertTrue(_pid_alive(ready_pid))
            pid_text = (data_dir / "zintriq.pid").read_text(encoding="utf-8")
            self.assertRegex(pid_text, rf"(?m)^pid={ready_pid}$")
            self.assertNotRegex(pid_text, rf"(?m)^pid={stale_pid}$")
            self.assertNotIn(token, pid_text)
            status, _pairs, body = _http_get(port, "/healthz", token)
            self.assertEqual(status, 200)
            self.assertIn(b"ok", body)
            log = log_path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn(token, log)
        finally:
            if proc.poll() is None:
                if proc.stdin:
                    proc.stdin.close()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            handle.close()
            shutil.rmtree(temp, ignore_errors=True)

    def test_log_artifact_guard_rejects_desktop_token(self):
        script = ROOT / "desktop" / "scripts" / "check_log_artifact.py"
        temp = Path(tempfile.mkdtemp(prefix="zintriq-artifact-"))
        try:
            log_dir = temp / "logs"
            log_dir.mkdir()
            token = "t" * 64
            token_file = temp / "token"
            token_file.write_text(token, encoding="utf-8")
            (log_dir / "flask.log").write_text("ready\n", encoding="utf-8")
            env = os.environ.copy()
            env["ZINTRIQ_SMOKE_TOKEN_FILE"] = str(token_file)
            env["ZINTRIQ_SMOKE_LOG_DIR"] = str(log_dir)
            clean = subprocess.run(
                [str(PYTHON), str(script)],
                cwd=str(temp),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertFalse(token_file.exists())
            self.assertNotIn(token, clean.stdout + clean.stderr)

            token_file.write_text(token, encoding="utf-8")
            (log_dir / "flask.log").write_text(f"leaked {token}\n", encoding="utf-8")
            leaked = subprocess.run(
                [str(PYTHON), str(script)],
                cwd=str(temp),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(leaked.returncode, 1)
            self.assertNotIn(token, leaked.stdout + leaked.stderr)
            self.assertIn("flask.log", leaked.stderr)

            token_file.write_text(token, encoding="utf-8")
            (log_dir / "flask.log").write_text("ready\n", encoding="utf-8")
            (log_dir / "secret_key").write_text("nope", encoding="utf-8")
            forbidden = subprocess.run(
                [str(PYTHON), str(script)],
                cwd=str(temp),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(forbidden.returncode, 1)
            self.assertIn("secret_key", forbidden.stderr)
            self.assertNotIn(token, forbidden.stdout + forbidden.stderr)
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def test_stdin_eof_releases_lock(self):
        token = "l" * 40
        temp = Path(tempfile.mkdtemp(prefix="zintriq-lock-eof-"))
        data_dir = temp / "data"
        log_path = temp / "server.log"
        port = _free_port()
        env = _desktop_env(data_dir, port, token)
        handle = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(PYTHON), str(ROOT / "app.py")],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_ready(log_path, proc)
            proc.stdin.close()
            proc.wait(timeout=8)
            self.assertIsNotNone(proc.returncode)
            restart_port = _free_port()
            restart_log = temp / "again.log"
            restart_env = _desktop_env(data_dir, restart_port, token)
            again_handle = open(restart_log, "w", encoding="utf-8")
            again = subprocess.Popen(
                [str(PYTHON), str(ROOT / "app.py")],
                cwd=str(ROOT),
                env=restart_env,
                stdin=subprocess.PIPE,
                stdout=again_handle,
                stderr=subprocess.STDOUT,
            )
            try:
                pid, ready_port = _wait_for_ready(restart_log, again)
                self.assertEqual(ready_port, restart_port)
                if os.name != "nt":
                    self.assertEqual(pid, again.pid)
                self.assertTrue(_pid_alive(pid))
                status, _pairs, body = _http_get(restart_port, "/healthz", token)
                self.assertEqual(status, 200)
                self.assertIn(b"ok", body)
            finally:
                if again.stdin:
                    again.stdin.close()
                if again.poll() is None:
                    again.wait(timeout=8)
                if again.poll() is None:
                    again.kill()
                    again.wait(timeout=5)
                again_handle.close()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            handle.close()
            shutil.rmtree(temp, ignore_errors=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    # On Windows signal 0 is CTRL_C_EVENT — os.kill(pid, 0) interrupts the
    # whole console group (including this unittest). Use tasklist instead.
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        text = (result.stdout or "") + (result.stderr or "")
        if "No tasks" in text or "没有运行" in text:
            return False
        return str(pid) in text
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _desktop_env(data_dir: Path, port: int, token: str) -> dict:
    env = os.environ.copy()
    env["ZINTRIQ_DESKTOP"] = "1"
    env["ZINTRIQ_DATA_DIR"] = str(data_dir)
    env["ZINTRIQ_DESKTOP_TOKEN"] = token
    env["PORT"] = str(port)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("HOST", None)
    return env


def _wait_for_ready(log_path: Path, proc: subprocess.Popen, timeout: float = 90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            raise AssertionError(f"server exited {proc.returncode}: {text[-1500:]}")
        if log_path.is_file():
            text = log_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"^ZINTRIQ_READY pid=(\d+) port=(\d+)$", text, re.M)
            if match:
                return int(match.group(1)), int(match.group(2))
        time.sleep(0.2)
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    raise AssertionError(f"timed out waiting for ZINTRIQ_READY\n{text[-1500:]}")


def _http_get(port: int, path: str, token: str):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.putrequest("GET", path, skip_host=True)
        conn.putheader("Host", f"127.0.0.1:{port}")
        conn.putheader("X-Zintriq-Desktop-Token", token)
        conn.endheaders()
        response = conn.getresponse()
        return response.status, response.getheaders(), response.read()
    finally:
        conn.close()


_PATH_PROBE = r"""
import sqlite3
import threading

from desktop.sqlite_io import open_connection, sqlite_file_uri
from desktop.server_mode import prepare_desktop_paths

paths = prepare_desktop_paths()
conn = open_connection(paths.database)
conn.execute("create table if not exists probe(id integer primary key, v text)")
conn.commit()
mode = conn.execute("pragma journal_mode").fetchone()[0]
timeout = int(conn.execute("pragma busy_timeout").fetchone()[0])
conn.close()
errors = []

def worker(name):
    try:
        local = open_connection(paths.database)
        for i in range(25):
            local.execute("insert into probe(v) values (?)", (name + "-" + str(i),))
            local.commit()
        local.close()
    except Exception as exc:
        errors.append(repr(exc))

threads = [threading.Thread(target=worker, args=(name,)) for name in ("a", "b")]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
if errors:
    raise SystemExit(" | ".join(errors))
(paths.upload_dir / "note.txt").write_text("hello", encoding="utf-8")
uri = sqlite_file_uri(paths.database)
uri_conn = sqlite3.connect(uri, uri=True)
count = uri_conn.execute("select count(*) from probe").fetchone()[0]
uri_conn.close()
if count < 50:
    raise SystemExit("count %s" % count)
if str(mode).lower() != "wal" or timeout < 60000:
    raise SystemExit("pragma %s %s" % (mode, timeout))
print("PATH_OK")
print("URI=" + uri)
"""

_PARENT_WRAPPER = r"""
import os
import re
import subprocess
import sys
import time

log_path, app_path, cwd = sys.argv[1], sys.argv[2], sys.argv[3]
log = open(log_path, "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, app_path],
    cwd=cwd,
    env=os.environ.copy(),
    stdin=subprocess.PIPE,
    stdout=log,
    stderr=subprocess.STDOUT,
)
deadline = time.time() + 90
while time.time() < deadline:
    log.flush()
    try:
        text = open(log_path, encoding="utf-8").read()
    except OSError:
        text = ""
    match = re.search(r"ZINTRIQ_READY pid=(\d+) port=(\d+)", text)
    if match:
        sys.stdout.write("PARENT_OK pid=%s port=%s\n" % (match.group(1), match.group(2)))
        sys.stdout.flush()
        while True:
            time.sleep(30)
    if proc.poll() is not None:
        sys.stderr.write(text[-1000:])
        raise SystemExit(2)
    time.sleep(0.2)
raise SystemExit(3)
"""


if __name__ == "__main__":
    unittest.main()
