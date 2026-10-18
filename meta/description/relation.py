"""Relations over descriptions: dependency and structural equivalence."""

from __future__ import annotations

from meta.description.composite import MappingDesc, SequenceDesc, StructDesc
from meta.description.types import AtomDesc, Desc, validate_desc


def equivalent(left: Desc, right: Desc) -> bool:
    """Structural equivalence after validation."""
    validate_desc(left)
    validate_desc(right)
    return left == right


def depends_on(node: Desc) -> frozenset[str]:
    """Collect ref targets reachable from this description."""
    validate_desc(node)
    found: set[str] = set()
    _walk(node, found)
    return frozenset(found)


def _walk(node: Desc, found: set[str]) -> None:
    if isinstance(node, AtomDesc):
        if node.ref:
            found.add(node.ref)
        return
    if isinstance(node, StructDesc):
        for _name, child in node.fields:
            _walk(child, found)
        return
    if isinstance(node, SequenceDesc):
        for child in node.items:
            _walk(child, found)
        return
    if isinstance(node, MappingDesc):
        for _key, child in node.entries:
            _walk(child, found)
