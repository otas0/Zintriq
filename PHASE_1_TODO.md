# Phase 1 TODO — Deferred Observability Work

This file is append-only. Never delete entries, only mark [DONE].

---

## Phase 1.1 — P0: init_db() gating causes /build 500

**Discovered**: Batch C.8 (2026-10-01)
**Severity**: P0 — any request to `/build/<slug>/<doc>` returns 500 on fresh deploy

**Root cause**: `init_db()` at `app.py:241` is only called under `if __name__ == "__main__":` (line 4864). When the app is loaded via WSGI (gunicorn, etc.) or imported (test_client), the DDL never runs. This means all 23 builder tables (`builder_projects`, `builder_documents`, `builder_nodes`, etc. defined in `universal_builder_core.py:22-363`) are missing.

**Impact**: `universal_builder_core.py:2274` and `universal_builder_runtime.py:369` query `builder_projects` table → `sqlite3.OperationalError: no such table: builder_projects` → 500.

**Secondary issue**: `seed_official_system_template(conn)` (called by `init_universal_builder_tables` at `universal_builder_core.py:512`) fails with `FileNotFoundError: builder_templates/zintriq-system/manifest.json`. The DDL runs before the seed, so tables are created even though seed fails — but the seed failure should also be handled.

**Fix required for Phase 1.1**:
1. Move `init_db()` call out of `if __name__ == "__main__":` guard — run on first request or app factory
2. Guard `seed_official_system_template` with try/except or check manifest existence before seeding
3. Ensure DDL is idempotent (uses `CREATE TABLE IF NOT EXISTS`)

**Temporary workaround applied**: DDL run manually on `marketqr.db` — 23 builder tables created. Route now returns 404 (correct — no test data). This workaround does NOT survive a fresh deploy.

---

## Phase 1.1 — SUSPECT Blocks (behavior fix, not just logging)

