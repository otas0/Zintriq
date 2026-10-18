"""Unified Intermediate Representation — dual visual/code bridge."""

from __future__ import annotations

from meta.uir.code import code_to_desc, from_code, to_code
from meta.uir.errors import UIRError
from meta.uir.graph import UIR, UIREdge, UIRNode, from_desc, to_desc, uir_from_data
from meta.uir.marks import attach_view, merge_visual_views, normalize_view, strip_view
from meta.uir.visual import desc_to_visual, from_visual, to_visual, visual_to_desc

__all__ = [
    "UIR",
    "UIREdge",
    "UIRError",
    "UIRNode",
    "attach_view",
    "code_to_desc",
    "desc_to_visual",
    "from_code",
    "from_desc",
    "from_visual",
    "merge_visual_views",
    "normalize_view",
    "strip_view",
    "to_code",
    "to_desc",
    "to_visual",
    "uir_from_data",
    "visual_to_desc",
]
