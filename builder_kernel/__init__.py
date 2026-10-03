"""Builder kernel contracts. K1 registers types; later steps execute them."""

from builder_kernel.ids import (
    IDENTIFIER_RE,
    RESERVED_DOCUMENT_KEYS,
    TOKEN_KEY_RE,
    check_document_key,
    is_reserved_document_key,
    new_record_key,
    valid_identifier,
)
from builder_kernel.limits import (
    COMPOSE_MAX_DEPTH,
    COMPOSE_MAX_STEPS,
    PUBLIC_INVOKE_MAX_BYTES,
    PUBLIC_LIST_DEFAULT_LIMIT,
    PUBLIC_LIST_MAX_LIMIT,
)
from builder_kernel.registry import kernel
from builder_kernel.validate import ValidationResult, prepare_record_write, validate_record, validate_schema

__all__ = [
    "COMPOSE_MAX_DEPTH",
    "COMPOSE_MAX_STEPS",
    "IDENTIFIER_RE",
    "PUBLIC_INVOKE_MAX_BYTES",
    "PUBLIC_LIST_DEFAULT_LIMIT",
    "PUBLIC_LIST_MAX_LIMIT",
    "RESERVED_DOCUMENT_KEYS",
    "TOKEN_KEY_RE",
    "check_document_key",
    "is_reserved_document_key",
    "kernel",
    "new_record_key",
    "prepare_record_write",
    "valid_identifier",
    "validate_record",
    "validate_schema",
    "ValidationResult",
]
