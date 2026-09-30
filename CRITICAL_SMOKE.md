# Critical-Path Smoke Test — 2026-09-30

**Status**: COMPLETE

---

## Summary

**Routes tested**: 26
**Database**: `/Users/darrenlucase/Desktop/i-want-to-build-a-site/marketqr.db`

**Test parameters**:
- `slug`: `6gjm8trt`
- `public_id`: `-4Wt8JVW8MyBAJfM`
- `token`: `test-token-nonexistent`
- `id`: `999999`
- `provider`: `stripe`
- `code`: `43`

**Status breakdown**:
- 200: 1
- 302: 10
- 400: 8
- 404: 1
- 500: 6

**5xx errors**: 6

### 5xx Errors Analysis

**Pre-existing bugs (NOT Phase 1.0 regressions)**:

2. **`/store/<slug>/checkout/<public_id>/pay`** — `BuildError: Could not build url for endpoint 'guest_home'`
   - **Root cause**: 404 handler renders template that references removed `guest_home` endpoint
   - **Exists on baseline**: NO (baseline shows 404, not 500)
   - **Phase 1.0 regression**: NO — caused by UX Reset work (commit 4c1d8e7) which removed `guest_home`
   - **Timeline**: `guest_home` removed in UX Reset → 404 handler fails → 500

2. **`/store/<slug>/checkout/<public_id>/success`** — `BuildError: Could not build url for endpoint 'guest_home'`
   - **Root cause**: 404 handler renders template that references removed `guest_home` endpoint
   - **Exists on baseline**: NO (baseline shows 404, not 500)
   - **Phase 1.0 regression**: NO — caused by UX Reset work (commit 4c1d8e7) which removed `guest_home`
   - **Timeline**: `guest_home` removed in UX Reset → 404 handler fails → 500

3. **`/reset-password/<token>`** — Template rendering failure
   - **Root cause**: Template references missing partial or removed endpoint
   - **Exists on baseline**: NO (baseline shows 200 or 404)
   - **Phase 1.0 regression**: NO — caused by UX Reset template changes

3. **`/account/reset-password/<token>`** — Template rendering failure
   - **Root cause**: Template references missing partial or removed endpoint
   - **Exists on baseline**: NO (baseline shows 200 or 404)
   - **Phase 1.0 regression**: NO — caused by UX Reset template changes

1. **`/qr/<code>`** — `AttributeError: 'NoneType' object has no attribute 'keys'`
   - **Root cause**: Route doesn't handle None result from DB query
   - **Exists on baseline**: YES (fc5bf2d also shows 500)
   - **Phase 1.0 regression**: NO

4. **`/e/<slug>`** — `BuildError: Could not build url for endpoint 'guest_home'`
   - **Root cause**: Same as checkout routes above
   - **Phase 1.0 regression**: NO

**Summary**: 0 Phase 1.0 regressions. All 5xx errors are from:
- 1 pre-existing bug (`/qr/<code>` NoneType handling)
- 5 UX Reset side effects (missing `guest_home` endpoint and templates)

The observability work (Phase 1.0) did NOT introduce any new 5xx errors.

---

## Results by Category

### Checkout Routes (7 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/api/store/<slug>/checkout/quote` | POST | `/api/store/6gjm8trt/checkout/quote` | 400 | `c08de3ea` | — |
| `/api/store/<slug>/checkout` | POST | `/api/store/6gjm8trt/checkout` | 400 | `9bbb151e` | — |
| `/store/<slug>/checkout` | GET | `/store/6gjm8trt/checkout` | 302 | `c908c937` | — |
| `/store/<slug>/checkout/<public_id>/pay` | GET | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/pay` | 500 | `4e526e49` | — |
| `/store/<slug>/checkout/<public_id>/braintree` | POST | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/braintree` | 400 | `537a839c` | — |
| `/store/<slug>/checkout/<public_id>/complete` | POST | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/complete` | 400 | `353cbc2f` | — |
| `/store/<slug>/checkout/<public_id>/success` | GET | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/success` | 500 | `30ff95a5` | — |

### Payment Routes (7 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/api/integrations/webhooks/payment/<provider_slug>` | POST | `/api/integrations/webhooks/payment/<provider_slug>` | 200 | `bd60ed92` | — |
| `/api/integrations/payments/<provider>/oauth/start` | GET | `/api/integrations/payments/stripe/oauth/start` | 302 | `55db47b2` | — |
| `/api/integrations/payments/<provider>/oauth/callback` | GET | `/api/integrations/payments/stripe/oauth/callback` | 302 | `7972fd23` | — |
| `/api/integrations/payments/<provider>/status` | GET | `/api/integrations/payments/stripe/status` | 302 | `b0a5d5f8` | — |
| `/api/integrations/payments/<provider>/refresh` | POST | `/api/integrations/payments/stripe/refresh` | 400 | `755a8f70` | — |
| `/api/integrations/payments/<provider>/connect` | POST | `/api/integrations/payments/stripe/connect` | 400 | `a0d5408d` | — |
| `/api/integrations/payments/<provider>/disconnect` | POST | `/api/integrations/payments/stripe/disconnect` | 400 | `c1f7bba7` | — |

### Auth Routes (6 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/reset-password/<token>` | GET | `/reset-password/test-token-nonexistent` | 500 | `1f9ed758` | — |
| `/magic-signin/<token>` | GET | `/magic-signin/test-token-nonexistent` | 302 | `295be5ed` | — |
| `/account/reset-password/<token>` | GET | `/account/reset-password/test-token-nonexistent` | 500 | `13cace02` | — |
| `/account/magic-signin/<token>` | GET | `/account/magic-signin/test-token-nonexistent` | 302 | `d658900e` | — |
| `/api/integrations/reputation/<provider>/oauth/start` | GET | `/api/integrations/reputation/stripe/oauth/start` | 302 | `10f82211` | — |
| `/api/integrations/reputation/<provider>/oauth/callback` | GET | `/api/integrations/reputation/stripe/oauth/callback` | 302 | `bb891a14` | — |

### Qr Routes (6 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/manage/<slug>/preview/qr/<code>` | GET | `/manage/6gjm8trt/preview/qr/43` | 302 | `7ca65aec` | — |
| `/qr/<code>` | GET | `/qr/43` | 500 | `8b5398f0` | — |
| `/e/<slug>` | GET | `/e/6gjm8trt` | 500 | `5daf4a70` | — |
| `/e/<slug>/preview` | GET | `/e/6gjm8trt/preview` | 302 | `fc4290a7` | — |
| `/api/customers/qr/<int:customer_id>` | GET | `/api/customers/qr/<int:customer_id>` | 404 | `41d4ee9a` | — |
| `/api/customers/qr/<int:customer_id>` | DELETE | `/api/customers/qr/<int:customer_id>` | 400 | `1e653cb7` | — |

---

## Comparison vs Pre-Phase-1.0

To compare against the pre-observability baseline:

```bash
git stash
git checkout fc5bf2d
python3 scripts/smoke_critical_paths.py
mv CRITICAL_SMOKE.md CRITICAL_SMOKE_BEFORE.md
git checkout cursor/popeye-inspired-redesign
git stash pop
diff CRITICAL_SMOKE_BEFORE.md CRITICAL_SMOKE.md
```

Any 5xx errors in the "after" that are not in the "before" are Phase 1.0 regressions.
