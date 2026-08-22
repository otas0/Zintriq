"""Business Help Center — separate from customer /help."""

from __future__ import annotations

from typing import Any

BUSINESS_HELP_CATEGORIES = (
    {"id": "all", "label": "All"},
    {"id": "stores", "label": "Stores"},
    {"id": "storefront", "label": "Storefront & QR"},
    {"id": "account", "label": "Account"},
)

BUSINESS_HOW_IT_WORKS_STEPS = (
    "Create a store in Zintriq and add your products or menu items",
    "Customize your storefront and print or display Customer QR codes",
    "Shoppers scan the QR, browse on their phone, and check out when you enable cart",
)

BUSINESS_HELP_TOPICS: list[dict[str, Any]] = [
    {
        "slug": "how-it-works",
        "title": "How Zintriq works",
        "category": "stores",
        "summary": "Set up a store, share QR codes, and serve in-store shoppers.",
        "steps": BUSINESS_HOW_IT_WORKS_STEPS,
    },
    {
        "slug": "create-store",
        "title": "Creating a store",
        "category": "stores",
        "summary": "Add your first storefront and open the merchant dashboard.",
        "body": [
            "Sign in with your business account — separate from the shopper sign-in.",
            "From Stores, create a new store with a name and URL slug.",
            "You land on Products to add items, groups, and pricing.",
        ],
    },
    {
        "slug": "products-menu",
        "title": "Products & menu",
        "category": "stores",
        "summary": "Add items, organize groups, and control what shoppers see.",
        "body": [
            "Each product can have a photo, description, price, and optional variants.",
            "Use item groups to structure your menu (e.g. Drinks, Pastries).",
            "Toggle visibility and stock status before publishing to your storefront.",
        ],
    },
    {
        "slug": "cart-checkout",
        "title": "Cart & checkout settings",
        "category": "storefront",
        "summary": "Let shoppers add items and pay from their phone.",
        "body": [
            "Enable Allow add to cart on each product that should show a + button.",
            "Connect a payment method in store settings when checkout is available.",
            "Shoppers build a cart on their device; you fulfill the order in store.",
        ],
    },
    {
        "slug": "storefront",
        "title": "Storefront customization",
        "category": "storefront",
        "summary": "Branding, deals, and the customer-facing menu.",
        "body": [
            "Open Storefront from your store to preview and edit the shopper view.",
            "Upload a logo, cover image, and welcome message.",
            "Publish deals or highlights that appear on your menu.",
        ],
    },
    {
        "slug": "customer-qr",
        "title": "Customer QR codes",
        "category": "storefront",
        "summary": "Codes that open your menu when scanned in store.",
        "body": [
            "Go to Customer QR to download counter codes, table tents, or product tags.",
            "Each code links directly to your live storefront URL.",
            "Place codes at checkout, on tables, or on individual product labels.",
        ],
    },
    {
        "slug": "markets-venues",
        "title": "Markets & venues",
        "category": "stores",
        "summary": "List your store inside multi-shop directories.",
        "body": [
            "Some operators run venue directories with many tenants.",
            "Apply or accept an invite to appear under a market or food hall.",
            "Shoppers discover you from the venue page and your store still saves to their Places list.",
        ],
    },
    {
        "slug": "team",
        "title": "Team & access",
        "category": "account",
        "summary": "Invite staff and manage who can edit your stores.",
        "body": [
            "Open Team in Zintriq to invite members by email.",
            "Assign roles so only trusted people can change products or settings.",
            "Team members sign in with their own business accounts.",
        ],
    },
    {
        "slug": "account-security",
        "title": "Account & security",
        "category": "account",
        "summary": "Profile, password, and two-factor authentication.",
        "body": [
            "Use Account to update your email and change your password.",
            "Enable two-factor authentication for extra sign-in protection.",
            "Business and shopper accounts are separate — use the correct sign-in for each.",
        ],
    },
    {
        "slug": "shopper-experience",
        "title": "What shoppers see",
        "category": "storefront",
        "summary": "Preview the customer app and in-store flow.",
        "body": [
            "Shoppers use the Zintriq customer hub — Home, Places, and Account tabs.",
            "Scanning your QR opens your storefront; the store is saved under Places.",
            "See the customer Help center for the full shopper guide.",
        ],
        "link": {"label": "Customer Help center", "endpoint": "customer_help_home"},
    },
]


def business_help_topics(*, category: str | None = None) -> list[dict[str, Any]]:
    if not category or category == "all":
        return list(BUSINESS_HELP_TOPICS)
    return [t for t in BUSINESS_HELP_TOPICS if t["category"] == category]


def business_help_topic(slug: str) -> dict[str, Any] | None:
    for topic in BUSINESS_HELP_TOPICS:
        if topic["slug"] == slug:
            return topic
    return None


def register_business_help_platform(app) -> None:
    from flask import abort, render_template, request

    @app.get("/business/help")
    def business_help_home():
        cat = (request.args.get("category") or "all").strip().lower()
        if cat not in {c["id"] for c in BUSINESS_HELP_CATEGORIES}:
            cat = "all"
        return render_template(
            "business/help.html",
            module_id="help",
            categories=BUSINESS_HELP_CATEGORIES,
            active_category=cat,
            topics=business_help_topics(category=cat),
        )

    @app.get("/business/help/<slug>")
    def business_help_topic_view(slug: str):
        topic = business_help_topic(slug)
        if not topic:
            abort(404)
        related = [
            t for t in BUSINESS_HELP_TOPICS
            if t["category"] == topic["category"] and t["slug"] != slug
        ]
        return render_template(
            "business/help_topic.html",
            module_id="help",
            topic=topic,
            categories=BUSINESS_HELP_CATEGORIES,
            related_topics=related[:4],
        )
