#!/usr/bin/env python3
"""Local Studio/dev server on SQLite (ignores DATABASE_URL from .env.local)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["PORT"] = os.environ.get("PORT") or "5001"
os.environ["SQLITE_PATH"] = os.environ.get("SQLITE_PATH") or str(ROOT / "zintriq-dev.db")
os.environ.pop("DATABASE_URL", None)

_orig = Path.read_text


def _filtered(self, *args, **kwargs):
    text = _orig(self, *args, **kwargs)
    if self.name == ".env.local":
        lines = [line for line in text.splitlines() if not line.strip().startswith("DATABASE_URL")]
        return "\n".join(lines) + "\n"
    return text


Path.read_text = _filtered

import app as app_module  # noqa: E402
from desktop.server_mode import desktop_enabled, listen_port  # noqa: E402

os.environ.pop("DATABASE_URL", None)
if desktop_enabled():
    from pathlib import Path

    from desktop.server_mode import (
        acquire_instance_lock,
        ensure_desktop_schema,
        serve_desktop,
        stamp_desktop_schema,
        start_parent_watch,
    )

    data_dir = Path(os.environ["ZINTRIQ_DATA_DIR"])
    acquire_instance_lock(data_dir, listen_port())
    start_parent_watch()
    ensure_desktop_schema(data_dir / "zintriq.db")
    app_module.init_db()
    stamp_desktop_schema(data_dir / "zintriq.db")
    serve_desktop(app_module.app)
else:
    app_module.init_db()
    app_module.app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5001")),
        debug=False,
        use_reloader=False,
    )
