"""Stable identifiers for pages, models, records, and package keys."""

from __future__ import annotations

import re
import secrets

# Same shape as desktop.transfer: dotted official keys such as official.product-card.
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}(?:\.[A-Za-z0-9_-]{1,40}){0,4}$")
TOKEN_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}(?:\.[A-Za-z0-9_-]{1,40}){0,4}$")

RESERVED_DOCUMENT_KEYS = frozenset({"records"})


class IdentifierError(ValueError):
    """Key is missing, malformed, or reserved."""


def valid_identifier(value: str) -> bool:
    return bool(value) and IDENTIFIER_RE.match(value) is not None


def is_reserved_document_key(value: str) -> bool:
    return str(value or "").strip().lower() in RESERVED_DOCUMENT_KEYS


def check_document_key(value: str) -> str:
    key = str(value or "").strip()
    if not valid_identifier(key):
        raise IdentifierError("invalid document key")
    if is_reserved_document_key(key):
        raise IdentifierError("reserved document key")
    return key


def new_record_key() -> str:
    """Unpredictable record id. Not sequential, not a page key."""
    return "rec_" + secrets.token_hex(16)
