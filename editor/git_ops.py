"""Local git wrappers — workspace only."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

_BRANCH_RE = re.compile(r"^[\w./@+-]+$")


def _run(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=check,
    )


def is_repo(workspace: Path) -> bool:
    return (workspace / ".git").exists()


def init(workspace: Path) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    if is_repo(workspace):
        return {"ok": True, "already": True}
    _run(workspace, "init")
    return {"ok": True, "already": False}


def status(workspace: Path) -> dict[str, Any]:
    if not is_repo(workspace):
        return {"ok": True, "repo": False, "entries": []}
    proc = _run(workspace, "status", "--porcelain=v1", "-uall", check=False)
    entries = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        entries.append({"code": line[:2], "path": line[3:].strip()})
    head = _run(workspace, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    return {
        "ok": True,
        "repo": True,
        "entries": entries,
        "raw": proc.stdout,
        "branch": (head.stdout or "").strip() or None,
    }


def diff(workspace: Path, staged: bool = False) -> dict[str, Any]:
    if not is_repo(workspace):
        return {"ok": True, "repo": False, "diff": ""}
    args = ["diff"]
    if staged:
        args.append("--cached")
    proc = _run(workspace, *args, check=False)
    return {"ok": True, "repo": True, "diff": proc.stdout}


def commit(workspace: Path, message: str) -> dict[str, Any]:
    if not is_repo(workspace):
        raise RuntimeError("not a git repository")
    msg = (message or "").strip()
    if not msg:
        raise ValueError("empty message")
    _run(workspace, "add", "-A")
    proc = _run(workspace, "commit", "-m", msg, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if "nothing to commit" in err.lower() or "nothing to commit" in (proc.stdout or "").lower():
            return {"ok": True, "committed": False, "message": "nothing to commit"}
        raise RuntimeError(err or "commit failed")
    return {"ok": True, "committed": True, "message": msg}


def branches(workspace: Path) -> dict[str, Any]:
    if not is_repo(workspace):
        return {"ok": True, "repo": False, "current": None, "branches": []}
    head = _run(workspace, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    current = (head.stdout or "").strip() or None
    proc = _run(workspace, "branch", "-a", "--format=%(refname:short)%00%(HEAD)%00%(objectname:short)", check=False)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split("\x00")
        if not parts or not parts[0]:
            continue
        name = parts[0].strip()
        if name in seen:
            continue
        seen.add(name)
        items.append(
            {
                "name": name,
                "current": parts[1].strip() == "*" if len(parts) > 1 else name == current,
                "sha": parts[2].strip() if len(parts) > 2 else "",
                "remote": name.startswith("remotes/") or name.startswith("origin/"),
            }
        )
    return {"ok": True, "repo": True, "current": current, "branches": items}


def checkout(workspace: Path, name: str, *, create: bool = False) -> dict[str, Any]:
    if not is_repo(workspace):
        raise RuntimeError("not a git repository")
    branch = (name or "").strip()
    if not branch or not _BRANCH_RE.match(branch):
        raise ValueError("invalid branch name")
    if create:
        proc = _run(workspace, "checkout", "-b", branch, check=False)
    else:
        # allow checkout of remotes/origin/foo → origin/foo tracking
        target = branch
        if branch.startswith("remotes/"):
            target = branch[len("remotes/") :]
        proc = _run(workspace, "checkout", target, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "checkout failed").strip())
    return {"ok": True, "branch": branch, "created": create, **branches(workspace)}


def log_graph(workspace: Path, *, limit: int = 80) -> dict[str, Any]:
    """Return git log --graph rows with parsed commit metadata."""
    if not is_repo(workspace):
        return {"ok": True, "repo": False, "lines": [], "commits": []}
    n = max(1, min(int(limit or 80), 200))
    # graph chars left of NUL-separated fields
    pretty = "%x00%h%x00%an%x00%ad%x00%d%x00%s"
    proc = _run(
        workspace,
        "log",
        f"--max-count={n}",
        "--graph",
        "--date=short",
        f"--pretty=format:{pretty}",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git log failed").strip())

    lines: list[dict[str, Any]] = []
    commits: list[dict[str, Any]] = []
    for raw in proc.stdout.splitlines():
        if "\x00" not in raw:
            # pure graph connector line
            lines.append({"graph": raw.rstrip(), "commit": None})
            continue
        graph, rest = raw.split("\x00", 1)
        parts = rest.split("\x00")
        while len(parts) < 5:
            parts.append("")
        sha, author, date, deco, subject = parts[:5]
        commit = {
            "sha": sha,
            "author": author,
            "date": date,
            "decorations": deco.strip(),
            "subject": subject,
        }
        commits.append(commit)
        lines.append({"graph": graph.rstrip(), "commit": commit})
    return {
        "ok": True,
        "repo": True,
        "lines": lines,
        "commits": commits,
        "limit": n,
    }
