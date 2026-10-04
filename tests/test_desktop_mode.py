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
        output = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{self.port}", "-sTCP:LISTEN"],
            text=True,
            errors="replace",
        )
        self.assertIn(f"127.0.0.1:{self.port}", output)
        self.assertNotIn(f"*:{self.port}", output)
        self.assertNotIn(f"0.0.0.0:{self.port}", output)
        for family, _, _, _, address in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
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
        for path in ("/studio", "/app/community", "/account/workspaces"):
            status, _pairs, body = self._exchange("GET", path)
            self.assertEqual(status, 200, f"{path} {self._scrub(body.decode('utf-8', 'replace')[:240])}")
        community = self._exchange("GET", "/app/community")[2].decode("utf-8", "replace")
        main = community.split("<main", 1)[1].split("</main>", 1)[0]
        self.assertNotIn("page.community", main)
        self.assertNotRegex(
            main,
            r"(?<![A-Za-z0-9_-])(?:community|item|share|profile)\.[a-z0-9_.]+",
        )
        self.assertIn("Templates and projects", main)
        status, _pairs, body = self._exchange("GET", "/app/settings")
        self.assertIn(status, (302, 303))
        editor_js = self._exchange("GET", "/static/builder/universal-builder.js")
        self.assertEqual(editor_js[0], 200)
        status, pairs, body = self._exchange("GET", "/studio")
        self.assertEqual(status, 200)
        match = re.search(r'csrf-token" content="([^"]+)"', body.decode("utf-8", "replace"))
        self.assertIsNotNone(match)
        csrf = match.group(1)
        cookie = "; ".join(
            value.split(";", 1)[0] for key, value in pairs if key.lower() == "set-cookie"
        )
        created = self._exchange(
            "POST",
            "/api/builder-core/projects",
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
                "Cookie": cookie,
            },
            body=json.dumps({"name": "Editor smoke", "csrf_token": csrf}).encode(),
        )
        self.assertIn(created[0], (200, 201), self._scrub(created[2].decode("utf-8", "replace")[:300]))
        payload = json.loads(created[2].decode("utf-8"))
        project_id = payload.get("id") or payload.get("project", {}).get("id")
        self.assertTrue(project_id)
        status, _pairs, body = self._exchange("GET", f"/studio/p/{project_id}")
        text = body.decode("utf-8", "replace")
        self.assertEqual(status, 200, self._scrub(text[:300]))
        self.assertIn("universal-builder.js", text)

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
        payload = json.dumps({"name": "Desktop smoke", "csrf_token": csrf}).encode()
        status, _pairs, body = self._exchange(
            "POST",
            "/api/builder-core/projects",
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
        if os.name == "posix":
            self.assertEqual(self.data_dir.stat().st_mode & 0o777, 0o700)
        conn = sqlite3.connect(database)
        try:
            row = conn.execute(
                "SELECT name FROM builder_projects WHERE name = ?",
                ("Desktop smoke",),
            ).fetchone()
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
        self.assertIsNotNone(row)
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
        self.assertEqual(runtime.status_code, 200)

    def test_web_does_not_provide_studio(self):
        if os.environ.get("ZINTRIQ_DESKTOP") == "1":
            self.skipTest("parent environment enables desktop mode")
        import app as app_module

        client = app_module.app.test_client()
        for path in ("/studio", "/studio/", "/studio/p/1"):
            response = client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 404, path)
            self.assertNotIn("/login", response.headers.get("Location") or "")


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
