"""Health check endpoints: /healthz, /readyz, /metrics-basic."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from flask import Flask, jsonify

from observability.metrics import get_metrics, increment_requests


def register_health_routes(app: Flask) -> None:
    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"}), 200

    @app.get("/readyz")
    def readyz():
        from app import DATABASE
        try:
            conn = sqlite3.connect(str(DATABASE), timeout=5)
            conn.execute("SELECT 1")
            db_dir = Path(str(DATABASE)).parent
            fd, tmp = tempfile.mkstemp(dir=db_dir, suffix=".tmp")
            try:
                with open(fd, "w") as f:
                    f.write("readyz")
            finally:
                Path(tmp).unlink(missing_ok=True)
            conn.close()
            return jsonify({"status": "ready"}), 200
        except Exception:
            return jsonify({"status": "not_ready"}), 503

    @app.get("/metrics-basic")
    def metrics_basic():
        return jsonify(get_metrics()), 200
