"""Customer Help Center — topics and articles (Uber Eats–style)."""

from __future__ import annotations

from typing import Any

HELP_CATEGORIES = (
    {"id": "all", "label": "All"},
    {"id": "shopping", "label": "Shopping"},
    {"id": "places", "label": "Places"},
    {"id": "account", "label": "Account"},
)

HOW_IT_WORKS_STEPS = (
    "Scan the QR code at the shop counter or on a product tag",
    "Browse the menu and add items to your cart on mobile devices",
    "Pay in store or check out online — the shop saves here under Places",
)

HELP_TOPICS: list[dict[str, Any]] = [
    {
        "slug": "how-it-works",
        "title": "How in-store shopping works",
        "category": "shopping",
        "summary": "Scan, browse, and check out on your phone.",
        "steps": HOW_IT_WORKS_STEPS,
    },
    {
        "slug": "scan-qr",
        "title": "Scanning a QR code",
        "category": "shopping",
        "summary": "Open your camera or tap a link to reach a shop menu.",
        "body": [
            "Find the Zintriq QR code at the checkout counter, on a table tent, or on a product tag.",
            "Point your phone camera at the code — most phones open the link automatically.",
            "You land on that store’s menu. No app download required.",
        ],
    },
    {
        "slug": "cart-checkout",
        "title": "Cart & checkout",
        "category": "shopping",
        "summary": "Add items and pay when the shop has payments enabled.",
        "body": [
            "Items must have Allow add to cart enabled by the merchant to show a + button.",
            "Your cart is saved on this device for each store.",
            "Checkout uses the payment method the shop connected (e.g. PayPal demo or live payments).",
        ],
    },
    {
        "slug": "saved-places",
        "title": "Saved places",
        "category": "places",
        "summary": "Shops you scan appear under Places for quick return visits.",
        "body": [
            "Every time you open a store via QR, it is added to Places.",
            "Use search and sort on the Places tab to find shops in busy markets.",
            "Tap a shop to open its menu again — no need to rescan if you still have the link.",
        ],
    },
    {
        "slug": "markets-venues",
        "title": "Markets & venues",
        "category": "places",
        "summary": "Browse multi-shop directories like food halls and markets.",
        "body": [
            "On Home, scroll to Markets & venues to explore directories with many shops.",
            "Tap a venue to see all tenants and open individual storefronts.",
            "Scanning any shop inside still saves it to your Places list.",
        ],
    },
    {
        "slug": "remember-me",
        "title": "Remember me & sync",
        "category": "account",
        "summary": "Bring your saved places to a new phone without a password.",
        "body": [
            "On Places, enter your email under Sync across devices.",
            "We email you a one-time link — open it on the new device to restore your list.",
            "Creating an account also keeps your profile and places tied to you.",
        ],
    },
    {
        "slug": "account-profile",
        "title": "Account & profile",
        "category": "account",
        "summary": "Sign in, edit your profile, and log out.",
        "body": [
            "Use Account to log in or create a profile with username and photo.",
            "Guests can browse and shop without an account; sign in to sync across devices.",
            "Business owners use a separate sign-in and Help center at /business/help.",
        ],
    },
]


def help_topics(*, category: str | None = None) -> list[dict[str, Any]]:
    if not category or category == "all":
        return list(HELP_TOPICS)
    return [t for t in HELP_TOPICS if t["category"] == category]


def help_topic(slug: str) -> dict[str, Any] | None:
    for topic in HELP_TOPICS:
        if topic["slug"] == slug:
            return topic
    return None


def register_help_platform(app) -> None:
    from flask import abort, render_template, request

    @app.get("/help")
    def customer_help_home():
        cat = (request.args.get("category") or "all").strip().lower()
        if cat not in {c["id"] for c in HELP_CATEGORIES}:
            cat = "all"
        return render_template(
            "customer/help.html",
            preview_mode=False,
            categories=HELP_CATEGORIES,
            active_category=cat,
            topics=help_topics(category=cat),
        )

    @app.get("/help/<slug>")
    def customer_help_topic(slug: str):
        topic = help_topic(slug)
        if not topic:
            abort(404)
        related = [t for t in HELP_TOPICS if t["category"] == topic["category"] and t["slug"] != slug]
        return render_template(
            "customer/help_topic.html",
            preview_mode=False,
            topic=topic,
            categories=HELP_CATEGORIES,
            related_topics=related[:4],
        )
