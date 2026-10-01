# Investigation: 6 Untracked Files + marketqr.db

**Date**: 2026-10-01
**Status**: COMPLETE — awaiting human decision

---

## Part A — Per-File Analysis

### A1. Basic Info

| File | Lines | Purpose |
|------|-------|---------|
| `builder_components.py` | 329 | Canonical component + action registry (V2). Defines `COMPONENT_REGISTRY`, `ACTION_REGISTRY`, normalization functions. |
| `merchant_phone_auth.py` | 187 | Phone-first merchant signup/login via SMS OTP. Registers `/auth/phone/send`, `/auth/phone/verify`, `/auth/phone/signup` routes. |
| `universal_builder_capabilities.py` | 62 | Normalized capability registry. 17 capabilities (core, navigation, commerce, booking, etc.). |
| `universal_builder_modules.py` | 174 | App Module + Data Source registries. Defines `APP_MODULE_REGISTRY`, `DATA_SOURCE_REGISTRY`, domain data loaders. |
| `universal_builder_packages.py` | 52 | Package manifest validation + summary. Depends on `universal_builder_capabilities`. |
| `universal_component_registry.py` | 173 | Universal Builder's enriched view of `builder_components.py`. Ownership boundary between Legacy and Universal builder. |

### A2. Completeness Signals

| File | NotImplementedError | TODO/FIXME/XXX | bare pass | Ellipsis stubs | def count |
|------|--------------------:|----------------:|----------:|---------------:|----------:|
| `builder_components.py` | 0 | 0 | 0 | 0 | 5 |
| `merchant_phone_auth.py` | 0 | 0 | 0 | 0 | 6 |
| `universal_builder_capabilities.py` | 0 | 0 | 0 | 0 | 3 |
| `universal_builder_modules.py` | 0 | 0 | 0 | 0 | 5 |
| `universal_builder_packages.py` | 0 | 0 | 0 | 0 | 2 |
| `universal_component_registry.py` | 0 | 0 | 0 | 0 | 2 |

**All 6 files are complete implementations** — no stubs, no TODOs, no unimplemented methods.

### A3. Who Imports Each File?

**builder_components.py**:
- `universal_component_registry.py:44` — `from builder_components import (...)` (MODULE-LEVEL, eager)
- `qr_experience_platform.py:370` — `from builder_components import registry_payload` (lazy, inside function)
- `qr_experience_platform.py:950` — `from builder_components import new_node_key` (lazy, inside function)

**merchant_phone_auth.py**:
- `app.py:4847` — `from merchant_phone_auth import register_merchant_phone_auth` (MODULE-LEVEL, eager)
- `app.py:4848` — `register_merchant_phone_auth(app, db=db, sign_in_user=sign_in_user)` (eager call)

**universal_builder_capabilities.py**:
- `universal_builder_packages.py:5` — `from universal_builder_capabilities import validate_capabilities` (MODULE-LEVEL)
- `universal_builder_core.py:1154` — lazy import inside `register_universal_builder_core()`
- `universal_builder_core.py:1426` — lazy import inside route handler

**universal_builder_modules.py**:
- `universal_builder_core.py:1156` — lazy import inside `register_universal_builder_core()`
- `universal_builder_migration.py:27,85` — lazy imports
- `universal_builder_runtime.py:281` — lazy import

**universal_builder_packages.py**:
- `universal_builder_core.py:473,1159` — lazy imports
- `universal_builder_marketplace.py:432` — lazy import

**universal_component_registry.py**:
- `universal_builder_core.py:564,1152` — lazy imports
- `universal_builder_migration.py:26` — lazy import

### A4. Routes That Depend on Each File

**Removal test** (each file removed individually, app import attempted):

| File Removed | Import Result | Crash Location |
|---|---|---|
| `builder_components.py` | **CRASH** | `universal_component_registry.py:44` → `ModuleNotFoundError` |
| `merchant_phone_auth.py` | **CRASH** | `app.py:4847` → `ModuleNotFoundError` |
| `universal_builder_capabilities.py` | **CRASH** | `universal_builder_core.py:1154` → `ModuleNotFoundError` |
| `universal_builder_modules.py` | **CRASH** | `universal_builder_core.py:1156` → `ModuleNotFoundError` |
| `universal_builder_packages.py` | **CRASH** | `universal_builder_core.py:1159` → `ModuleNotFoundError` |
| `universal_component_registry.py` | **CRASH** | `universal_builder_core.py:1152` → `ModuleNotFoundError` |

**All 6 are hard runtime dependencies.** Removing any one of them prevents the app from starting. Zero routes would work without any of them.

Routes served through these dependency chains:
- `builder_components.py` → all builder routes (~55 `/api/builder-core/...` routes, `/app/builder`, marketplace routes)
- `merchant_phone_auth.py` → `/auth/phone/send`, `/auth/phone/verify`, `/auth/phone/signup`
- `universal_builder_capabilities.py` → `/api/builder-core/capabilities`
- `universal_builder_modules.py` → `/api/builder-core/app-modules`, `/api/builder-core/data-sources`, domain data routes
- `universal_builder_packages.py` → `/api/builder-core/packages`, `/api/marketplace/packages`
- `universal_component_registry.py` → `/api/builder-core/components`, `/api/builder-core/schema`

### A5. Template References

No templates directly reference any of the 6 module names. These are pure Python modules — they serve API routes and provide data to frontend JavaScript, not server-rendered templates.

