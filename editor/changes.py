"""Auditable change stack: propose → accept/reject (set or per-file) → rollback."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileChange:
    path: str
    before: str
    after: str
    status: str = "pending"  # pending | accepted | rejected


@dataclass
class ChangeSet:
    id: str
    source: str
    created_at: float
    status: str  # pending | accepted | rejected | rolled_back | mixed
    files: list[FileChange] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "created_at": self.created_at,
            "status": self.status,
            "note": self.note,
            "files": [asdict(f) for f in self.files],
        }


def _store(data_dir: Path) -> Path:
    path = Path(data_dir) / "changes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file(data_dir: Path, change_id: str) -> Path:
    return _store(data_dir) / f"{change_id}.json"


def _load(data_dir: Path, change_id: str) -> ChangeSet | None:
    path = _file(data_dir, change_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    files = [
        FileChange(
            path=str(f["path"]),
            before=str(f.get("before", "")),
            after=str(f.get("after", "")),
            status=str(f.get("status") or "pending"),
        )
        for f in raw.get("files") or []
    ]
    return ChangeSet(
        id=str(raw["id"]),
        source=str(raw.get("source") or "tool"),
        created_at=float(raw.get("created_at") or 0),
        status=str(raw.get("status") or "pending"),
        files=files,
        note=str(raw.get("note") or ""),
    )


def _save(data_dir: Path, cs: ChangeSet) -> None:
    _file(data_dir, cs.id).write_text(json.dumps(cs.to_dict(), indent=2) + "\n", encoding="utf-8")


def _sync_set_status(cs: ChangeSet) -> None:
    if not cs.files:
        return
    statuses = {f.status for f in cs.files}
    if statuses == {"accepted"}:
        cs.status = "accepted"
    elif statuses == {"rejected"}:
        cs.status = "rejected"
    elif "pending" in statuses:
        cs.status = "pending" if statuses == {"pending"} else "mixed"
    else:
        cs.status = "mixed"


def _write_file(workspace: Path, fc: FileChange) -> None:
    root = workspace.resolve()
    target = (root / fc.path).resolve()
    target.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(fc.after, encoding="utf-8")


def list_changes(data_dir: Path, status: str | None = None) -> list[dict[str, Any]]:
    items: list[ChangeSet] = []
    for path in sorted(_store(data_dir).glob("*.json"), reverse=True):
        cs = _load(data_dir, path.stem)
        if cs and (status is None or cs.status == status):
            items.append(cs)
    return [c.to_dict() for c in items]


def propose(
    data_dir: Path,
    *,
    source: str,
    files: list[dict[str, str]],
    note: str = "",
) -> dict[str, Any]:
    parsed: list[FileChange] = []
    for item in files:
        path = str(item.get("path") or "").replace("\\", "/").strip()
        if not path or path.startswith("/") or ".." in Path(path).parts:
            raise ValueError(f"invalid path: {path}")
        parsed.append(
            FileChange(
                path=path,
                before=str(item.get("before", "")),
                after=str(item.get("after", "")),
                status="pending",
            )
        )
    if not parsed:
        raise ValueError("no files")
    cs = ChangeSet(
        id=uuid.uuid4().hex[:12],
        source=source or "tool",
        created_at=time.time(),
        status="pending",
        files=parsed,
        note=note or "",
    )
    _save(data_dir, cs)
    return cs.to_dict()


def get_change(data_dir: Path, change_id: str) -> dict[str, Any] | None:
    cs = _load(data_dir, change_id)
    return cs.to_dict() if cs else None


def accept(data_dir: Path, workspace: Path, change_id: str) -> dict[str, Any]:
    cs = _load(data_dir, change_id)
    if not cs:
        raise FileNotFoundError("change not found")
    if cs.status not in ("pending", "mixed"):
        raise ValueError(f"cannot accept status={cs.status}")
    for fc in cs.files:
        if fc.status != "pending":
            continue
        _write_file(workspace, fc)
        fc.status = "accepted"
    cs.status = "accepted"
    _save(data_dir, cs)
    return cs.to_dict()


def reject(data_dir: Path, change_id: str) -> dict[str, Any]:
    cs = _load(data_dir, change_id)
    if not cs:
        raise FileNotFoundError("change not found")
    if cs.status not in ("pending", "mixed"):
        raise ValueError(f"cannot reject status={cs.status}")
    for fc in cs.files:
        if fc.status == "pending":
            fc.status = "rejected"
    cs.status = "rejected"
    _save(data_dir, cs)
    return cs.to_dict()


def accept_file(data_dir: Path, workspace: Path, change_id: str, rel_path: str) -> dict[str, Any]:
    cs = _load(data_dir, change_id)
    if not cs:
        raise FileNotFoundError("change not found")
    if cs.status not in ("pending", "mixed"):
        raise ValueError(f"cannot accept file status={cs.status}")
    path = rel_path.replace("\\", "/").strip()
    found = False
    for fc in cs.files:
        if fc.path != path:
            continue
        found = True
        if fc.status != "pending":
            raise ValueError(f"file already {fc.status}")
        _write_file(workspace, fc)
        fc.status = "accepted"
        break
    if not found:
        raise FileNotFoundError("file not in change")
    _sync_set_status(cs)
    _save(data_dir, cs)
    return cs.to_dict()


def reject_file(data_dir: Path, change_id: str, rel_path: str) -> dict[str, Any]:
    cs = _load(data_dir, change_id)
    if not cs:
        raise FileNotFoundError("change not found")
    if cs.status not in ("pending", "mixed"):
        raise ValueError(f"cannot reject file status={cs.status}")
    path = rel_path.replace("\\", "/").strip()
    found = False
    for fc in cs.files:
        if fc.path != path:
            continue
        found = True
        if fc.status != "pending":
            raise ValueError(f"file already {fc.status}")
        fc.status = "rejected"
        break
    if not found:
        raise FileNotFoundError("file not in change")
    _sync_set_status(cs)
    _save(data_dir, cs)
    return cs.to_dict()


def rollback(data_dir: Path, workspace: Path, change_id: str) -> dict[str, Any]:
    cs = _load(data_dir, change_id)
    if not cs:
        raise FileNotFoundError("change not found")
    if cs.status not in ("accepted", "mixed"):
        raise ValueError(f"cannot rollback status={cs.status}")
    root = workspace.resolve()
    for fc in cs.files:
        if fc.status != "accepted":
            continue
        target = (root / fc.path).resolve()
        target.relative_to(root)
        if fc.before == "" and target.is_file():
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(fc.before, encoding="utf-8")
        fc.status = "pending"
    cs.status = "rolled_back"
    _save(data_dir, cs)
    return cs.to_dict()


def unified_diff(before: str, after: str, path: str) -> str:
    import difflib

    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
