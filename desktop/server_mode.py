"""Local desktop mode for the Flask process.

Enabled only when ZINTRIQ_DESKTOP=1. Web mode does not call these gates.

Runtime database and upload paths:
- app.DATABASE / app.UPLOAD_DIR are replaced at import when this mode is on,
  before other modules bind UPLOAD_DIR (task_platform registers later).
- app._open_db_connection uses sqlite3 against app.DATABASE
  and does not follow DATABASE_URL.
- observability.health readyz opens app.DATABASE at request time.
Scripts that open marketqr.db themselves are not the desktop server.
"""

from __future__ import annotations

import hmac
import os
import secrets
import stat
import subprocess
import sys
import threading
from pathlib import Path
from typing import NamedTuple, Optional

TOKEN_HEADER = "X-Zintriq-Desktop-Token"
MIN_TOKEN_LENGTH = 32
LOCAL_EMAIL = "local@desktop.zintriq"
DB_FILENAME = "zintriq.db"
SECRET_FILENAME = "secret_key"
DESKTOP_SCHEMA_VERSION = 2
# 40 MiB: larger than the 32 MiB project package cap.
WAITRESS_MAX_REQUEST_BODY = 40 * 1024 * 1024
WAITRESS_IDENT = ""

# Flask rule strings. The test walks url_map and requires every auth-shaped
# rule to be in this set, then requests each one on the desktop server.
_WORK_ACCOUNT_AUTH = tuple(
    f"{prefix}{suffix}"
    for prefix in ("/store/<work_slug>/account", "/build/<work_slug>/account")
    for suffix in (
        "/register",
        "/login",
        "/logout",
        "/forgot-password",
        "/reset-password/<token>",
        "/magic-link",
        "/magic-signin/<token>",
        "/verify/send",
        "/verify/check",
        "/link-email/send",
        "/link-email/check",
        "/onboarding/complete",
    )
)

AUTH_RULES = frozenset(
    {
        "/register",
        "/login",
        "/login/2fa",
        "/logout",
        "/forgot-password",
        "/reset-password/<token>",
        "/magic-link",
        "/magic-signin/<token>",
        "/auth/phone/send",
        "/auth/phone/check",
        "/auth/phone/complete",
        "/account/2fa",
        "/account/2fa/disable",
        "/account/change-password",
        "/account/delete",
        "/account/delete/cancel",
        "/guest/remember/<token>",
        "/places/remember",
        "/studio/desktop",
        "/api/studio/auth/pkce/exchange",
        "/api/studio/tokens",
        "/api/studio/tokens/<int:token_id>",
        "/api/integrations/payments/<provider>/oauth/start",
        "/api/integrations/payments/<provider>/oauth/callback",
        "/api/integrations/reputation/<provider>/oauth/start",
        "/api/integrations/reputation/<provider>/oauth/callback",
    }
    | set(_WORK_ACCOUNT_AUTH)
)

_AUTH_HINT = (
    "/login",
    "/register",
    "/logout",
    "forgot-password",
    "reset-password",
    "magic-link",
    "magic-signin",
    "/oauth/",
    "/auth/",
    "pkce",
    "/2fa",
    "change-password",
    "link-email",
    "/account/verify/",
    "onboarding/complete",
    "/guest/remember",
    "/places/remember",
    "/studio/desktop",
)


class DesktopPaths(NamedTuple):
    data_dir: Path
    database: Path
    upload_dir: Path
    secret_key: str


def desktop_enabled() -> bool:
    return (os.environ.get("ZINTRIQ_DESKTOP") or "").strip() == "1"


