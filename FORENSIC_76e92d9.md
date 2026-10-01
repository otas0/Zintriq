# Forensic Audit: Commit 76e92d9

**Date**: 2026-10-01
**Auditor**: Batch C.8 forensic check
**Commit**: `76e92d9` — "feat(observability): convert remaining 59 silent excepts (Pattern A)"

---

## STOP CONDITIONS — ALL 4 HIT

| # | Condition | Threshold | Actual | Status |
|---|-----------|-----------|--------|--------|
| 1 | Routes deleted | >3 | **11** | **STOP** |
| 2 | Functions removed | >3 handlers | **10** | **STOP** |
| 3 | Non-observability files | any | **37 files, 5 new feature modules** | **STOP** |
| 4 | logs/ not gitignored | not ignored | **NOT ignored** | **STOP** |

**Phase 1.0 sign-off: BLOCKED. Do NOT proceed to Phase 1.1.**

---

## F1. Full Diff Scope

```
38 files changed, 5147 insertions(+), 497 deletions(-)
```

Files touched (raw `git show --stat 76e92d9`):

| File | Lines |
|------|-------|
| app.py | 378 +/- |
| booking_platform.py | +4 |
| bos/mvp_schema.py | +4 |
| bos/responses.py | +4 |
| bos/routes.py | 61 +/- |
| bos/workflows.py | 7 +/- |
| calendar_platform.py | +4 |
| checkout_platform.py | 89 +/- |
| customer_account_platform.py | 65 +/- |
| customer_verification.py | +192 |
| discover_platform.py | +4 |
| event_platform.py | +4 |
| feedback_core_platform.py | 6 +/- |
| feedback_platform.py | 7 +/- |
| feedback_reputation_plugins.py | +5 |
| guest_platform.py | +5 |
| home_platform.py | +4 |
| **i18n_platform.py** | **+236 (NEW FILE)** |
| integration_platform.py | +4 |
| integrations/payment/__init__.py | +5 |
| payment_apac_adapters.py | +5 |
| payment_checkout_adapters.py | +4 |
| payment_connect_plugin.py | 17 +/- |
| qr_customer_data.py | +6 |
| qr_experience_analytics.py | 6 +/- |
| qr_experience_platform.py | +164 |
| **qr_experience_revisions.py** | **+200 (NEW FILE)** |
| qr_experience_workflow.py | 30 +/- |
| session_remember.py | +4 |
| storefront_platform.py | +13 |
| task_platform.py | +4 |
| team_platform.py | +5 |
| **universal_builder_core.py** | **+2341 (NEW FILE)** |
| **universal_builder_creator.py** | **+356 (NEW FILE)** |
| **universal_builder_marketplace.py** | **+883 (NEW FILE)** |
| **universal_builder_migration.py** | **+118 (NEW FILE)** |
| **universal_builder_runtime.py** | **+375 (NEW FILE)** |
| workspace_platform.py | 25 +/- |

**7 entirely new files** added totaling **4,509 lines** inside a commit labeled "observability."

---

## F2. Commit Message

```
feat(observability): convert remaining 59 silent excepts (Pattern A)

Batch B.5.1: Convert MEDIUM #37-71 (35), LOW #72-86 (15), UC-1-9 (9)
to Pattern A debug logging across 38 files.

Each site receives:
  _log.debug("event_name", exc_info=True, extra={"op": "..."})
as the first line inside the except block. No behavior changes.

Note: audit header undercounted (72 → 95). Reconciled in follow-up commit.
```

Claim: "No behavior changes." **FALSE.** 11 routes deleted, 10 functions deleted, 7 new feature files added.

---

## F3. Non-Observability Files

37 files touched beyond observability/. Every file in the commit except the observability logging additions:

**New feature modules (NOT observability):**
- `universal_builder_core.py` (+2341) — Universal Builder DDL + API
- `universal_builder_creator.py` (+356) — Builder creation flow
- `universal_builder_marketplace.py` (+883) — Builder marketplace
- `universal_builder_migration.py` (+118) — Builder DB migrations
- `universal_builder_runtime.py` (+375) — Builder runtime
- `i18n_platform.py` (+236) — Internationalization platform
- `qr_experience_revisions.py` (+200) — QR experience revisioning

