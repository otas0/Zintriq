# Expanded Smoke Test v2 — Full Route Coverage

**Date**: 2026-10-01
**Branch**: `cursor/popeye-inspired-redesign`
**Base**: Batch C.8

---

## Summary

| Metric | C.7 (v1) | C.8 (v2) |
|--------|----------|----------|
| Routes tested | 40 | 325 |
| 2xx | 20 | 26 |
| 3xx | 176 | 177 |
| 4xx | 94 | 122 |
| **5xx** | **3** | **0** |
| BuildErrors | 0 | 0 |

## 5xx Errors

**None.** Zero 5xx across all 325 routes.

## Status Breakdown

- **26 x 2xx** — Static assets, health endpoints, public pages
- **177 x 3xx** — Auth redirects (302), trailing-slash redirects (308)
- **122 x 4xx** — 404 (no test data), 405 (wrong method), 302→login (auth required)

## Key Route Tests

### /qr Tests (3/3 pass)

| Route | Expected | Actual |
|-------|----------|--------|
| `/qr/nonexistent-code-xyz` | 404 | 404 |
| `/qr/qr-test-archived-456` | 404 | 404 |
| `/qr/qr-test-active-123` | 302 | 302 |

### Restored Routes (3/3 pass)

| Route | Expected | Actual |
|-------|----------|--------|
| `/discover` | 302 | 302 (redirect → index) |
| `/venues` | 200 | 200 |
| `/places` | 200 | 200 |

### /build Test

| Route | Before C.8 | After C.8 |
|-------|-----------|-----------|
| `/build/test-slug/test-doc` | 500 | 404 |

500 was caused by missing `builder_projects` table. DDL run manually (Phase 1.1 will fix init_db gating). Route now returns 404 (correct — no test data).

### Health Endpoints

| Endpoint | Status | Body |
|----------|--------|------|
| `/healthz` | 200 | `{"status": "ok"}` |
| `/readyz` | 200 | `{"status": "ready"}` |
| `/metrics-basic` | 200 | `{"errors_total": 0, ...}` |

## Methodology

All routes enumerated via `app.url_map.iter_rules()`, excluding `/static/<path:filename>`. URL parameters filled with `"test"` dummy values. Each route tested with its primary HTTP method (GET preferred, POST if GET not allowed).
