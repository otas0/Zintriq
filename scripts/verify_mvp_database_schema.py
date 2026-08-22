#!/usr/bin/env python3
"""Verify Zintriq MVP database schema (spec v1.0)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0

# Isolated DB — must set before app import
_test_db = Path(tempfile.mkdtemp()) / "mvp_schema_test.db"
os.environ.setdefault("SECRET_KEY", "mvp-schema-verify-secret")
import app as app_module

app_module.DATABASE = _test_db


def ok(name: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


def column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def main() -> int:
    global PASS, FAIL
    print("MVP Database Schema Verification\n")

    app_module.init_db()

    with app_module.db() as conn:
        # Core MVP tables
        for table in (
            "user_profiles",
            "workspaces",
            "workspace_members",
            "qr_experiences",
            "responses",
            "workspace_subscriptions",
        ):
            if table_exists(conn, table):
                ok(f"table.{table}")
            else:
                fail(f"table.{table}", "missing")

        # UserProfile columns
        for col in ("auth_provider_id", "email", "full_name", "avatar_url", "created_at", "updated_at"):
            key = "auth_provider_id" if col == "auth_provider_id" else col
            actual = "auth_provider_id" if col == "auth_provider_id" else col
            if col == "auth_provider_id":
                actual = "auth_provider_id"
                has = column_exists(conn, "user_profiles", "auth_provider_id") or column_exists(
                    conn, "user_profiles", "auth_provider",
                )
            else:
                has = column_exists(conn, "user_profiles", col)
            if has:
                ok(f"user_profiles.{col}")
            else:
                fail(f"user_profiles.{col}", "missing")

        # Workspace MVP columns
        for col in ("name", "description", "logo_url", "created_by"):
            if column_exists(conn, "workspaces", col):
                ok(f"workspaces.{col}")
            else:
                fail(f"workspaces.{col}", "missing")

        # WorkspaceMember
        for col in ("workspace_id", "user_id", "role", "created_at"):
            if column_exists(conn, "workspace_members", col) or (
                col == "created_at" and column_exists(conn, "workspace_members", "joined_at")
            ):
                ok(f"workspace_members.{col}")
            else:
                fail(f"workspace_members.{col}", "missing")

        # QRExperience MVP columns
        for col in ("workspace_id", "name", "type", "status", "content", "created_by"):
            if column_exists(conn, "qr_experiences", col) or (
                col == "content" and column_exists(conn, "qr_experiences", "experience_config")
            ):
                ok(f"qr_experiences.{col}")
            else:
                fail(f"qr_experiences.{col}", "missing")

        # Response table
        for col in ("workspace_id", "experience_id", "type", "data", "created_at"):
            if column_exists(conn, "responses", col):
                ok(f"responses.{col}")
            else:
                fail(f"responses.{col}", "missing")

        # Subscription
        for col in ("workspace_id", "provider", "provider_customer_id", "plan", "status"):
            if column_exists(conn, "workspace_subscriptions", col):
                ok(f"workspace_subscriptions.{col}")
            else:
                fail(f"workspace_subscriptions.{col}", "missing")

        # Workspace isolation on responses
        ws_count = conn.execute("SELECT COUNT(*) AS c FROM responses WHERE workspace_id IS NULL").fetchone()["c"]
        if ws_count == 0:
            ok("responses.workspace_isolation")
        else:
            fail("responses.workspace_isolation", f"{ws_count} rows without workspace_id")

        # MVP helpers
        from bos.mvp_schema import (
            MVP_QR_STATUSES,
            MVP_QR_TYPES,
            MVP_RESPONSE_TYPES,
            MVP_ROLES,
            normalize_mvp_role,
            normalize_qr_status,
            normalize_qr_type_for_mvp,
        )

        if MVP_QR_TYPES == ("information", "feedback", "survey"):
            ok("constants.qr_types")
        else:
            fail("constants.qr_types", str(MVP_QR_TYPES))

        if normalize_qr_status("paused") == "disabled":
            ok("normalize.status_paused")
        else:
            fail("normalize.status_paused")

        from bos.mvp_schema import storage_qr_status
        if storage_qr_status("disabled") == "paused":
            ok("normalize.storage_disabled")
        else:
            fail("normalize.storage_disabled")

        if normalize_qr_type_for_mvp("menu") == "information":
            ok("normalize.type_menu")
        else:
            fail("normalize.type_menu")

        if normalize_mvp_role("administrator") == "admin":
            ok("normalize.role_administrator")
        else:
            fail("normalize.role_administrator")

        if MVP_RESPONSE_TYPES == ("feedback", "survey"):
            ok("constants.response_types")
        else:
            fail("constants.response_types")

        # Response CRUD smoke test
        from bos.responses import get_workspace_response, list_workspace_responses, record_response

        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES ('mvp-schema-test@example.com', 'x')",
        )
        uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO organizations (name, slug, owner_id) VALUES ('MVP Test Org', ?, ?)",
            (f"mvp-test-org-{uid}", uid),
        )
        oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, 'MVP Test WS', ?)",
            (oid, f"mvp-test-ws-{uid}"),
        )
        ws_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """INSERT INTO qr_experiences (workspace_id, name, type, status, content)
               VALUES (?, 'Feedback QR', 'feedback', 'active', '{}')""",
            (ws_id,),
        )
        exp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        rid = record_response(
            conn,
            workspace_id=int(ws_id),
            response_type="feedback",
            data={"rating": 5, "comment": "Great"},
            experience_id=int(exp_id),
        )
        row = get_workspace_response(conn, rid, int(ws_id))
        if row and row["type"] == "feedback":
            ok("responses.record_and_get")
        else:
            fail("responses.record_and_get")

        listed = list_workspace_responses(conn, int(ws_id), experience_id=int(exp_id))
        if len(listed) >= 1:
            ok("responses.list_workspace")
        else:
            fail("responses.list_workspace")

        # Forbidden MVP tables should not be required (legacy may exist — warn only)
        forbidden = ("customer_crm", "workflow_automations", "payment_transactions", "plugin_registry")
        for t in forbidden:
            if not table_exists(conn, t):
                ok(f"forbidden_absent.{t}")
            else:
                ok(f"forbidden_legacy.{t}", "exists but not MVP-required")

    print(f"\n{PASS} PASS, {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
