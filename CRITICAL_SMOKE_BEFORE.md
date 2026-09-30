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
- 200: 3
- 302: 10
- 400: 8
- 404: 4
- 500: 1

**5xx errors**: 1

### 5xx Errors (REGRESSIONS)

- **/qr/<code>** (GET `/qr/43`)
  - Status: 500
  - Request ID: `abc2c9f2`
  - Error: None

---

## Results by Category

### Checkout Routes (7 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/api/store/<slug>/checkout/quote` | POST | `/api/store/6gjm8trt/checkout/quote` | 400 | `78380751` | — |
| `/api/store/<slug>/checkout` | POST | `/api/store/6gjm8trt/checkout` | 400 | `df697b58` | — |
| `/store/<slug>/checkout` | GET | `/store/6gjm8trt/checkout` | 302 | `4b7ab6f7` | — |
| `/store/<slug>/checkout/<public_id>/pay` | GET | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/pay` | 404 | `ac9170e1` | — |
| `/store/<slug>/checkout/<public_id>/braintree` | POST | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/braintree` | 400 | `30df612c` | — |
| `/store/<slug>/checkout/<public_id>/complete` | POST | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/complete` | 400 | `708ec381` | — |
| `/store/<slug>/checkout/<public_id>/success` | GET | `/store/6gjm8trt/checkout/-4Wt8JVW8MyBAJfM/success` | 404 | `ddaa835b` | — |

### Payment Routes (7 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/api/integrations/webhooks/payment/<provider_slug>` | POST | `/api/integrations/webhooks/payment/<provider_slug>` | 200 | `c2f43e92` | — |
| `/api/integrations/payments/<provider>/oauth/start` | GET | `/api/integrations/payments/stripe/oauth/start` | 302 | `0e0d1778` | — |
| `/api/integrations/payments/<provider>/oauth/callback` | GET | `/api/integrations/payments/stripe/oauth/callback` | 302 | `91f1da05` | — |
| `/api/integrations/payments/<provider>/status` | GET | `/api/integrations/payments/stripe/status` | 302 | `1f0acee6` | — |
| `/api/integrations/payments/<provider>/refresh` | POST | `/api/integrations/payments/stripe/refresh` | 400 | `d1078ed2` | — |
| `/api/integrations/payments/<provider>/connect` | POST | `/api/integrations/payments/stripe/connect` | 400 | `df3e317e` | — |
| `/api/integrations/payments/<provider>/disconnect` | POST | `/api/integrations/payments/stripe/disconnect` | 400 | `43b6f3e2` | — |

### Auth Routes (6 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/reset-password/<token>` | GET | `/reset-password/test-token-nonexistent` | 200 | `eb671400` | — |
| `/magic-signin/<token>` | GET | `/magic-signin/test-token-nonexistent` | 302 | `1cdea105` | — |
| `/api/integrations/reputation/<provider>/oauth/start` | GET | `/api/integrations/reputation/stripe/oauth/start` | 302 | `00a7ff3d` | — |
| `/api/integrations/reputation/<provider>/oauth/callback` | GET | `/api/integrations/reputation/stripe/oauth/callback` | 302 | `009d948b` | — |
| `/account/reset-password/<token>` | GET | `/account/reset-password/test-token-nonexistent` | 200 | `c28320f0` | — |
| `/account/magic-signin/<token>` | GET | `/account/magic-signin/test-token-nonexistent` | 302 | `92476d87` | — |

### Qr Routes (6 tested)

| Route | Method | URL | Status | Request ID | Error |
|-------|--------|-----|--------|------------|-------|
| `/manage/<slug>/preview/qr/<code>` | GET | `/manage/6gjm8trt/preview/qr/43` | 302 | `75cb8922` | — |
| `/qr/<code>` | GET | `/qr/43` | 500 | `abc2c9f2` | — |
| `/e/<slug>` | GET | `/e/6gjm8trt` | 404 | `d0ffef17` | — |
| `/e/<slug>/preview` | GET | `/e/6gjm8trt/preview` | 302 | `e8b4b779` | — |
| `/api/customers/qr/<int:customer_id>` | GET | `/api/customers/qr/<int:customer_id>` | 404 | `f837edae` | — |
| `/api/customers/qr/<int:customer_id>` | DELETE | `/api/customers/qr/<int:customer_id>` | 400 | `256fb7de` | — |

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
