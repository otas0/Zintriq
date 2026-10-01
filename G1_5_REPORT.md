# G-1.5 Report: Auth Flows Standalone Verification

**Date:** 2026-10-01
**Phase:** G-1.5 (gate before G-2 Firebase removal)
**Verdict:** PASS — all 4 auth flows work without Firebase

## Tests

| # | Flow | Route(s) | Mechanism | Firebase? |
|---|------|----------|-----------|-----------|
| T1 | Registration | `/register` (code path) | PBKDF2-SHA256 (werkzeug) + SQLite | NO |
| T2 | Password reset | `/forgot-password` + `/reset-password/<token>` | `create_auth_token` / `consume_auth_token` (secrets + SQLite) | NO |
| T3 | Magic link | `/magic-link` + `/magic-signin/<token>` | `create_auth_token` / `consume_auth_token` (secrets + SQLite) | NO |
| T4 | 2FA/TOTP | `/login` + `/login/2fa` | `totp_code()` / `valid_totp()` (hmac + base64) | NO |

## Test Output

```
test_t1_registration_no_firebase ... ok
test_t2_password_reset_no_firebase ... ok
test_t3_magic_link_no_firebase ... ok
test_t4_totp_two_factor_no_firebase ... ok

Ran 4 tests in 1.129s
OK
```

G-0 regression check (4 tests): OK

## Key Findings

1. **Registration**: `generate_password_hash(method="pbkdf2:sha256:600000")` — pure werkzeug.
   Note: `merchant_phone_auth.py` blocks form POST to `/register` (phone-first policy),
   but the underlying code path is Firebase-free.

2. **Password reset**: `create_auth_token()` uses `secrets.token_urlsafe(32)` + SHA256 hash
   stored in `auth_tokens` table. `consume_auth_token()` is single-use with 15-min expiry.

3. **Magic link**: Same token mechanism as password reset, different purpose string (`"magic"`).
   Signs user in via `sign_in_user()` which sets `session["user_id"]`.

4. **2FA/TOTP**: Custom RFC 6238 implementation using `hmac` + `base64.b32decode`.
   Checks current ±1 time window (30s steps). No external dependency.

## Firebase Touchpoints Remaining

All 4 flows mock `firebase_admin` to raise `AssertionError` if called. None triggered.

The only remaining Firebase reference in the auth path is:
- `verify_firebase_token()` at app.py:1840 — dead code (returns 410 at `/auth/firebase`)
- `firebase_uid` column in `users` table — unused but present (safe to drop in G-2)

## Gate Decision

**GO for G-2.** All auth flows are proven Firebase-independent. The Firebase SDK
(`firebase-admin`, `firebase-auth`) can be safely removed.
