"""Atomic descriptions: value, ref, type, unit, constraints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Union

from meta.description.errors import DescriptionError

ATOM_TYPES = frozenset({"null", "bool", "int", "float", "string", "bytes"})
CONSTRAINT_OPS = frozenset({"min", "max", "enum", "pattern"})
# Bare path (system.limit) or root-ish path ($.input.count).
REF_RE = re.compile(
    r"^(?:\$?(?:\.[A-Za-z_][A-Za-z0-9_]*)+|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)$"
)


@dataclass(frozen=True)
class Constraint:
    op: str
    arg: Any

    def to_data(self) -> dict:
        return {"op": self.op, "arg": self.arg}

    @staticmethod
    def from_data(data: dict) -> Constraint:
        if not isinstance(data, dict):
            raise DescriptionError("constraint must be an object")
        op = str(data.get("op") or "").strip()
        if op not in CONSTRAINT_OPS:
            raise DescriptionError(f"unsupported constraint op: {op!r}")
        if "arg" not in data:
            raise DescriptionError("constraint requires arg")
        return Constraint(op=op, arg=data["arg"])


@dataclass(frozen=True)
class AtomDesc:
    """Atomic description node."""

    type_name: str
    value: Any = None
    ref: str | None = None
    unit: str | None = None
    constraints: tuple[Constraint, ...] = ()
    has_value: bool = False

    def to_data(self) -> dict:
        out: dict[str, Any] = {"form": "atom", "type": self.type_name}
        if self.has_value:
            out["value"] = self.value
        if self.ref is not None:
            out["ref"] = self.ref
        if self.unit:
            out["unit"] = self.unit
        if self.constraints:
            out["constraints"] = [item.to_data() for item in self.constraints]
        return out


# Forward-declared union; composite modules attach concrete types.
Desc = Union[AtomDesc, "StructDesc", "SequenceDesc", "MappingDesc"]


def atom(
    type_name: str,
    *,
    value: Any = None,
    has_value: bool = False,
    ref: str | None = None,
    unit: str | None = None,
    constraints: tuple[Constraint, ...] | list[Constraint] = (),
) -> AtomDesc:
    node = AtomDesc(
        type_name=str(type_name or "").strip(),
        value=value,
        has_value=bool(has_value),
        ref=None if ref is None else str(ref).strip(),
        unit=None if unit is None else str(unit).strip() or None,
        constraints=tuple(constraints),
    )
    validate_atom(node)
    return node


def validate_atom(node: AtomDesc) -> None:
    if node.type_name not in ATOM_TYPES:
        raise DescriptionError(f"unsupported atom type: {node.type_name!r}")
    if node.has_value and node.ref is not None:
        raise DescriptionError("atom cannot have both value and ref")
    if node.ref is not None and not REF_RE.match(node.ref):
        raise DescriptionError(f"invalid ref: {node.ref!r}")
    if node.unit is not None and len(node.unit) > 32:
        raise DescriptionError("unit too long")
    for constraint in node.constraints:
        _validate_constraint(node, constraint)
    if node.has_value:
        _check_value_type(node.type_name, node.value)


def _validate_constraint(node: AtomDesc, constraint: Constraint) -> None:
    if constraint.op in {"min", "max"}:
        if node.type_name not in {"int", "float", "string"}:
            raise DescriptionError(f"{constraint.op} not valid for {node.type_name}")
        if not isinstance(constraint.arg, (int, float)) and not (
            node.type_name == "string" and isinstance(constraint.arg, int)
        ):
            raise DescriptionError(f"{constraint.op} arg must be numeric")
    elif constraint.op == "enum":
        if not isinstance(constraint.arg, (list, tuple)) or not constraint.arg:
            raise DescriptionError("enum arg must be a non-empty list")
    elif constraint.op == "pattern":
        if node.type_name != "string":
            raise DescriptionError("pattern only valid for string")
        if not isinstance(constraint.arg, str):
            raise DescriptionError("pattern arg must be a string")
        try:
            re.compile(constraint.arg)
        except re.error as exc:
            raise DescriptionError(f"invalid pattern: {exc}") from exc


def _check_value_type(type_name: str, value: Any) -> None:
    if type_name == "null":
        if value is not None:
            raise DescriptionError("null atom value must be null")
        return
    if type_name == "bool" and not isinstance(value, bool):
        raise DescriptionError("bool atom value must be bool")
    if type_name == "int" and (not isinstance(value, int) or isinstance(value, bool)):
        raise DescriptionError("int atom value must be int")
    if type_name == "float" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise DescriptionError("float atom value must be number")
    if type_name == "string" and not isinstance(value, str):
        raise DescriptionError("string atom value must be string")
    if type_name == "bytes" and not isinstance(value, str):
        # JSON carries bytes as base64/text; step 1 stores text payload only.
        raise DescriptionError("bytes atom value must be string payload")


def validate_desc(node: Desc) -> None:
    from meta.description.composite import MappingDesc, SequenceDesc, StructDesc

    if isinstance(node, AtomDesc):
        validate_atom(node)
        return
    if isinstance(node, StructDesc):
        seen = set()
        for name, child in node.fields:
            if not name or name in seen:
                raise DescriptionError(f"invalid struct field: {name!r}")
            seen.add(name)
            validate_desc(child)
        return
    if isinstance(node, SequenceDesc):
        for child in node.items:
            validate_desc(child)
        return
    if isinstance(node, MappingDesc):
        seen = set()
        for key, child in node.entries:
            if not isinstance(key, str) or not key or key in seen:
                raise DescriptionError(f"invalid mapping key: {key!r}")
            seen.add(key)
            validate_desc(child)
        return
    raise DescriptionError(f"unknown description form: {type(node)!r}")
