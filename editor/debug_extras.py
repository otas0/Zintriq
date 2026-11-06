"""Coverage, profiling, postmortem, reverse-debug helpers, test-debug launchers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_LOCK = threading.Lock()
_COVERAGE: dict[str, dict[str, Any]] = {}  # path -> {hits, misses, branches}
_PROFILES: dict[str, dict[str, Any]] = {}
_RR_AVAILABLE: bool | None = None


def rr_available() -> bool:
    global _RR_AVAILABLE
    if _RR_AVAILABLE is None:
        _RR_AVAILABLE = bool(shutil.which("rr"))
    return _RR_AVAILABLE


def reverse_capabilities() -> dict[str, Any]:
    return {
        "rr": rr_available(),
        "hint": None
        if rr_available()
        else "Install Mozilla rr for true reverse execution; otherwise Step Back uses timeline snapshots.",
        "modes": ["timeline", "dap-stepBack", "rr"] if rr_available() else ["timeline", "dap-stepBack"],
    }


def rr_trace_dir(workspace: Path) -> Path:
    d = workspace.resolve() / ".zintriq" / "rr"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rr_record(
    workspace: Path,
    program: str,
    args: list[str] | None = None,
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Record a program under `rr record`. Returns {ok, traceDir, latest}."""
    if not rr_available():
        raise RuntimeError("rr not found on PATH")
    target = (workspace / program).resolve() if not Path(program).is_absolute() else Path(program)
    if not target.is_file():
        raise FileNotFoundError(program)
    out = rr_trace_dir(workspace) / f"trace-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["rr", "record", "-o", str(out), str(target), *[str(a) for a in (args or [])]]
    proc = subprocess.run(
        cmd,
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "RR_TRACE_DIR": str(out)},
    )
    latest = out
    # rr may nest under out/<binary>/
    nested = list(out.glob("*"))
    if nested:
        latest = nested[0] if nested[0].is_dir() else out
    return {
        "ok": proc.returncode == 0,
        "traceDir": str(out.relative_to(workspace.resolve())).replace("\\", "/"),
        "latest": str(latest),
        "code": proc.returncode,
        "stderr": (proc.stderr or "")[-2000:],
        "stdout": (proc.stdout or "")[-1000:],
    }


def rr_replay_gdb_server(
    workspace: Path,
    trace: str,
    *,
    port: int = 1234,
) -> dict[str, Any]:
    """Start `rr replay -s <port>` in background. Returns {ok, port, pid, cmd}."""
    if not rr_available():
        raise RuntimeError("rr not found on PATH")
    trace_path = Path(trace)
    if not trace_path.is_absolute():
        trace_path = (workspace / trace).resolve()
    if not trace_path.exists():
        raise FileNotFoundError(trace)
    cmd = ["rr", "replay", "-s", str(int(port)), str(trace_path)]
    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ},
    )
    time.sleep(0.4)
    if proc.poll() is not None:
        err = ""
        try:
            err = (proc.stderr.read() if proc.stderr else "") or ""
        except Exception:
            pass
        raise RuntimeError(f"rr replay failed: {err[:500]}")
    return {
        "ok": True,
        "port": int(port),
        "pid": proc.pid,
        "cmd": cmd,
        "trace": str(trace_path),
        "proc": proc,
    }


def set_coverage_file(
    path: str,
    *,
    hits: list[int] | None = None,
    misses: list[int] | None = None,
    branches: list[dict[str, Any]] | None = None,
) -> None:
    with _LOCK:
        _COVERAGE[path.replace("\\", "/")] = {
            "hits": sorted({int(x) for x in (hits or []) if int(x) > 0}),
            "misses": sorted({int(x) for x in (misses or []) if int(x) > 0}),
            "branches": list(branches or []),
        }


def set_coverage(path: str, lines: list[int]) -> None:
    """Backward-compatible: set hits only."""
    set_coverage_file(path, hits=lines)


def clear_coverage() -> None:
    with _LOCK:
        _COVERAGE.clear()


def get_coverage() -> dict[str, Any]:
    with _LOCK:
        return {"ok": True, "files": {k: dict(v) for k, v in _COVERAGE.items()}}


def run_python_coverage(workspace: Path, program: str, args: list[str] | None = None) -> dict[str, Any]:
    """Run program under coverage.py; collect hits, misses, and branch arcs."""
    try:
        import coverage  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pip install coverage") from exc
    clear_coverage()
    target = (workspace / program).resolve() if not Path(program).is_absolute() else Path(program)
    if not target.is_file():
        raise FileNotFoundError(program)
    cov = coverage.Coverage(source=[str(workspace)], data_file=None, branch=True)
    cov.start()
    ns: dict[str, Any] = {"__name__": "__main__", "__file__": str(target)}
    code = compile(target.read_text(encoding="utf-8"), str(target), "exec")
    try:
        old_argv = sys.argv[:]
        sys.argv = [str(target), *[str(a) for a in (args or [])]]
        try:
            exec(code, ns)  # noqa: S102
        except SystemExit:
            pass
        finally:
            sys.argv = old_argv
    finally:
        cov.stop()
    files: dict[str, Any] = {}
    for measured in cov.get_data().measured_files():
        try:
            rel = str(Path(measured).resolve().relative_to(workspace.resolve())).replace("\\", "/")
        except Exception:
            continue
        try:
            analysis = cov.analysis2(measured)
            # analysis2: (filename, statements, excluded, missing, missing_formatted)
            statements = set(analysis[1] or [])
            missing = set(analysis[3] or [])
            hits = sorted(statements - missing)
            misses = sorted(missing)
        except Exception:
            hits = sorted(cov.get_data().lines(measured) or [])
            misses = []
            statements = set(hits)
        branches: list[dict[str, Any]] = []
        try:
            # missing_branch_arcs: dict line -> [arcs]
            mba = cov.get_data().missing_branch_arcs()
            arcs_for = mba.get(measured) or {}
            for ln, dests in arcs_for.items():
                branches.append(
                    {
                        "line": int(ln),
                        "taken": 0,
                        "total": max(1, len(dests) if dests else 1),
                        "partial": True,
                    }
                )
        except Exception:
            pass
        files[rel] = {"hits": hits, "misses": misses, "branches": branches}
        set_coverage_file(rel, hits=hits, misses=misses, branches=branches)
    return {"ok": True, "files": files, "engine": "coverage.py", "branch": True}


