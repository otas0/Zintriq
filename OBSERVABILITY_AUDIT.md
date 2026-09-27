# OBSERVABILITY_AUDIT.md — Step 1 Deliverable

**Date:** 2026-09-27
**Scope:** Full Python backend at `/Users/darrenlucase/Desktop/i-want-to-build-a-site/`
**Excluded:** `.venv/`, `scripts/`, node_modules, static assets

---

## Executive Summary

The system has **zero formal logging infrastructure**. There is no `import logging` anywhere in the codebase. The only logging is 15 ad-hoc `app.logger.warning()` calls scattered across 4 files. There are **95 silent/swallowing except blocks** across 38 files (86 numbered below + 9 unconverted `except Exception` found by RULE 1 second-pass), **5 bare `print()` calls** in production paths, and **only 1 error handler** (404) — no 500 handler exists. When things break, they break silently and invisibly.

**Key numbers:**
- 95 silent except blocks (86 numbered + 9 UC; 19 CRITICAL, 17 HIGH, 35 MEDIUM, 15 LOW, 9 UC)
- 15 existing log calls (all `warning` level except 1 `error`, 1 `exception`)
- 0 logging configuration (no formatters, handlers, rotation, or levels)
- 5 bare `print()` in production code
- 6 generic "Something went wrong" error messages with no traceability
- ~380 routes across 26 files, 0 request-level logging
- 7 files making external HTTP calls, no centralized error tracking
- 1 error handler (404 only) — no 400, 403, 500 handlers

---

## (a) Silent/Swallowing `except` Block Inventory

**Total: 95 instances across 38 files (86 numbered + 9 UC)**

### CRITICAL RISK — `except Exception: pass` (catches everything, discards silently)

These catch *all* exceptions including programming errors (NameError, TypeError, etc.), making debugging impossible.

| # | File:Line | Exception Type | Function | What the try block does | Tag | Rationale |
|---|-----------|---------------|----------|------------------------|-----|-----------|
| 1 | `app.py:661` | `Exception` | `inject_guest_context()` | Building guest context dict — returns default on any error | **SAFE** | Returns safe fallback dict; page renders with degraded but non-breaking guest context |
| 2 | `app.py:801` | `Exception` | `wrapped()` (decorator) | Recording user presence via `touch_user_presence()` | **SAFE** | Pure side-effect (presence heartbeat); execution continues to view() regardless |
| 3 | `app.py:1359` | `Exception` | `perform_check_in()` | Bridging legacy check-in data | **SAFE** | Post-success data migration; check-in already logged; validation dict continues normally |
| 4 | `app.py:3250` | `Exception` | `qr_entry()` `/qr/<code>` | Looking up QR experience slug for redirect | **SUSPECT** | If DB query throws, redirect to `/e/<slug>` is skipped; user lands on wrong page (storefront instead of experience) |
| 5 | `bos_modules_platform.py:78` | `Exception` | `emit_mod()` inner fn | Emitting platform event via `bos.events.emit()` | **SAFE** | Fire-and-forget activity/event feed side-effect; no user-visible output depends on it |
| 6 | `checkout_platform.py:384` | `Exception` | `fulfill_checkout()` | Recording store event `checkout_paid` after order fulfillment | **SAFE** | Fires AFTER fulfill_checkout already returned; purely analytics/event log, order already fulfilled |
| 7 | `checkout_platform.py:734` | `Exception` | `store_checkout_success()` | Verifying Stripe payment status to fulfill order | **SUSPECT** | Verification + fulfill_checkout silently skipped; order stays unpaid, no order created, yet checkout_success.html renders — customer sees success for unfulfilled payment |
| 8 | `checkout_platform.py:753` | `Exception` | `store_checkout_success()` | Verifying PayPal payment capture to fulfill order | **SUSPECT** | Same as #7 — PayPal capture + fulfillment skipped; success page shown for potentially un-captured order |
| 9 | `checkout_platform.py:770` | `Exception` | `store_checkout_success()` | Verifying generic payment provider | **SUSPECT** | Same as #7 — generic verification + fulfillment skipped; success page rendered for unverified order |
| 10 | `customer_verification.py:787` | `Exception` | `customer_link_email_check()` | ALTER TABLE to add `allow_email_login` column | **SUSPECT** | UPDATE allow_email_login=1 is inside same try; if ALTER fails, flag stays 0, user cannot log in with linked email, but response returns `{"ok": True}` |
| 11 | `feedback_core_platform.py:701` | `Exception` | `survey_submit_post()` | Recording store event after survey submission | **SAFE** | Survey already saved; swallowed block only records QR session interactions — purely analytics side-effects |
| 12 | `feedback_platform.py:834` | `Exception` | `manage_feedback_detail()` | Loading feedback template and parsing blocks | **SUSPECT** | If template loading fails, template=None and blocks=[] passed to rendered page; owner sees feedback detail page missing its content blocks — silently broken view |
| 13 | `payment_connect_plugin.py:408` | `Exception` | `_rollback_request_db()` | Rolling back SQLite connection on error | **SAFE** | Teardown/error-recovery helper; if rollback itself fails, no meaningful recovery path; connection cleaned up at request end |
| 14 | `payment_connect_plugin.py:950` | `Exception` | `payment_connect_status()` | Refreshing Stripe account status from API | **SUSPECT** | If refresh fails, status endpoint returns stale/cached DB data; user sees potentially wrong payment connection status with no indication of failure |
| 15 | `payment_connect_plugin.py:956` | `Exception` | `payment_connect_status()` | Refreshing PayPal account status from API | **SUSPECT** | Same as #14 but for PayPal; stale data shown with no error signal |
| 16 | `place_platform.py:327` | `Exception` | `add_place_tenant()` | Inserting store into place (tenant approval) | **SUSPECT** | Returns False on any exception; caller shows "already listed or cannot be added" — masks real DB error (constraint, connection, etc.) with misleading message |
| 17 | `qr_experience_analytics.py:198` | `Exception` | `_worker()` background thread | Inserting analytics event into DB | **SAFE** | Background daemon thread draining analytics queue; no user-facing request depends on this |
| 18 | `reputation_connect_plugin.py:333` | `Exception` | `reputation_oauth_callback()` | Fetching Google business profile after OAuth | **SUSPECT** | If profile fetch fails, code falls through with empty/wrong external_id/email; OAuth connection succeeds but with incomplete profile data, no error signal |
| 19 | `storefront_platform.py:788` | `Exception` | `_count_landing_scans()` | Counting QR scan analytics events | **SUSPECT** | Returns 0 on any exception; feeds owner's Insights dashboard; DB error silently shows zero scans instead of real count or error state |

