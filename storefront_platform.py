"""Customer storefront — store profile, hours, ratings, maps, deals, location."""

from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from observability.trace import trace, slow_query

_log = logging.getLogger("app.storefront")

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_LABELS = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}

DEFAULT_TIMEZONE = "Asia/Singapore"

_log = logging.getLogger("app.storefront")


def normalize_allow_cart(value) -> int:
    """Coerce item.allow_cart to 0/1 for templates and checkout."""
    try:
        return 1 if int(value or 0) else 0
    except (TypeError, ValueError):
        _log.debug("allow_cart_coerce_failed", exc_info=True, extra={"op": "normalize_allow_cart"})
        return 0


def item_cart_enabled(item, *, checkout_enabled: bool = False) -> bool:
    """True when checkout is on and the item is flagged for cart."""
    if not checkout_enabled:
        return False
    allow = item["allow_cart"] if isinstance(item, dict) else item["allow_cart"]
    return normalize_allow_cart(allow) == 1


def migrate_storefront_columns(conn) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(stores)")}
    for column, definition in (
        ("business_hours_json", "TEXT"),
        ("timezone", f"TEXT DEFAULT '{DEFAULT_TIMEZONE}'"),
        ("logo_url", "TEXT"),
        ("latitude", "REAL"),
        ("longitude", "REAL"),
    ):
        if column not in columns:
            conn.execute(f"ALTER TABLE stores ADD COLUMN {column} {definition}")
    migrate_store_deals(conn)
    migrate_store_inquiries(conn)
    migrate_store_analytics(conn)
    migrate_storefront_catalog_columns(conn)
    from guest_platform import migrate_guest_tables

    migrate_guest_tables(conn)
    from place_platform import migrate_place_tables

    migrate_place_tables(conn)
    from discover_platform import migrate_discover_columns

    migrate_discover_columns(conn)


def migrate_storefront_catalog_columns(conn) -> None:
    group_columns = {row["name"] for row in conn.execute("PRAGMA table_info(item_groups)")}
    if "prefix" not in group_columns:
        conn.execute("ALTER TABLE item_groups ADD COLUMN prefix TEXT")
    item_columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
    if "unit" not in item_columns:
        conn.execute("ALTER TABLE items ADD COLUMN unit TEXT")
    if "allow_cart" not in item_columns:
        conn.execute("ALTER TABLE items ADD COLUMN allow_cart INTEGER NOT NULL DEFAULT 0")


def category_label(prefix: str | None, index: int) -> str:
    """Uber-style category number — owner prefix or zero-padded index."""
    text = (prefix or "").strip()
    if text:
        return text.rstrip(".")
    return f"{index:02d}"


def migrate_store_inquiries(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS store_inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            item_id INTEGER,
            customer_name TEXT NOT NULL,
            customer_email TEXT,
            customer_phone TEXT,
            message TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE SET NULL
        );
    """)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(store_inquiries)")}
    if "status" not in columns:
        conn.execute("ALTER TABLE store_inquiries ADD COLUMN status TEXT DEFAULT 'new'")
    if "source_ref" not in columns:
        conn.execute("ALTER TABLE store_inquiries ADD COLUMN source_ref TEXT")


STOREFRONT_REF_SOURCES = ("discover", "place_directory", "brand_hub", "qr")


def remember_storefront_ref(flask_session, store_id: int, ref: str | None) -> None:
    if ref not in STOREFRONT_REF_SOURCES:
        return
    refs = dict(flask_session.get("storefront_refs") or {})
    refs[str(store_id)] = ref
    flask_session["storefront_refs"] = refs


def pop_storefront_ref(flask_session, store_id: int) -> str | None:
    refs = dict(flask_session.get("storefront_refs") or {})
    ref = refs.pop(str(store_id), None)
    flask_session["storefront_refs"] = refs
    return ref


def migrate_store_analytics(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS store_analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            item_id INTEGER,
            qr_code TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_store_analytics_store
            ON store_analytics_events(store_id, event_type, created_at);
    """)