def run_node_coverage(workspace: Path, program: str) -> dict[str, Any]:
    """Best-effort: run node with NODE_V8_COVERAGE; hits + misses from ranges."""
    clear_coverage()
    target = (workspace / program).resolve() if not Path(program).is_absolute() else Path(program)
    if not target.is_file():
        raise FileNotFoundError(program)
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found")
    with tempfile.TemporaryDirectory(prefix="zintriq-cov-") as tmp:
        env = {**os.environ, "NODE_V8_COVERAGE": tmp}
        subprocess.run([node, str(target)], cwd=str(workspace), env=env, capture_output=True, timeout=60)
        files: dict[str, Any] = {}
        for p in Path(tmp).glob("*.json"):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for res in payload.get("result") or []:
                url = str(res.get("url") or "")
                if not url.startswith("file://"):
                    continue
                fpath = Path(urlparse(url).path)
                try:
                    rel = str(fpath.resolve().relative_to(workspace.resolve())).replace("\\", "/")
                except Exception:
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                hits: set[int] = set()
                seen: set[int] = set()
                branches: list[dict[str, Any]] = []
                for fn in res.get("functions") or []:
                    for r in fn.get("ranges") or []:
                        start = int(r.get("startOffset") or 0)
                        line = text.count("\n", 0, start) + 1
                        seen.add(line)
                        count = int(r.get("count") or 0)
                        if count > 0:
                            hits.add(line)
                        else:
                            branches.append({"line": line, "taken": 0, "total": 1, "partial": True})
                misses = sorted(seen - hits)
                if hits or misses:
                    files[rel] = {
                        "hits": sorted(hits),
                        "misses": misses,
                        "branches": branches[:200],
                    }
                    set_coverage_file(
                        rel, hits=sorted(hits), misses=misses, branches=branches[:200]
                    )
        return {"ok": True, "files": files, "engine": "NODE_V8_COVERAGE", "branch": True}


