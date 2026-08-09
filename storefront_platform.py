"""Customer storefront — store profile, hours, ratings, maps, deals, location."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE SET NULL
        );
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
        """SELECT d.*, i.name AS item_name, i.price AS item_price, i.image_url, i.status AS item_status
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


def parse_hours_json(raw: str | None) -> dict[str, dict[str, str | None]]:
    """Return normalized hours: { day: {open, close} | {} if closed }."""
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
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


def maps_directions_url(address: str | None) -> str | None:
    text = (address or "").strip()
    if not text:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={quote(text)}"


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
    req = urllib.request.Request(url, headers={"User-Agent": "MarketQR-Storefront/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if not data:
        return None
    try:
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (KeyError, TypeError, ValueError):
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


def save_store_inquiry(
    conn,
    store_id: int,
    *,
    customer_name: str,
    customer_email: str | None = None,
    customer_phone: str | None = None,
    message: str | None = None,
    item_id: int | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO store_inquiries (store_id, item_id, customer_name, customer_email, customer_phone, message)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (store_id, item_id, customer_name, customer_email, customer_phone, message),
    )
    return int(cur.lastrowid)


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
        "maps_url": maps_directions_url(address),
        "location": location,
    }