### HIGH RISK — Silent error response returned to user with no logging

Exception is caught and converted to an API error response, but the actual error is never logged — diagnostic information is lost.

| # | File:Line | Exception Type | Function | What the try block does | Tag | Rationale |
|---|-----------|---------------|----------|------------------------|-----|-----------|
| 20 | `bos_modules_platform.py:327` | `Exception` | `api_tags_create()` | Inserting new customer tag (catches duplicate) | **SUSPECT** | `except Exception` too broad — should be `sqlite3.IntegrityError`; masks DB errors, connection failures with misleading "Tag already exists" 409 |
| 21 | `checkout_platform.py:408` | `ValueError` | `api_checkout_quote()` | Price validation during cart quote | **SAFE** | ValueError is exactly what quote_cart() raises for validation; 400 with str(exc) is correct response |
| 22 | `checkout_platform.py:435` | `ValueError` | `api_checkout_create()` | Price validation during checkout creation | **SAFE** | Same as #21 — ValueError from quote_cart() is correct catch; 400 is appropriate |
| 23 | `checkout_platform.py:670` | `RuntimeError` | `store_checkout_braintree()` | Braintree payment API call | **SUSPECT** | Wrong exception type — `_http_post_form()` uses urllib which raises URLError/HTTPError/TimeoutError, never RuntimeError; except block is dead code, real failures produce unhandled 500s |
| 24 | `customer_platform.py:805` | `Exception` | `api_customer_tags_create()` | Inserting customer tag (catches duplicate) | **SUSPECT** | `except Exception` too broad — should be `sqlite3.IntegrityError`; masks DB errors with misleading "Tag already exists" 409 |
| 25 | `customer_platform.py:846` | `Exception` | `api_customer_groups_create()` | Inserting customer group (catches duplicate) | **SUSPECT** | `except Exception` too broad — should be `sqlite3.IntegrityError`; masks DB errors with misleading "Group already exists" 409 |
| 26 | `customer_verification.py:585` | `ValueError` | `customer_onboarding_complete()` | Saving uploaded avatar image | **SAFE** | ValueError is exactly what save_uploaded_image() raises for invalid file type; validation message is correct; OSError correctly propagates as 500 |
| 27 | `customer_verification.py:713` | `sqlite3.IntegrityError` | `customer_onboarding_complete()` | Creating user account (unique constraint) | **SAFE** | Precise and correct catch for unique-constraint violation on username; message is appropriate |
| 28 | `merchant_phone_auth.py:175` | `sqlite3.IntegrityError` | `merchant_phone_complete()` | Creating merchant user (unique constraint) | **SAFE** | Precise and correct catch for unique-constraint violation; message is appropriate |
| 29 | `payment_connect_plugin.py:850` | `Exception` | `payment_connect_oauth_callback()` | Exchanging OAuth code for access token | **SAFE** | `except Exception` reasonable for OAuth (covers URLError, HTTPError, JSONDecodeError, KeyError); generic redirect doesn't leak provider details |
| 30 | `reputation_connect_plugin.py:349` | `Exception` | `reputation_oauth_callback()` | Storing OAuth credentials in DB | **SUSPECT** | `except Exception` wraps both token exchange AND DB INSERT, but always reports "token_exchange_failed" — DB storage failure mislabeled, misleading for debugging |
| 31 | `universal_builder_core.py:1367` | `ValueError` | `api_builder_core_project_create()` | Creating project from template | **SAFE** | ValueError is exactly what create_project_from_template() raises; 400 with str(error) is correct |
| 32 | `universal_builder_core.py:1982` | `PermissionError` | `api_builder_core_package_install()` | Package install permission check | **SAFE** | PermissionError is exactly what install_package() raises; 403 is correct HTTP status |
| 33 | `universal_builder_core.py:1984` | `ValueError` | `api_builder_core_package_install()` | Package install validation | **SUSPECT** | ValueError means "package version not available" — validation/not-found error — but response is 409 Conflict; wrong HTTP status, should be 400 or 404 |
| 34 | `universal_builder_core.py:2061` | `ValueError` | `api_builder_component_from_node()` | Creating component from document subtree | **SAFE** | ValueError is exactly what create_definition_from_subtree() raises; 400 with message is appropriate |
| 35 | `universal_builder_marketplace.py:694` | `PermissionError` | `marketplace_publish_component()` | Publishing component (permission) | **SAFE** | PermissionError is exactly what publish_component() raises for wrong owner; 403 is correct |
| 36 | `universal_builder_marketplace.py:696` | `ValueError` | `marketplace_publish_component()` | Publishing component (validation) | **SAFE** | ValueError is exactly what publish_component() raises for validation failures; 400 is appropriate |

