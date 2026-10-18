"""Meta-description layer (minimal subset)."""

from __future__ import annotations

from meta.description.composite import MappingDesc, SequenceDesc, StructDesc, mapping, sequence, struct
from meta.description.errors import DescriptionError
from meta.description.relation import depends_on, equivalent
from meta.description.serialize import from_json, to_json
from meta.description.types import AtomDesc, Constraint, Desc, atom, validate_desc

__all__ = [
    "AtomDesc",
    "Constraint",
    "Desc",
    "DescriptionError",
    "MappingDesc",
    "SequenceDesc",
    "StructDesc",
    "atom",
    "depends_on",
    "equivalent",
    "from_json",
    "mapping",
    "sequence",
    "struct",
    "to_json",
    "validate_desc",
]
