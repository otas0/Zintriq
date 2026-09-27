# BATCH_B5_REPORT.md — Phase 1.0 Batch B.5

**Date:** 2026-09-27
**Scope:** MEDIUM #37–71 (35), LOW #72–86 (15), UC-1–UC-9 (9) = 59 sites across 38 files
**Pattern:** Pattern A — `_log.debug("event_name", exc_info=True, extra={"op": "..."})`

---

## 1. Blocks Converted

59 silent except blocks converted to Pattern A debug logging across 38 files.

### MEDIUM #37–#71 (35 sites)

| # | File | Logger | Event |
|---|------|--------|-------|
| 37 | `bos/mvp_schema.py` | `app.bos` | `bos_mvp_schema_fallback` |
| 38 | `bos/responses.py` | `app.bos` | `bos_responses_fallback` |
| 39 | `bos/workflows.py` | `app.bos` | `bos_workflows_fallback` |
| 40 | `bos/routes.py` | `app.bos` | `bos_routes_fallback` |
| 41 | `bos/workflows.py` | `app.bos` | `bos_workflows_subscriber_fallback` |
| 42 | `checkout_platform.py` | `app.checkout` | `checkout_braintree_token_fallback` |
| 43 | `customer_account_platform.py` | `app.customer_account` | `customer_account_fallback` |
| 44 | `discover_platform.py` | `app.discover` | `discover_fallback` |
| 45 | `event_platform.py` | `app.event` | `event_fallback` |
| 46 | `feedback_core_platform.py` | `app.feedback` | `feedback_core_fallback` |
| 47 | `feedback_platform.py` | `app.feedback` | `feedback_template_fallback` |
| 48 | `feedback_platform.py` | `app.feedback` | `feedback_render_fallback` |
| 49 | `guest_platform.py` | `app.guest` | `guest_stats_fallback` |
| 50 | `guest_platform.py` | `app.guest` | `guest_context_fallback` |
| 51 | `home_platform.py` | `app.home` | `home_fallback` |
| 52 | `i18n_platform.py` | `app.i18n` | `i18n_locale_fallback` |
| 53 | `i18n_platform.py` | `app.i18n` | `i18n_translations_fallback` |
| 54 | `integrations/payment/__init__.py` | `app.payment` | `payment_integration_fallback` |
| 55 | `integrations/payment/__init__.py` | `app.payment` | `payment_integration_init_fallback` |
| 56 | `payment_connect_plugin.py` | `app.payment` | `payment_connect_access_fallback` |
| 57 | `payment_connect_plugin.py` | `app.payment` | `payment_connect_refresh_fallback` |
| 58 | `qr_customer_data.py` | `app.qr_customer` | `qr_customer_data_fallback` |
| 59 | `qr_customer_data.py` | `app.qr_customer` | `qr_customer_display_fallback` |
| 60 | `qr_customer_data.py` | `app.qr_customer` | `qr_customer_render_fallback` |
| 61 | `qr_experience_platform.py` | `app.qr_experience` | `qr_experience_fallback` |
| 62 | `qr_experience_platform.py` | `app.qr_experience` | `qr_experience_builder_fallback` |
| 63 | `qr_experience_revisions.py` | `app.qr_experience` | `qr_experience_revision_fallback` |
| 64 | `qr_experience_workflow.py` | `app.qr_experience` | `qr_experience_workflow_fallback` |
| 65 | `storefront_platform.py` | `app.storefront` | `storefront_fallback` |
| 66 | `universal_builder_core.py` | `app.universal_builder` | `universal_builder_core_fallback` |
| 67 | `universal_builder_creator.py` | `app.universal_builder` | `universal_builder_creator_fallback` |
| 68 | `universal_builder_marketplace.py` | `app.universal_builder` | `universal_builder_marketplace_fallback` |
| 69 | `universal_builder_migration.py` | `app.universal_builder` | `universal_builder_migration_fallback` |
| 70 | `universal_builder_runtime.py` | `app.universal_builder` | `universal_builder_runtime_fallback` |
| 71 | `workspace_platform.py` | `app.workspace` | `workspace_fallback` |

### LOW #72–#86 (15 sites)

| # | File | Logger | Event |
|---|------|--------|-------|
| 72 | `app.py` | `app.core` | `core_inject_fallback` |
| 73 | `app.py` | `app.core` | `core_presence_fallback` |
| 74 | `booking_platform.py` | `app.booking` | `booking_fallback` |
| 75 | `calendar_platform.py` | `app.calendar` | `calendar_fallback` |
| 76 | `integration_platform.py` | `app.integration` | `integration_fallback` |
| 77 | `payment_apac_adapters.py` | `app.payment_apac` | `payment_apac_fallback` |
| 78 | `qr_experience_analytics.py` | `app.qr_experience` | `qr_experience_analytics_fallback` |
| 79 | `session_remember.py` | `app.session` | `session_remember_fallback` |
| 80 | `storefront_platform.py` | `app.storefront` | `storefront_tz_fallback` |
| 81 | `storefront_platform.py` | `app.storefront` | `storefront_locale_fallback` |
| 82 | `storefront_platform.py` | `app.storefront` | `storefront_currency_fallback` |
| 83 | `storefront_platform.py` | `app.storefront` | `storefront_analytics_fallback` |
| 84 | `storefront_platform.py` | `app.storefront` | `storefront_scan_fallback` |
| 85 | `task_platform.py` | `app.task` | `task_fallback` |
| 86 | `team_platform.py` | `app.team` | `team_fallback` |

