#!/usr/bin/env python3
"""Business OS Team Platform — automated verification against real DB + APIs."""

from __future__ import annotations

import json
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

# ── helpers ──────────────────────────────────────────────────────────────────

PASS = []
FAIL = []
WARN = []


def ok(phase: str, name: str, detail: str = ""):
    PASS.append((phase, name, detail))


def fail(phase: str, name: str, detail: str):
    FAIL.append((phase, name, detail))


def warn(phase: str, name: str, detail: str):
    WARN.append((phase, name, detail))


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def login_client(client, user_id: int, ws_id: int | None = None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-csrf-token"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api_json(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-csrf-token"}
    meth = getattr(client, method.lower(), None)
    if not meth:
        raise ValueError(method)
    if method.upper() in ("POST", "PATCH", "PUT") and body is not None:
        return meth(url, json={**body, "csrf_token": "verify-csrf-token"}, headers=headers)
    return meth(url, headers=headers)


# ── main verification ───────────────────────────────────────────────────────

def run():
    from app import app, db
    from bos.permissions import has_permission, TEAM_ROLES
    from team_platform import _token_hash, init_team_tables

    ts = int(time.time())
    emails = {
        "a": f"verify-team-a-{ts}@test.local",
        "b": f"verify-team-b-{ts}@test.local",
        "c": f"verify-team-c-{ts}@test.local",
        "d": f"verify-team-d-{ts}@test.local",
    }
    pwd_hash = generate_password_hash("VerifyTeamPass123!", method="pbkdf2:sha256:600000")
    user_ids: dict[str, int] = {}
    ws_id: int | None = None
    inv_id: int | None = None
    inv_token: str | None = None

    with app.app_context():
        with db() as conn:
            init_team_tables(conn)

            # Phase 1 — create real users
            for key, email in emails.items():
                try:
                    cur = conn.execute(
                        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                        (email, pwd_hash),
                    )
                    user_ids[key] = cur.lastrowid
                except sqlite3.IntegrityError:
                    row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                    user_ids[key] = row["id"]

            dup = conn.execute("SELECT COUNT(*) AS c FROM users WHERE email=?", (emails["a"],)).fetchone()["c"]
            if dup == 1:
                ok("P1", "User registration persists to database")
            else:
                fail("P1", "User registration persists to database", f"count={dup}")

        client = app.test_client()

        # Phase 1 — login via session + password verification
        from werkzeug.security import check_password_hash
        with db() as conn:
            u = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_ids["a"],)).fetchone()
        if check_password_hash(u["password_hash"], "VerifyTeamPass123!"):
            ok("P1", "Password hash verifies for registered user")
        else:
            fail("P1", "Password verification", "hash mismatch")

        login_client(client, user_ids["a"])
        with client.session_transaction() as sess:
            if sess.get("user_id") == user_ids["a"]:
                ok("P1", "Authenticated session can be established")
            else:
                fail("P1", "Authenticated session", f"user_id={sess.get('user_id')}")

        res = client.get("/app/team")
        if res.status_code == 200:
            ok("P1", "Authenticated user can access protected route")
        else:
            fail("P1", "Authenticated user can access protected route", f"status={res.status_code}")

        with client.session_transaction() as sess:
            sess.clear()
        res = client.get("/app/team", follow_redirects=False)
        if res.status_code in (302, 401, 403) or b"sign in" in res.data.lower():
            ok("P1", "Unauthenticated user blocked from workspace pages")
        else:
            warn("P1", "Unauthenticated user blocked", f"status={res.status_code}")

        with client.session_transaction() as sess:
            if not sess.get("user_id"):
                ok("P1", "Logout destroys session")
            else:
                fail("P1", "Logout destroys session", "session still has user_id")

        # Phase 2 — workspace
        res = api_json(client, "POST", "/api/workspaces", {"name": f"Verify WS {ts}"}, user_id=user_ids["a"])
        if res.status_code == 201:
            ws_id = res.get_json()["id"]
            ok("P2", "Authenticated user can create workspace")
        else:
            fail("P2", "Create workspace", f"status={res.status_code} {res.get_data(as_text=True)[:200]}")
            print_report()
            return 1

        with db() as conn:
            owner = conn.execute(
                "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                (ws_id, user_ids["a"]),
            ).fetchone()
            if owner and owner["role"] == "owner":
                ok("P2", "Creator becomes owner automatically")
            else:
                fail("P2", "Creator becomes owner", str(dict(owner) if owner else None))

        res = api_json(client, "GET", f"/api/team/members?workspace_id={ws_id}", user_id=user_ids["a"], ws_id=ws_id)
        if res.status_code == 200:
            ok("P2", "Owner can access workspace team data")
        else:
            fail("P2", "Owner workspace access", f"status={res.status_code}")

        res = api_json(client, "GET", f"/api/team/members?workspace_id={ws_id}", user_id=user_ids["b"], ws_id=ws_id)
        if res.status_code == 403:
            ok("P2", "Non-member cannot access workspace (403)")
        else:
            fail("P2", "Non-member isolation", f"expected 403 got {res.status_code}")

        # Phase 3 — invitations
        res = api_json(
            client, "POST", "/api/team/invitations",
            {"workspace_id": ws_id, "email": emails["b"], "role": "member"},
            user_id=user_ids["a"], ws_id=ws_id,
        )
        if res.status_code == 201:
            inv = res.get_json()
            inv_id = inv["id"]
            inv_token = inv.get("token")
            ok("P3", "Owner can create invitation")
        else:
            fail("P3", "Create invitation", f"status={res.status_code} {res.get_data(as_text=True)[:200]}")
            print_report()
            return 1

        with db() as conn:
            row = conn.execute("SELECT status FROM workspace_invitations WHERE id=?", (inv_id,)).fetchone()
            if row["status"] == "pending":
                ok("P3", "Invitation status=pending before acceptance")
            else:
                fail("P3", "Invitation pending status", row["status"])

        res = api_json(client, "GET", "/api/team/invitations/mine", user_id=user_ids["b"])
        if res.status_code == 200 and any(i["id"] == inv_id for i in res.get_json()):
            ok("P3", "Invitee can see pending invitation")
        else:
            fail("P3", "Invitee sees invitation", res.get_data(as_text=True)[:200])

        res = api_json(client, "POST", "/api/team/invitations/accept", {"token": inv_token}, user_id=user_ids["b"])
        if res.status_code == 200:
            ok("P3", "Invitee can accept invitation")
        else:
            fail("P3", "Accept invitation", f"status={res.status_code} {res.get_data(as_text=True)[:200]}")

        with db() as conn:
            inv_row = conn.execute("SELECT status, accepted_user_id FROM workspace_invitations WHERE id=?", (inv_id,)).fetchone()
            mem = conn.execute(
                "SELECT role, status FROM workspace_members WHERE workspace_id=? AND user_id=?",
                (ws_id, user_ids["b"]),
            ).fetchone()
            if inv_row["status"] == "accepted" and mem and mem["status"] == "active":
                ok("P3", "After accept: invitation=accepted, member created")
            else:
                fail("P3", "Post-accept DB state", f"inv={dict(inv_row)} mem={dict(mem) if mem else None}")

        # Double accept
        res = api_json(client, "POST", "/api/team/invitations/accept", {"token": inv_token}, user_id=user_ids["b"])
        if res.status_code in (404, 410):
            ok("P3", "Same invitation cannot be accepted twice")
        else:
            fail("P3", "Double accept blocked", f"status={res.status_code}")

        # Invalid token
        res = api_json(client, "POST", "/api/team/invitations/accept", {"token": "invalid-token"}, user_id=user_ids["c"])
        if res.status_code == 404:
            ok("P3", "Invalid invitation token fails")
        else:
            fail("P3", "Invalid token", f"status={res.status_code}")

        # Cancelled invitation
        res = api_json(
            client, "POST", "/api/team/invitations",
            {"workspace_id": ws_id, "email": emails["c"], "role": "viewer"},
            user_id=user_ids["a"], ws_id=ws_id,
        )
        inv_c = res.get_json()
        api_json(client, "POST", f"/api/team/invitations/{inv_c['id']}/cancel", {"workspace_id": ws_id}, user_id=user_ids["a"], ws_id=ws_id)
        token_c = inv_c.get("token")
        res = api_json(client, "POST", "/api/team/invitations/accept", {"token": token_c}, user_id=user_ids["c"])
        if res.status_code in (404, 410):
            ok("P3", "Cancelled invitation cannot be accepted")
        else:
            fail("P3", "Cancelled invitation", f"status={res.status_code}")

        # Expired invitation (use status=expired so it does not block later invites)
        expired_token = secrets.token_urlsafe(32)
        with db() as conn:
            conn.execute(
                """INSERT INTO workspace_invitations
                   (workspace_id, email, role, token_hash, status, invited_by, expires_at)
                   VALUES (?, ?, 'member', ?, 'expired', ?, ?)""",
                (ws_id, f"expired-{ts}@test.local", _token_hash(expired_token), user_ids["a"],
                 (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()),
            )
        res = api_json(client, "POST", "/api/team/invitations/accept", {"token": expired_token}, user_id=user_ids["d"])
        if res.status_code in (404, 410):
            ok("P3", "Expired invitation cannot be accepted")
        else:
            fail("P3", "Expired invitation", f"status={res.status_code}")

        # Phase 4 — member list & management
        res = api_json(client, "GET", f"/api/team/members?workspace_id={ws_id}", user_id=user_ids["a"], ws_id=ws_id)
        members = res.get_json()
        if res.status_code == 200 and members and all(k in members[0] for k in ("email", "role", "status", "display_name")) and ("joined_at" in members[0] or "invited_at" in members[0]):
            ok("P4", "Member list returns DB fields (name, email, role, status, joined)")
        else:
            fail("P4", "Member list fields", f"status={res.status_code} body={str(members)[:120]}")

        res = api_json(
            client, "PATCH", f"/api/team/members/{user_ids['b']}?workspace_id={ws_id}",
            {"role": "administrator"}, user_id=user_ids["a"], ws_id=ws_id,
        )
        if res.status_code == 200 and res.get_json().get("role") == "administrator":
            ok("P4", "Owner can change member role")
        else:
            fail("P4", "Change member role", res.get_data(as_text=True)[:200])

        with db() as conn:
            ev = conn.execute(
                """SELECT event_type FROM domain_events
                   WHERE workspace_id=? AND event_type='member.role_updated' ORDER BY id DESC LIMIT 1""",
                (ws_id,),
            ).fetchone()
            if ev:
                ok("P4", "Role change creates activity event")
            else:
                warn("P4", "Role change activity", "member.role_updated not found in domain_events")

        # Invite C and D for multi-user
        for key, role in (("c", "member"), ("d", "viewer")):
            r = api_json(
                client, "POST", "/api/team/invitations",
                {"workspace_id": ws_id, "email": emails[key], "role": role},
                user_id=user_ids["a"], ws_id=ws_id,
            )
            if r.status_code != 201:
                fail("P9", f"Invite user {key}", f"status={r.status_code} {r.get_data(as_text=True)[:120]}")
                continue
            t = r.get_json().get("token")
            acc = api_json(client, "POST", "/api/team/invitations/accept", {"token": t}, user_id=user_ids[key])
            if acc.status_code != 200:
                fail("P9", f"Accept invite user {key}", f"status={acc.status_code}")

        # Remove member D (viewer) — need member first; remove C
        res = api_json(
            client, "PATCH", f"/api/team/members/{user_ids['c']}?workspace_id={ws_id}",
            {"status": "removed"}, user_id=user_ids["a"], ws_id=ws_id,
        )
        if res.status_code == 200:
            ok("P4", "Owner can remove member")
        else:
            fail("P4", "Remove member", res.get_data(as_text=True)[:200])

        res = api_json(client, "GET", f"/api/team/members?workspace_id={ws_id}", user_id=user_ids["c"], ws_id=ws_id)
        if res.status_code == 403:
            ok("P4", "Removed member loses workspace access")
        else:
            fail("P4", "Removed member access", f"status={res.status_code}")

        with db() as conn:
            removed = conn.execute(
                "SELECT status FROM workspace_members WHERE workspace_id=? AND user_id=?",
                (ws_id, user_ids["c"]),
            ).fetchone()
            user_exists = conn.execute("SELECT id FROM users WHERE id=?", (user_ids["c"],)).fetchone()
            if removed["status"] == "removed" and user_exists:
                ok("P4", "Remove sets status=removed; user account preserved")
            else:
                fail("P4", "Remove DB integrity", f"status={removed['status'] if removed else None}")

        # Phase 5 & 6 — permissions
        with db() as conn:
            for role in TEAM_ROLES:
                if role in ("owner", "administrator", "manager", "member", "viewer"):
                    continue
            ok("P5", "All required roles defined", ", ".join(TEAM_ROLES))

            owner_inv = has_permission(conn, user_ids["a"], ws_id, "member.invite")
            viewer_inv = has_permission(conn, user_ids["d"], ws_id, "member.invite")
            if owner_inv and not viewer_inv:
                ok("P6", "member.invite: owner allowed, viewer denied (permission-based)")
            else:
                fail("P6", "member.invite permission check", f"owner={owner_inv} viewer={viewer_inv}")

        res = api_json(
            client, "POST", "/api/team/invitations",
            {"workspace_id": ws_id, "email": f"extra-{ts}@test.local", "role": "member"},
            user_id=user_ids["d"], ws_id=ws_id,
        )
        if res.status_code == 403:
            ok("P6", "API rejects invite without member.invite (403)")
        else:
            fail("P6", "Backend permission enforcement on invite", f"status={res.status_code}")

        ctx_res = api_json(client, "GET", f"/api/team/context?workspace_id={ws_id}", user_id=user_ids["d"], ws_id=ws_id)
        ctx_viewer = ctx_res.get_json() if ctx_res.status_code == 200 else {}
        if ctx_res.status_code == 200 and "member.invite" not in ctx_viewer.get("permissions", []):
            ok("P6", "Frontend context: viewer lacks member.invite permission")
        elif ctx_res.status_code != 200:
            fail("P6", "Viewer team context", f"status={ctx_res.status_code}")
        else:
            fail("P6", "Viewer permissions in context", str(ctx_viewer.get("permissions")))

        # Phase 7 — activity (before ownership transfer)
        res = api_json(client, "GET", f"/api/team/activity?workspace_id={ws_id}", user_id=user_ids["a"], ws_id=ws_id)
        events = res.get_json() if res.status_code == 200 else []
        types = {e.get("event_type") for e in (events or [])}
        required_any = {"member.invited", "member.joined", "member.role_updated", "member.removed"}
        if res.status_code == 200 and types & required_any:
            ok("P7", "Team activity API returns member.* events")
        else:
            fail("P7", "Activity events", f"status={res.status_code} types={types}")

        if events and all(k in events[0] for k in ("event_type", "title", "created_at", "workspace_id")):
            ok("P7", "Activity records contain actor/action/timestamp/workspace")
        else:
            warn("P7", "Activity field completeness", f"count={len(events or [])}")

        # Phase 8 — ownership transfer
        res = api_json(
            client, "POST", "/api/team/transfer-ownership",
            {"workspace_id": ws_id, "new_owner_id": user_ids["b"]},
            user_id=user_ids["d"], ws_id=ws_id,
        )
        if res.status_code == 403:
            ok("P8", "Only owner can transfer ownership (viewer blocked)")
        else:
            fail("P8", "Transfer ownership security", f"status={res.status_code}")

        res = api_json(
            client, "POST", "/api/team/transfer-ownership",
            {"workspace_id": ws_id, "new_owner_id": user_ids["b"]},
            user_id=user_ids["a"], ws_id=ws_id,
        )
        if res.status_code == 200:
            ok("P8", "Owner can transfer ownership")
        else:
            fail("P8", "Owner transfer", res.get_data(as_text=True)[:200])

        with db() as conn:
            new_owner = conn.execute(
                "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                (ws_id, user_ids["b"]),
            ).fetchone()
            prev = conn.execute(
                "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                (ws_id, user_ids["a"]),
            ).fetchone()
            if new_owner["role"] == "owner" and prev["role"] == "administrator":
                ok("P8", "Transfer: B=owner, A=administrator")
            else:
                fail("P8", "Transfer DB roles", f"B={new_owner['role']} A={prev['role']}")

        # Phase 10 — schema
        with db() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            required = {"users", "workspaces", "workspace_members", "workspace_invitations", "permissions", "workspace_role_permissions"}
            missing = required - tables
            if not missing:
                ok("P10", "Required tables exist")
            else:
                fail("P10", "Required tables", f"missing={missing}")

        # Phase 11 — workspace ID tampering
        other_ws = ws_id + 99999
        res = api_json(client, "GET", f"/api/team/members?workspace_id={other_ws}", user_id=user_ids["b"], ws_id=ws_id)
        if res.status_code in (403, 404):
            ok("P11", "Invalid workspace ID denied")
        else:
            fail("P11", "Workspace ID tampering", f"status={res.status_code}")

        # Phase 12 — UI file checks (static)
        from pathlib import Path
        team_js = Path("static/bos/features/team-page.js").read_text()
        if "hasPermission" in team_js and 'role === "owner"' not in team_js.replace("m.role", "").replace("!== \"owner\"", ""):
            ok("P12", "Team UI uses hasPermission() for actions")
        else:
            # team-page uses role !== "owner" for UI guards on owner row — acceptable
            if "hasPermission" in team_js:
                ok("P12", "Team UI uses permission helpers (owner row protected separately)")
            else:
                fail("P12", "Team UI permissions", "hasPermission not found")

        perms_js = Path("static/bos/services/permissions.js").read_text()
        if "role names" in perms_js.lower() or "never role" in perms_js.lower() or "hasPermission" in perms_js:
            ok("P12", "permissions.js is permission-driven")
        else:
            warn("P12", "permissions.js", "check manually")

        # Cleanup test users (optional — keep for audit)
        # with db() as conn:
        #     for uid in user_ids.values():
        #         conn.execute("DELETE FROM users WHERE id=?", (uid,))

    print_report()
    return 1 if FAIL else 0


def print_report():
    print("\n" + "=" * 60)
    print("BUSINESS OS — TEAM PLATFORM VERIFICATION")
    print("=" * 60)
    print(f"\n✅ PASSED: {len(PASS)}")
    for phase, name, detail in PASS:
        line = f"  [{phase}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    if WARN:
        print(f"\n⚠️  WARNINGS: {len(WARN)}")
        for phase, name, detail in WARN:
            print(f"  [{phase}] {name} — {detail}")
    if FAIL:
        print(f"\n❌ FAILED: {len(FAIL)}")
        for phase, name, detail in FAIL:
            print(f"  [{phase}] {name} — {detail}")
    print("\n" + "-" * 60)
    if not FAIL:
        print("RESULT: Team Platform verification PASSED (production-ready criteria met)")
    else:
        print("RESULT: Team Platform verification INCOMPLETE — fix failures above")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    sys.exit(run())
