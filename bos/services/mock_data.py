"""Centralized mock data for Business OS modules — never hardcode in components."""

from __future__ import annotations

from datetime import datetime, timedelta


def _iso(days_ago: int = 0) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


MOCK_CATALOG = [
    {"id": "cat-1", "name": "Standard Service Package", "sku": "SRV-001", "status": "active", "price": 99.0, "category": "Services", "updated_at": _iso(1)},
    {"id": "cat-2", "name": "Premium Consultation", "sku": "SRV-002", "status": "active", "price": 249.0, "category": "Services", "updated_at": _iso(3)},
    {"id": "cat-3", "name": "Physical Product A", "sku": "PRD-101", "status": "draft", "price": 45.5, "category": "Products", "updated_at": _iso(5)},
    {"id": "cat-4", "name": "Physical Product B", "sku": "PRD-102", "status": "active", "price": 78.0, "category": "Products", "updated_at": _iso(2)},
    {"id": "cat-5", "name": "Add-on Module", "sku": "ADD-010", "status": "archived", "price": 19.0, "category": "Add-ons", "updated_at": _iso(14)},
]

MOCK_TRANSACTIONS = [
    {"id": "txn-1", "reference": "TXN-2026-001", "customer": "Acme Corp", "amount": 1240.0, "status": "completed", "date": _iso(0)},
    {"id": "txn-2", "reference": "TXN-2026-002", "customer": "Northwind LLC", "amount": 580.0, "status": "pending", "date": _iso(1)},
    {"id": "txn-3", "reference": "TXN-2026-003", "customer": "Globex Inc", "amount": 3200.0, "status": "completed", "date": _iso(4)},
]

MOCK_CUSTOMERS = [
    {"id": "cus-1", "name": "Acme Corp", "email": "billing@acme.example", "status": "active", "tags": ["enterprise"], "updated_at": _iso(1)},
    {"id": "cus-2", "name": "Northwind LLC", "email": "accounts@northwind.example", "status": "active", "tags": ["partner"], "updated_at": _iso(3)},
    {"id": "cus-3", "name": "Globex Inc", "email": "hello@globex.example", "status": "inactive", "tags": [], "updated_at": _iso(10)},
]

MOCK_TEAM = [
    {"id": "tm-1", "name": "Alex Morgan", "email": "alex@example.com", "role": "owner", "status": "active"},
    {"id": "tm-2", "name": "Jordan Lee", "email": "jordan@example.com", "role": "admin", "status": "active"},
    {"id": "tm-3", "name": "Sam Rivera", "email": "sam@example.com", "role": "member", "status": "invited"},
]

MOCK_OPERATIONS = [
    {"id": "op-1", "title": "Monthly inventory review", "status": "in_progress", "priority": "medium", "due_at": _iso(-2)},
    {"id": "op-2", "title": "Update catalog pricing", "status": "open", "priority": "high", "due_at": _iso(-5)},
    {"id": "op-3", "title": "Archive inactive assets", "status": "done", "priority": "low", "due_at": _iso(7)},
]

MOCK_DOCUMENTS = [
    {"id": "doc-1", "name": "Business Plan 2026.pdf", "type": "pdf", "size": "2.4 MB", "updated_at": _iso(2)},
    {"id": "doc-2", "name": "Vendor Agreement.docx", "type": "doc", "size": "840 KB", "updated_at": _iso(8)},
    {"id": "doc-3", "name": "Brand Guidelines.pdf", "type": "pdf", "size": "5.1 MB", "updated_at": _iso(15)},
]

MOCK_TAGS = [
    {"id": "tag-1", "name": "Priority", "color": "warning", "count": 12},
    {"id": "tag-2", "name": "Enterprise", "color": "info", "count": 5},
    {"id": "tag-3", "name": "Internal", "color": "muted", "count": 8},
    {"id": "tag-4", "name": "Archived", "color": "danger", "count": 3},
]

MOCK_ACTIVITIES = [
    {"id": "act-1", "message": "Workspace updated", "actor": "You", "time": _iso(0)},
    {"id": "act-2", "message": "New catalog item added", "actor": "Jordan Lee", "time": _iso(1)},
    {"id": "act-3", "message": "Customer record created", "actor": "You", "time": _iso(2)},
]


def mock_for_module(module_id: str) -> dict:
    """Return boot payload for a module from centralized mock data."""
    payloads = {
        "catalog": {"items": MOCK_CATALOG, "filters": ["all", "active", "draft", "archived"]},
        "transactions": {"items": MOCK_TRANSACTIONS, "filters": ["all", "completed", "pending"]},
        "customers": {"items": MOCK_CUSTOMERS, "filters": ["all", "active", "inactive"]},
        "team": {"items": MOCK_TEAM, "filters": ["all", "active", "invited"]},
        "operations": {"items": MOCK_OPERATIONS, "filters": ["all", "open", "in_progress", "done"]},
        "documents": {"items": MOCK_DOCUMENTS, "filters": ["all", "pdf", "doc"]},
        "tags": {"items": MOCK_TAGS, "filters": []},
        "home": {"activities": MOCK_ACTIVITIES},
    }
    return payloads.get(module_id, {"items": []})