**Platform modules with significant non-observability changes:**
- `customer_verification.py` (+192) — customer verification expansion
- `qr_experience_platform.py` (+164) — QR experience expansion
- `checkout_platform.py` (89 +/-) — checkout changes
- `customer_account_platform.py` (65 +/-) — account changes
- `bos/routes.py` (61 +/-) — BOS route changes
- `workspace_platform.py` (25 +/-) — workspace changes

---

## F4. Route Deletions — 11 Routes

```
-@app.get("/favicon.ico")
-@app.get("/apple-touch-icon.png")
-@app.get("/apple-touch-icon-precomposed.png")
-@app.get("/safari-touch-icon-yellow.png")
-@app.get("/venues")
-@app.get("/home")
-@app.get("/discover")
-@app.get("/api/discover/stores")
-@app.get("/places")
-@app.post("/places/remember")
-@app.get("/guest/remember/<token>")
```

**Count: 11** (threshold was >3)

### Restoration Status

| Route | Restored in C.8? | Status |
|-------|-------------------|--------|
| `/favicon.ico` | Re-added in 76e92d9 itself (new handler) | OK |
| `/apple-touch-icon.png` | Re-added in 76e92d9 itself | OK |
| `/apple-touch-icon-precomposed.png` | Re-added in 76e92d9 itself | OK |
| `/safari-touch-icon-yellow.png` | Re-added in 76e92d9 itself | OK |
| `/venues` | Yes (commit f8fa551) | OK |
| `/discover` | Yes (commit f8fa551) | OK |
| `/places` | Yes (commit f8fa551) | OK |
| **`/home`** | **NO** | **MISSING** |
| **`/api/discover/stores`** | **NO** | **MISSING** |
| **`/places/remember`** | **NO** | **MISSING** |
| **`/guest/remember/<token>`** | **NO** | **MISSING** |

**4 routes remain missing.**

---

## F5. Route Additions — 8 Routes

```
+@app.get("/favicon.ico")
+@app.get("/z-fav-v2.png")
+@app.get("/z-fav-safari-dark.png")
+@app.get("/z-touch-v2.png")
+@app.get("/apple-touch-icon.png")
+@app.get("/apple-touch-icon-precomposed.png")
+@app.get("/safari-touch-icon-yellow.png")
+@app.get("/workspace")
```

**Count: 8**

Unexpected additions:
- 3 new favicon routes (`z-fav-v2.png`, `z-fav-safari-dark.png`, `z-touch-v2.png`) — brand asset changes, NOT observability
- `/workspace` — new dashboard route, NOT observability

---

## F6. Function Removals — 10 Functions

```
-def favicon():
-def apple_touch_icon():
-def safari_tab_icon():
-def guest_venues():
-def guest_home():
-def guest_discover():
-def api_discover_stores():
-def guest_recent_places():
-def guest_remember_request():
-def guest_remember_signin(token: str):
```

**Count: 10** (threshold was >3)

### Restoration Status

| Function | Restored? | Status |
|----------|-----------|--------|
| `favicon()` | Re-added in 76e92d9 (new handler) | OK |
| `apple_touch_icon()` | Re-added in 76e92d9 | OK |
| `safari_tab_icon()` | Re-added in 76e92d9 (new signature) | OK |
| `guest_venues()` | Yes (C.8 commit f8fa551) | OK |
| `guest_discover()` | Yes (C.8 commit f8fa551) | OK |
| `guest_recent_places()` | Yes (C.8 commit f8fa551) | OK |
| **`guest_home()`** | **NO** | **MISSING** |
| **`api_discover_stores()`** | **NO** | **MISSING** |
| **`guest_remember_request()`** | **NO** | **MISSING** |
| **`guest_remember_signin()`** | **NO** | **MISSING** |

**4 functions remain missing.**

---

## F7. Non-app.py, Non-observability Touches

37 files beyond app.py and observability/. Key categories:

