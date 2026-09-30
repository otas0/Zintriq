# Phase 1 TODO — Deferred Observability Work

This file is append-only. Never delete entries, only mark [DONE].

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
