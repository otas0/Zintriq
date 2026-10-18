"""Code view of UIR — JSON and restricted YAML of canonical Desc."""

from __future__ import annotations

import json

from meta.description.serialize import from_data, from_json, to_json
from meta.description.types import Desc, validate_desc
from meta.uir.errors import UIRError
from meta.uir.graph import UIR, from_desc, to_desc
from meta.uir.yaml_desc import dump_yaml, load_yaml

CODE_LANGUAGES = ("json", "yaml")


def to_code(uir_or_desc: UIR | Desc, *, language: str = "json") -> str:
    lang = str(language or "json").strip().lower() or "json"
    if lang not in CODE_LANGUAGES:
        raise UIRError(f"unsupported code language: {lang!r}")
    if isinstance(uir_or_desc, UIR):
        desc = to_desc(uir_or_desc)
    else:
        validate_desc(uir_or_desc)
        desc = uir_or_desc
    if lang == "json":
        return to_json(desc)
    return dump_yaml(json.loads(to_json(desc)))


def from_code(text: str, *, language: str = "json") -> UIR:
    lang = str(language or "json").strip().lower() or "json"
    if lang not in CODE_LANGUAGES:
        raise UIRError(f"unsupported code language: {lang!r}")
    if lang == "json":
        desc = from_json(text)
    else:
        data = load_yaml(text)
        desc = from_data(data)
    return from_desc(desc, source="code")


def code_to_desc(text: str, *, language: str = "json") -> Desc:
    return to_desc(from_code(text, language=language))
