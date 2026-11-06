"""Run VS Code / Zintriq tasks.json entries (preLaunchTask, dependsOn, problemMatchers)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

TASK_CANDIDATES = (".zintriq/tasks.json", ".vscode/tasks.json")


def load_tasks_doc(workspace: Path) -> dict[str, Any]:
    root = workspace.resolve()
    for rel in TASK_CANDIDATES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict):
            return raw
    return {"version": "2.0.0", "tasks": []}


def load_tasks(workspace: Path) -> list[dict[str, Any]]:
    doc = load_tasks_doc(workspace)
    tasks = doc.get("tasks") if isinstance(doc, dict) else None
    if isinstance(tasks, list):
        return [t for t in tasks if isinstance(t, dict)]
    return []


def find_task(workspace: Path, label: str) -> dict[str, Any] | None:
    want = (label or "").strip()
    if not want:
        return None
    for t in load_tasks(workspace):
        if str(t.get("label") or t.get("labelName") or "") == want:
            return t
    return None


def _apply_problem_matchers(text: str, matchers: list[Any]) -> list[dict[str, Any]]:
    """Best-effort parse of output using simple $gcc-like patterns or custom regexp."""
    problems: list[dict[str, Any]] = []
    patterns: list[re.Pattern[str]] = []
    for m in matchers or []:
        if isinstance(m, str):
            if m in {"$gcc", "$tsc", "$eslint-stylish"}:
                patterns.append(
                    re.compile(
                        r"^(?P<file>[^:]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s*"
                        r"(?P<severity>error|warning|info):\s*(?P<message>.+)$",
                        re.I,
                    )
                )
            continue
        if isinstance(m, dict):
            pat = m.get("pattern")
            if isinstance(pat, dict) and pat.get("regexp"):
                try:
                    patterns.append(re.compile(str(pat["regexp"])))
                except re.error:
                    pass
            elif isinstance(pat, list):
                for p in pat:
                    if isinstance(p, dict) and p.get("regexp"):
                        try:
                            patterns.append(re.compile(str(p["regexp"])))
                        except re.error:
                            pass
    if not patterns:
        patterns.append(
            re.compile(
                r"^(?P<file>[^:]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s*"
                r"(?P<severity>error|warning|info):\s*(?P<message>.+)$",
                re.I,
            )
        )
    for line in (text or "").splitlines():
        for pat in patterns:
            mm = pat.search(line)
            if not mm:
                continue
            gd = mm.groupdict() if mm.groupdict() else {}
            problems.append(
                {
                    "file": gd.get("file") or (mm.group(1) if mm.lastindex else ""),
                    "line": int(gd.get("line") or 0),
                    "column": int(gd.get("col") or gd.get("column") or 1),
                    "severity": (gd.get("severity") or "error").lower(),
                    "message": gd.get("message") or line,
                    "raw": line,
                }
            )
            break
    return problems[:100]


def _run_one(
    workspace: Path,
    task: dict[str, Any],
    *,
    timeout: float,
    stack: list[str],
) -> dict[str, Any]:
    label = str(task.get("label") or "")
    if label in stack:
        raise RuntimeError(f"circular dependsOn involving {label!r}")
    stack.append(label)

    depends = task.get("dependsOn")
    dep_results: list[dict[str, Any]] = []
    dep_labels: list[str] = []
    if isinstance(depends, str):
        dep_labels = [depends]
    elif isinstance(depends, list):
        dep_labels = [str(x) for x in depends]
    order = str(task.get("dependsOrder") or "sequence").lower()
    if order == "parallel" and len(dep_labels) > 1:
        def _run_dep(dep: str) -> dict[str, Any]:
            dep_task = find_task(workspace, dep)
            if not dep_task:
                raise FileNotFoundError(f"dependsOn task not found: {dep}")
            return _run_one(workspace, dep_task, timeout=timeout, stack=[*stack])

        with ThreadPoolExecutor(max_workers=min(8, len(dep_labels))) as pool:
            futs = {pool.submit(_run_dep, d): d for d in dep_labels}
            for fut in as_completed(futs):
                dep_results.append(fut.result())
    else:
        for dep in dep_labels:
            dep_task = find_task(workspace, dep)
            if not dep_task:
                raise FileNotFoundError(f"dependsOn task not found: {dep}")
            dep_results.append(_run_one(workspace, dep_task, timeout=timeout, stack=stack))
            if not dep_results[-1].get("ok"):
                raise RuntimeError(f"dependsOn {dep!r} failed")

    typ = str(task.get("type") or "shell").lower()
    cwd = str(workspace.resolve())
    env = {**os.environ}
    opts = task.get("options") if isinstance(task.get("options"), dict) else {}
    if opts.get("cwd"):
        cwd = str(Path(str(opts["cwd"])))
        if not Path(cwd).is_absolute():
            cwd = str((workspace / cwd).resolve())
    if isinstance(opts.get("env"), dict):
        env.update({str(k): str(v) for k, v in opts["env"].items()})

    if typ not in {"shell", "process"} and "command" not in task:
        raise ValueError(f"unsupported task type for {label!r}: {typ}")

    cmd = task.get("command")
    args = task.get("args") or []
    if not isinstance(args, list):
        args = [str(args)]
    if not cmd:
        raise ValueError(f"task {label!r} missing command")
    argv = [str(cmd), *[str(a) for a in args]]
    if typ == "shell" and len(argv) == 1:
        shell = os.environ.get("SHELL") or ("cmd.exe" if os.name == "nt" else "/bin/sh")
        argv = [shell, "-c" if os.name != "nt" else "/c", str(cmd)]
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    matchers = task.get("problemMatcher") or task.get("problemMatchers") or []
    if not isinstance(matchers, list):
        matchers = [matchers]
    problems = _apply_problem_matchers(combined, matchers)
    ok = proc.returncode == 0
    # Fail if problemMatcher found errors and owner treats as fail
    if any(p.get("severity") == "error" for p in problems) and task.get("problemMatcher"):
        # don't auto-fail unless exit non-zero; VS Code often still uses exit code
        pass
    if not ok:
        raise RuntimeError(
            f"task {label!r} exited {proc.returncode}: {(proc.stderr or proc.stdout or '')[:800]}"
        )
    stack.pop()
    return {
        "ok": True,
        "label": label,
        "code": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
        "problems": problems,
        "dependsOn": dep_results,
    }


def run_pre_launch_task(workspace: Path, label: str, *, timeout: float = 120.0) -> dict[str, Any]:
    """Execute a shell/process task by label, honoring dependsOn and problemMatchers."""
    task = find_task(workspace, label)
    if not task:
        raise FileNotFoundError(f"preLaunchTask not found: {label}")
    return _run_one(workspace, task, timeout=timeout, stack=[])


def which_or(name: str, fallback: str | None = None) -> str | None:
    return shutil.which(name) or fallback