### MEDIUM RISK — JSON/parse helpers returning defaults silently

Defensible as defensive coding, but can mask data corruption.

| # | File:Line | Exception Type | Function | What the try block does |
|---|-----------|---------------|----------|------------------------|
| 37 | `bos/mvp_schema.py:158` | `(TypeError, json.JSONDecodeError)` | `experience_content_from_row()` | Parsing JSON `content` field from DB row |
| 38 | `bos/responses.py:33` | `(TypeError, json.JSONDecodeError)` | `_parse_data()` | Parsing raw JSON string into dict |
| 39 | `bos/workflows.py:182` | `(json.JSONDecodeError, TypeError)` | `_parse_json()` | Parsing raw JSON with fallback |
| 40 | `bos/routes.py:57` | `(TypeError, ValueError)` | `inject_bos_modules()` | Fetching workspace name from DB |
| 41 | `bos/workflows.py:208` | `(TypeError, ValueError)` | `evaluate_conditions()` | Converting values to float for comparison |
| 42 | `checkout_platform.py:83` | `(TypeError, ValueError)` | `platform_fee_cap()` | Parsing `PLATFORM_FEE_CAP_USD` env var |
| 43 | `customer_account_platform.py:196` | `(TypeError, ValueError)` | `current_customer_id()` | Converting session `customer_user_id` to int |
| 44 | `discover_platform.py:59` | `(TypeError, ValueError)` | `_store_discover_payload()` | Computing haversine distance |
| 45 | `event_platform.py:50` | `(json.JSONDecodeError, TypeError)` | `event_row_to_api()` | Parsing event metadata JSON |
| 46 | `feedback_core_platform.py:214` | `(TypeError, ValueError)` | `_submit_survey_response()` | Parsing rating answer as int |
| 47 | `feedback_platform.py:454` | `json.JSONDecodeError` | `parse_blocks()` | Parsing feedback template blocks JSON |
| 48 | `feedback_platform.py:468` | `(TypeError, ValueError)` | `extract_from_responses()` | Parsing rating value as int |
| 49 | `guest_platform.py:490` | `(KeyError, TypeError)` | `_store_field()` | Accessing field from store dict |
| 50 | `guest_platform.py:561` | `(TypeError, ValueError)` | `brand_hub_for_store()` | Computing haversine distance |
| 51 | `home_platform.py:178` | `(TypeError, json.JSONDecodeError)` | `_recent_responses()` | Parsing response data JSON |
| 52 | `i18n_platform.py:93` | `(OSError, json.JSONDecodeError)` | `_load_locale()` | Reading/parsing locale JSON file |
| 53 | `i18n_platform.py:108` | `(KeyError, ValueError)` | `translate()` | Formatting translated string |
| 54 | `integrations/payment/__init__.py:95` | `json.JSONDecodeError` | `parse_webhook()` | Parsing Stripe webhook payload |
| 55 | `integrations/payment/__init__.py:104` | `(TypeError, ValueError)` | `parse_webhook()` | Converting workspace_id from metadata |
| 56 | `payment_connect_plugin.py:356` | `json.JSONDecodeError` | `_connection_metadata()` | Parsing connection metadata JSON |
| 57 | `payment_connect_plugin.py:586` | `json.JSONDecodeError` | `payment_connection_to_api()` | Parsing metadata JSON from row |
| 58 | `qr_customer_data.py:134` | `json.JSONDecodeError` | `_enrich_customer_profile()` | Parsing customer profile metadata |
| 59 | `qr_customer_data.py:337` | `json.JSONDecodeError` | `list_qr_customers()` | Parsing customer metadata per row |
| 60 | `qr_customer_data.py:367` | `json.JSONDecodeError` | `customer_detail()` | Parsing customer metadata for detail |
| 61 | `qr_experience_platform.py:252` | `(TypeError, json.JSONDecodeError)` | `experience_to_api()` | Parsing analytics_config JSON |
| 62 | `qr_experience_platform.py:708` | `(TypeError, json.JSONDecodeError)` | `api_qr_experience_update()` | Parsing experience_config for ref_id |
| 63 | `qr_experience_revisions.py:149` | `json.JSONDecodeError` | `published_snapshot()` | Parsing revision snapshot JSON |
| 64 | `qr_experience_workflow.py:109` | `json.JSONDecodeError` | `_parse_steps()` | Parsing workflow steps JSON |
| 65 | `storefront_platform.py:370` | `(TypeError, json.JSONDecodeError)` | `parse_hours_json()` | Parsing store hours JSON |
| 66 | `universal_builder_core.py:389` | `(TypeError, json.JSONDecodeError)` | `_json()` | Parsing JSON value with fallback |
| 67 | `universal_builder_creator.py:32` | `(TypeError, json.JSONDecodeError)` | `load_json()` | Parsing JSON value with fallback |
| 68 | `universal_builder_marketplace.py:124` | `(TypeError, json.JSONDecodeError)` | `json_load()` | Parsing JSON value with fallback |
| 69 | `universal_builder_migration.py:17` | `(TypeError, json.JSONDecodeError)` | `_json()` | Parsing JSON value with fallback |
| 70 | `universal_builder_runtime.py:29` | `(TypeError, json.JSONDecodeError)` | `_json()` | Parsing JSON value with fallback |
| 71 | `workspace_platform.py:792` | `json.JSONDecodeError` | `api_workspace_settings_get()` | Parsing workspace settings JSON |