def flame_from_cdp_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Convert CDP Profiler.stop profile into a flame-friendly tree."""
    nodes = {int(n["id"]): n for n in (profile.get("nodes") or []) if "id" in n}
    samples = [int(x) for x in (profile.get("samples") or [])]
    counts: dict[int, int] = {}
    for s in samples:
        counts[s] = counts.get(s, 0) + 1
    if not counts and nodes:
        for nid, n in nodes.items():
            counts[nid] = int(n.get("hitCount") or 1)

    def label(n: dict[str, Any]) -> str:
        cf = n.get("callFrame") or {}
        name = cf.get("functionName") or "(anonymous)"
        url = str(cf.get("url") or "")
        line = cf.get("lineNumber")
        short = url.rsplit("/", 1)[-1] if url else ""
        if short and line is not None:
            return f"{name} @ {short}:{int(line) + 1}"
        return str(name)

    # Build parent map from children arrays
    parent: dict[int, int | None] = {nid: None for nid in nodes}
    for nid, n in nodes.items():
        for c in n.get("children") or []:
            parent[int(c)] = nid

    # Aggregate self time up the stack into exclusive + inclusive
    self_t = {nid: counts.get(nid, 0) for nid in nodes}
    incl: dict[int, int] = dict(self_t)

    def walk_incl(nid: int) -> int:
        n = nodes[nid]
        total = self_t.get(nid, 0)
        for c in n.get("children") or []:
            total += walk_incl(int(c))
        incl[nid] = total
        return total

    roots = [nid for nid, p in parent.items() if p is None]
    for r in roots:
        walk_incl(r)

    def to_node(nid: int) -> dict[str, Any]:
        n = nodes[nid]
        kids = [to_node(int(c)) for c in (n.get("children") or []) if int(c) in nodes]
        kids.sort(key=lambda x: -int(x.get("value") or 0))
        return {
            "name": label(n),
            "value": incl.get(nid, 0),
            "self": self_t.get(nid, 0),
            "children": kids,
        }

    tree = {
        "name": "root",
        "value": sum(incl.get(r, 0) for r in roots) or sum(self_t.values()),
        "self": 0,
        "children": [to_node(r) for r in roots],
    }
    return {"ok": True, "flame": tree, "sampleCount": sum(self_t.values())}


def flame_from_pstats_text(text: str) -> dict[str, Any]:
    """Best-effort parse of pstats print_stats output into a flat flame list."""
    children: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        # e.g. "   12    0.001    0.000    0.010    0.001 filename:line(func)"
        m = re.match(
            r"\s*(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(.+)$",
            line,
        )
        if not m:
            continue
        try:
            tottime = float(m.group(4))
        except ValueError:
            continue
        name = m.group(6).strip()
        if name.startswith("ncalls") or name.startswith("---"):
            continue
        children.append({"name": name, "value": max(1, int(tottime * 10000)), "self": 0, "children": []})
    children.sort(key=lambda x: -int(x["value"]))
    total = sum(int(c["value"]) for c in children) or 1
    return {
        "ok": True,
        "flame": {"name": "root", "value": total, "self": 0, "children": children[:80]},
        "sampleCount": total,
    }


def store_profile(session_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    pid = uuid.uuid4().hex[:8]
    # Attach flame tree when possible
    flame = None
    if isinstance(payload.get("flame"), dict):
        flame = payload["flame"]
    elif isinstance(payload.get("profile"), dict):
        try:
            flame = flame_from_cdp_profile(payload["profile"]).get("flame")
        except Exception:
            flame = None
    elif payload.get("text"):
        try:
            flame = flame_from_pstats_text(str(payload["text"])).get("flame")
        except Exception:
            flame = None
    timeline = None
    if kind in {"allocation", "alloc"} and isinstance(payload.get("profile"), dict):
        try:
            timeline = allocation_timeline_from_profile(payload["profile"])
        except Exception:
            timeline = None
    with _LOCK:
        _PROFILES[pid] = {
            "id": pid,
            "sessionId": session_id,
            "kind": kind,
            "ts": time.time(),
            "payload": payload,
            "flame": flame,
            "timeline": timeline,
        }
        if len(_PROFILES) > 20:
            for k in list(_PROFILES)[: len(_PROFILES) - 20]:
                _PROFILES.pop(k, None)
    return {
        "ok": True,
        "id": pid,
        "kind": kind,
        "hasFlame": flame is not None,
        "hasTimeline": bool(timeline),
    }


def list_profiles() -> list[dict[str, Any]]:
    with _LOCK:
        return [
            {
                "id": v["id"],
                "sessionId": v["sessionId"],
                "kind": v["kind"],
                "ts": v["ts"],
                "hasFlame": bool(v.get("flame")),
            }
            for v in _PROFILES.values()
        ]


def get_profile(pid: str) -> dict[str, Any]:
    with _LOCK:
        item = _PROFILES.get(pid)
    if not item:
        raise KeyError("unknown profile")
    return {"ok": True, **item}


def flame_to_speedscope(flame: dict[str, Any], *, name: str = "profile") -> dict[str, Any]:
    """Convert our flame tree to Speedscope file format (evented)."""
    frames: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    t = 0

    def walk(node: dict[str, Any]) -> None:
        nonlocal t
        idx = len(frames)
        frames.append({"name": str(node.get("name") or "?")})
        events.append({"type": "O", "frame": idx, "at": t})
        kids = list(node.get("children") or [])
        if not kids:
            t += max(1, int(node.get("self") or node.get("value") or 1))
        else:
            for ch in kids:
                walk(ch)
        events.append({"type": "C", "frame": idx, "at": t})

    root = flame if flame.get("name") == "root" else {"name": "root", "children": [flame], "value": flame.get("value")}
    for ch in root.get("children") or [root]:
        walk(ch)
    return {
        "$schema": "https://www.speedscope.app/file-format-schema.json",
        "shared": {"frames": frames},
        "profiles": [
            {
                "type": "evented",
                "name": name,
                "unit": "none",
                "startValue": 0,
                "endValue": t,
                "events": events,
            }
        ],
        "activeProfileIndex": 0,
        "exporter": "zintriq",
        "name": name,
    }


def export_speedscope(pid: str) -> dict[str, Any]:
    item = get_profile(pid)
    flame = item.get("flame")
    if not flame:
        raise ValueError("profile has no flame data")
    doc = flame_to_speedscope(flame, name=f"{item.get('kind')}-{pid}")
    return {"ok": True, "id": pid, "speedscope": doc}


_COVERAGE_TIP: dict[str, Any] | None = None


def coverage_summary() -> dict[str, Any]:
    with _LOCK:
        files = {k: dict(v) for k, v in _COVERAGE.items()}
    rows = []
    total_h = total_m = 0
    for path, info in sorted(files.items()):
        hits = len(info.get("hits") or [])
        misses = len(info.get("misses") or [])
        denom = hits + misses
        pct = round(100.0 * hits / denom, 1) if denom else 100.0
        total_h += hits
        total_m += misses
        rows.append(
            {
                "path": path,
                "hits": hits,
                "misses": misses,
                "branches": len(info.get("branches") or []),
                "pct": pct,
            }
        )
    denom = total_h + total_m
    return {
        "ok": True,
        "files": rows,
        "totals": {
            "hits": total_h,
            "misses": total_m,
            "pct": round(100.0 * total_h / denom, 1) if denom else 100.0,
        },
        "hasTip": _COVERAGE_TIP is not None,
    }


def save_coverage_tip() -> dict[str, Any]:
    global _COVERAGE_TIP
    with _LOCK:
        _COVERAGE_TIP = {k: dict(v) for k, v in _COVERAGE.items()}
    return {"ok": True, "files": len(_COVERAGE_TIP)}


def coverage_diff_tip() -> dict[str, Any]:
    if _COVERAGE_TIP is None:
        raise RuntimeError("no coverage tip saved — call save tip first")
    with _LOCK:
        cur = {k: dict(v) for k, v in _COVERAGE.items()}
    paths = sorted(set(cur) | set(_COVERAGE_TIP))
    diffs = []
    for p in paths:
        a = set((_COVERAGE_TIP.get(p) or {}).get("hits") or [])
        b = set((cur.get(p) or {}).get("hits") or [])
        gained = sorted(b - a)
        lost = sorted(a - b)
        if gained or lost or p not in cur or p not in _COVERAGE_TIP:
            diffs.append({"path": p, "gained": gained, "lost": lost})
    return {"ok": True, "diff": diffs, "changedFiles": len(diffs)}


_SSH_TUNNELS: dict[str, subprocess.Popen[str]] = {}


def ssh_start_tunnel(ssh: dict[str, Any]) -> dict[str, Any]:
    """Start SSH local forward; supports ControlMaster reuse, JumpHost, RemoteCommand."""
    host = str(ssh.get("host") or "").strip()
    if not host:
        raise ValueError("ssh.host required")
    local_port = int(ssh.get("localPort") or ssh.get("port") or 5678)
    remote_port = int(ssh.get("remotePort") or local_port)
    remote_host = str(ssh.get("remoteHost") or "127.0.0.1")
    key = f"{host}:{local_port}:{remote_host}:{remote_port}"
    if key in _SSH_TUNNELS and _SSH_TUNNELS[key].poll() is None:
        return {"ok": True, "key": key, "pid": _SSH_TUNNELS[key].pid, "reused": True}
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        raise RuntimeError("ssh not found on PATH")
    remote_cmd = str(ssh.get("remoteCommand") or ssh.get("RemoteCommand") or "").strip()
    control_path = str(ssh.get("controlPath") or "").strip()
    if ssh.get("controlMaster", True) and not control_path:
        control_path = str(Path(tempfile.gettempdir()) / f"zintriq-ssh-{uuid.uuid4().hex[:8]}")
    cmd = [
        ssh_bin,
        "-L",
        f"{local_port}:{remote_host}:{remote_port}",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
    ]
    if control_path:
        # Reuse multiplexed connection when possible
        if Path(control_path).exists() or ssh.get("controlMasterReuse"):
            cmd.extend(["-o", f"ControlPath={control_path}", "-o", "ControlMaster=auto", "-o", "ControlPersist=300"])
        else:
            cmd.extend(
                [
                    "-o",
                    f"ControlPath={control_path}",
                    "-o",
                    "ControlMaster=yes",
                    "-o",
                    "ControlPersist=300",
                ]
            )
    jump = str(ssh.get("jumpHost") or ssh.get("proxyJump") or ssh.get("ProxyJump") or "").strip()
    if jump:
        cmd.extend(["-J", jump])
    if remote_cmd:
        cmd.extend(["-o", f"RemoteCommand={remote_cmd}", "-t"])
    else:
        cmd.append("-N")
    identity = str(ssh.get("identityFile") or "").strip()
    if identity:
        cmd.extend(["-i", identity])
    cmd.append(host)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    if proc.poll() is not None:
        err = ""
        try:
            err = (proc.stderr.read() if proc.stderr else "") or ""
        except Exception:
            pass
        raise RuntimeError(f"ssh tunnel failed: {err[:500]}")
    _SSH_TUNNELS[key] = proc
    return {"ok": True, "key": key, "pid": proc.pid, "localPort": local_port, "cmd": cmd}


def ssh_stop_tunnel(key: str | None = None) -> dict[str, Any]:
    stopped = []
    keys = [key] if key else list(_SSH_TUNNELS.keys())
    for k in keys:
        proc = _SSH_TUNNELS.pop(k, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            stopped.append(k)
    return {"ok": True, "stopped": stopped}


def ssh_list_tunnels() -> dict[str, Any]:
    """Status panel for active SSH tunnels (incl. multi-hop JumpHost keys)."""
    tunnels = []
    dead = []
    for key, proc in list(_SSH_TUNNELS.items()):
        alive = proc.poll() is None
        if not alive:
            dead.append(key)
            continue
        parts = key.split(":")
        host = parts[0] if parts else key
        local_port = int(parts[1]) if len(parts) > 1 else 0
        # Detect multi-hop from cmd if stored — reconstruct from key shape
        hops = [host]
        tunnels.append(
            {
                "key": key,
                "pid": proc.pid,
                "alive": True,
                "host": host,
                "localPort": local_port,
                "remote": ":".join(parts[2:]) if len(parts) > 2 else "",
                "hops": hops,
                "multiHop": "-J" in " ".join(str(x) for x in (getattr(proc, "args", None) or [])),
            }
        )
    for k in dead:
        _SSH_TUNNELS.pop(k, None)
    return {"ok": True, "tunnels": tunnels, "count": len(tunnels)}


def gdb_hardware_watch(
    expression: str,
    *,
    access: str = "write",
    gdb_path: str | None = None,
) -> dict[str, Any]:
    """Set a hardware watchpoint via gdb MI (-break-watch). Returns MI-ish result."""
    from editor.gdb_mi import GdbMi, GdbMiError, resolve_mi_backend

    expr = (expression or "").strip()
    if not expr:
        raise ValueError("expression required")
    access = (access or "write").lower()
    if access not in {"read", "write", "readWrite", "access"}:
        access = "write"
    try:
        backend, exe = resolve_mi_backend(gdb_path or "gdb")
    except GdbMiError as exc:
        return {"ok": False, "error": str(exc), "hardware": True, "expression": expr}
    mi = GdbMi(exe, backend=backend)
    mi.start()
    try:
        # -break-watch [-r|-a] expr
        args = []
        if access == "read":
            args.append("-r")
        elif access in {"readWrite", "access"}:
            args.append("-a")
        args.append(expr)
        try:
            body = mi.cmd("-break-watch", *args, timeout=8.0)
        except Exception as exc:  # noqa: BLE001
            # Fallback CLI
            flag = "rwatch" if access == "read" else ("awatch" if access in {"readWrite", "access"} else "watch")
            text = mi.cli(f"{flag} {expr}")
            return {
                "ok": True,
                "backend": backend,
                "expression": expr,
                "access": access,
                "hardware": True,
                "mode": "cli",
                "raw": text[:2000],
                "note": str(exc)[:200],
            }
        return {
            "ok": True,
            "backend": backend,
            "expression": expr,
            "access": access,
            "hardware": True,
            "mode": "mi",
            "body": body,
        }
    finally:
        mi.close()


def _is_elf_core(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".core") or name.startswith("core.") or name == "core":
        return True
    try:
        with path.open("rb") as f:
            magic = f.read(4)
        return magic == b"\x7fELF"
    except OSError:
        return False


def _parse_gdb_bt(text: str, workspace: Path) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for line in text.splitlines():
        # #0  0x... in foo () at path:12
        m = re.search(r"#(\d+)\s+.*?in\s+(\S+)\s+.*?(?:at|from)\s+([^:]+):(\d+)", line)
        if not m:
            m = re.search(r"#(\d+)\s+0x[0-9a-fA-F]+\s+in\s+(\S+)", line)
            if m:
                frames.append(
                    {
                        "id": int(m.group(1)) + 1,
                        "name": m.group(2),
                        "path": "(native)",
                        "line": 0,
                        "column": 1,
                    }
                )
            continue
        fpath = m.group(3).strip()
        try:
            pref = str(Path(fpath).resolve().relative_to(workspace.resolve())).replace("\\", "/")
        except Exception:
            pref = fpath
        frames.append(
            {
                "id": int(m.group(1)) + 1,
                "name": m.group(2),
                "path": pref,
                "line": int(m.group(4)),
                "column": 1,
            }
        )
    return frames


def load_core_dump(workspace: Path, path: str) -> dict[str, Any]:
    """Load ELF core via gdb MI (locals) or lldb/gdb batch backtrace."""
    rel = (path or "").replace("\\", "/").strip()
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())
    if not target.is_file():
        raise FileNotFoundError(rel)
    gdb = shutil.which("gdb")
    lldb = shutil.which("lldb")
    # Prefer persistent-style MI for locals
    if gdb:
        try:
            from editor.gdb_mi import GdbMi

            mi = GdbMi(gdb)
            mi.start(extra_args=["--core", str(target)])
            try:
                frames_raw = mi.stack_list_frames()
                locals_ = mi.stack_list_locals(0)
                text = mi.cli("bt full") + "\n" + mi.cli("info registers")
            finally:
                mi.close()
            frames = []
            for fr in frames_raw:
                fpath = fr.get("file") or ""
                try:
                    pref = (
                        str(Path(fpath).resolve().relative_to(workspace.resolve())).replace("\\", "/")
                        if fpath
                        else rel
                    )
                except Exception:
                    pref = fpath or rel
                frames.append(
                    {
                        "id": int(fr.get("level") or 0) + 1,
                        "name": fr.get("func") or "?",
                        "path": pref,
                        "line": int(fr.get("line") or 0),
                        "column": 1,
                    }
                )
            if not frames:
                frames = _parse_gdb_bt(text, workspace)
            from editor import debug_advanced

            sym = debug_advanced.enhance_core_symbols(workspace, frames)
            frames = sym.get("frames") or frames
            return {
                "ok": True,
                "mode": "core",
                "tool": "gdb-mi",
                "path": rel,
                "reason": "core dump (gdb-mi)",
                "stack": frames
                or [{"id": 1, "name": "<core>", "path": rel, "line": 0, "column": 1}],
                "variables": locals_,
                "console": [{"type": "output", "text": text[-12000:]}],
                "raw": text[-12000:],
                "symbols": sym.get("symbols") or [],
                "symbolTool": sym.get("tool") or "",
            }
        except Exception:
            pass
    text = ""
    tool = ""
    if gdb:
        tool = "gdb"
        proc = subprocess.run(
            [
                gdb,
                "-batch",
                "-ex",
                "set pagination off",
                "-ex",
                "bt full",
                "-ex",
                "info registers",
                "--core",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    elif lldb:
        tool = "lldb"
        proc = subprocess.run(
            [
                lldb,
                "-c",
                str(target),
                "-o",
                "bt all",
                "-o",
                "register read",
                "-o",
                "quit",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    else:
        raise RuntimeError("neither gdb nor lldb found for core dump")
    frames = _parse_gdb_bt(text, workspace)
    return {
        "ok": True,
        "mode": "core",
        "tool": tool,
        "path": rel,
        "reason": f"core dump ({tool})",
        "stack": frames
        or [{"id": 1, "name": "<core>", "path": rel, "line": 0, "column": 1}],
        "variables": [],
        "console": [{"type": "output", "text": text[-12000:]}],
        "raw": text[-12000:],
    }


def load_postmortem(workspace: Path, path: str) -> dict[str, Any]:
    """Load a traceback / core dump / JSON for postmortem viewing."""
    rel = (path or "").replace("\\", "/").strip()
    if not rel or ".." in Path(rel).parts:
        raise ValueError("invalid path")
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())
    if not target.is_file():
        raise FileNotFoundError(rel)
    if _is_elf_core(target):
        return load_core_dump(workspace, rel)
    # Binary ELF without .core suffix still tried as core if gdb available
    try:
        with target.open("rb") as f:
            magic = f.read(4)
        if magic == b"\x7fELF" and (shutil.which("gdb") or shutil.which("lldb")):
            # Prefer core path only when named like core; otherwise fall through if text-readable
            if target.name.startswith("core") or target.suffix == ".core":
                return load_core_dump(workspace, rel)
    except OSError:
        pass
    text = target.read_text(encoding="utf-8", errors="replace")
    if target.suffix.lower() == ".json":
        data = json.loads(text)
        return {
            "ok": True,
            "mode": "json",
            "path": rel,
            "reason": data.get("reason") or "postmortem",
            "stack": data.get("stack") or [],
            "variables": data.get("variables") or [],
            "console": data.get("console") or [{"type": "output", "text": text[:4000]}],
        }
    frames = []
    variables: list[dict[str, Any]] = []
    lines = text.splitlines()
    for line in lines:
        if 'File "' in line and ", line " in line:
            m = re.search(r'File "([^"]+)", line (\d+)(?:, in (\S+))?', line)
            if m:
                fpath = m.group(1)
                try:
                    pref = str(Path(fpath).resolve().relative_to(workspace.resolve())).replace("\\", "/")
                except Exception:
                    pref = fpath
                frames.append(
                    {
                        "id": len(frames) + 1,
                        "name": m.group(3) or "<module>",
                        "path": pref,
                        "line": int(m.group(2)),
                        "column": 1,
                    }
                )
    reason = "postmortem"
    for line in reversed(lines):
        if line.strip() and not line.startswith(" "):
            reason = line.strip()[:200]
            break
    return {
        "ok": True,
        "mode": "traceback",
        "path": rel,
        "reason": reason,
        "stack": list(reversed(frames)) or [{"id": 1, "name": "<dump>", "path": rel, "line": 1}],
        "variables": variables,
        "console": [{"type": "output", "text": text[-8000:]}],
        "raw": text[-8000:],
    }


def docker_path_mappings(container: str, workspace: Path) -> dict[str, Any]:
    """Infer pathMappings from `docker inspect` Mounts."""
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("docker not found on PATH")
    name = (container or "").strip()
    if not name:
        raise ValueError("container name required")
    proc = subprocess.run(
        [docker, "inspect", name, "--format", "{{json .Mounts}}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "docker inspect failed")[:500])
    try:
        mounts = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid docker inspect JSON") from exc
    if not isinstance(mounts, list):
        mounts = []
    ws = str(workspace.resolve())
    mappings: list[dict[str, str]] = []
    for m in mounts:
        if not isinstance(m, dict):
            continue
        src = str(m.get("Source") or "")
        dest = str(m.get("Destination") or m.get("Target") or "")
        if not src or not dest:
            continue
        # Prefer mounts that contain the workspace
        if ws.startswith(src) or src.startswith(ws) or src == ws:
            mappings.append({"localRoot": src, "remoteRoot": dest})
        else:
            mappings.append({"localRoot": src, "remoteRoot": dest})
    # Also try published ports
    port_proc = subprocess.run(
        [docker, "inspect", name, "--format", "{{json .NetworkSettings.Ports}}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    ports: dict[str, Any] = {}
    try:
        ports = json.loads(port_proc.stdout or "{}") if port_proc.returncode == 0 else {}
    except json.JSONDecodeError:
        ports = {}
    host_port = None
    for key, binds in (ports or {}).items():
        if binds and isinstance(binds, list) and binds[0].get("HostPort"):
            host_port = int(binds[0]["HostPort"])
            break
    if not mappings:
        mappings = [{"localRoot": ws, "remoteRoot": "/app"}]
    return {"ok": True, "container": name, "pathMappings": mappings, "hostPort": host_port}


def detect_test_kind(path: str, workspace: Path | None = None) -> str | None:
    rel = (path or "").replace("\\", "/")
    name = Path(rel).name
    if name.startswith("test_") and name.endswith(".py"):
        return "pytest"
    if name.endswith("_test.py"):
        return "pytest"
    if name.endswith((".spec.ts", ".spec.js")) and ("playwright" in rel or "e2e" in rel):
        return "playwright"
    if workspace is not None:
        pkg = workspace.resolve() / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            deps = {
                **(data.get("dependencies") or {}),
                **(data.get("devDependencies") or {}),
            }
            scripts = data.get("scripts") or {}
            script_blob = " ".join(str(v) for v in scripts.values())
            if "@playwright/test" in deps or "playwright" in script_blob:
                if name.endswith((".spec.ts", ".spec.js", ".test.ts")):
                    return "playwright"
            if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")) or "vitest" in deps or "vitest" in script_blob:
                if name.endswith((".test.js", ".test.mjs", ".test.ts", ".test.tsx", ".spec.js", ".spec.mjs", ".spec.ts", ".spec.tsx")):
                    return "vitest"
            if "mocha" in deps or "mocha" in script_blob:
                if name.endswith((".test.js", ".spec.js", ".mjs")):
                    return "mocha"
    if name.endswith(".test.js") or name.endswith(".spec.js") or name.endswith(".test.mjs"):
        return "jest"
    if name.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx")):
        return "vitest"
    if "/__tests__/" in rel:
        return "jest"
    return None


def _resolve_bin(workspace: Path, *parts: str, npx_pkg: str) -> tuple[str, list[str]]:
    local = workspace.resolve().joinpath(*parts)
    if local.is_file():
        return str(local), []
    which = shutil.which(parts[-1].replace(".js", ""))
    if which:
        return which, []
    npx = shutil.which("npx")
    if npx:
        return npx, [npx_pkg]
    raise RuntimeError(f"{npx_pkg} not found (install or ensure npx is available)")


def resolve_jest_program(workspace: Path) -> tuple[str, list[str], bool]:
    program, prefix = _resolve_bin(
        workspace, "node_modules", "jest", "bin", "jest.js", npx_pkg="jest"
    )
    return program, prefix, bool(prefix)


def test_launch_config(workspace: Path, path: str) -> dict[str, Any]:
    kind = detect_test_kind(path, workspace)
    if kind == "pytest":
        return {
            "name": f"pytest: {path}",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": [path, "-s", "--tb=short"],
            "cwd": "${workspaceFolder}",
            "stopOnEntry": False,
            "justMyCode": False,
        }
    if kind == "jest":
        program, prefix, _is_npx = resolve_jest_program(workspace)
        return {
            "name": f"jest: {path}",
            "type": "node",
            "request": "launch",
            "program": program,
            "args": [*prefix, path, "--runInBand", "--no-coverage"],
            "cwd": "${workspaceFolder}",
            "stopOnEntry": True,
        }
    if kind == "vitest":
        program, prefix = _resolve_bin(
            workspace, "node_modules", "vitest", "vitest.mjs", npx_pkg="vitest"
        )
        if not Path(program).name.startswith("vitest") and not prefix:
            # vitest.mjs may be under vitest/dist
            alt = workspace.resolve() / "node_modules" / "vitest" / "vitest.mjs"
            if not alt.is_file():
                program, prefix = _resolve_bin(
                    workspace, "node_modules", "vitest", "dist", "cli.js", npx_pkg="vitest"
                )
        return {
            "name": f"vitest: {path}",
            "type": "node",
            "request": "launch",
            "program": program,
            "args": [*prefix, "run", path, "--no-coverage"],
            "cwd": "${workspaceFolder}",
            "stopOnEntry": True,
        }
    if kind == "mocha":
        program, prefix = _resolve_bin(
            workspace, "node_modules", "mocha", "bin", "mocha.js", npx_pkg="mocha"
        )
        return {
            "name": f"mocha: {path}",
            "type": "node",
            "request": "launch",
            "program": program,
            "args": [*prefix, path],
            "cwd": "${workspaceFolder}",
            "stopOnEntry": True,
        }
    if kind == "playwright":
        program, prefix = _resolve_bin(
            workspace,
            "node_modules",
            "@playwright",
            "test",
            "cli.js",
            npx_pkg="@playwright/test",
        )
        return {
            "name": f"playwright: {path}",
            "type": "node",
            "request": "launch",
            "program": program,
            "args": [*prefix, "test", path, "--workers=1", "--timeout=0"],
            "cwd": "${workspaceFolder}",
            "stopOnEntry": True,
            "env": {"PWDEBUG": "console"},
        }
    raise ValueError("not a recognized test file (pytest/jest/vitest/mocha/playwright)")


def pytest_xdist_launch(workspace: Path, path: str, *, workers: str = "auto") -> dict[str, Any]:
    """Launch config for pytest-xdist (each worker attachable via subProcess)."""
    return {
        "name": f"pytest-xdist: {path}",
        "type": "python",
        "request": "launch",
        "module": "pytest",
        "args": [path, "-s", "-n", str(workers), "--dist=loadscope"],
        "cwd": "${workspaceFolder}",
        "stopOnEntry": False,
        "justMyCode": False,
        "subProcess": True,
    }


def coverage_html_report(workspace: Path) -> dict[str, Any]:
    """Write a simple HTML coverage report under .zintriq/coverage/index.html."""
    summary = coverage_summary()
    out_dir = workspace.resolve() / ".zintriq" / "coverage"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in summary.get("files") or []:
        rows.append(
            f"<tr><td><a href='#{f['path']}'>{f['path']}</a></td>"
            f"<td>{f['pct']}%</td><td>{f['hits']}</td><td>{f['misses']}</td></tr>"
        )
    sections = []
    with _LOCK:
        files = {k: dict(v) for k, v in _COVERAGE.items()}
    for path, info in files.items():
        hits = set(info.get("hits") or [])
        misses = set(info.get("misses") or [])
        src_path = workspace / path
        try:
            lines = src_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        body = []
        for i, line in enumerate(lines, 1):
            cls = "hit" if i in hits else ("miss" if i in misses else "")
            body.append(f"<div class='{cls}'><span class='ln'>{i}</span>{_html_esc(line)}</div>")
        sections.append(f"<h2 id='{path}'>{path}</h2><pre>{''.join(body)}</pre>")
    tot = summary.get("totals") or {}
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Coverage</title>
<style>
body{{font:13px/1.4 ui-monospace,monospace;background:#111;color:#ddd;padding:16px}}
.hit{{background:rgba(80,160,100,.25)}} .miss{{background:rgba(180,60,60,.3)}}
.ln{{display:inline-block;width:3em;color:#666;user-select:none}}
table{{border-collapse:collapse;margin-bottom:1em}} td,th{{border:1px solid #333;padding:4px 8px}}
</style></head><body>
<h1>Coverage {tot.get('pct', '—')}%</h1>
<p>{tot.get('hits', 0)} hit / {tot.get('misses', 0)} miss</p>
<table><tr><th>File</th><th>%</th><th>Hits</th><th>Miss</th></tr>
{''.join(rows)}</table>
{''.join(sections)}
</body></html>"""
    index = out_dir / "index.html"
    index.write_text(html, encoding="utf-8")
    rel = str(index.relative_to(workspace.resolve())).replace("\\", "/")
    return {"ok": True, "path": rel, "url": f"/api/fs/read?path={rel}", "totals": tot}