### UC-1–UC-9 (9 sites — unconverted `except Exception:` found by RULE 1 second-pass)

| # | File | Logger | Event |
|---|------|--------|-------|
| UC-1 | `checkout_platform.py` | `app.checkout` | `checkout_braintree_token_exception` |
| UC-2 | `customer_verification.py` | `app.customer_verification` | `customer_verification_url_for_failed` |
| UC-3 | `team_platform.py` | `app.team` | `team_upsert_fallback` |
| UC-4 | `payment_connect_plugin.py` | `app.payment` | `payment_connect_decrypt_access` |
| UC-5 | `payment_connect_plugin.py` | `app.payment` | `payment_connect_decrypt_refresh` |
| UC-6 | `storefront_platform.py` | `app.storefront` | `storefront_zoneinfo_fallback` |
| UC-7 | `feedback_reputation_plugins.py` | `app.feedback` | `feedback_reputation_meta_fallback` |
| UC-8 | `feedback_reputation_plugins.py` | `app.feedback` | `feedback_reputation_reviews_fallback` |
| UC-9 | `payment_checkout_adapters.py` | `app.payment_checkout` | `payment_checkout_signing_key_fallback` |

---

## 2. RULE 1 Second-Pass Results

RULE 1 requires a self-audit with a different grep pattern before finalizing reports.

**Grep pattern used:** `except Exception:` across all `.py` files (excluding `.venv/`, `scripts/`).

**Result:** 9 additional `except Exception:` blocks found that were NOT in the original audit (UC-1 through UC-9). All 9 were converted in this batch.

**Post-conversion verification:** `grep -rn "except Exception:" --include="*.py" . | grep -v .venv | grep -v scripts/` — all remaining `except Exception:` blocks now have a `_log.debug()` or `_log.error()` call as the first line inside the except body. Zero silent swallowing remains.

---

## 3. RULE 2 Disclosure — Under-Count

The original OBSERVABILITY_AUDIT.md header claimed **72** silent except blocks. The actual count was **95**:

- 86 numbered items (19 CRITICAL + 17 HIGH + 35 MEDIUM + 15 LOW)
- 9 unconverted `except Exception:` blocks (UC-1 through UC-9)

The discrepancy of 23 items (95 − 72) arose from:
1. Non-contiguous numbering in the original audit (some sections skipped numbers)
2. 9 `except Exception:` blocks not captured by the initial audit methodology

**This under-count is now corrected.** Header updated to 95. Reconciliation table added to audit file.

---

## 4. RULE 3 — PHASE_1_TODO.md Updates

Section `Phase 1.1c` updated: all 9 UC items marked `[DONE — Batch B.5]` with Status column showing "Converted" for each. UC-4 and UC-5 retain MEDIUM risk note (silent credential loss if decryption fails — logging added but swallow unchanged).

No new deferred items discovered during B.5.1.

---

## 5. Commit Count

Exactly **3 commits:**

1. `feat(observability): convert remaining 59 silent excepts (Pattern A)` — B.5.1
2. `fix(auth): detect 0-row UPDATE in email login flag path` — B.5.2
3. `docs(observability): reconcile audit numbers (72 → 95)` — B.5.3

---

## 6. Zero Behavior Changes Confirmation

**B.5.1:** Pattern A adds `_log.debug()` as the first line inside each except block. No try/except structure changed. No swallow behavior changed. No return values changed. No control flow changed. Debug-level logs are invisible at default WARNING threshold — zero runtime impact unless log level is explicitly lowered.

**B.5.2:** Added `rowcount == 0` check after `UPDATE users SET allow_email_login = 1`. This is a **detection improvement** — if the UPDATE affects 0 rows (user ID doesn't exist), it now returns a 500 with a reference ID instead of silently succeeding. The upstream code path already validates `uid` exists, so this check is a defensive guard that should never fire in normal operation. No change to the happy path.

**B.5.3:** Documentation-only changes to OBSERVABILITY_AUDIT.md and PHASE_1_TODO.md. No code changes.

**SUSPECT flags:** None. All 59 MEDIUM/LOW/UC items classified as SAFE or defensible fallbacks. No load-bearing logic identified.

**PII flags:** None. All event names are generic (`*_fallback`, `*_failed`). No user data, email addresses, or payment tokens logged. PIIFilter provides last-line defense.

**User-visible behavior change:** None. B.5.2's rowcount check could theoretically change a silent success to a 500 error, but only if the user ID doesn't exist in the database — which upstream validation prevents.