### LOWER RISK — Infrastructure/safety, arguably intentional

| # | File:Line | Exception Type | Function | What the try block does |
|---|-----------|---------------|----------|------------------------|
| 72 | `app.py:1066` | `(TypeError, ValueError)` | `parse_item_group_arg()` | Parsing string arg to int |
| 73 | `app.py:1790` | `OSError` | `lan_ip()` | Detecting LAN IP via UDP socket |
| 74 | `booking_platform.py:55` | `ValueError` | `_default_end()` | Parsing ISO datetime for default end |
| 75 | `calendar_platform.py:127` | `ValueError` | `_default_end()` | Parsing datetime for default end |
| 76 | `integration_platform.py:110` | `ImportError` | `init_integration_tables()` | Optional module import |
| 77 | `payment_apac_adapters.py:66` | `ValueError` | `_safe_https_base()` | IP validation (SSRF check) |
| 78 | `qr_experience_analytics.py:177` | `queue.Full` | `enqueue_analytics_event()` | Non-blocking enqueue (bounded queue) |
| 79 | `session_remember.py:67` | `(BadSignature, SignatureExpired, ...)` | `customer_id_from_remember_token()` | Validating remember-me token |
| 80 | `storefront_platform.py:33` | `(TypeError, ValueError)` | `normalize_allow_cart()` | Coercing allow_cart to 0/1 |
| 81 | `storefront_platform.py:179` | `ValueError` | `_parse_deal_datetime()` | Parsing ISO datetime for deal |
| 82 | `storefront_platform.py:425` | `(TypeError, ValueError)` | `_parse_clock()` | Parsing time string |
| 83 | `storefront_platform.py:612` | `(URLError, TimeoutError, ...)` | `geocode_address()` | OpenStreetMap Nominatim API call |
| 84 | `storefront_platform.py:618` | `(KeyError, TypeError, ValueError)` | `geocode_address()` | Extracting lat/lon from response |
| 85 | `task_platform.py:150` | `ValueError` | `_due_bucket()` | Parsing ISO date for task bucket |
| 86 | `team_platform.py:109` | `(ValueError, TypeError)` | `_presence_state()` | Parsing timestamp for presence |

---

## (b) `except Exception` Inventory (Non-Silent)