def is_production_env() -> bool:
    raw = (os.environ.get("ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
    return raw in {"production", "prod"}


def is_loopback_bind(host: str) -> bool:
    value = (host or "").strip().lower()
    if value.startswith("["):
        end = value.find("]")
        value = value[1:end] if end > 1 else value
    elif value.count(":") == 1:
        value = value.split(":", 1)[0]
    return value in {"127.0.0.1", "localhost", "::1"}


def assert_production_desktop_bind() -> None:
    """Production must not boot the desktop server on a public address."""
    if not desktop_enabled() or not is_production_env():
        return
    host = (os.environ.get("HOST") or "0.0.0.0").strip()
    if not is_loopback_bind(host):
        _fail("Refusing to start: ZINTRIQ_DESKTOP=1 with a non-loopback bind address in production.")


def remote_is_loopback(addr: str) -> bool:
    value = (addr or "").strip().lower()
    if value.startswith("::ffff:"):
        value = value[7:]
    return value in {"127.0.0.1", "::1"}


def _fail(message: str) -> None:
    """Exit without echoing secrets. Callers must pass a fixed message."""
    print(message, file=sys.stderr)
    raise SystemExit(1)


def listen_port() -> int:
    raw = (os.environ.get("PORT") or "5001").strip()
    if not raw.isdigit():
        _fail("PORT must be an integer between 1 and 65535.")
    port = int(raw)
    if port < 1 or port > 65535:
        _fail("PORT must be an integer between 1 and 65535.")
    return port


def listen_host() -> str:
    if desktop_enabled():
        return "127.0.0.1"
    return os.environ.get("HOST", "0.0.0.0")


def host_allowed(host_header: str, port: int) -> bool:
    return (host_header or "").strip().lower() in {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
    }


def tokens_match(presented: str, expected: str) -> bool:
    if len(expected) < MIN_TOKEN_LENGTH or len(presented) < MIN_TOKEN_LENGTH:
        return False
    return hmac.compare_digest(presented, expected)


def rule_is_auth(rule: str) -> bool:
    return rule in AUTH_RULES


def rule_looks_like_auth(rule: str) -> bool:
    return any(hint in rule for hint in _AUTH_HINT)


def concrete_path(rule: str) -> str:
    import re

    path = re.sub(r"<int:[^>]+>", "1", rule)
    path = re.sub(r"<[^>]+>", "sample", path)
    return path


def _restrict_owner(path: Path, *, directory: bool) -> None:
    mode = 0o700 if directory else 0o600
    if os.name == "posix":
        os.chmod(path, mode)
        return
    if os.name != "nt":
        return
    username = os.environ.get("USERNAME") or ""
    if not username:
        return
    grant = f"{username}:(OI)(CI)F" if directory else f"{username}:F"
    # Frozen builds must never spawn sys.executable (that would relaunch this app).
    subprocess.run(
        ["icacls", os.fspath(path), "/inheritance:r", "/grant:r", grant],
        check=False,
        capture_output=True,
    )


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _restrict_owner(path, directory=True)


def _write_private(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            fd = -1
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    _restrict_owner(path, directory=False)


def _secret_key(data_dir: Path) -> str:
    env_key = (os.environ.get("SECRET_KEY") or "").strip()
    if env_key:
        return env_key
    path = data_dir / SECRET_FILENAME
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    _write_private(path, secrets.token_hex(32))
    return path.read_text(encoding="utf-8").strip()


def prepare_desktop_paths() -> Optional[DesktopPaths]:
    """Validate desktop env and return paths. Exit if the token or data dir is unusable."""
    if not desktop_enabled():
        return None
    assert_production_desktop_bind()
    # .env.local may set a cloud DATABASE_URL. Desktop mode always uses the SQLite file.
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("DATABASE_IAM_AUTH", None)
    token = os.environ.get("ZINTRIQ_DESKTOP_TOKEN") or ""
    if len(token) < MIN_TOKEN_LENGTH:
        _fail("ZINTRIQ_DESKTOP_TOKEN must be at least 32 characters.")
    raw_dir = (os.environ.get("ZINTRIQ_DATA_DIR") or "").strip()
    if not raw_dir:
        _fail("ZINTRIQ_DATA_DIR is required when ZINTRIQ_DESKTOP=1.")
    # Reject a non-numeric PORT before creating directories.
    listen_port()
    data_dir = Path(raw_dir)
    _mkdir_private(data_dir)
    upload_dir = data_dir / "uploads"
    _mkdir_private(upload_dir)
    return DesktopPaths(
        data_dir=data_dir,
        database=data_dir / DB_FILENAME,
        upload_dir=upload_dir,
        secret_key=_secret_key(data_dir),
    )


def matched_rule(app, path: str, method: str) -> Optional[str]:
    from werkzeug.exceptions import MethodNotAllowed, NotFound

    adapter = app.url_map.bind("127.0.0.1")
    methods = [method] + [item for item in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS") if item != method]
    found = []
    for candidate in methods:
        try:
            rule, _args = adapter.match(path, method=candidate, return_rule=True)
            found.append(rule.rule)
        except (MethodNotAllowed, NotFound):
            continue
    for rule in found:
        if rule_is_auth(rule):
            return rule
    return found[0] if found else None


def ensure_local_owner(conn) -> tuple:
    """Create the single local user and owner workspace. Does not log identifiers."""
    from werkzeug.security import generate_password_hash

    from bos.services.organization import ensure_default_organization
    from bos.services.workspace import ensure_default_workspace

    row = conn.execute("SELECT id FROM users WHERE email = ?", (LOCAL_EMAIL,)).fetchone()
    if row:
        user_id = int(row["id"])
    else:
        cursor = conn.execute(
            """INSERT INTO users (email, password_hash, account_kind)
               VALUES (?, ?, 'merchant')""",
            (LOCAL_EMAIL, generate_password_hash(secrets.token_urlsafe(32), method="pbkdf2:sha256:600000")),
        )
        user_id = int(cursor.lastrowid)
    ensure_default_organization(conn, user_id)
    workspace = ensure_default_workspace(conn, user_id)
    workspace_id = int(workspace["id"])
    member = conn.execute(
        "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
        (workspace_id, user_id),
    ).fetchone()
    if not member:
        conn.execute(
            """INSERT INTO workspace_members (workspace_id, user_id, role, status, joined_at)
               VALUES (?, ?, 'owner', 'active', CURRENT_TIMESTAMP)""",
            (workspace_id, user_id),
        )
    elif member["role"] != "owner":
        conn.execute(
            "UPDATE workspace_members SET role='owner', status='active' WHERE workspace_id=? AND user_id=?",
            (workspace_id, user_id),
        )
    return user_id, workspace_id


def install_desktop_guards(app) -> None:
    from flask import redirect, request, session

    @app.before_request
    def _desktop_guard():
        if not desktop_enabled():
            return None
        port = listen_port()
        raw_host = (request.environ.get("HTTP_HOST") or "").strip()
        if not remote_is_loopback(request.remote_addr or ""):
            return _bad_host()
        if not host_allowed(raw_host, port):
            return _bad_host()
        presented = request.headers.get(TOKEN_HEADER) or ""
        expected = os.environ.get("ZINTRIQ_DESKTOP_TOKEN") or ""
        if not tokens_match(presented, expected):
            return _unauthorized()
        if request.path == "/sw.js":
            return app.response_class("", status=404, mimetype="text/plain")
        if request.path in {"/app/settings", "/app/team", "/app/workspaces"}:
            return redirect("/account/workspaces")
        rule = matched_rule(app, request.path, request.method)
        if rule_is_auth(rule or ""):
            return redirect("/studio")
        _attach_local_session(session)
        return None

    @app.after_request
    def _strip_cors(response):
        if not desktop_enabled():
            return response
        names = list(response.headers.keys())
        for key in names:
            if str(key).lower().startswith("access-control-"):
                del response.headers[key]
        return response


def _unauthorized():
    from flask import jsonify

    response = jsonify({"error": "unauthorized"})
    response.status_code = 401
    return response


def _bad_host():
    from flask import jsonify

    response = jsonify({"error": "bad host"})
    response.status_code = 400
    return response


_INSTANCE_LOCK_FD: Optional[int] = None
_PARENT_WATCH_STARTED = False


def _read_instance_info(pid_path: Path) -> tuple:
    try:
        text = pid_path.read_text(encoding="utf-8")
    except OSError:
        return "", ""
    pid = ""
    port = ""
    for line in text.splitlines():
        if line.startswith("pid="):
            pid = line.split("=", 1)[1].strip()
        elif line.startswith("port="):
            port = line.split("=", 1)[1].strip()
    if not pid.isdigit():
        return "", ""
    return pid, port


def _try_lock(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def acquire_instance_lock(data_dir: Path, port: int) -> None:
    """Hold an exclusive lock for this data directory until the process exits.

    Only the first byte is locked. pid and port are written to zintriq.pid,
    outside that byte, so a second process can still read them on Windows.
    The token is never written.
    """
    global _INSTANCE_LOCK_FD
    if _INSTANCE_LOCK_FD is not None:
        return
    data_dir = Path(data_dir)
    lock_path = data_dir / "zintriq.lock"
    pid_path = data_dir / "zintriq.pid"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.fstat(fd).st_size < 1:
            os.write(fd, b"\0")
        _try_lock(fd)
    except OSError:
        os.close(fd)
        pid, held_port = _read_instance_info(pid_path)
        if pid and held_port:
            _fail(f"此数据目录已有 Zintriq 桌面进程在运行 (pid {pid}, port {held_port})。请先关闭已打开的窗口。")
        if pid:
            _fail(f"此数据目录已有 Zintriq 桌面进程在运行 (pid {pid})。请先关闭已打开的窗口。")
        _fail("此数据目录已有 Zintriq 桌面进程在运行。请先关闭已打开的窗口。")
    _INSTANCE_LOCK_FD = fd
    _write_private(pid_path, f"pid={os.getpid()}\nport={port}\n")


def start_parent_watch() -> None:
    """Exit when stdin hits EOF so a dead parent releases the data-dir lock."""
    global _PARENT_WATCH_STARTED
    if _PARENT_WATCH_STARTED:
        return
    _PARENT_WATCH_STARTED = True

    def _watch() -> None:
        try:
            while True:
                chunk = sys.stdin.buffer.read(4096)
                if not chunk:
                    _shutdown_server()
                    return
        except Exception:
            _shutdown_server()

    threading.Thread(target=_watch, name="zintriq-parent-watch", daemon=True).start()


_DESKTOP_SERVER = None


def release_instance_lock() -> None:
    global _INSTANCE_LOCK_FD
    fd = _INSTANCE_LOCK_FD
    _INSTANCE_LOCK_FD = None
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _shutdown_server() -> None:
    server = _DESKTOP_SERVER
    if server is not None:
        try:
            server.close()
        except Exception:
            pass
    release_instance_lock()
    timer = threading.Timer(3.0, lambda: os._exit(0))
    timer.daemon = True
    timer.start()


def serve_desktop(flask_app) -> None:
    """Listen on 127.0.0.1 with waitress and announce readiness on stdout."""
    global _DESKTOP_SERVER
    from waitress.server import create_server

    port = listen_port()
    server = create_server(
        flask_app,
        host="127.0.0.1",
        port=port,
        threads=8,
        ident=WAITRESS_IDENT,
        expose_tracebacks=False,
        clear_untrusted_proxy_headers=True,
        max_request_body_size=WAITRESS_MAX_REQUEST_BODY,
        channel_timeout=30,
    )
    _DESKTOP_SERVER = server
    sys.stdout.write(f"ZINTRIQ_READY pid={os.getpid()} port={port}\n")
    sys.stdout.flush()
    try:
        server.run()
    finally:
        try:
            server.close()
        except Exception:
            pass
        release_instance_lock()


def ensure_desktop_schema(database: Path) -> None:
    """Refuse a newer database; stamp or migrate an older one after init_db."""
    import sqlite3

    path = Path(database)
    if not path.is_file():
        return
    conn = sqlite3.connect(path)
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()
    if version > DESKTOP_SCHEMA_VERSION:
        _fail("这个数据目录是用更新的 Zintriq 创建的，请升级应用后再打开。")


def stamp_desktop_schema(database: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(database)
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > DESKTOP_SCHEMA_VERSION:
            _fail("这个数据目录是用更新的 Zintriq 创建的，请升级应用后再打开。")
        if version < DESKTOP_SCHEMA_VERSION:
            from builder_kernel.events import migrate_kernel_events

            migrate_kernel_events(conn)
            conn.execute(f"PRAGMA user_version={DESKTOP_SCHEMA_VERSION}")
            conn.commit()
    finally:
        conn.close()


def _attach_local_session(session) -> None:
    from app import db

    with db() as conn:
        user_id, workspace_id = ensure_local_owner(conn)
    session["user_id"] = user_id
    session["active_workspace_id"] = workspace_id
    session.modified = True