def migrate_store_deals(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS store_deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            discount_type TEXT NOT NULL DEFAULT 'percent',
            discount_value REAL NOT NULL,
            label TEXT,
            starts_at TEXT,
            ends_at TEXT,
            featured INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            UNIQUE(store_id, item_id),
            FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        );
    """)


# ── Deals ─────────────────────────────────────────────────────────────────────

def _parse_deal_datetime(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", ""))
    except ValueError:
        _log.debug("deal_datetime_parse_failed", exc_info=True, extra={"op": "parse_deal_datetime"})
        return None


def deal_schedule_status(row: Any, *, now: datetime | None = None) -> str:
    """Return active | scheduled | expired for owner display."""
    if not row or row["status"] != "active":
        return str(row["status"]) if row else "inactive"
    now = now or datetime.utcnow()
    starts = row["starts_at"] if "starts_at" in row.keys() else None
    ends = row["ends_at"] if "ends_at" in row.keys() else None
    start_dt = _parse_deal_datetime(starts)
    end_dt = _parse_deal_datetime(ends)
    if start_dt and now < start_dt:
        return "scheduled"
    if end_dt and now > end_dt:
        return "expired"
    return "active"


def _deal_is_active(row: Any, *, now: datetime | None = None) -> bool:
    return deal_schedule_status(row, now=now) == "active"


def default_deal_label(discount_type: str, discount_value: float) -> str:
    if discount_type == "percent":
        return f"{int(round(discount_value))}% off"
    return f"${discount_value:.0f} off"


def compute_sale_price(original: float, discount_type: str, discount_value: float) -> float:
    if discount_type == "percent":
        sale = original * (1 - discount_value / 100.0)
    else:
        sale = original - discount_value
    return round(max(0.0, sale), 2)


def resolve_deal(row: Any, item_price: float) -> dict[str, Any]:
    """Turn a store_deals row + item price into customer-facing deal dict."""
    compare_at = round(float(item_price), 2)
    sale = compute_sale_price(compare_at, row["discount_type"], float(row["discount_value"]))
    label = (row["label"] or "").strip() or default_deal_label(row["discount_type"], float(row["discount_value"]))
    return {
        "id": row["id"],
        "item_id": row["item_id"],
        "discount_type": row["discount_type"],
        "discount_value": float(row["discount_value"]),
        "label": label,
        "featured": bool(row["featured"]),
        "compare_at_price": compare_at,
        "sale_price": sale,
    }


def list_store_deals(conn, store_id: int, *, active_only: bool = False) -> list:
    rows = conn.execute(
        """SELECT d.*, i.name AS item_name, i.price AS item_price, i.image_url, i.unit AS item_unit,
                  i.status AS item_status, i.allow_cart AS item_allow_cart
           FROM store_deals d
           JOIN items i ON i.id = d.item_id
           WHERE d.store_id = ?
           ORDER BY d.featured DESC, d.id DESC""",
        (store_id,),
    ).fetchall()
    if not active_only:
        return rows
    out = []
    for row in rows:
        if row["item_status"] != "published":
            continue
        if not _deal_is_active(row):
            continue
        out.append(row)
    return out


def active_deals_for_storefront(conn, store_id: int) -> list[dict[str, Any]]:
    """Active deals with computed prices, for carousel and item badges."""
    deals = []
    for row in list_store_deals(conn, store_id, active_only=True):
        deal = resolve_deal(row, float(row["item_price"]))
        deal["item_name"] = row["item_name"]
        deal["image_url"] = row["image_url"]
        deal["item_unit"] = row["item_unit"] if "item_unit" in row.keys() else None
        deal["item_allow_cart"] = normalize_allow_cart(
            row["item_allow_cart"] if "item_allow_cart" in row.keys() else 0
        )
        deals.append(deal)
    deals.sort(key=lambda d: (not d["featured"], d["item_name"]))
    return deals


def deals_map_for_items(conn, store_id: int) -> dict[int, dict[str, Any]]:
    return {d["item_id"]: d for d in active_deals_for_storefront(conn, store_id)}


def save_deal_from_form(conn, store_id: int, item_id: int, form, prefix: str = "") -> None:
    """Create/update/delete deal from owner form fields."""
    enabled = form.get(f"{prefix}deal_enabled_{item_id}") == "1"
    existing = conn.execute(
        "SELECT id FROM store_deals WHERE store_id = ? AND item_id = ?",
        (store_id, item_id),
    ).fetchone()
    if not enabled:
        if existing:
            conn.execute("DELETE FROM store_deals WHERE id = ?", (existing["id"],))
        return
    discount_type = form.get(f"{prefix}deal_type_{item_id}", "percent")
    if discount_type not in ("percent", "fixed"):
        discount_type = "percent"
    try:
        discount_value = float(form.get(f"{prefix}deal_value_{item_id}", "0") or 0)
    except (TypeError, ValueError):
        discount_value = 0
    if discount_value <= 0:
        if existing:
            conn.execute("DELETE FROM store_deals WHERE id = ?", (existing["id"],))
        return
    label = form.get(f"{prefix}deal_label_{item_id}", "").strip() or None
    featured = 1 if form.get(f"{prefix}deal_featured_{item_id}") == "1" else 0
    starts_at = form.get(f"{prefix}deal_starts_{item_id}", "").strip() or None
    ends_at = form.get(f"{prefix}deal_ends_{item_id}", "").strip() or None
    if existing:
        conn.execute(
            """UPDATE store_deals SET discount_type=?, discount_value=?, label=?, featured=?,
               starts_at=?, ends_at=?, status='active', updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (discount_type, discount_value, label, featured, starts_at, ends_at, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO store_deals (store_id, item_id, discount_type, discount_value, label, featured,
               starts_at, ends_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            (store_id, item_id, discount_type, discount_value, label, featured, starts_at, ends_at),
        )


def toggle_item_deal(
    conn,
    store_id: int,
    item_id: int,
    enabled: bool,
    *,
    discount_type: str = "percent",
    discount_value: float = 20.0,
) -> dict[str, Any]:
    """Quick on/off deal from products list — defaults to 20% off when enabling."""
    existing = conn.execute(
        "SELECT * FROM store_deals WHERE store_id = ? AND item_id = ?",
        (store_id, item_id),
    ).fetchone()
    if not enabled:
        if existing:
            conn.execute("DELETE FROM store_deals WHERE id = ?", (existing["id"],))
        return {"enabled": False, "item_id": item_id}
    if discount_type not in ("percent", "fixed"):
        discount_type = "percent"
    if discount_value <= 0:
        discount_value = 20.0
    label = default_deal_label(discount_type, discount_value)
    if existing:
        conn.execute(
            """UPDATE store_deals SET discount_type=?, discount_value=?, label=?, status='active',
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (discount_type, discount_value, label, existing["id"]),
        )
        row = conn.execute("SELECT * FROM store_deals WHERE id = ?", (existing["id"],)).fetchone()
    else:
        cur = conn.execute(
            """INSERT INTO store_deals (store_id, item_id, discount_type, discount_value, label, status)
               VALUES (?, ?, ?, ?, ?, 'active')""",
            (store_id, item_id, discount_type, discount_value, label),
        )
        row = conn.execute("SELECT * FROM store_deals WHERE id = ?", (cur.lastrowid,)).fetchone()
    item = conn.execute("SELECT price FROM items WHERE id = ? AND store_id = ?", (item_id, store_id)).fetchone()
    deal = resolve_deal(row, float(item["price"])) if row and item else None
    return {
        "enabled": True,
        "item_id": item_id,
        "label": deal["label"] if deal else label,
        "sale_price": deal["sale_price"] if deal else None,
    }


def parse_hours_json(raw: str | None) -> dict[str, dict[str, str | None]]:
    """Return normalized hours: { day: {open, close} | {} if closed }."""
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        _log.debug("hours_json_parse_failed", exc_info=True, extra={"op": "parse_hours_json"})
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str | None]] = {}
    for day in WEEKDAYS:
        block = data.get(day)
        if not isinstance(block, dict):
            continue
        if block.get("closed"):
            out[day] = {}
            continue
        open_t = _norm_time(block.get("open"))
        close_t = _norm_time(block.get("close"))
        if open_t and close_t:
            out[day] = {"open": open_t, "close": close_t}
    return out


def hours_from_form(form) -> str:
    """Build business_hours_json from owner settings form."""
    payload: dict[str, dict[str, str | bool]] = {}
    for day in WEEKDAYS:
        closed = form.get(f"hours_{day}_closed") == "1"
        if closed:
            payload[day] = {"closed": True}
            continue
        open_t = _norm_time(form.get(f"hours_{day}_open", ""))
        close_t = _norm_time(form.get(f"hours_{day}_close", ""))
        if open_t and close_t:
            payload[day] = {"open": open_t, "close": close_t}
        else:
            payload[day] = {"closed": True}
    return json.dumps(payload)


def _norm_time(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 5 and text[2] == ":":
        return text
    if len(text) >= 8 and text[2] == ":":
        return text[:5]
    return None


def _parse_clock(value: str) -> time | None:
    value = _norm_time(value)
    if not value:
        return None
    try:
        return time(int(value[:2]), int(value[3:5]))
    except (TypeError, ValueError):
        _log.debug("clock_time_parse_failed", exc_info=True, extra={"op": "parse_clock"})
        return None


def _fmt_time_12h(value: str) -> str:
    t = _parse_clock(value)
    if not t:
        return value
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    if t.minute:
        return f"{hour}:{t.minute:02d} {suffix}"
    return f"{hour} {suffix}"


def hours_status(store: dict | Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Open/closed state and display strings for storefront sidebar."""
    tz_name = (store.get("timezone") if isinstance(store, dict) else store["timezone"]) or DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        _log.debug("store_timezone_fallback", exc_info=True, extra={"op": "hours_status"})
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        tz_name = DEFAULT_TIMEZONE

    hours = parse_hours_json(
        store.get("business_hours_json") if isinstance(store, dict) else store["business_hours_json"]
    )
    legacy = (store.get("business_hours") if isinstance(store, dict) else store["business_hours"]) or ""

    if not hours:
        return {
            "has_structured_hours": False,
            "legacy_text": legacy.strip() or None,
            "is_open": None,
            "status_line": legacy.strip() or None,
            "weekly_lines": [],
            "timezone": tz_name,
        }

    now = now or datetime.now(tz)
    weekday = WEEKDAYS[now.weekday()]
    today = hours.get(weekday, {})
    now_t = now.time()

    is_open: bool | None = None
    status_line: str | None = None

    if today.get("open") and today.get("close"):
        open_t = _parse_clock(today["open"])
        close_t = _parse_clock(today["close"])
        if open_t and close_t:
            if open_t <= close_t:
                is_open = open_t <= now_t < close_t
            else:
                is_open = now_t >= open_t or now_t < close_t
            if is_open:
                status_line = f"Open until {_fmt_time_12h(today['close'])}"
            else:
                next_open = _next_open_line(hours, weekday, now)
                status_line = next_open or f"Closed · opens {_fmt_time_12h(today['open'])}"
    else:
        next_open = _next_open_line(hours, weekday, now)
        status_line = next_open or "Closed today"

    weekly_lines = []
    for day in WEEKDAYS:
        block = hours.get(day, {})
        label = WEEKDAY_LABELS[day]
        if block.get("open") and block.get("close"):
            weekly_lines.append(
                f"{label}: {_fmt_time_12h(block['open'])} – {_fmt_time_12h(block['close'])}"
            )
        else:
            weekly_lines.append(f"{label}: Closed")

    return {
        "has_structured_hours": True,
        "legacy_text": legacy.strip() or None,
        "is_open": is_open,
        "status_line": status_line,
        "weekly_lines": weekly_lines,
        "timezone": tz_name,
    }


def _next_open_line(hours: dict, start_day: str, now: datetime) -> str | None:
    start_idx = WEEKDAYS.index(start_day)
    for offset in range(1, 8):
        day = WEEKDAYS[(start_idx + offset) % 7]
        block = hours.get(day, {})
        if block.get("open") and block.get("close"):
            day_label = "Tomorrow" if offset == 1 else WEEKDAY_LABELS[day]
            return f"Closed · opens {day_label} {_fmt_time_12h(block['open'])}"
    return None


def store_rating_summary(conn, store_id: int) -> dict[str, Any]:
    row = conn.execute(
        """SELECT AVG(rating) AS avg_rating, COUNT(*) AS rating_count
           FROM feedback_records
           WHERE store_id = ? AND rating IS NOT NULL AND rating > 0""",
        (store_id,),
    ).fetchone()
    count = int(row["rating_count"] or 0) if row else 0
    if count <= 0:
        return {"average": None, "count": 0, "display": None}
    avg = round(float(row["avg_rating"]), 1)
    return {
        "average": avg,
        "count": count,
        "display": f"{avg} ★ ({count} rating{'s' if count != 1 else ''})",
    }


def store_public_reviews(conn, store_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
    """Reviews shown on the customer storefront (native + synced plugins)."""
    rows = conn.execute(
        """SELECT fr.id, fr.rating, fr.comment, fr.customer_name, fr.source, fr.external_platform,
                  fr.created_at, fr.updated_at
           FROM feedback_records fr
           WHERE fr.store_id = ?
             AND (
               (fr.comment IS NOT NULL AND TRIM(fr.comment) != '')
               OR (fr.rating IS NOT NULL AND fr.rating > 0)
             )
             AND COALESCE(fr.status, 'new') NOT IN ('hidden', 'spam', 'deleted')
           ORDER BY COALESCE(fr.updated_at, fr.created_at) DESC
           LIMIT ?""",
        (store_id, limit),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        comment = (r["comment"] or "").strip()
        name = (r["customer_name"] or "").strip() or "Customer"
        platform = (r["external_platform"] or r["source"] or "").strip()
        out.append({
            "id": int(r["id"]),
            "rating": int(r["rating"]) if r["rating"] is not None else None,
            "comment": comment,
            "customer_name": name,
            "platform": platform,
            "created_at": r["updated_at"] or r["created_at"],
        })
    return out


def maps_directions_url(address: str | None) -> str | None:
    text = (address or "").strip()
    if not text:
        return None
    return f"https://www.openstreetmap.org/search?query={quote(text)}"


def maps_embed_url(lat: float, lng: float, *, zoom: int = 15) -> str:
    delta = 0.012 / max(zoom / 15, 1)
    bbox = f"{lng - delta},{lat - delta},{lng + delta},{lat + delta}"
    marker = f"{lat},{lng}"
    params = urllib.parse.urlencode({"bbox": bbox, "layer": "mapnik", "marker": marker})
    return f"https://www.openstreetmap.org/export/embed.html?{params}"


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def format_distance_km(km: float) -> str:
    if km < 1:
        return f"{int(round(km * 1000))} m away"
    return f"{km:.1f} km away"


def geocode_address(address: str | None) -> tuple[float, float] | None:
    """Best-effort geocode via OpenStreetMap Nominatim (no API key)."""
    text = (address or "").strip()
    if not text:
        return None
    params = urllib.parse.urlencode({"q": text, "format": "json", "limit": "1"})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Zintriq-Storefront/1.0"})
    try:
        with trace("geocode.osm", op="geocode_address"):
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        _log.debug("geocode_request_failed", exc_info=True, extra={"op": "geocode_address"})
        return None
    if not data:
        return None
    try:
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (KeyError, TypeError, ValueError):
        _log.debug("geocode_response_parse_failed", exc_info=True, extra={"op": "geocode_address"})
        return None


def sync_store_geocode(conn, store_id: int, address: str | None) -> None:
    coords = geocode_address(address)
    if coords:
        conn.execute(
            "UPDATE stores SET latitude=?, longitude=? WHERE id=?",
            (coords[0], coords[1], store_id),
        )
    else:
        conn.execute(
            "UPDATE stores SET latitude=NULL, longitude=NULL WHERE id=?",
            (store_id,),
        )


STOREFRONT_EVENT_TYPES = ("qr_scan", "storefront_view", "item_view", "inquiry", "brand_hub_click")


def analytics_period_clause(period: str, *, column: str = "created_at") -> tuple[str, list]:
    if period == "today":
        return f"date({column})=date('now')", []
    if period == "7d":
        return f"{column} >= datetime('now', '-7 days')", []
    if period == "30d":
        return f"{column} >= datetime('now', '-30 days')", []
    return "1=1", []


def record_store_event(
    conn,
    store_id: int,
    event_type: str,
    *,
    item_id: int | None = None,
    qr_code: str | None = None,
    metadata: dict | None = None,
) -> None:
    if event_type not in STOREFRONT_EVENT_TYPES:
        return
    conn.execute(
        """INSERT INTO store_analytics_events (store_id, event_type, item_id, qr_code, metadata)
           VALUES (?, ?, ?, ?, ?)""",
        (
            store_id,
            event_type,
            item_id,
            qr_code,
            json.dumps(metadata or {}),
        ),
    )


def save_store_inquiry(
    conn,
    store_id: int,
    *,
    customer_name: str,
    customer_email: str | None = None,
    customer_phone: str | None = None,
    message: str | None = None,
    item_id: int | None = None,
    customer_id: int | None = None,
    visitor_key: str | None = None,
    source_ref: str | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO store_inquiries
           (store_id, item_id, customer_id, customer_name, customer_email, customer_phone, message, status, source_ref)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)""",
        (store_id, item_id, customer_id, customer_name, customer_email, customer_phone, message, source_ref),
    )
    inquiry_id = int(cur.lastrowid)
    meta = {"inquiry_id": inquiry_id}
    if visitor_key:
        meta["visitor_key"] = visitor_key
    if source_ref:
        meta["source_ref"] = source_ref
    record_store_event(conn, store_id, "inquiry", item_id=item_id, metadata=meta)
    return inquiry_id


def notify_owner_new_inquiry(conn, store_id: int, inquiry_id: int, *, inbox_url: str) -> bool:
    from email_delivery import send_transactional_email

    row = conn.execute(
        """SELECT s.name AS store_name, u.email AS owner_email,
                  si.customer_name, si.customer_email, si.customer_phone, si.message,
                  si.source_ref, i.name AS item_name
           FROM store_inquiries si
           JOIN stores s ON s.id = si.store_id
           JOIN users u ON u.id = s.owner_id
           LEFT JOIN items i ON i.id = si.item_id
           WHERE si.id = ? AND si.store_id = ?""",
        (inquiry_id, store_id),
    ).fetchone()
    if not row or not row["owner_email"]:
        return False

    source = row["source_ref"] or "shop"
    source_labels = {
        "discover": "Discover",
        "place_directory": "Place directory",
        "brand_hub": "Brand hub",
        "qr": "QR",
    }
    source_label = source_labels.get(source, "Shop")

    subject = f"New customer request — {row['store_name']}"
    contact_bits = []
    if row["customer_email"]:
        contact_bits.append(row["customer_email"])
    if row["customer_phone"]:
        contact_bits.append(row["customer_phone"])
    contact_line = " · ".join(contact_bits) or "No email or phone provided"

    text = (
        f"New request for {row['store_name']} (via {source_label}).\n\n"
        f"From: {row['customer_name']}\n"
        f"Contact: {contact_line}\n"
    )
    if row["item_name"]:
        text += f"Product: {row['item_name']}\n"
    if row["message"]:
        text += f"\nMessage:\n{row['message']}\n"
    text += f"\nOpen inbox: {inbox_url}\n"

    html = (
        f"<p>New request for <strong>{row['store_name']}</strong> (via {source_label}).</p>"
        f"<p><strong>{row['customer_name']}</strong><br>{contact_line}</p>"
    )
    if row["item_name"]:
        html += f"<p>Product: {row['item_name']}</p>"
    if row["message"]:
        html += f"<p>{row['message']}</p>"
    html += f'<p><a href="{inbox_url}">View in inbox</a></p>'

    return send_transactional_email(row["owner_email"], subject, text, html_body=html)


def _pct(part: int, whole: int) -> int | None:
    if whole <= 0:
        return None
    return round((part / whole) * 100)


def _count_store_events(conn, store_id: int, event_type: str, period: str) -> int:
    clause, params = analytics_period_clause(period)
    row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM store_analytics_events
            WHERE store_id = ? AND event_type = ? AND {clause}""",
        [store_id, event_type, *params],
    ).fetchone()
    return int(row["c"] or 0)


def _count_landing_scans(conn, store_id: int, period: str) -> int:
    clause, params = analytics_period_clause(period, column="e.created_at")
    try:
        row = conn.execute(
            f"""SELECT COUNT(*) AS c
                FROM qr_experience_analytics_events e
                JOIN qr_experiences x ON x.id = e.experience_id
                WHERE x.store_id = ? AND e.event_type IN ('qr_scan', 'experience_view')
                  AND {clause}""",
            [store_id, *params],
        ).fetchone()
        return int(row["c"] or 0)
    except Exception:
        logging.getLogger("app.storefront").error("landing_scan_count_failed", exc_info=True)  # SUSPECT: swallow may hide bug — see Phase 1.1
        return 0


def storefront_insights(conn, store_id: int, *, period: str = "7d") -> dict[str, Any]:
    """Funnel metrics for owner Insights overview."""
    shop_qr_scans = _count_store_events(conn, store_id, "qr_scan", period)
    landing_scans = _count_landing_scans(conn, store_id, period)
    qr_scans = shop_qr_scans + landing_scans
    shop_views = _count_store_events(conn, store_id, "storefront_view", period)
    item_views = _count_store_events(conn, store_id, "item_view", period)

    inq_clause, inq_params = analytics_period_clause(period)
    inq_row = conn.execute(
        f"""SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) AS new_count
            FROM store_inquiries WHERE store_id = ? AND {inq_clause}""",
        [store_id, *inq_params],
    ).fetchone()
    inquiries = int(inq_row["total"] or 0)
    new_inquiries = int(inq_row["new_count"] or 0)

    clause, params = analytics_period_clause(period, column="e.created_at")
    with slow_query("storefront_top_items"):
        top_items = conn.execute(
            f"""SELECT e.item_id, i.name, COUNT(*) AS views
                FROM store_analytics_events e
                LEFT JOIN items i ON i.id = e.item_id
                WHERE e.store_id = ? AND e.event_type = 'item_view' AND e.item_id IS NOT NULL
                  AND {clause}
                GROUP BY e.item_id ORDER BY views DESC LIMIT 5""",
            [store_id, *params],
        ).fetchall()

    recent_inquiries = list_store_inquiries(conn, store_id, limit=5)
    discovery = _storefront_discovery_metrics(conn, store_id, period)

    return {
        "period": period,
        "qr_scans": qr_scans,
        "shop_qr_scans": shop_qr_scans,
        "landing_scans": landing_scans,
        "shop_views": shop_views,
        "item_views": item_views,
        "inquiries": inquiries,
        "new_inquiries": new_inquiries,
        "discovery": discovery,
        "funnel": [
            {"key": "qr_scans", "label": "QR & landing", "count": qr_scans},
            {"key": "shop_views", "label": "Shop views", "count": shop_views},
            {"key": "item_views", "label": "Product views", "count": item_views},
            {"key": "inquiries", "label": "Requests", "count": inquiries},
        ],
        "conversion": {
            "shop_from_qr": _pct(shop_views, qr_scans),
            "items_from_shop": _pct(item_views, shop_views),
            "requests_from_shop": _pct(inquiries, shop_views),
        },
        "top_items": [dict(r) for r in top_items],
        "recent_inquiries": recent_inquiries,
    }


def _storefront_discovery_metrics(conn, store_id: int, period: str) -> dict[str, Any]:
    """Guest discovery — returning visitors and brand hub clicks."""
    visit_clause, visit_params = analytics_period_clause(period, column="last_visited_at")
    unique_row = conn.execute(
        f"""SELECT COUNT(DISTINCT visitor_key) AS c FROM guest_store_visits
            WHERE store_id = ? AND {visit_clause}""",
        [store_id, *visit_params],
    ).fetchone()
    returning_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM guest_store_visits
            WHERE store_id = ? AND visit_count >= 2 AND {visit_clause}""",
        [store_id, *visit_params],
    ).fetchone()
    unique_visitors = int(unique_row["c"] or 0)
    returning_visitors = int(returning_row["c"] or 0)
    brand_hub_clicks = _count_store_events(conn, store_id, "brand_hub_click", period)
    clause2, params2 = analytics_period_clause(period)
    place_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM store_analytics_events
            WHERE store_id = ? AND event_type = 'storefront_view'
              AND metadata LIKE '%place_directory%' AND {clause2}""",
        [store_id, *params2],
    ).fetchone()
    place_directory_views = int(place_row["c"] or 0)
    discover_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM store_analytics_events
            WHERE store_id = ? AND event_type = 'storefront_view'
              AND metadata LIKE '%discover%' AND {clause2}""",
        [store_id, *params2],
    ).fetchone()
    discover_views = int(discover_row["c"] or 0)
    inq_clause, inq_params = analytics_period_clause(period, column="created_at")
    discover_inq_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM store_inquiries
            WHERE store_id = ? AND source_ref = 'discover' AND {inq_clause}""",
        [store_id, *inq_params],
    ).fetchone()
    discover_inquiries = int(discover_inq_row["c"] or 0)
    place_inq_row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM store_inquiries
            WHERE store_id = ? AND source_ref = 'place_directory' AND {inq_clause}""",
        [store_id, *inq_params],
    ).fetchone()
    place_directory_inquiries = int(place_inq_row["c"] or 0)

    return {
        "unique_visitors": unique_visitors,
        "returning_visitors": returning_visitors,
        "returning_pct": _pct(returning_visitors, unique_visitors),
        "brand_hub_clicks": brand_hub_clicks,
        "place_directory_views": place_directory_views,
        "discover_views": discover_views,
        "discover_inquiries": discover_inquiries,
        "discover_request_rate": _pct(discover_inquiries, discover_views),
        "place_directory_inquiries": place_directory_inquiries,
        "place_directory_request_rate": _pct(place_directory_inquiries, place_directory_views),
    }


INQUIRY_STATUSES = ("new", "read", "archived")


def list_store_inquiries(
    conn,
    store_id: int,
    *,
    q: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = """
        SELECT si.*, i.name AS item_name
        FROM store_inquiries si
        LEFT JOIN items i ON i.id = si.item_id
        WHERE si.store_id = ?
    """
    params: list[Any] = [store_id]
    if status:
        query += " AND si.status = ?"
        params.append(status)
    if q:
        like = f"%{q.strip()}%"
        query += " AND (si.customer_name LIKE ? OR si.customer_email LIKE ? OR si.customer_phone LIKE ? OR si.message LIKE ?)"
        params.extend([like, like, like, like])
    query += " ORDER BY si.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_store_inquiry(conn, store_id: int, inquiry_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT si.*, i.name AS item_name
           FROM store_inquiries si
           LEFT JOIN items i ON i.id = si.item_id
           WHERE si.id = ? AND si.store_id = ?""",
        (inquiry_id, store_id),
    ).fetchone()
    return dict(row) if row else None