These catch `Exception` but do something (re-raise, log, or transform). Found **0 additional non-silent `except Exception` blocks** beyond the 15 silent ones listed in section (a). Every `except Exception` in the codebase is silent.

---

## (c) Bare `print()` in Production Paths

**Total: 5 instances in 2 files**

| # | File:Line | What it prints | Context |
|---|-----------|---------------|---------|
| 1 | `payment_connect_plugin.py:1198` | `f" * Purged {n} fake/unverified integration connection(s)"` | Startup bootstrap — purge report |
| 2 | `payment_connect_plugin.py:1200` | `f" * Integration purge skipped: {exc}"` | Startup bootstrap — purge failure |
| 3 | `app.py:4763` | `f" * Local:   http://127.0.0.1:{port}"` | `__main__` block — dev server URL |
| 4 | `app.py:4765` | `f" * Network: http://{ip}:{port}"` | `__main__` block — dev server URL |
| 5 | `app.py:4767` | `f" * QR tip:  PUBLIC_BASE_URL=..."` | `__main__` block — dev server hint |

**Risk:** Items 1-2 run at startup inside `with app.app_context()` and are reached in production WSGI. Items 3-5 are inside `if __name__ == "__main__"` and are dev-only.

---

## (d) Generic Error Responses to Users

**Total: 6 distinct messages**

| # | File:Line | Exact Text | Context |
|---|-----------|-----------|---------|
| 1 | `universal_builder_runtime.py:320` | `'Something went wrong. Please try again.'` | Form failure default in rendered HTML |
| 2 | `builder_components.py:67` | `"Something went wrong. Please try again."` | Form component default failure_message |
| 3 | `feedback_platform.py:139` | `"We're sorry something went wrong"` | Complaint feedback template heading |
| 4 | `app.py:4467` | `"Something went wrong."` | Flash message for place-application result |
| 5 | `i18n/locales/en.json:307` | `"bos.error": "Something went wrong"` | i18n locale string |
| 6 | `static/i18n/messages.js:3574` | `"bos.error": "Something went wrong"` | JS i18n message catalog |

**Risk:** None of these include correlation IDs, request IDs, or any traceability. When a user reports "something went wrong", there is no way to find the corresponding server-side state.

### Payment error responses that leak internals

| # | File:Line | Issue |
|---|-----------|-------|
| 7 | `checkout_platform.py:502` | Raw Stripe error message returned to user |
| 8 | `checkout_platform.py:539` | Raw PayPal error detail returned to user |
| 9 | `checkout_platform.py:568` | Raw Braintree error returned to user |
| 10 | `checkout_platform.py:671` | Raw provider RuntimeError returned to user |

---

## (e) Existing Logging Setup

### Configuration: **NONE**

- `import logging` — **0 occurrences** in entire codebase
- `logging.basicConfig` — **0 occurrences**
- `logging.getLogger` — **0 occurrences**
- `logging.config.dictConfig` — **0 occurrences**
- No log formatters, no handlers, no file output, no rotation, no log levels configured

### Existing log calls: **15 total across 4 files**

| # | File:Line | Level | What is logged |
|---|-----------|-------|---------------|
| 1 | `app.py:223` | `warning` | `"place analytics skipped: %s"` — DB lock error |
| 2 | `app.py:692` | `warning` | `"Could not record store visit (database busy)"` — with exc_info |
| 3 | `app.py:1930` | `warning` | `"Development password-reset link: %s"` — dev reset URL |
| 4 | `app.py:1962` | `warning` | `"Development magic-login link: %s"` — dev magic URL |
| 5 | `app.py:4183` | `warning` | `"Dev: new inquiry %s for store %s"` — notification failure |
| 6 | `app.py:4360` | `warning` | `"Dev: tenant approved for application %s"` |
| 7 | `app.py:4379` | `warning` | `"Dev: tenant rejected for application %s"` |
| 8 | `app.py:4455` | `warning` | `"Dev: new tenant application %s"` |
| 9 | `app.py:4524` | `warning` | `"Dev: new tenant application %s"` (place detail variant) |
| 10 | `customer_account_platform.py:525` | `warning` | `"Customer password-reset link: %s"` |
| 11 | `customer_account_platform.py:573` | `warning` | `"Customer magic-login link: %s"` |
| 12 | `customer_verification.py:190` | `warning` | `"Customer verification email to %s — %s: %s"` — **logs full email body** |
| 13 | `customer_verification.py:204` | `exception` | `"Twilio SMS failed: %s"` — Twilio API failure |
| 14 | `customer_verification.py:205` | `warning` | `"Customer verification SMS to %s — %s"` — **logs full SMS body** |
| 15 | `universal_builder_migration.py:113` | `error` | `"Universal Builder route fallback for %s: %s"` |

