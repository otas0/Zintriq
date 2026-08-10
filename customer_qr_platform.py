"""Owner-facing Customer QR hub — manage URLs and legacy link resolution."""


def manage_qr_hub_path(store_slug: str) -> str:
    return f"/manage/{store_slug}/qr"


def manage_landing_qr_href(conn, experience_id: int, *, builder: bool = False) -> str:
    """Deep link into Landing QR builder or detail for a store-bound experience."""
    row = conn.execute(
        "SELECT store_id FROM qr_experiences WHERE id=?",
        (int(experience_id),),
    ).fetchone()
    if row and row["store_id"]:
        store = conn.execute(
            "SELECT slug FROM stores WHERE id=?",
            (int(row["store_id"]),),
        ).fetchone()
        if store and store["slug"]:
            frag = "builder" if builder else "experience"
            return f"/manage/{store['slug']}/landing-qr#{frag}/{int(experience_id)}"
    frag = "builder" if builder else "experience"
    return f"/app/store#{frag}/{int(experience_id)}"