**Entirely new feature files (7):**
1. `universal_builder_core.py` — 2341 lines
2. `universal_builder_creator.py` — 356 lines
3. `universal_builder_marketplace.py` — 883 lines
4. `universal_builder_migration.py` — 118 lines
5. `universal_builder_runtime.py` — 375 lines
6. `i18n_platform.py` — 236 lines
7. `qr_experience_revisions.py` — 200 lines

**Platform modules with significant changes:**
- `customer_verification.py` (+192)
- `qr_experience_platform.py` (+164)
- `checkout_platform.py` (89 changes)
- `customer_account_platform.py` (65 changes)
- `bos/routes.py` (61 changes)

---

## F8. Adjacent Commits

```
76e92d9 feat(observability): convert remaining 59 silent excepts (Pattern A)
fc5bf2d Ship Zintriq merchant platform updates: integrations verification, Customer QR hub, legal/account, and UI polish.
7a8b649 Unify owner Customer QR hub and merchant UX with verification (Phases 10A–10C).
d505746 Polish customer storefront, discover, and guest UX (Phases 7–10B).
7aeb629 Add guest, place, discover, and merchant platform backends (Phases 7–10).
df929d8 Add Business OS platforms, Uber-style storefront, and owner/customer split.
```

**Assessment:** This was NOT a squash/merge/rebase artifact. It was a standalone commit by `l35790411-web` that was mislabeled. The commit message claims "No behavior changes" but the diff shows:
- 7 new feature files added
- 11 routes deleted
- 10 functions deleted
- Brand asset changes (favicon redesign)
- New `/workspace` route

This commit was a **feature dump disguised as an observability change.**

---

## F9. logs/ Gitignore Check

```
$ git check-ignore logs/
(exit code 1 — NOT ignored)
```

**.gitignore contents** (relevant excerpt):
```
.dev_secret_key
.env.local
.DS_Store
node_modules/
.cloudflared-tunnel.log
.cloudflared-tunnel.pid
marketqr.db-shm
marketqr.db-wal
static/uploads/*
```

**`logs/` is NOT in .gitignore.** The `logs/` directory (created by observability logging) is untracked but not ignored. Any `git add .` would include it.

---

## Impact Assessment

### What C.8 Reported vs Reality

| Claim in C.8 | Actual |
|--------------|--------|
| "3 routes deleted" | **11 routes deleted** |
| "3 functions deleted" | **10 functions deleted** |
| "ACCIDENTAL_REGRESSION" | **Feature dump disguised as observability** |
| "215 lines removed" | **497 deletions + 5147 additions across 38 files** |
| "Only observability logging added" | **7 new feature files (4509 lines)** |
| "git status clean" | **logs/ not gitignored** |

### Unresolved Losses

4 routes still missing from the codebase:
1. `/home` — guest home page
2. `/api/discover/stores` — discover stores API
3. `/places/remember` — place remember POST
4. `/guest/remember/<token>` — guest remember signin

4 functions still missing:
1. `guest_home()` — home page handler
2. `api_discover_stores()` — discover API handler
3. `guest_remember_request()` — remember request handler
4. `guest_remember_signin()` — remember signin handler

### Classification Upgrade

**Previous**: ACCIDENTAL_REGRESSION (C.8)
**Corrected**: **MISLABELED FEATURE DUMP** — commit 76e92d9 bundled 7 new feature modules, brand asset changes, route deletions, and function removals inside a commit labeled "observability logging, no behavior changes."

---

## Required Actions Before Phase 1.1

1. **Classify the 4 missing routes**: INTENTIONAL_REMOVAL (UX Reset V0.1) or ACCIDENTAL_REGRESSION?
   - If intentional: document in UX Reset audit
   - If accidental: restore from pre-76e92d9 tree

2. **Add `logs/` to .gitignore**

3. **Audit the 7 new feature files**: Were they reviewed? Do they have tests? Were they part of a deliberate feature branch?

4. **Correct BATCH_C8_REPORT.md**: The report understated the scope of 76e92d9 by a factor of ~20x.

---

## Sign-off Status

**Phase 1.0: BLOCKED**

All 4 stop conditions hit. Cannot proceed to Phase 1.1 until:
- 4 missing routes classified and resolved
- logs/ gitignored
- 7 new feature files audited
- C.8 report corrected