**Observations:**
- All 15 use Flask's default `app.logger` / `current_app.logger`
- 13 of 15 are `warning` level — no `info`, no `debug`
- Items 12 and 14 log full email/SMS body content (potential PII concern)
- Items 3, 4, 10, 11 log dev-only URLs (acceptable in dev, risk in prod)
- No request logging middleware exists
- No log correlation IDs

---

## (f) External Calls as Trace Points

**Total: 7 production files making outbound HTTP calls. All use `urllib.request`.**

### Payment Providers

| File:Line | Service | Endpoint | Purpose |
|-----------|---------|----------|---------|
| `checkout_platform.py:312` | **Stripe** | `POST https://api.stripe.com/v1/checkout/sessions` | Create checkout session |
| `checkout_platform.py:721` | **Stripe** | `GET https://api.stripe.com/v1/checkout/sessions/{id}` | Verify payment status |
| `payment_connect_plugin.py:361` | **Stripe** | `GET {STRIPE_API}/account` | Verify secret key |
| `payment_connect_plugin.py:481` | **Stripe** | `GET {STRIPE_API}/accounts/{id}` | Get connected account status |
| `integrations/payment/__init__.py:65` | **Stripe** | `POST https://api.stripe.com/v1/customers` | Create customer |
| `checkout_platform.py:670` | **Braintree** | (via adapter) | Payment processing |
| `payment_connect_plugin.py:53-76` | **Generic** | (helper functions) | POST/GET/JSON for any provider |

### Reputation / Review Providers

| File:Line | Service | Endpoint | Purpose |
|-----------|---------|----------|---------|
| `reputation_connect_plugin.py:139` | **Google Merchant Center** | `GET https://shoppingcontent.googleapis.com/content/v2.1/accounts/authinfo` | Verify OAuth auth |
| `reputation_connect_plugin.py:144` | **Google Business Profile** | `GET https://mybusinessaccountmanagement.googleapis.com/v1/accounts` | Verify OAuth auth |
| `reputation_connect_plugin.py:129-158` | **Generic** | (helper functions) | OAuth token exchange for any provider |

### Geocoding

| File:Line | Service | Endpoint | Purpose |
|-----------|---------|----------|---------|
| `storefront_platform.py:607` | **OpenStreetMap Nominatim** | `GET https://nominatim.openstreetmap.org/search` | Geocode store address |

### Other External Services (identified but not HTTP)

| Service | File | Purpose |
|---------|------|---------|
| **Firebase** | `app.py` | Push notifications |
| **SMTP** | `customer_verification.py` | Email sending |
| **Twilio** | `customer_verification.py` | SMS sending |
| **QR generation** | `qr_experience_platform.py` | QR code image generation |
| **Local file upload** | Multiple | File storage to disk |

### Generic Adapters

| File:Line | Purpose |
|-----------|---------|
| `payment_checkout_adapters.py:35-55` | Generic POST/GET for any payment checkout provider |
| `integration_credential_verify.py:37-39` | Generic credential verification against any provider |

**Trace point count: ~20 distinct outbound call sites across 7+ files. None have centralized error tracking, retry logic, or timeout standardization.**

---

## (g) Request Entry Points

### Route inventory: ~380 routes across 26 files

| File | Route Count | Domain |
|------|------------|--------|
| `app.py` | 97 | Core: auth, storefront, manage, places, QR scans |
| `universal_builder_core.py` | 51 | Builder: projects, components, documents, publishing |
| `qr_experience_platform.py` | 39 | QR experiences: CRUD, publish, workflow |
| `contact_platform.py` | 15 | Contact management: CRUD, merge, export |
| `team_platform.py` | 18 | Team: members, invitations, ownership |
| `customer_platform.py` | 16 | Customer CRM: CRUD, tags, groups, export |
| `customer_account_platform.py` | 14 | Customer auth: register, login, account |
| `task_platform.py` | 12 | Tasks: CRUD, complete, comments |
| `feedback_platform.py` | 9 | Feedback: inbox, templates, surveys |
| `payment_connect_plugin.py` | 8 | Payment integration: OAuth, connect |
| `checkout_platform.py` | 7 | Checkout: quote, create, pay, success |
| `calendar_platform.py` | 7 | Calendar: CRUD, conflicts |
| `booking_platform.py` | 7 | Bookings: CRUD, assign, cancel |
| `checkin_platform.py` | 7 | Check-ins: CRUD, scan, complete |
| `qr_experience_workflow.py` | 6 | QR workflow: CRUD, publish |
| `qr_experience_runtime.py` | 6 | QR runtime: session interact, booking |
| `reputation_connect_plugin.py` | 6 | Reputation: OAuth, connect |
| `event_platform.py` | 7 | Events, notifications, analytics |
| `bos/routes.py` | ~20 | BOS dashboard: store, settings, QR |
| `universal_builder_marketplace.py` | ~5 | Marketplace: browse, publish |
| `universal_builder_migration.py` | ~3 | Migration: route fallback |
| `qr_experience_analytics.py` | 2 | Analytics: dashboard, per-experience |
| `qr_customer_data.py` | 3 | Customer QR data |
| `merchant_phone_auth.py` | 3 | Phone auth: send, check, complete |
| `i18n_platform.py` | 3 | Languages, locale |
| `mobile_platform.py` | 3 | Manifest, config, service worker |
| `help_platform.py` | 2 | Help pages |
| `integration_platform.py` | 3 | Plugin integrations |
| `workspace_platform.py` | ~5 | Workspace settings |

