"""Public Zintriq product website helpers — marketing pages, not Builder/app surfaces.

Marketing never frames permanent Customer/Business (or Website/IoT/AI/Commerce) product
silos. Templates are compositions of the five primitives.

Copy uses dotted i18n keys (page.*) resolved via i18n_platform.translate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent

TranslateFn = Callable[..., str]


def _t(key: str, translate: TranslateFn | None = None, **vars: Any) -> str:
    if translate is not None:
        return translate(key, **vars) if vars else translate(key)
    from i18n_platform import translate as default_translate

    return default_translate(key, **vars) if vars else default_translate(key)


# Technical package ids stay stable; display copy is composition-first (i18n keys).
TEMPLATE_MARKETING = {
    "zintriq-customer": {
        "id": "zintriq-customer",
        "name_key": "page.templates.zintriq_customer.name",
        "description_key": "page.templates.zintriq_customer.description",
        "category_key": "page.templates.zintriq_customer.category",
        "publisher": "Zintriq",
        "primitives": ["Data", "Interface", "Connection", "Publish"],
        "official": True,
    },
    "zintriq-business": {
        "id": "zintriq-business",
        "name_key": "page.templates.zintriq_business.name",
        "description_key": "page.templates.zintriq_business.description",
        "category_key": "page.templates.zintriq_business.category",
        "publisher": "Zintriq",
        "primitives": ["Data", "Interface", "Logic", "Connection", "Publish"],
        "official": True,
    },
    # Deprecated umbrella — kept for legacy project lookups only; not sold in activation.
    "zintriq-system": {
        "id": "zintriq-system",
        "name_key": "page.templates.zintriq_system.name",
        "description_key": "page.templates.zintriq_system.description",
        "category_key": "page.templates.zintriq_system.category",
        "publisher": "Zintriq",
        "primitives": ["Data", "Interface", "Logic", "Connection", "Publish"],
        "official": False,
    },
}

PRICING_PLANS = [
    {
        "id": "free",
        "name_key": "page.pricing.plan.free.name",
        "price": "$0",
        "period_key": "page.pricing.plan.free.period",
        "blurb_key": "page.pricing.plan.free.blurb",
        "cta_key": "page.pricing.plan.free.cta",
        "featured": False,
        "feature_keys": [
            "page.pricing.plan.free.f1",
            "page.pricing.plan.free.f2",
            "page.pricing.plan.free.f3",
            "page.pricing.plan.free.f4",
            "page.pricing.plan.free.f5",
        ],
    },
    {
        "id": "starter",
        "name_key": "page.pricing.plan.starter.name",
        "price": "$29",
        "period_key": "page.pricing.plan.starter.period",
        "blurb_key": "page.pricing.plan.starter.blurb",
        "cta_key": "page.pricing.plan.starter.cta",
        "featured": True,
        "feature_keys": [
            "page.pricing.plan.starter.f1",
            "page.pricing.plan.starter.f2",
            "page.pricing.plan.starter.f3",
            "page.pricing.plan.starter.f4",
            "page.pricing.plan.starter.f5",
        ],
    },
    {
        "id": "pro",
        "name_key": "page.pricing.plan.pro.name",
        "price": "$99",
        "period_key": "page.pricing.plan.pro.period",
        "blurb_key": "page.pricing.plan.pro.blurb",
        "cta_key": "page.pricing.plan.pro.cta",
        "featured": False,
        "feature_keys": [
            "page.pricing.plan.pro.f1",
            "page.pricing.plan.pro.f2",
            "page.pricing.plan.pro.f3",
            "page.pricing.plan.pro.f4",
            "page.pricing.plan.pro.f5",
        ],
    },
]

COMPOSITIONS = [
    {
        "slug": "official-starter",
        "name_key": "page.compositions.official.name",
        "headline_key": "page.compositions.official.headline",
        "lead_key": "page.compositions.official.lead",
        "primitives": ["Data", "Interface", "Logic", "Connection", "Publish"],
        "status_key": "page.common.status.implemented",
    },
    {
        "slug": "booking",
        "name_key": "page.compositions.booking.name",
        "headline_key": "page.compositions.booking.headline",
        "lead_key": "page.compositions.booking.lead",
        "primitives": ["Data", "Interface", "Logic", "Publish"],
        "status_key": "page.common.status.implemented",
    },
    {
        "slug": "commerce-qr",
        "name_key": "page.compositions.commerce.name",
        "headline_key": "page.compositions.commerce.headline",
        "lead_key": "page.compositions.commerce.lead",
        "primitives": ["Data", "Interface", "Logic", "Connection", "Publish"],
        "status_key": "page.common.status.implemented",
    },
]

CONNECTIONS = [
    {
        "name_key": "page.connections.qr.name",
        "body_key": "page.connections.qr.body",
        "status_key": "page.common.status.implemented",
    },
    {
        "name_key": "page.connections.payments.name",
        "body_key": "page.connections.payments.body",
        "status_key": "page.common.status.integrated",
    },
    {
        "name_key": "page.connections.messaging.name",
        "body_key": "page.connections.messaging.body",
        "status_key": "page.common.status.integrated",
    },
    {
        "name_key": "page.connections.catalog.name",
        "body_key": "page.connections.catalog.body",
        "status_key": "page.common.status.implemented",
    },
    {
        "name_key": "page.connections.devices.name",
        "body_key": "page.connections.devices.body",
        "status_key": "page.common.status.planned",
    },
    {
        "name_key": "page.connections.ai.name",
        "body_key": "page.connections.ai.body",
        "status_key": "page.common.status.planned",
    },
]

CUSTOMER_STORIES = [
    {
        "quote_key": "page.customers.s1.quote",
        "who_key": "page.customers.s1.who",
        "detail_key": "page.customers.s1.detail",
    },
    {
        "quote_key": "page.customers.s2.quote",
        "who_key": "page.customers.s2.who",
        "detail_key": "page.customers.s2.detail",
    },
]

BLOG_POSTS = [
    {
        "slug": "primitives-not-modules",
        "title_key": "page.blog.post.primitives_not_modules.title",
        "date": "2026-10-02",
        "excerpt_key": "page.blog.post.primitives_not_modules.excerpt",
    },
    {
        "slug": "compose-then-publish",
        "title_key": "page.blog.post.compose_then_publish.title",
        "date": "2026-10-02",
        "excerpt_key": "page.blog.post.compose_then_publish.excerpt",
    },
]

CHANGELOG = []

COMPARE_PAGES = {
    "site-builders": {
        "slug": "site-builders",
        "title_key": "page.compare.site_builders.title",
        "lead_key": "page.compare.site_builders.lead",
        "them_key": "compare.them.builders",
        "point_keys": [
            (
                "page.compare.site_builders.p1.dim",
                "page.compare.site_builders.p1.them",
                "page.compare.site_builders.p1.us",
            ),
            (
                "page.compare.site_builders.p2.dim",
                "page.compare.site_builders.p2.them",
                "page.compare.site_builders.p2.us",
            ),
            (
                "page.compare.site_builders.p3.dim",
                "page.compare.site_builders.p3.them",
                "page.compare.site_builders.p3.us",
            ),
            ("compare.where.dim", "compare.where.them", "compare.where.us"),
            ("compare.hardware.dim", "compare.hardware.them", "compare.hardware.us"),
        ],
    },
    "low-code": {
        "slug": "low-code",
        "title_key": "page.compare.low_code.title",
        "lead_key": "page.compare.low_code.lead",
        "them_key": "compare.them.lowcode",
        "point_keys": [
            (
                "page.compare.low_code.p1.dim",
                "page.compare.low_code.p1.them",
                "page.compare.low_code.p1.us",
            ),
            (
                "page.compare.low_code.p2.dim",
                "page.compare.low_code.p2.them",
                "page.compare.low_code.p2.us",
            ),
            (
                "page.compare.low_code.p3.dim",
                "page.compare.low_code.p3.them",
                "page.compare.low_code.p3.us",
            ),
            ("compare.where.dim", "compare.where.them", "compare.where.us"),
            ("compare.hardware.dim", "compare.hardware.them", "compare.hardware.us"),
        ],
    },
}

ACTIVATION_CHOICES = [
    {
        "id": "zintriq-customer",
        "name_key": "page.activate.choice.customer.name",
        "body_key": "page.activate.choice.customer.body",
        "next_key": "page.activate.choice.customer.next",
    },
    {
        "id": "zintriq-business",
        "name_key": "page.activate.choice.business.name",
        "body_key": "page.activate.choice.business.body",
        "next_key": "page.activate.choice.business.next",
    },
]


def _localize_template(item: dict, translate: TranslateFn | None = None) -> dict:
    return {
        "id": item["id"],
        "name": _t(item["name_key"], translate),
        "description": _t(item["description_key"], translate),
        "category": _t(item["category_key"], translate),
        "publisher": item["publisher"],
        "primitives": list(item["primitives"]),
        "official": item["official"],
    }


def load_official_templates(translate: TranslateFn | None = None) -> list[dict]:
    """Public gallery cards — composition labels, not Customer/Business product names."""
    return [
        _localize_template(TEMPLATE_MARKETING["zintriq-customer"], translate),
        _localize_template(TEMPLATE_MARKETING["zintriq-business"], translate),
    ]


def template_by_id(template_id: str, translate: TranslateFn | None = None) -> dict | None:
    item = TEMPLATE_MARKETING.get(template_id)
    if not item:
        return None
    return _localize_template(item, translate)


def localized_pricing_plans(translate: TranslateFn | None = None) -> list[dict]:
    out = []
    for plan in PRICING_PLANS:
        out.append(
            {
                "id": plan["id"],
                "name": _t(plan["name_key"], translate),
                "price": plan["price"],
                "period": _t(plan["period_key"], translate),
                "blurb": _t(plan["blurb_key"], translate),
                "cta": _t(plan["cta_key"], translate),
                "featured": plan["featured"],
                "features": [_t(k, translate) for k in plan["feature_keys"]],
            }
        )
    return out


def localized_compositions(translate: TranslateFn | None = None) -> list[dict]:
    out = []
    for item in COMPOSITIONS:
        out.append(
            {
                "slug": item["slug"],
                "name": _t(item["name_key"], translate),
                "headline": _t(item["headline_key"], translate),
                "lead": _t(item["lead_key"], translate),
                "primitives": list(item["primitives"]),
                "status": _t(item["status_key"], translate),
            }
        )
    return out


def composition_by_slug(slug: str, translate: TranslateFn | None = None) -> dict | None:
    for item in COMPOSITIONS:
        if item["slug"] == slug:
            return {
                "slug": item["slug"],
                "name": _t(item["name_key"], translate),
                "headline": _t(item["headline_key"], translate),
                "lead": _t(item["lead_key"], translate),
                "primitives": list(item["primitives"]),
                "status": _t(item["status_key"], translate),
            }
    return None


def localized_connections(translate: TranslateFn | None = None) -> list[dict]:
    return [
        {
            "name": _t(item["name_key"], translate),
            "body": _t(item["body_key"], translate),
            "status": _t(item["status_key"], translate),
        }
        for item in CONNECTIONS
    ]


def localized_customer_stories(translate: TranslateFn | None = None) -> list[dict]:
    return [
        {
            "quote": _t(item["quote_key"], translate),
            "who": _t(item["who_key"], translate),
            "detail": _t(item["detail_key"], translate),
        }
        for item in CUSTOMER_STORIES
    ]


def localized_blog_posts(translate: TranslateFn | None = None) -> list[dict]:
    return [
        {
            "slug": item["slug"],
            "title": _t(item["title_key"], translate),
            "date": item["date"],
            "excerpt": _t(item["excerpt_key"], translate),
        }
        for item in BLOG_POSTS
    ]


def blog_by_slug(slug: str, translate: TranslateFn | None = None) -> dict | None:
    for item in BLOG_POSTS:
        if item["slug"] == slug:
            return {
                "slug": item["slug"],
                "title": _t(item["title_key"], translate),
                "date": item["date"],
                "excerpt": _t(item["excerpt_key"], translate),
            }
    return None


def localized_changelog(translate: TranslateFn | None = None) -> list[dict]:
    return [
        {
            "date": item["date"],
            "title": _t(item["title_key"], translate),
            "body": _t(item["body_key"], translate),
        }
        for item in CHANGELOG
    ]


def compare_by_slug(slug: str, translate: TranslateFn | None = None) -> dict | None:
    page = COMPARE_PAGES.get(slug)
    if not page:
        return None
    return {
        "slug": page["slug"],
        "title": _t(page["title_key"], translate),
        "lead": _t(page["lead_key"], translate),
        "them": _t(page.get("them_key") or "page.compare.th_them", translate),
        "points": [
            (_t(dim, translate), _t(them, translate), _t(us, translate))
            for dim, them, us in page["point_keys"]
        ],
    }


def localized_activation_choices(translate: TranslateFn | None = None) -> list[dict]:
    return [
        {
            "id": item["id"],
            "name": _t(item["name_key"], translate),
            "body": _t(item["body_key"], translate),
            "next": _t(item["next_key"], translate),
        }
        for item in ACTIVATION_CHOICES
    ]
