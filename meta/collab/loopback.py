"""Loopback peer exchange. Local directories only — not a WAN sync product."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from meta.collab.store import mailbox_root, replica_id, sync_mailbox


class LoopbackError(ValueError):
    pass


def peers_path(data_root: Path) -> Path:
    folder = Path(data_root) / "collab"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "peers.json"


def list_peers(data_root: Path) -> list[Path]:
    path = peers_path(data_root)
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        peer = Path(str(row))
        if peer.is_dir():
            out.append(peer)
    return out


def register_peer(data_root: Path, peer_root: str) -> list[str]:
    raw = str(peer_root or "").strip()
    if not raw or "://" in raw or raw.startswith("\\\\"):
        raise LoopbackError("peer must be a local directory")
    path = Path(raw)
    if not path.is_dir():
        raise LoopbackError("peer directory missing")
    rows = [str(item) for item in list_peers(data_root)]
    resolved = str(path.resolve())
    if resolved not in rows:
        rows.append(resolved)
    peers_path(data_root).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def clocks_path(data_root: Path) -> Path:
    folder = Path(data_root) / "collab"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "clocks.json"


def load_clocks(data_root: Path) -> dict[str, int]:
    path = clocks_path(data_root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): int(value) for key, value in raw.items()}


def bump_clock(data_root: Path) -> dict[str, int]:
    clocks = load_clocks(data_root)
    ident = replica_id(data_root)
    clocks[ident] = int(clocks.get(ident) or 0) + 1
    clocks_path(data_root).write_text(json.dumps(clocks, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return clocks


def clock_skew(clocks: dict[str, int] | None) -> int:
    vals = [int(v) for v in (clocks or {}).values()]
    if not vals:
        return 0
    return max(vals) - min(vals)


def merge_clocks(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    out = dict(left)
    for key, value in right.items():
        out[key] = max(int(out.get(key) or 0), int(value))
    return out


def mailbox_merkle(data_root: Path) -> str:
    root = mailbox_root(data_root)
    digest = hashlib.sha256()
    if root.is_dir():
        for path in sorted(root.rglob("*.json")):
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def acks_path(data_root: Path) -> Path:
    folder = Path(data_root) / "collab"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "acks.json"


def ack_clock(data_root: Path, replica: str, clock: int) -> dict[str, int]:
    path = acks_path(data_root)
    rows: dict[str, int] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                rows = {str(k): int(v) for k, v in raw.items()}
        except (OSError, json.JSONDecodeError, ValueError):
            rows = {}
    ident = str(replica or replica_id(data_root))
    rows[ident] = max(int(rows.get(ident) or 0), int(clock))
    path.write_text(json.dumps(rows, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return rows


def exchange_peers(data_root: Path) -> dict:
    local = mailbox_root(data_root)
    copied = 0
    clocks = bump_clock(data_root)
    for peer in list_peers(data_root):
        dest = mailbox_root(peer)
        if dest.resolve() == local.resolve():
            continue
        remote_clocks = load_clocks(peer)
        merged = merge_clocks(clocks, remote_clocks)
        clocks_path(data_root).write_text(json.dumps(merged, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        clocks_path(peer).write_text(json.dumps(merged, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        clocks = merged
        if not local.is_dir():
            continue
        for folder in local.iterdir():
            if not folder.is_dir():
                continue
            target = dest / folder.name
            target.mkdir(parents=True, exist_ok=True)
            for path in folder.glob("*.json"):
                dest_file = target / path.name
                if dest_file.is_file() and hashlib.sha256(dest_file.read_bytes()).digest() == hashlib.sha256(path.read_bytes()).digest():
                    continue
                shutil.copy2(path, dest_file)
                copied += 1
        slugs = {path.stem for folder in dest.iterdir() if folder.is_dir() for path in folder.glob("*.json")}
        for slug in slugs:
            sync_mailbox(peer, slug)
            sync_mailbox(data_root, slug)
    status = {"acks": ack_clock(data_root, replica_id(data_root), int((clocks or {}).get(replica_id(data_root)) or 0)), "clocks": clocks, "copied": copied, "merkle": mailbox_merkle(data_root), "ok": True, "peers": [str(p) for p in list_peers(data_root)], "skew": clock_skew(clocks), "wan": False}
    (Path(data_root) / "collab").mkdir(parents=True, exist_ok=True)
    (Path(data_root) / "collab" / "status.json").write_text(json.dumps(status, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return status


def replicate_place(data_root: Path, place: dict) -> dict:
    folder = Path(data_root) / "world"
    folder.mkdir(parents=True, exist_ok=True)
    payload = dict(place or {})
    payload["roblox"] = False
    payload["wan"] = False
    (folder / "place.json").write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    copied = 0
    for peer in list_peers(data_root):
        dest = Path(peer) / "world"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / "place.json", dest / "place.json")
        copied += 1
    return {"copied": copied, "ok": True, "place": payload.get("place") or payload.get("title") or "", "roblox": False, "wan": False}