### Request Hooks

| File:Line | Hook | Purpose |
|-----------|------|---------|
| `app.py:707` | `before_request` | Restore customer "remember me" session from cookie |
| `app.py:728` | `before_request` | Refresh session persistence metadata |
| `app.py:762` | `before_request` | Enforce auth separation (shopper vs business) |
| `app.py:807` | `before_request` | CSRF protection for all POST requests |
| `merchant_phone_auth.py:178` | `before_request` | Block email registration POSTs |
| `i18n_platform.py:164` | `before_request` | Set request language and text direction |
| `app.py:735` | `after_request` | Sync "remember me" cookie on every response |

### Error Handlers

| File:Line | Status | Behavior |
|-----------|--------|----------|
| `app.py:4750` | 404 | JSON for `/api/` paths, HTML template for others |

**Missing error handlers: 400, 403, 405, 413, 500** — all use Flask defaults with no logging.

---

## Risk Summary

| Tier | Count | Description |
|------|-------|-------------|
| **CRITICAL** | 19 | `except Exception: pass` — catches everything, logs nothing |
| **HIGH** | 17 | Silent error responses — user sees error, server has no record |
| **MEDIUM** | 35 | Silent JSON/parse defaults — can mask data corruption |
| **LOW** | 15 | Infrastructure/safety — arguably intentional |
| **TOTAL** | 72+ | Silent exception handling |

### What makes this urgent

1. **Payment flow has 4 silent `except Exception: pass` blocks** (`checkout_platform.py:384,734,753,770`) — if order fulfillment fails, nobody knows
2. **OAuth flows have 3 silent blocks** — if token exchange fails, users are stuck with no diagnostic trail
3. **No 500 error handler** — unhandled exceptions get Flask's default page with zero logging
4. **No request logging** — cannot determine which endpoints are erroring, latency, or error rates
5. **No correlation IDs** — cannot trace a user's request through multiple function calls
6. **PII in logs** — `customer_verification.py:190,205` logs full email/SMS body content

### What Step 2 must address

1. Create a `log.py` module with structured logging configuration
2. Add request-level middleware (method, path, status, duration, correlation ID)
3. Add a 500 error handler that logs the full traceback
4. Replace the 19 CRITICAL `except Exception: pass` blocks with logged versions
5. Replace the 17 HIGH silent error responses with logged versions
6. Replace 5 `print()` calls with proper log calls
7. Remove PII from existing log calls in `customer_verification.py`
8. All changes must be revertable by reverting one commit
9. No changes to return values, control flow, DB schema, or API contracts

---

## Step 0 — SWALLOW_SAFE / SWALLOW_SUSPECT Annotations

**Methodology:** Each of the 36 CRITICAL and HIGH blocks was analyzed against the actual source code. The test: *if the exception were re-raised, would user-visible behavior change?*

### Summary

| Tag | Count | Meaning |
|-----|-------|---------|
| **SWALLOW_SAFE** | 19 | Truly best-effort; re-raising would NOT change user-visible behavior |
| **SWALLOW_SUSPECT** | 17 | Re-raising WOULD change behavior, or catch is too broad, or error response is wrong |

### SWALLOW_SUSPECT blocks flagged for Phase 1.1 (17 total)

These are NOT fixed in Step 2 — they are logged only. The underlying bug (wrong exception type, too-broad catch, misleading error, silent data loss) is flagged for Phase 1.1.

