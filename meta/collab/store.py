"""Local CRDT document store under ZINTRIQ_DATA_DIR."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from meta.collab import dump_state, empty_clock, integrate_plain, load_state, merge, merge_clocks, new_replica, tick, to_plain

_LOCK = threading.Lock()


def replica_id(data_root: Path) -> str:
    path = Path(data_root) / "collab" / "replica_id"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        ident = path.read_text(encoding="utf-8").strip()
        if ident:
            return ident
    ident = new_replica()
    path.write_text(ident, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return ident


def _doc_path(data_root: Path, slug: str) -> Path:
    folder = Path(data_root) / "collab"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{slug}.json"


def load(data_root: Path, slug: str) -> dict:
    path = _doc_path(data_root, slug)
    replica = replica_id(data_root)
    if not path.is_file():
        return {"clock": empty_clock(), "doc": None, "replica": replica}
    try:
        state = load_state(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"clock": empty_clock(), "doc": None, "replica": replica}
    state["replica"] = replica
    return state


def save(data_root: Path, slug: str, state: dict) -> None:
    path = _doc_path(data_root, slug)
    path.write_text(
        dump_state(replica=state.get("replica") or replica_id(data_root), clock=state.get("clock") or {}, doc=state.get("doc")),
        encoding="utf-8",
    )


def push_plain(data_root: Path, slug: str, plain: object) -> dict:
    with _LOCK:
        state = load(data_root, slug)
        replica = state["replica"]
        clock, lamport = tick(state.get("clock") or {}, replica)
        doc = integrate_plain(state.get("doc"), plain, replica, lamport)
        next_state = {"clock": clock, "doc": doc, "replica": replica}
        save(data_root, slug, next_state)
        out = {"clock": clock, "plain": to_plain(doc), "replica": replica}
    publish_mailbox(data_root, slug)
    return out


def _room_path(data_root: Path, slug: str) -> Path:
    folder = Path(data_root) / "collab" / "rooms"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{slug}.json"


def join_room(data_root: Path, slug: str, replica_name: str = "") -> dict:
    replica = str(replica_name or "").strip() or replica_id(data_root)
    path = _room_path(data_root, slug)
    with _LOCK:
        room = {"replicas": []}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    room = loaded
            except (OSError, json.JSONDecodeError):
                room = {"replicas": []}
        names = [str(item) for item in room.get("replicas") or []]
        if replica not in names:
            names.append(replica)
        room = {"replicas": names, "slug": slug}
        path.write_text(json.dumps(room, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return {"replica": replica, "replicas": names, "slug": slug}


def push_replica(data_root: Path, slug: str, replica_name: str, plain: object) -> dict:
    replica = str(replica_name or "").strip() or replica_id(data_root)
    room = join_room(data_root, slug, replica)
    with _LOCK:
        path = Path(data_root) / "collab" / f"{slug}.{replica}.json"
        if path.is_file():
            try:
                state = load_state(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                state = {"clock": empty_clock(), "doc": None, "replica": replica}
        else:
            state = {"clock": empty_clock(), "doc": None, "replica": replica}
        clock, lamport = tick(state.get("clock") or {}, replica)
        doc = integrate_plain(state.get("doc"), plain, replica, lamport)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_state(replica=replica, clock=clock, doc=doc), encoding="utf-8")
        canonical = load(data_root, slug)
        merged = merge(canonical.get("doc"), doc) if canonical.get("doc") is not None else doc
        clocks = merge_clocks(canonical.get("clock") or {}, clock)
        save(data_root, slug, {"clock": clocks, "doc": merged, "replica": canonical.get("replica") or replica})
        path_out = mailbox_root(data_root) / replica / f"{slug}.json"
        path_out.parent.mkdir(parents=True, exist_ok=True)
        path_out.write_text(dump_state(replica=replica, clock=clocks, doc=merged), encoding="utf-8")
        return {"clock": clocks, "plain": to_plain(merged), "replica": replica, "replicas": room["replicas"]}


def room_state(data_root: Path, slug: str) -> dict:
    path = _room_path(data_root, slug)
    replicas = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            replicas = list(data.get("replicas") or [])
        except (OSError, json.JSONDecodeError):
            replicas = []
    canonical = load(data_root, slug)
    return {
        "clock": canonical.get("clock") or {},
        "plain": to_plain(canonical["doc"]) if canonical.get("doc") is not None else None,
        "replica": canonical.get("replica"),
        "replicas": replicas,
        "slug": slug,
    }


def pull_merged(data_root: Path, slug: str, incoming: dict | None = None) -> dict:
    with _LOCK:
        state = load(data_root, slug)
        if incoming and incoming.get("doc") is not None:
            merged_doc = merge(state.get("doc"), incoming.get("doc"))
            clock = merge_clocks(state.get("clock") or {}, incoming.get("clock") or {})
            state = {"clock": clock, "doc": merged_doc, "replica": state["replica"]}
            save(data_root, slug, state)
        plain = to_plain(state["doc"]) if state.get("doc") is not None else None
        return {"clock": state.get("clock") or {}, "doc": state.get("doc"), "plain": plain, "replica": state["replica"]}


def mailbox_root(data_root: Path) -> Path:
    raw = (os.environ.get("ZINTRIQ_COLLAB_DIR") or "").strip()
    base = Path(raw) if raw else Path(data_root)
    folder = base / "collab" / "mailbox"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def publish_mailbox(data_root: Path, slug: str) -> Path:
    replica = replica_id(data_root)
    state = load(data_root, slug)
    path = mailbox_root(data_root) / replica / f"{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dump_state(replica=replica, clock=state.get("clock") or {}, doc=state.get("doc")),
        encoding="utf-8",
    )
    return path


def sync_mailbox(data_root: Path, slug: str) -> dict:
    mine = replica_id(data_root)
    root = mailbox_root(data_root)
    merged = None
    peers = []
    if root.is_dir():
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or folder.name == mine:
                continue
            path = folder / f"{slug}.json"
            if not path.is_file():
                continue
            try:
                incoming = load_state(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            peers.append(folder.name)
            merged = pull_merged(data_root, slug, incoming)
    publish_mailbox(data_root, slug)
    state = merged or room_state(data_root, slug)
    state["peers"] = peers
    state["slug"] = slug
    return state


def presence_path(data_root: Path) -> Path:
    folder = Path(data_root) / "collab"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "presence.json"


def heartbeat(data_root: Path, replica: str = "") -> dict:
    ident = replica or replica_id(data_root)
    path = presence_path(data_root)
    rows = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                rows = raw
        except (OSError, json.JSONDecodeError):
            rows = {}
    import time

    now = time.time()
    rows[ident] = {"at": now, "host": "127.0.0.1", "replica": ident}
    stale = now - 30
    live = {key: val for key, val in rows.items() if float((val or {}).get("at") or 0) >= stale}
    path.write_text(json.dumps(live, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return {"ok": True, "peers": sorted(live), "replica": ident}


def list_presence(data_root: Path) -> list[str]:
    path = presence_path(data_root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, dict):
        return []
    return sorted(raw)


def append_conflict(data_root: Path, slug: str, note: str) -> Path:
    folder = Path(data_root) / "collab"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "conflicts.jsonl"
    line = json.dumps({"note": note, "slug": slug}, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path