def _html_esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def resolve_sourcemap(workspace: Path, generated_path: str, line: int, column: int = 0) -> dict[str, Any]:
    """Map generated JS line → original TS via inline/external sourceMappingURL."""
    rel = (generated_path or "").replace("\\", "/")
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())
    if not target.is_file():
        raise FileNotFoundError(rel)
    text = target.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"sourceMappingURL=(\S+)", text)
    if not m:
        raise RuntimeError("no sourceMappingURL")
    url = m.group(1).strip()
    if url.startswith("data:"):
        # data:application/json;base64,...
        if "base64," in url:
            import base64

            raw = base64.b64decode(url.split("base64,", 1)[1])
            smap = json.loads(raw.decode("utf-8"))
        else:
            raise RuntimeError("unsupported data sourcemap")
    else:
        smap_path = (target.parent / url).resolve()
        smap = json.loads(smap_path.read_text(encoding="utf-8"))
    # Minimal VLQ mapping: find closest generated line mapping
    mappings = smap.get("mappings") or ""
    sources = smap.get("sources") or []
    # Parse only line-level (semicolon-separated generated lines)
    gen_lines = mappings.split(";")
    if line < 1 or line > len(gen_lines):
        raise ValueError("line out of range for sourcemap")
    segment = gen_lines[line - 1]
    if not segment:
        # search nearby
        for delta in range(1, 20):
            for cand in (line - 1 - delta, line - 1 + delta):
                if 0 <= cand < len(gen_lines) and gen_lines[cand]:
                    segment = gen_lines[cand]
                    line = cand + 1
                    break
            if segment:
                break
    if not segment:
        raise RuntimeError("no mapping for line")
    # First segment fields: genCol, sourcesIndex, origLine, origCol
    fields = segment.split(",")[0]
    vals = _decode_vlq_fields(fields)
    src_index = vals[1] if len(vals) > 1 else 0
    orig_line = (vals[2] + 1) if len(vals) > 2 else 1
    orig_col = vals[3] if len(vals) > 3 else 0
    src = sources[src_index] if 0 <= src_index < len(sources) else ""
    # normalize source path
    src_rel = src
    try:
        if src and not Path(src).is_absolute():
            cand = (target.parent / src).resolve()
            src_rel = str(cand.relative_to(workspace.resolve())).replace("\\", "/")
    except Exception:
        src_rel = src
    return {
        "ok": True,
        "generated": {"path": rel, "line": line, "column": column},
        "original": {"path": src_rel, "line": orig_line, "column": orig_col},
        "sourceRoot": smap.get("sourceRoot") or "",
    }


