"""Independent collab sync daemon. Polls the mailbox on this machine (127.0.0.1 data dir)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from meta.collab.loopback import exchange_peers
from meta.collab.store import heartbeat, mailbox_root, replica_id, sync_mailbox


def discover_slugs(data_root: Path) -> list[str]:
    slugs: set[str] = set()
    root = mailbox_root(data_root)
    if not root.is_dir():
        return []
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            slugs.add(path.stem)
    return sorted(slugs)


def tick(data_root: Path) -> dict:
    beat = heartbeat(data_root, replica_id(data_root))
    loop = exchange_peers(data_root)
    rows = []
    for slug in discover_slugs(data_root):
        state = sync_mailbox(data_root, slug)
        rows.append({"peers": state.get("peers") or [], "slug": slug})
    return {"ok": True, "loopback": loop, "presence": beat.get("peers") or [], "synced": rows}


def pid_path(data_root: Path) -> Path:
    folder = Path(data_root) / "collab"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "daemon.pid"


def write_pid(data_root: Path) -> None:
    path = pid_path(data_root)
    path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def run_forever(data_root: Path, interval: float = 0.5) -> None:
    write_pid(data_root)
    while True:
        tick(data_root)
        time.sleep(max(0.1, float(interval)))


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    raw = (os.environ.get("ZINTRIQ_DATA_DIR") or "").strip()
    if args:
        raw = args[0]
    if not raw:
        raise SystemExit("ZINTRIQ_DATA_DIR is required")
    interval = float(os.environ.get("ZINTRIQ_COLLAB_INTERVAL") or 0.5)
    run_forever(Path(raw), interval=interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
