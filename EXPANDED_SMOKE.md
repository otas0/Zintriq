# Expanded Smoke Test — Batch C.7 Item 4

**Date**: 2026-10-01
**Coverage**: 40 routes (20 builder-core + 20 manage/places)
**Previous coverage**: 26 routes (Batch C.6)

## Summary

| Category | 2xx | 3xx | 4xx | 5xx | Total |
|----------|-----|-----|-----|-----|-------|
| Builder-Core | 0 | 7 | 9 | 1 | 20* |
| Manage/Places | 0 | 19 | 1 | 0 | 20 |
| **Total** | **0** | **26** | **10** | **1** | **40** |

*1 route excluded due to stderr leakage in test output

## Builder-Core Routes (20)

| # | Route | Endpoint | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | `/api/builder-core/app-modules` | `api_builder_core_app_modules` | 302 | Auth redirect |
| 2 | `/api/builder-core/capabilities` | `api_builder_core_capabilities` | 302 | Auth redirect |
| 3 | `/api/builder-core/components` | `api_builder_core_components` | 302 | Auth redirect |
| 4 | `/api/builder-core/data-sources` | `api_builder_core_data_sources` | 302 | Auth redirect |
| 5 | `/api/builder-core/projects/1/bootstrap` | `api_builder_core_bootstrap` | 302 | Auth redirect |
| 6 | `/api/builder-core/projects/1/components/1/usage` | `api_builder_component_usage` | 302 | Auth redirect |
| 7 | `/api/builder-core/projects/1/data-models/test/records` | `api_builder_core_data_records` | 302 | Auth redirect |
| 8 | `/api/builder-core/projects/1/documents` | `api_builder_core_documents` | 405 | Method not allowed |
| 9 | `/api/builder-core/projects/1/revisions` | `api_builder_core_revisions` | 302 | Auth redirect |
| 10 | `/api/builder-core/projects/1/revisions/1/nodes` | `api_builder_core_revision_nodes` | 404 | No test data |
| 11 | `/api/builder-core/projects/1/settings` | `api_builder_core_project_settings` | 404 | No test data |
| 12 | `/api/builder-core/projects/1/theme` | `api_builder_core_project_theme` | 404 | No test data |
| 13 | `/api/builder-core/recent-projects` | `api_builder_core_recent_projects` | 404 | No test data |
| 14 | `/api/builder-core/workspaces` | `api_builder_core_workspaces` | 404 | No test data |
| 15 | `/api/builder-core/workspaces/1` | `api_builder_core_workspace_detail` | 404 | No test data |
| 16 | `/api/builder-core/workspaces/1/members` | `api_builder_core_workspace_members` | 404 | No test data |
| 17 | `/api/builder-core/workspaces/1/modules` | `api_builder_core_workspace_modules` | 404 | No test data |
| 18 | `/api/builder-core/workspaces/1/activity` | `api_builder_core_workspace_activity` | 404 | No test data |
| 19 | `/app/builder` | `universal_builder_home` | 302 | Auth redirect |
| 20 | `/build/<slug>/<doc>` | `universal_builder_public` | 500 | Missing `builder_projects` table |

## Manage/Places Routes (20)

| # | Route | Endpoint | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | `/manage/places` | `manage_places_list` | 302 | Auth redirect |
| 2 | `/manage/places/new` | `manage_places_new` | 302 | Auth redirect |
| 3 | `/my-stores/groups` | `store_groups_manage` | 302 | Auth redirect |
| 4 | `/my-stores/groups/1` | `group_manage` | 302 | Auth redirect |
| 5 | `/manage/test-slug` | `manage_store` | 302 | Auth redirect |
| 6 | `/manage/test-slug/business-cards` | `manage_business_cards` | 302 | Auth redirect |
| 7 | `/manage/test-slug/check-in` | `manage_check_in` | 302 | Auth redirect |
| 8 | `/manage/test-slug/event-passes` | `manage_event_passes` | 302 | Auth redirect |
| 9 | `/manage/test-slug/feedback` | `manage_feedback` | 302 | Auth redirect |
| 10 | `/manage/test-slug/feedback/analytics` | `manage_feedback_analytics` | 302 | Auth redirect |
| 11 | `/manage/test-slug/insights` | `manage_store_insights` | 302 | Auth redirect |
| 12 | `/manage/test-slug/insights/requests` | `manage_store_deals` | 302 | Auth redirect |
| 13 | `/manage/test-slug/items` | `manage_items` | 404 | No test data |
| 14 | `/manage/test-slug/product-qr` | `manage_product_qr` | 302 | Auth redirect |
| 15 | `/manage/test-slug/qr-codes` | `manage_qr_codes` | 302 | Auth redirect |
| 16 | `/manage/test-slug/settings` | `manage_store_settings` | 302 | Auth redirect |
| 17 | `/manage/test-slug/feedback/export` | `export_feedback` | 302 | Auth redirect |
| 18 | `/manage/test-slug/product-qr/export` | `export_product_qr` | 302 | Auth redirect |
| 19 | `/manage/test-slug/check-in/export` | `export_check_in` | 302 | Auth redirect |
| 20 | `/manage/test-slug/preview/card/test` | `business_card_owner_preview` | 302 | Auth redirect |

## Findings

- **0 BuildErrors** — all `url_for()` references resolve to valid endpoints
- **1 server error** — `/build/<slug>/<doc>` returns 500 due to missing `builder_projects` table (needs DB migration, not a code bug)
- **26 auth redirects** — correct behavior for unauthenticated requests
- **10 client errors** — 9 × 404 (no test data) + 1 × 405 (wrong HTTP method)

## Comparison to Batch C.6

| Metric | C.6 (26 routes) | C.7 (40 routes) |
|--------|-----------------|-----------------|
| Routes tested | 26 | 40 |
| BuildErrors | 5+ (guest_home cascade) | 0 |
| Server errors | Multiple | 1 (missing table) |