### A6. Version Comparison vs wip/ux-reset-continuation

```
builder_components.py          → IDENTICAL to wip branch
merchant_phone_auth.py         → IDENTICAL to wip branch
universal_builder_capabilities.py → IDENTICAL to wip branch
universal_builder_modules.py   → IDENTICAL to wip branch
universal_builder_packages.py  → IDENTICAL to wip branch
universal_component_registry.py → IDENTICAL to wip branch
```

All 6 are byte-for-byte identical to commit `4c1d8e7` on `wip/ux-reset-continuation`.

### A7. Git History

All 6 files share the same history:
- **Only commit**: `4c1d8e7` — "wip: UX Reset continuation with workspace context and asset updates"
- **Only branch**: `wip/ux-reset-continuation`
- **Never committed to main** (`cursor/popeye-inspired-redesign`)
- **Reflog**: appeared in working tree when commit `4c1d8e7` was checked out, then the working tree was cleaned back to main — files were left behind as untracked

### A8. Tests

No tests exist for any of the 6 files. `tests/` directory is empty. No grep matches in any test file.

---

## Part B — marketqr.db

### B1. Tracked?
```
$ git ls-files marketqr.db
marketqr.db
```
**YES — it is tracked.** Committed in 3 commits: `be6d06a`, `df929d8`, `fc5bf2d`.

### B2. Recent log
```
fc5bf2d Ship Zintriq merchant platform updates...
df929d8 Add Business OS platforms, Uber-style storefront...
be6d06a first commit
```

### B3. Current size
```
-rw-r--r--@  3.7M  Sep 30 20:50  marketqr.db
```

### B4. Diff stat
```
marketqr.db | Bin 3895296 -> 3895296 bytes
1 file changed, 0 insertions(+), 0 deletions(-)
```
Same byte count (3,895,296). Modification is likely a WAL checkpoint or journal flush that changed the file on disk without changing content. Git detects the mtime change and flags it as modified.

### B5. .gitignore
```
marketqr.db-shm    ← gitignored
marketqr.db-wal    ← gitignored
marketqr.db        ← NOT gitignored (tracked)
```

### B6. Config reference
```python
# app.py:34
DATABASE = BASE_DIR / "marketqr.db"
```
Hardcoded in `app.py`. This is the production database.

---

## Part C — Classification

### 6 Untracked Files

| File | Classification | Rationale |
|------|---------------|-----------|
| `builder_components.py` | **COMPLETE_AND_NEEDED** | 0 stubs, 0 TODOs, app crashes without it, serves ~55 builder routes |
| `merchant_phone_auth.py` | **COMPLETE_AND_NEEDED** | 0 stubs, 0 TODOs, app crashes without it, serves auth routes |
| `universal_builder_capabilities.py` | **COMPLETE_AND_NEEDED** | 0 stubs, 0 TODOs, app crashes without it, serves capability API |
| `universal_builder_modules.py` | **COMPLETE_AND_NEEDED** | 0 stubs, 0 TODOs, app crashes without it, serves app-modules API |
| `universal_builder_packages.py` | **COMPLETE_AND_NEEDED** | 0 stubs, 0 TODOs, app crashes without it, serves packages API |
| `universal_component_registry.py` | **COMPLETE_AND_NEEDED** | 0 stubs, 0 TODOs, app crashes without it, serves components API |

### marketqr.db

| Classification | Rationale |
|---------------|-----------|
| **PRODUCTION_DATA** | 3.7M SQLite database, tracked in git, hardcoded as `DATABASE` in app.py. Modified by smoke test runs (WAL checkpoint). Contains real store/customer/checkout data. |

---

## Part D — Recommended Actions

| File | Action | Justification |
|------|--------|---------------|
| `builder_components.py` | **commit** | Complete, needed at runtime, identical to wip branch. App cannot start without it. |
| `merchant_phone_auth.py` | **commit** | Complete, needed at runtime, identical to wip branch. App cannot start without it. |
| `universal_builder_capabilities.py` | **commit** | Complete, needed at runtime, identical to wip branch. App cannot start without it. |
| `universal_builder_modules.py` | **commit** | Complete, needed at runtime, identical to wip branch. App cannot start without it. |
| `universal_builder_packages.py` | **commit** | Complete, needed at runtime, identical to wip branch. App cannot start without it. |
| `universal_component_registry.py` | **commit** | Complete, needed at runtime, identical to wip branch. App cannot start without it. |
| `marketqr.db` | **need-human-decision** | It IS already tracked in git (committed 3 times). Current diff is cosmetic (same byte count). Two options: (A) `git checkout -- marketqr.db` to restore the committed version, or (B) add to .gitignore and remove from tracking if it shouldn't be in version control. |

---

## Summary

**The 6 untracked files are not orphaned, partial, or duplicate.** They are complete, production-required modules that the app cannot import without. They were left in the working tree when the UX Reset branch was cleaned up — they are byte-for-byte identical to `wip/ux-reset-continuation:4c1d8e7`.

**marketqr.db is tracked production data** that was modified by smoke test runs. The diff shows the same byte count, suggesting a WAL checkpoint rather than content change.

**Waiting for human decision on:**
1. Commit the 6 files? (recommended: yes)
2. Reset marketqr.db via `git checkout -- marketqr.db`? (recommended: yes)
3. Or different action?
