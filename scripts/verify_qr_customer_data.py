#!/usr/bin/env python3
"""QR Customer Data Layer — verification (real DB, no mock data)."""

from __future__ import annotations

import os
import sys
import time

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS, FAIL = [], []


def ok(name, detail=""):
    PASS.append((name, detail))


def fail(name, detail):
    FAIL.append((name, detail))


def login_client(client, user_id, ws_id=None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-qr-customer-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-qr-customer-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
        payload = {**(body or {}), "csrf_token": "verify-qr-customer-csrf"}
        return meth(url, json=payload, headers=headers)
    return meth(url, headers=headers)


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from qr_experience_platform import init_qr_experience_tables
    from qr_experience_runtime import init_runtime_tables
    from qr_customer_data import init_qr_customer_tables

    ts = int(time.time())
    pwd = generate_password_hash("QrCustomerVerify!123", method="pbkdf2:sha256:600000")

    with app.app_context():
        client = app.test_client()

        with db() as conn:
            init_qr_experience_tables(conn)
            init_runtime_tables(conn)
            init_qr_customer_tables(conn)

            for table in ("qr_customer_interactions", "qr_customer_identities"):
                if table_exists(conn, table):
                    ok(f"Table.{table}")
                else:
                    fail(f"Table.{table}", "missing")

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"qcd_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"QCD Org {ts}", f"qcd-org-{ts}", owner_id),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"qcd-org-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"QCD WS {ts}", f"qcd-ws-{ts}"),
            )
            ws_id = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"qcd-ws-{ts}",)
            ).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )
            store_id = conn.execute(
                "INSERT INTO stores (name, slug, owner_id, workspace_id) VALUES (?, ?, ?, ?)",
                (f"QCD Store {ts}", f"qcd-store-{ts}", owner_id, ws_id),
            ).lastrowid
            conn.execute(
                """INSERT INTO check_in_points (store_id, point_code, name, status, active_status)
                   VALUES (?, ?, ?, 'published', 'active')""",
                (store_id, f"qcdci{ts}", f"Arrival {ts}"),
            )

        r = api(client, "POST", "/api/qr-experiences", {
            "name": f"Customer Data Experience {ts}",
            "template_id": "feedback_only",
        }, owner_id, ws_id)
        if r.status_code != 201:
            fail("Experience.create", f"status={r.status_code}")
            return 1
        exp = r.get_json()
        eid = exp["id"]
        code = exp.get("code")
        ok("Experience.create", f"id={eid}")

        r = api(client, "POST", f"/api/qr-experiences/{eid}/publish", {}, owner_id, ws_id)
        if r.status_code != 200:
            fail("Experience.publish", f"status={r.status_code}")
            return 1
        published = r.get_json()
        slug = published.get("public_slug")
        ok("Experience.publish", slug or "")

        r = client.get(f"/qr/{code}", follow_redirects=True)
        if r.status_code == 200:
            ok("QR.scan_landing", f"/qr/{code}")
        else:
            fail("QR.scan_landing", f"status={r.status_code}")

        with db() as conn:
            scans = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_customer_interactions
                   WHERE workspace_id=? AND interaction_type='qr_scan'""",
                (ws_id,),
            ).fetchone()["c"]
            customers = conn.execute(
                "SELECT COUNT(DISTINCT customer_id) AS c FROM qr_customer_interactions WHERE workspace_id=?",
                (ws_id,),
            ).fetchone()["c"]
            sess_row = conn.execute(
                "SELECT session_id, customer_id FROM qr_experience_sessions WHERE experience_id=? ORDER BY id DESC LIMIT 1",
                (eid,),
            ).fetchone()
        if scans >= 1:
            ok("Interaction.qr_scan", f"count={scans}")
        else:
            fail("Interaction.qr_scan", "no qr_scan row")
        if customers >= 1 and sess_row and sess_row["customer_id"]:
            ok("Customer.from_scan", f"customer_id={sess_row['customer_id']}")
            customer_id = int(sess_row["customer_id"])
        else:
            fail("Customer.from_scan", "no customer linked to session")
            return 1

        sid = sess_row["session_id"]

        r = api(client, "POST", f"/api/runtime/sessions/{sid}/booking", {
            "customer_name": "Alex Customer",
            "starts_at": "2026-08-15 14:00:00",
            "customer_email": f"alex{ts}@test.local",
        })
        if r.status_code == 201 and r.get_json().get("booking_id"):
            booking_id = r.get_json()["booking_id"]
            ok("Runtime.booking", f"id={booking_id}")
        else:
            fail("Runtime.booking", f"status={r.status_code}")
            booking_id = None

        with db() as conn:
            if booking_id:
                link = conn.execute(
                    """SELECT i.*, b.contact_id FROM qr_customer_interactions i
                       LEFT JOIN bookings b ON b.id=i.related_object_id
                       WHERE i.workspace_id=? AND i.interaction_type='booking_created' AND i.related_object_id=?""",
                    (ws_id, booking_id),
                ).fetchone()
                if link and int(link["customer_id"]) == customer_id:
                    ok("Booking.customer_link", f"customer_id={customer_id}")
                else:
                    fail("Booking.customer_link", "missing or wrong customer")
                if link and link["experience_id"] == eid:
                    ok("Booking.experience_source", f"experience_id={eid}")
                else:
                    fail("Booking.experience_source", "experience not stored")

            fid = conn.execute(
                """INSERT INTO feedback_records
                   (store_id, workspace_id, feedback_type, source_type, source, rating, comment, status, updated_at)
                   VALUES (?, ?, 'feedback', 'qr', 'qr', 5, 'Great table service', 'new', datetime('now'))""",
                (store_id, ws_id),
            ).lastrowid

        r = client.get(f"/e/{slug}?from=qr")
        if r.status_code == 200:
            ok("Session.new_scan")
        else:
            fail("Session.new_scan", f"status={r.status_code}")

        with db() as conn:
            sid2 = conn.execute(
                "SELECT session_id FROM qr_experience_sessions WHERE experience_id=? ORDER BY id DESC LIMIT 1",
                (eid,),
            ).fetchone()["session_id"]

        r = api(client, "POST", f"/api/runtime/sessions/{sid2}/complete-survey", {
            "feedback_id": fid,
            "customer_name": "Alex Customer",
            "customer_email": f"alex{ts}@test.local",
            "type": "feedback",
        })
        if r.status_code == 201:
            ok("Runtime.feedback_complete")
        else:
            fail("Runtime.feedback_complete", f"status={r.status_code}")

        with db() as conn:
            fb = conn.execute(
                "SELECT customer_id FROM feedback_records WHERE id=?", (fid,),
            ).fetchone()
            fb_int = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_customer_interactions
                   WHERE workspace_id=? AND interaction_type='feedback_submitted' AND related_object_id=?""",
                (ws_id, fid),
            ).fetchone()["c"]
        if fb and int(fb["customer_id"] or 0) == customer_id:
            ok("Feedback.customer_link", f"customer_id={customer_id}")
        else:
            fail("Feedback.customer_link", f"customer_id={fb['customer_id'] if fb else None}")
        if fb_int >= 1:
            ok("Feedback.interaction_record")
        else:
            fail("Feedback.interaction_record", "missing feedback_submitted")

        r = client.get(f"/e/{slug}?from=qr")
        with db() as conn:
            sid3 = conn.execute(
                "SELECT session_id FROM qr_experience_sessions WHERE experience_id=? ORDER BY id DESC LIMIT 1",
                (eid,),
            ).fetchone()["session_id"]

        r = api(client, "POST", f"/api/runtime/sessions/{sid3}/checkin", {
            "customer_name": "Jordan Guest",
        })
        if r.status_code == 201 and r.get_json().get("check_in_id"):
            checkin_id = r.get_json()["check_in_id"]
            ok("Runtime.checkin", f"id={checkin_id}")
        else:
            fail("Runtime.checkin", f"status={r.status_code}")
            checkin_id = None

        if checkin_id:
            with db() as conn:
                ci = conn.execute(
                    """SELECT i.* FROM qr_customer_interactions i
                       WHERE workspace_id=? AND interaction_type='checkin_completed' AND related_object_id=?""",
                    (ws_id, checkin_id),
                ).fetchone()
            if ci and int(ci["customer_id"]):
                ok("Checkin.customer_link", f"customer_id={ci['customer_id']}")
            else:
                fail("Checkin.customer_link", "missing interaction")

        r = api(client, "GET", f"/api/customers/qr/{customer_id}", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200:
            detail = r.get_json()
            if detail.get("timeline") and detail.get("interactions"):
                ok("Customer.detail_timeline", f"timeline={len(detail['timeline'])} interactions={len(detail['interactions'])}")
            else:
                fail("Customer.detail_timeline", "empty timeline or interactions")
            if detail.get("qr_sources"):
                ok("Customer.qr_sources", f"count={len(detail['qr_sources'])}")
            else:
                fail("Customer.qr_sources", "no sources")
            if detail.get("bookings") and booking_id:
                ok("Customer.detail_bookings")
            elif booking_id:
                fail("Customer.detail_bookings", "missing bookings in detail")
        else:
            fail("Customer.detail_api", f"status={r.status_code}")

        r = api(client, "GET", "/api/customers/qr/dashboard", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("total_customers", 0) >= 1:
            ok("Dashboard.summary", f"total={r.get_json()['total_customers']}")
        else:
            fail("Dashboard.summary", f"status={r.status_code}")

        r = api(client, "GET", "/api/customers/qr?type=booking_created", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200:
            listed = r.get_json().get("customers") or []
            if any(c["id"] == customer_id for c in listed):
                ok("Customer.filter_booking")
            else:
                fail("Customer.filter_booking", "customer not in filtered list")
        else:
            fail("Customer.filter_booking", f"status={r.status_code}")

        r = api(client, "GET", f"/api/customers/qr?q=alex{ts}", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and (r.get_json().get("customers") or []):
            ok("Customer.search_email")
        else:
            fail("Customer.search_email", f"status={r.status_code}")

    print(f"\n{'=' * 60}\nQR Customer Data Layer Verification\n{'=' * 60}")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