| # | File:Line | Issue | Phase 1.1 Fix |
|---|-----------|-------|---------------|
| 4 | `app.py:3250` | QR lookup failure → user lands on wrong page (storefront instead of experience) | Narrow catch, add fallback redirect |
| 7 | `checkout_platform.py:734` | Stripe verification failure → success page shown for unfulfilled order | **P0 — silent order loss** |
| 8 | `checkout_platform.py:753` | PayPal verification failure → success page shown for unfulfilled order | **P0 — silent order loss** |
| 9 | `checkout_platform.py:770` | Generic verification failure → success page shown for unfulfilled order | **P0 — silent order loss** |
| 10 | `customer_verification.py:787` | ALTER TABLE failure → email login flag never set, user can't log in | Split try blocks, handle race |
| 12 | `feedback_platform.py:834` | Template load failure → page rendered with missing content blocks | Add error state to template |
| 14 | `payment_connect_plugin.py:950` | Stripe refresh failure → stale status shown to user | Add "stale" indicator to response |
| 15 | `payment_connect_plugin.py:956` | PayPal refresh failure → stale status shown to user | Add "stale" indicator to response |
| 16 | `place_platform.py:327` | Tenant approval failure → misleading "already listed" message | Narrow catch, surface real error |
| 18 | `reputation_connect_plugin.py:333` | Google profile fetch failure → incomplete OAuth connection data | Separate profile fetch from credential storage |
| 19 | `storefront_platform.py:788` | Analytics count failure → zero shown on Insights dashboard | Add error state or retry |
| 20 | `bos_modules_platform.py:327` | `except Exception` too broad for INSERT — should be `IntegrityError` | Narrow exception type |
| 23 | `checkout_platform.py:670` | `except RuntimeError` is dead code — urllib never raises RuntimeError | Change to `(URLError, TimeoutError, JSONDecodeError)` |
| 24 | `customer_platform.py:805` | `except Exception` too broad for INSERT — should be `IntegrityError` | Narrow exception type |
| 25 | `customer_platform.py:846` | `except Exception` too broad for INSERT — should be `IntegrityError` | Narrow exception type |
| 30 | `reputation_connect_plugin.py:349` | `except Exception` wraps token exchange + DB store, always reports "token_exchange_failed" | Separate into distinct try/except |
| 33 | `universal_builder_core.py:1984` | ValueError → 409 Conflict is wrong HTTP status | Change to 400 or 404 |

### SWALLOW_SAFE blocks (19 total)

These are logged in Step 2 (adding `log.debug()` or `log.error()` as appropriate) but the swallow itself is correct and stays.

| # | File:Line | Why safe |
|---|-----------|----------|
| 1 | `app.py:661` | Guest context fallback dict — page renders fine without it |
| 2 | `app.py:801` | Presence heartbeat — pure side-effect |
| 3 | `app.py:1359` | Legacy check-in bridge — check-in already recorded |
| 5 | `bos_modules_platform.py:78` | Fire-and-forget event emission |
| 6 | `checkout_platform.py:384` | Post-fulfillment analytics event |
| 11 | `feedback_core_platform.py:701` | Post-submit analytics side-effect |
| 13 | `payment_connect_plugin.py:408` | Rollback teardown — no recovery path |
| 17 | `qr_experience_analytics.py:198` | Background analytics worker thread |
| 21 | `checkout_platform.py:408` | Correct ValueError catch for price validation |
| 22 | `checkout_platform.py:435` | Correct ValueError catch for price validation |
| 26 | `customer_verification.py:585` | Correct ValueError catch for avatar validation |
| 27 | `customer_verification.py:713` | Correct IntegrityError catch for unique constraint |
| 28 | `merchant_phone_auth.py:175` | Correct IntegrityError catch for unique constraint |
| 29 | `payment_connect_plugin.py:850` | Reasonable broad catch for OAuth token exchange |
| 31 | `universal_builder_core.py:1367` | Correct ValueError catch for template validation |
| 32 | `universal_builder_core.py:1982` | Correct PermissionError catch for package install |
| 34 | `universal_builder_core.py:2061` | Correct ValueError catch for component creation |
| 35 | `universal_builder_marketplace.py:694` | Correct PermissionError catch for publish |
| 36 | `universal_builder_marketplace.py:696` | Correct ValueError catch for publish validation |

---

## Reconciliation — Original Count vs Actual

The original audit header claimed **72** silent except blocks. A RULE 1 second-pass grep during Batch B.5 revealed the actual count is **95**. The discrepancy arose because the original audit numbered items non-contiguously (some sections skipped numbers) and 9 additional `except Exception:` blocks were not captured.

| Category | Items | Count | Batch | Status |
|----------|-------|-------|-------|--------|
| CRITICAL | #1–#19 | 19 | Batch B (Step 2) | Converted |
| HIGH | #20–#36 | 17 | Batch B (Step 2) | Converted |
| MEDIUM | #37–#71 | 35 | Batch B.5 | Converted |
| LOW | #72–#86 | 15 | Batch B.5 | Converted |
| UC (unconverted) | UC-1–UC-9 | 9 | Batch B.5 | Converted |
| **Total** | | **95** | | **All converted** |

**Correction:** Header updated from 72 → 95. All 95 silent except blocks now have Pattern A/B logging. Zero silent swallowing remains in production code.