13 remaining SWALLOW_SUSPECT blocks from OBSERVABILITY_AUDIT.md.
Batch A fixed 4 of the original 17 (#7, #8, #9 in 2.0.4; #10 in 2.0.5; #20, #24, #25 in 2.0.7; #23 in 2.0.6).

| # | File:Line | Risk |
|---|-----------|------|
| 4 | `app.py:3250` | QR experience slug lookup — if DB throws, user lands on wrong page |
| 12 | `feedback_platform.py:834` | Template loading — owner sees feedback page missing content blocks |
| 14 | `payment_connect_plugin.py:950` | Stripe status refresh — stale data shown with no error signal |
| 15 | `payment_connect_plugin.py:956` | PayPal status refresh — same as #14 for PayPal |
| 16 | `place_platform.py:327` | Place tenant insert — masks real DB error with "already listed" |
| 18 | `reputation_connect_plugin.py:333` | Google profile fetch — OAuth succeeds with incomplete profile |
| 19 | `storefront_platform.py:788` | Landing scan count — Insights dashboard shows 0 instead of real count |
| 30 | `reputation_connect_plugin.py:349` | Token exchange + DB store — DB failure mislabeled as "token_exchange_failed" |
| 33 | `universal_builder_core.py:1984` | Package version validation — ValueError returns 409 instead of 400/404 |
| 34 | `app.py:673` | Guest stats fallback — DB failure returns empty dict with no error signal |
| 35 | `app.py:844` | touch_user_presence — auth decorator swallows DB error, view still runs |

All SUSPECT blocks above now have `logging.getLogger("app.<module>").error(...)` with `# SUSPECT` comment (Batch B Step 2.3.4). Swallow behavior unchanged — only added visibility.

Logger names assigned per module: `app.guest`, `app.presence`, `app.checkin`, `app.qr_experience`, `app.bos`, `app.checkout`, `app.feedback`, `app.payment`, `app.place`, `app.reputation`, `app.storefront`.

### Recovery Queue

7 checkout sites log with `recover=true` (Step 2.0.4):
- `checkout_platform.py:748` — Stripe verify failed
- `checkout_platform.py:761` — Stripe fulfill failed
- `checkout_platform.py:780` — PayPal verify failed
- `checkout_platform.py:793` — PayPal fulfill failed
- `checkout_platform.py:810` — Generic verify failed
- `checkout_platform.py:823` — Generic fulfill failed
- `checkout_platform.py:829` — Overall checkout success error

No durable queue exists. Failed checkouts are logged but not persisted for merchant reconciliation.

Design note: needs a DB table (e.g., `checkout_recovery_queue`) with columns:
`id, checkout_id, reference, provider, failure_type, payload_json, created_at, retried_at, status`.
Background worker retries or flags for manual review.

---

## Phase 2.6 — External Call Tracing [DONE — Batch C Step 2.6 + C.5 GAP 3]

**Status:** COMPLETE (2026-09-27)

Original plan: 9 bare urllib sites. Actual: 14 HTTP + 2 SMTP = 16 total trace() wrappings.

**Line number mapping** (pre-edit → post-edit after trace() wrapping added lines):
- checkout_platform.py:319 → :324 (Stripe create session)
- checkout_platform.py:740 → :747 (Stripe verify session)
- payment_connect_plugin.py:57 → :61 (HTTP POST form)
- payment_connect_plugin.py:65 → :70 (HTTP GET JSON)
- payment_connect_plugin.py:76 → :82 (HTTP POST JSON)
- payment_connect_plugin.py:366 → :376 (Stripe verify secret)
- payment_connect_plugin.py:486 → :497 (Stripe account status)
- reputation_connect_plugin.py:132 → :134 (HTTP GET JSON)
- reputation_connect_plugin.py:158 → :161 (HTTP POST form)

**Additional sites found and wrapped:**
- payment_checkout_adapters.py:47, :61 (2 HTTP adapters)
- storefront_platform.py:622 (geocode OSM)
- integrations/payment/__init__.py:80 (Stripe create customer)
- integration_credential_verify.py:41 (credential verify)
- email_delivery.py:44, :50 (2 SMTP connections)

**Final count:** `grep -c "with trace(" *.py` = 16 (excl. observability/trace.py docstring)
**Plus:** 2 `with slow_query()` wrappings (storefront_platform.py, qr_experience_analytics.py)

All outbound HTTP + SMTP calls in production code are now traced.

---

## Phase 1.1b — New SUSPECT Blocks (found during Batch B, not in original audit)

2 silent excepts converted during Batch B that were NOT in OBSERVABILITY_AUDIT.md:

| # | File:Line | Logger | Risk |
|---|-----------|--------|------|
| NB-1 | `bos/workflows.py:438` | `app.bos` | Workflow subscriber — error swallowed, workflow silently skipped |
| NB-2 | `bos/events.py:212` | `app.bos` | Event subscriber — error swallowed, event silently skipped |

Both tagged SAFE (fire-and-forget subscribers) but should be verified in Phase 1.1.

---

## Phase 1.1c — Unconverted `except Exception:` (found by RULE 1 second-pass grep) [DONE — Batch B.5]

9 additional `except Exception:` blocks in production code NOT in original audit. All converted to Pattern A logging in Batch B.5.

| # | File:Line | What it does | Risk | Status |
|---|-----------|-------------|------|--------|
| UC-1 | `checkout_platform.py:620` | Braintree client token fallback → `braintree_token = ""` | LOW | Converted |
| UC-2 | `customer_verification.py:803` | `url_for("bos.store")` fallback → `next_url = "/app/stores"` | LOW | Converted |
| UC-3 | `team_platform.py:597` | INSERT→UPDATE upsert pattern | LOW | Converted |
| UC-4 | `payment_connect_plugin.py:274` | `decrypt_token()` fallback → `access = ""` | MEDIUM | Converted |
| UC-5 | `payment_connect_plugin.py:278` | `decrypt_token()` fallback → `refresh = ""` | MEDIUM | Converted |
| UC-6 | `storefront_platform.py:446` | `ZoneInfo()` fallback → default TZ | LOW | Converted |
| UC-7 | `feedback_reputation_plugins.py:110` | Metadata JSON fetch fallback → `meta_raw = ""` | LOW | Converted |
| UC-8 | `feedback_reputation_plugins.py:117` | Metadata JSON parse fallback → `reviews = []` | LOW | Converted |
| UC-9 | `payment_checkout_adapters.py:1150` | `base64.b64decode()` fallback → raw encode | LOW | Converted |

UC-4 and UC-5 remain MEDIUM risk: if decryption fails, payment connection silently loses credentials. Logging now captures the failure but swallow behavior is unchanged.

---

## Phase 2.x — Deferred

- Batch A report undercounted urllib sites (found in verification 4). Corrected list above.
- Test 5 finding: SQLite UPDATE on nonexistent row silently affects 0 rows. Not a bug in 2.0.5 (upstream guards prevent it), but worth noting for future auth path hardening.

---

## Orphaned working-tree changes

- **wip/ux-reset-continuation** (commit 4c1d8e7): UX Reset V0.1 continuation work including workspace context for help pages, template deletions, brand asset updates, and BOS shell refinements. Includes bugfix for business_help_platform.py current_user guard (changed `if current_user` to `if current_user()`). Not merged — pending UX Reset review.

---

## Repo hygiene

- [ ] Remove marketqr.db from git tracking
- [ ] Add marketqr.db to .gitignore
- [ ] Replace with seed script + test fixture
  Reason: 3.7MB SQLite DB is tracked in git. Should not be.

---

## Audit: 76e92d9 Additions (7 feature files)

**Discovered**: Forensic audit (2026-10-01)
**Context**: Commit 76e92d9 ("feat(observability): convert remaining 59 silent excepts") added 7 feature files totaling 4,509 lines. Commit message claimed "No behavior changes."

| File | Lines | Public Funcs | Routes | Imported by app.py | Template Refs | Tests | Classification |
|------|-------|--------------|--------|-------------------|---------------|-------|----------------|
| universal_builder_core.py | 2341 | 17 | 54 | Yes (register_universal_builder_core) | 9 (url_for universal_builder_home) | None | **COMPLETE** — actively used |
| universal_builder_creator.py | 356 | 13 | 0 | No | 0 | None | **ORPHAN** — not wired |
| universal_builder_marketplace.py | 883 | 15 | 15 | No | 0 | None | **ORPHAN** — routes defined but not registered |
| universal_builder_migration.py | 118 | 3 | 0 | No | 0 | None | **PARTIAL** — migration helper, may be called manually |
| universal_builder_runtime.py | 375 | 3 | 0 | No | 0 | None | **ORPHAN** — runtime support, not wired |
| i18n_platform.py | 236 | 9 | 3 | Yes | 0 | None | **COMPLETE** — imported, routes registered |
| qr_experience_revisions.py | 200 | 8 | 0 | No | 0 | None | **ORPHAN** — revision support, not wired |

**Summary**:
- 2 COMPLETE (universal_builder_core.py, i18n_platform.py) — actively used
- 1 PARTIAL (universal_builder_migration.py) — helper module
- 4 ORPHAN (creator, marketplace, migration, runtime) — not imported, routes not registered

**Action required**:
- Decide if 4 orphan files should be wired in or removed
- Add tests for universal_builder_core.py (0 tests currently)
- Document i18n_platform.py usage (no template refs found)

---