def update_inquiry_status(conn, store_id: int, inquiry_id: int, status: str) -> bool:
    if status not in INQUIRY_STATUSES:
        return False
    cur = conn.execute(
        "UPDATE store_inquiries SET status = ? WHERE id = ? AND store_id = ?",
        (status, inquiry_id, store_id),
    )
    return cur.rowcount > 0


def build_location_profile(store: dict | Any) -> dict[str, Any]:
    lat = store.get("latitude") if isinstance(store, dict) else store["latitude"]
    lng = store.get("longitude") if isinstance(store, dict) else store["longitude"]
    try:
        lat_f = float(lat) if lat is not None else None
        lng_f = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat_f = lng_f = None
    if lat_f is None or lng_f is None:
        return {"lat": None, "lng": None, "map_embed_url": None}
    return {
        "lat": lat_f,
        "lng": lng_f,
        "map_embed_url": maps_embed_url(lat_f, lng_f),
    }


def build_store_profile(conn, store: dict | Any) -> dict[str, Any]:
    """Aggregate sidebar data for customer storefront."""
    store_id = store["id"] if hasattr(store, "__getitem__") else store.id
    hours = hours_status(store)
    ratings = store_rating_summary(conn, store_id)
    reviews = store_public_reviews(conn, store_id)
    address = (store.get("address") if isinstance(store, dict) else store["address"]) or ""
    logo_url = (store.get("logo_url") if isinstance(store, dict) else store["logo_url"]) or ""
    location = build_location_profile(store)
    return {
        "name": store.get("name") if isinstance(store, dict) else store["name"],
        "description": (store.get("description") if isinstance(store, dict) else store["description"]) or "",
        "logo_url": logo_url.strip() or None,
        "address": address.strip() or None,
        "contact": (store.get("contact") if isinstance(store, dict) else store["contact"]) or None,
        "background_image": (store.get("background_image") if isinstance(store, dict) else store["background_image"]) or None,
        "hours": hours,
        "ratings": ratings,
        "reviews": reviews,
        "maps_url": maps_directions_url(address),
        "location": location,
    }
