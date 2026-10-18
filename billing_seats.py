"""Team seats for Zintriq SaaS billing (collaboration)."""

from __future__ import annotations

SEAT_LIMITS = {"personal": 1, "team": 50}


def ensure_seat_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS zintriq_org_members (
            owner_user_id INTEGER NOT NULL,
            member_user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'editor',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (owner_user_id, member_user_id)
        )
        """
    )


def seat_limit_for_plan(plan: str) -> int:
    return int(SEAT_LIMITS.get(str(plan or "").strip() or "personal", 1))


def members_of(conn, owner_user_id: int) -> list[dict]:
    ensure_seat_schema(conn)
    rows = conn.execute(
        """
        SELECT owner_user_id, member_user_id, role
        FROM zintriq_org_members
        WHERE owner_user_id=?
        ORDER BY member_user_id
        """,
        (int(owner_user_id),),
    ).fetchall()
    out = []
    for row in rows:
        out.append(
            {
                "owner_user_id": row["owner_user_id"] if not isinstance(row, tuple) else row[0],
                "member_user_id": row["member_user_id"] if not isinstance(row, tuple) else row[1],
                "role": row["role"] if not isinstance(row, tuple) else row[2],
            }
        )
    return out


def seats_used(conn, owner_user_id: int) -> int:
    return 1 + len(members_of(conn, owner_user_id))


def can_collaborate(conn, owner_user_id: int, member_user_id: int) -> bool:
    if int(owner_user_id) == int(member_user_id):
        return True
    ensure_seat_schema(conn)
    row = conn.execute(
        """
        SELECT 1 FROM zintriq_org_members
        WHERE owner_user_id=? AND member_user_id=?
        """,
        (int(owner_user_id), int(member_user_id)),
    ).fetchone()
    return row is not None


def invite_member(conn, owner_user_id: int, member_user_id: int, *, plan: str, role: str = "editor") -> None:
    ensure_seat_schema(conn)
    if int(owner_user_id) == int(member_user_id):
        raise ValueError("owner already occupies a seat")
    limit = seat_limit_for_plan(plan)
    if seats_used(conn, owner_user_id) >= limit:
        raise ValueError("seat limit reached")
    conn.execute(
        """
        INSERT OR IGNORE INTO zintriq_org_members (owner_user_id, member_user_id, role)
        VALUES (?, ?, ?)
        """,
        (int(owner_user_id), int(member_user_id), str(role or "editor")),
    )
