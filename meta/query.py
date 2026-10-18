"""Visual query over in-memory rows. No SQL string is executed."""

from __future__ import annotations

from typing import Any

OPS = frozenset({"eq", "neq", "gt", "lt", "contains", "and", "or"})


class QueryError(ValueError):
    pass


def visual_query(rows: list[dict[str, Any]], spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not spec:
        return list(rows)
    return [row for row in rows if _match(row, spec)]


def _match(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    op = str(spec.get("op") or "eq")
    if op not in OPS:
        raise QueryError(f"unsupported op: {op}")
    if op == "and":
        return all(_match(row, child) for child in spec.get("children") or [])
    if op == "or":
        kids = list(spec.get("children") or [])
        return any(_match(row, child) for child in kids) if kids else False
    field = str(spec.get("field") or "")
    if not field or "." in field or ";" in field:
        raise QueryError("invalid field")
    left = row.get(field)
    right = spec.get("value")
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    if op == "gt":
        return _num(left) > _num(right)
    if op == "lt":
        return _num(left) < _num(right)
    if op == "contains":
        return str(right or "") in str(left or "")
    return False


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
