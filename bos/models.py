"""Generic Business OS domain models — industry-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BosModule:
    id: str
    label: str
    icon: str
    endpoint: str
    description: str = ""


BOS_MODULES: tuple[BosModule, ...] = (
    BosModule("home", "Home", "⌂", "bos.home", "Overview and quick access"),
    BosModule("organizations", "Organization", "◉", "bos.organizations", "Company profile and settings"),
    BosModule("workspaces", "Workspaces", "◫", "bos.workspaces", "Business units and locations"),
    BosModule("catalog", "Catalog", "▦", "bos.catalog", "Products and services"),
    BosModule("transactions", "Transactions", "⇄", "bos.transactions", "Sales and payments"),
    BosModule("customers", "Customers", "◎", "bos.customers", "Contacts and relationships"),
    BosModule("team", "Team", "◈", "bos.team", "Members and roles"),
    BosModule("assets", "Assets", "⬡", "bos.assets", "Files, QR codes, and resources"),
    BosModule("operations", "Operations", "⚙", "bos.operations", "Tasks and workflows"),
    BosModule("documents", "Documents", "▤", "bos.documents", "Files and records"),
    BosModule("tags", "Tags", "◆", "bos.tags", "Labels and classification"),
)


def module_for_id(module_id: str) -> BosModule | None:
    return next((m for m in BOS_MODULES if m.id == module_id), None)


def row_to_dict(row: Any) -> dict:
    return dict(row) if row is not None else {}
