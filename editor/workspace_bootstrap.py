"""First-run workspace seed and onboarding state."""

from __future__ import annotations

import json
from pathlib import Path

WELCOME_NAME = "WELCOME.md"
HELLO_REL = "examples/hello.py"

WELCOME_TEXT = """# Welcome to Zintriq

Your workspace starts here. Use the sidebar to open files, or create new ones with **New File** / **New Folder**.

## Quick start

1. Open `examples/hello.py` (seeded for you).
2. Edit, then save with Cmd+S / Ctrl+S.
3. Open **Term** for a local shell (enable Terminal in Perms first).
4. Open **Debug** when you are ready to run/attach.

## What Zintriq is for

An embedded-friendly editor: LSP/DAP language services, capability-scoped tools, and hardware verification that stays off the typing hot path.

## Community contribution types

See `GOVERNANCE.md` in the product repo: Core PRs, HAL Mapping Packs, and Diagnostic Knowledge entries are all first-class.

Dismiss this guide anytime — you can reopen onboarding from the sidebar **?** button.
"""

HELLO_TEXT = '''"""Tiny starter — open Debug → Python launch when ready."""


def main() -> None:
    name = "Zintriq"
    print(f"Hello from {name}")


if __name__ == "__main__":
    main()
'''


def visible_entries(workspace: Path) -> list[Path]:
    if not workspace.is_dir():
        return []
    return [p for p in workspace.iterdir() if not p.name.startswith(".")]


def is_empty_workspace(workspace: Path) -> bool:
    return len(visible_entries(workspace)) == 0


def onboarding_path(data_dir: Path) -> Path:
    return Path(data_dir) / "onboarding.json"


def load_onboarding(data_dir: Path) -> dict:
    path = onboarding_path(data_dir)
    if not path.is_file():
        return {"completed": False, "version": 1}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"completed": False, "version": 1}
    if not isinstance(raw, dict):
        return {"completed": False, "version": 1}
    return {
        "completed": bool(raw.get("completed")),
        "version": int(raw.get("version") or 1),
    }


def save_onboarding(data_dir: Path, completed: bool = True, version: int = 1) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    state = {"completed": bool(completed), "version": int(version)}
    onboarding_path(data_dir).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def seed_workspace(workspace: Path) -> dict:
    """Create starter files when the workspace has no visible content."""
    workspace.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    if not is_empty_workspace(workspace):
        return {"seeded": False, "created": created, "empty": False}

    welcome = workspace / WELCOME_NAME
    if not welcome.exists():
        welcome.write_text(WELCOME_TEXT, encoding="utf-8")
        created.append(WELCOME_NAME)

    hello = workspace / HELLO_REL
    hello.parent.mkdir(parents=True, exist_ok=True)
    if not hello.exists():
        hello.write_text(HELLO_TEXT, encoding="utf-8")
        created.append(HELLO_REL)

    return {"seeded": bool(created), "created": created, "empty": False}


def ensure_ready(workspace: Path, data_dir: Path) -> dict:
    seed = seed_workspace(workspace)
    onboarding = load_onboarding(data_dir)
    return {
        "workspace": str(workspace.resolve()),
        "empty": is_empty_workspace(workspace),
        "seed": seed,
        "onboarding": onboarding,
        "show_onboarding": not onboarding.get("completed"),
    }
