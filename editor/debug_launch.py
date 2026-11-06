"""launch.json-style debug configurations (.zintriq/launch.json or .vscode/launch.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CANDIDATES = (".zintriq/launch.json", ".vscode/launch.json")


def config_path(workspace: Path) -> Path:
    root = workspace.resolve()
    for rel in CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    return root / ".zintriq" / "launch.json"


def default_document(workspace: Path) -> dict[str, Any]:
    return {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "Python: current file",
                "type": "python",
                "request": "launch",
                "program": "${file}",
                "cwd": "${workspaceFolder}",
                "stopOnEntry": True,
                "justMyCode": True,
            },
            {
                "name": "Python: attach",
                "type": "python",
                "request": "attach",
                "host": "127.0.0.1",
                "port": 5678,
                "pathMappings": [
                    {
                        "localRoot": "${workspaceFolder}",
                        "remoteRoot": "${workspaceFolder}",
                    }
                ],
            },
            {
                "name": "Node: current file",
                "type": "node",
                "request": "launch",
                "program": "${file}",
                "cwd": "${workspaceFolder}",
                "stopOnEntry": True,
            },
            {
                "name": "Node: attach",
                "type": "node",
                "request": "attach",
                "host": "127.0.0.1",
                "port": 9229,
            },
            {
                "name": "Python: pytest current file",
                "type": "python",
                "request": "launch",
                "module": "pytest",
                "args": ["${file}", "-s"],
                "cwd": "${workspaceFolder}",
                "justMyCode": False,
            },
            {
                "name": "Python: attach (SSH tunnel)",
                "type": "python",
                "request": "attach",
                "host": "127.0.0.1",
                "port": 5678,
                "ssh": {
                    "host": "user@remote",
                    "localPort": 5678,
                    "remotePort": 5678,
                    "autoTunnel": True,
                    "remoteCommand": "",
                },
                "pathMappings": [
                    {"localRoot": "${workspaceFolder}", "remoteRoot": "/app"}
                ],
            },
            {
                "name": "Python: attach (Docker)",
                "type": "python",
                "request": "attach",
                "host": "127.0.0.1",
                "port": 5678,
                "docker": {"container": "my-app", "port": 5678},
                "pathMappings": [
                    {"localRoot": "${workspaceFolder}", "remoteRoot": "/app"}
                ],
            },
            {
                "name": "Python: rr record+replay",
                "type": "python",
                "request": "launch",
                "program": "${file}",
                "cwd": "${workspaceFolder}",
                "reverse": "rr",
                "stopOnEntry": True,
            },
            {
                "name": "Custom DAP adapter",
                "type": "custom",
                "request": "launch",
                "program": "${file}",
                "cwd": "${workspaceFolder}",
                "debugAdapter": ["python", "-m", "debugpy.adapter"],
            },
            {
                "name": "Jupyter / IPython attach",
                "type": "jupyter",
                "request": "attach",
                "host": "127.0.0.1",
                "port": 5678,
                "justMyCode": False,
                "pathMappings": [
                    {"localRoot": "${workspaceFolder}", "remoteRoot": "${workspaceFolder}"}
                ],
            },
            {
                "name": "WASM (Chrome CDP + DWARF)",
                "type": "wasm",
                "request": "attach",
                "host": "127.0.0.1",
                "port": 9222,
                "webRoot": "${workspaceFolder}",
                "skipFiles": ["**/node_modules/**"],
            },
            {
                "name": "Node: skipFiles blackbox",
                "type": "node",
                "request": "launch",
                "program": "${file}",
                "cwd": "${workspaceFolder}",
                "skipFiles": ["**/node_modules/**", "**/venv/**", "**/.venv/**"],
                "stopOnEntry": True,
            },
            {
                "name": "Rust: lldb (custom adapter)",
                "type": "custom",
                "request": "launch",
                "program": "${workspaceFolder}/target/debug/${workspaceFolderBasename}",
                "cwd": "${workspaceFolder}",
                "debugAdapter": ["codelldb"],
            },
            {
                "name": "Go: delve (dlv dap)",
                "type": "custom",
                "request": "launch",
                "program": "${workspaceFolder}",
                "cwd": "${workspaceFolder}",
                "debugAdapter": ["dlv", "dap"],
                "mode": "debug",
            },
            {
                "name": "Notebook cell (jupyter attach)",
                "type": "jupyter",
                "request": "attach",
                "host": "127.0.0.1",
                "port": 5678,
                "notebook": {"path": "${file}", "cellIndex": 0},
            },
        ],
        "compounds": [
            {
                "name": "Python + Node",
                "configurations": ["Python: current file", "Node: current file"],
                "stopAll": True,
            }
        ],
    }


def load(workspace: Path) -> dict[str, Any]:
    path = config_path(workspace)
    if not path.is_file():
        doc = default_document(workspace)
    else:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = default_document(workspace)
        if not isinstance(raw, dict):
            raw = default_document(workspace)
        configs = raw.get("configurations")
        if not isinstance(configs, list):
            raw = default_document(workspace)
        doc = raw
    compounds = doc.get("compounds") if isinstance(doc.get("compounds"), list) else []
    configurations = [c for c in (doc.get("configurations") or []) if isinstance(c, dict)]
    # Merge extension-contributed launch configs (non-destructive)
    try:
        from editor import debug_platform

        existing = {str(c.get("name")) for c in configurations}
        for c in debug_platform.extension_launch_configs(workspace):
            if str(c.get("name")) not in existing:
                configurations.append(c)
                existing.add(str(c.get("name")))
    except Exception:
        pass
    return {
        "version": str(doc.get("version") or "0.2.0"),
        "configurations": configurations,
        "compounds": [c for c in compounds if isinstance(c, dict) and c.get("name")],
        "path": str(path.relative_to(workspace.resolve())).replace("\\", "/")
        if path.is_file()
        else ".zintriq/launch.json",
    }


def save(workspace: Path, document: dict[str, Any]) -> dict[str, Any]:
    from editor import debug_advanced

    root = workspace.resolve()
    path = root / ".zintriq" / "launch.json"
    configs = document.get("configurations") if isinstance(document, dict) else None
    if not isinstance(configs, list):
        raise ValueError("configurations must be a list")
    clean_cfgs = []
    for c in configs:
        if isinstance(c, dict) and str(c.get("name") or "").strip():
            clean_cfgs.append(dict(c))
    compounds_in = document.get("compounds") if isinstance(document, dict) else None
    clean_compounds = []
    if isinstance(compounds_in, list):
        for c in compounds_in:
            if isinstance(c, dict) and str(c.get("name") or "").strip():
                names = c.get("configurations") or []
                if not isinstance(names, list):
                    names = []
                clean_compounds.append(
                    {
                        "name": str(c["name"]).strip(),
                        "configurations": [str(x) for x in names if str(x).strip()],
                        "stopAll": bool(c.get("stopAll", True)),
                    }
                )
    payload = {
        "version": str((document or {}).get("version") or "0.2.0"),
        "configurations": clean_cfgs,
        "compounds": clean_compounds,
    }
    validation = debug_advanced.validate_launch_document(payload)
    if not validation["ok"] and document.get("force") is not True:
        raise ValueError(
            "launch.json schema errors: "
            + "; ".join(f"{e['path']}: {e['message']}" for e in validation["errors"][:8])
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {**payload, "ok": True, "path": ".zintriq/launch.json", "validation": validation}


def resolve_compound(workspace: Path, name: str) -> dict[str, Any]:
    doc = load(workspace)
    for c in doc.get("compounds") or []:
        if str(c.get("name")) == name:
            return {
                "name": name,
                "configurations": list(c.get("configurations") or []),
            }
    raise KeyError(f"unknown compound: {name}")


def _expand(value: Any, *, workspace: Path, current_file: str) -> Any:
    if isinstance(value, list):
        return [_expand(v, workspace=workspace, current_file=current_file) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v, workspace=workspace, current_file=current_file) for k, v in value.items()}
    if not isinstance(value, str):
        return value
    ws = str(workspace.resolve())
    out = value.replace("${workspaceFolder}", ws).replace("${workspaceRoot}", ws)
    out = out.replace("${file}", current_file or "")
    if current_file:
        out = out.replace("${fileBasename}", Path(current_file).name)
        out = out.replace("${fileDirname}", str((workspace / current_file).resolve().parent))
    return out


def resolve(
    workspace: Path,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    current_file: str = "",
) -> dict[str, Any]:
    """Return a normalized, path-expanded launch configuration."""
    if config and isinstance(config, dict):
        raw = dict(config)
    else:
        doc = load(workspace)
        configs = doc.get("configurations") or []
        if name:
            raw = next((c for c in configs if str(c.get("name")) == name), None)
            if not raw:
                raise KeyError(f"unknown configuration: {name}")
        elif configs:
            raw = dict(configs[0])
        else:
            raise ValueError("no debug configurations")
    expanded = _expand(raw, workspace=workspace, current_file=current_file)
    req = str(expanded.get("request") or "launch").lower()
    typ = str(expanded.get("type") or "").lower()
    if typ in {"debugpy", "python"}:
        typ = "python"
    elif typ in {"node", "javascript", "js", "pwa-node"}:
        typ = "node"
    elif typ in {"rr", "mozilla-rr"}:
        typ = "python"
        expanded.setdefault("reverse", "rr")
    program = str(expanded.get("program") or current_file or "").strip()
    if program and not Path(program).is_absolute():
        # allow workspace-relative
        cand = (workspace / program).resolve()
        if cand.is_file() or req == "launch":
            try:
                program = str(cand.relative_to(workspace.resolve())).replace("\\", "/")
            except ValueError:
                program = str(cand)
    cwd = str(expanded.get("cwd") or workspace)
    args = expanded.get("args") or []
    if not isinstance(args, list):
        args = [str(args)]
    env = expanded.get("env") or {}
    if not isinstance(env, dict):
        env = {}
    mappings = expanded.get("pathMappings") or []
    if not isinstance(mappings, list):
        mappings = []
    module = str(expanded.get("module") or "").strip()
    pre = str(expanded.get("preLaunchTask") or "").strip()
    pipe = expanded.get("pipeTransport") or {}
    docker = expanded.get("docker") or expanded.get("container") or {}
    ssh = expanded.get("ssh") or {}
    return {
        "name": str(expanded.get("name") or "Debug"),
        "type": typ,
        "request": req,
        "program": program,
        "module": module,
        "cwd": cwd,
        "args": [str(a) for a in args],
        "env": {str(k): str(v) for k, v in env.items()},
        "host": str(expanded.get("host") or "127.0.0.1"),
        "port": int(expanded.get("port") or (5678 if typ == "python" else 9229)),
        "stopOnEntry": bool(expanded.get("stopOnEntry", True)),
        "justMyCode": bool(expanded.get("justMyCode", True)),
        "pathMappings": [
            {
                "localRoot": str(m.get("localRoot") or "").replace("\\", "/"),
                "remoteRoot": str(m.get("remoteRoot") or "").replace("\\", "/"),
            }
            for m in mappings
            if isinstance(m, dict) and m.get("localRoot") and m.get("remoteRoot")
        ],
        "console": str(expanded.get("console") or "internalConsole"),
        "preLaunchTask": pre,
        "pipeTransport": pipe if isinstance(pipe, dict) else {},
        "docker": docker if isinstance(docker, dict) else {},
        "ssh": ssh if isinstance(ssh, dict) else {},
        "subProcess": bool(expanded.get("subProcess", True)),
        "reverse": str(expanded.get("reverse") or "").strip().lower(),
        "trace": str(expanded.get("trace") or expanded.get("rrTrace") or "").strip(),
    }