def _decode_vlq_fields(segment: str) -> list[int]:
    """Decode comma-less VLQ field group into relative ints (best-effort cumulative)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    values = []
    i = 0
    while i < len(segment):
        result = 0
        shift = 0
        while True:
            if i >= len(segment):
                break
            ch = segment[i]
            i += 1
            digit = alphabet.find(ch)
            if digit < 0:
                break
            cont = digit & 32
            digit &= 31
            result += digit << shift
            shift += 5
            if not cont:
                break
        neg = result & 1
        result >>= 1
        values.append(-result if neg else result)
    return values


def allocation_timeline_from_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Build scrub-able allocation timeline samples from CDP sampling profile."""
    samples = profile.get("samples") or []
    out = []
    t = 0
    for i, s in enumerate(samples):
        size = int(s.get("size") or 0)
        t += size
        out.append(
            {
                "i": i,
                "size": size,
                "cumulative": t,
                "nodeId": s.get("nodeId") or s.get("ordinal"),
            }
        )
    return out[:5000]


def breakpoints_to_vscode(breakpoints: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Export Zintriq breakpoints as VS Code-style JSON."""
    out = []
    for path, bps in (breakpoints or {}).items():
        for bp in bps:
            item: dict[str, Any] = {
                "path": path,
                "line": int(bp.get("line") or 0),
            }
            if bp.get("condition"):
                item["condition"] = bp["condition"]
            if bp.get("hitCondition"):
                item["hitCondition"] = bp["hitCondition"]
            if bp.get("logMessage"):
                item["logMessage"] = bp["logMessage"]
            if bp.get("enabled") is False:
                item["enabled"] = False
            if bp.get("group") and bp.get("group") != "default":
                item["group"] = bp["group"]
            out.append(item)
    return {"version": "0.2.0", "breakpoints": out}


def breakpoints_from_vscode(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Import VS Code / Zintriq breakpoint JSON into path→list map."""
    items = document.get("breakpoints") if isinstance(document, dict) else None
    if not isinstance(items, list):
        raise ValueError("breakpoints must be a list")
    out: dict[str, list[dict[str, Any]]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or raw.get("uri") or "").replace("\\", "/")
        # strip file://
        if path.startswith("file://"):
            path = urlparse(path).path
        if not path or int(raw.get("line") or 0) < 1:
            continue
        out.setdefault(path, []).append(
            {
                "line": int(raw["line"]),
                "condition": str(raw.get("condition") or ""),
                "hitCondition": str(raw.get("hitCondition") or ""),
                "logMessage": str(raw.get("logMessage") or ""),
                "enabled": True if raw.get("enabled") is None else bool(raw.get("enabled")),
                "group": str(raw.get("group") or "default"),
            }
        )
    for path in out:
        out[path].sort(key=lambda x: x["line"])
    return out
