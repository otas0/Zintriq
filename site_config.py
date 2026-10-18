"""Public website stage switches. Environment variables override the defaults."""

from __future__ import annotations

import os


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _optional_int(name: str):
    raw = (os.environ.get(name) or "").strip()
    if not raw or raw.lower() in {"none", "null"}:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


SITE_STAGE = _int("SITE_STAGE", 2)
BILLING_ENABLED = _flag("BILLING_ENABLED", False)
HARDWARE_SALES_ENABLED = _flag("HARDWARE_SALES_ENABLED", False)
COMMUNITY_SHARE_PAGES = _flag("COMMUNITY_SHARE_PAGES", SITE_STAGE >= 2)
MAINLAND_SERVICE_OPEN = _flag("MAINLAND_SERVICE_OPEN", False)
PRICE_PERSONAL_MONTHLY_USD = _int("PRICE_PERSONAL_MONTHLY_USD", 10)
PRICE_TEAM_SEAT_MONTHLY_USD = _int("PRICE_TEAM_SEAT_MONTHLY_USD", 20)
TRIAL_DAYS = _optional_int("TRIAL_DAYS")
CONTACT_REPLY_DAYS = _int("CONTACT_REPLY_DAYS", 2)
CONTACT_EMAIL = (os.environ.get("CONTACT_EMAIL") or os.environ.get("LEGAL_CONTACT_EMAIL") or "zintriq@gmail.com").strip()
STORAGE_QUOTA_PERSONAL = _optional_int("STORAGE_QUOTA_PERSONAL")
STORAGE_QUOTA_PER_SEAT = _optional_int("STORAGE_QUOTA_PER_SEAT")

# Public page hooks (empty = section hidden). Override via env JSON where noted.
# BUILD_LOG: list of {"date": "2026-09", "text": "..."} — do not invent entries.
BUILD_LOG: list[dict[str, str]] = []
# HW_STAGE: one of concept|prototype|evt|dvt|mp, or "" to hide the stage strip.
HW_STAGE = (os.environ.get("HW_STAGE") or "").strip().lower()
# HW_SPECS: list of {"label": "...", "value": "..."} target specs; empty hides the table.
HW_SPECS: list[dict[str, str]] = []

# Language picker lists a locale only when this fraction of core keys exist in its catalog.
# Phase 3: hreflang and sitemap include only locales at or above this threshold.
# Pages in every other language send noindex.
I18N_SELECTOR_COVERAGE = float(os.environ.get("I18N_SELECTOR_COVERAGE") or "0.90")

# Missing strings walk this chain after the active language. Unlisted languages fall back to English.
LOCALE_FALLBACKS = {
    "zh-Hant": ("zh-Hans", "en"),
    "yue": ("zh-Hant", "zh-Hans", "en"),
}
DEFAULT_LOCALE_FALLBACK = ("en",)

# Keys that define "core pages" for the language picker. Coverage is counted by scripts/i18n_core_coverage.py.
CORE_MESSAGE_KEYS = (
    "nav.product",
    "nav.hardware",
    "nav.pricing",
    "nav.docs",
    "nav.download",
    "nav.login",
    "nav.signup",
    "nav.account",
    "nav.logout",
    "nav.menu",
    "nav.skip",
    "footer.col.product",
    "footer.col.resources",
    "footer.col.company",
    "footer.legal",
    "footer.region",
    "footer.copyright",
    "footer.residency",
    "footer.mor",
    "region.title",
    "region.lead",
    "region.suggested",
    "region.all",
    "region.language_only",
    "region.banner",
    "region.switch",
    "region.stay",
    "err.403.title",
    "err.403.body",
    "err.403.cta",
    "err.404.title",
    "err.404.body",
    "err.404.cta",
    "err.500.title",
    "err.500.body",
    "err.500.status",
    "err.maintenance",
    "i18n.partial",
    "product.title",
    "product.lead",
    "product.cta",
    "hw.badge",
    "hw.title",
    "hw.lead",
    "hw.cta",
    "translate.title",
    "translate.lead",
    "translate.start",
)
