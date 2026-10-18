"""Composite descriptions: struct, sequence, mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from meta.description.errors import DescriptionError

if TYPE_CHECKING:
    from meta.description.types import Desc


@dataclass(frozen=True)
class StructDesc:
    fields: tuple[tuple[str, Desc], ...] = ()

    def to_data(self) -> dict:
        return {
            "form": "struct",
            "fields": {name: child.to_data() for name, child in self.fields},
        }


@dataclass(frozen=True)
class SequenceDesc:
    items: tuple[Desc, ...] = ()

    def to_data(self) -> dict:
        return {"form": "sequence", "items": [child.to_data() for child in self.items]}


@dataclass(frozen=True)
class MappingDesc:
    """String-keyed mapping for step 1 (non-string keys deferred)."""

    entries: tuple[tuple[str, Desc], ...] = ()

    def to_data(self) -> dict:
        return {
            "form": "mapping",
            "entries": {key: child.to_data() for key, child in self.entries},
        }


def struct(**fields: Desc) -> StructDesc:
    from meta.description.types import validate_desc

    node = StructDesc(fields=tuple(sorted(fields.items(), key=lambda item: item[0])))
    validate_desc(node)
    return node


def sequence(*items: Desc) -> SequenceDesc:
    from meta.description.types import validate_desc

    node = SequenceDesc(items=tuple(items))
    validate_desc(node)
    return node


def mapping(**entries: Desc) -> MappingDesc:
    from meta.description.types import validate_desc

    node = MappingDesc(entries=tuple(sorted(entries.items(), key=lambda item: item[0])))
    validate_desc(node)
    return node


def struct_from_items(items: list[tuple[str, Desc]] | tuple[tuple[str, Desc], ...]) -> StructDesc:
    from meta.description.types import validate_desc

    names = [name for name, _child in items]
    if len(names) != len(set(names)):
        raise DescriptionError("duplicate struct field")
    node = StructDesc(fields=tuple(items))
    validate_desc(node)
    return node
