# G-0 Pre-Flight Report: Email/Password Login Independence

## Verdict: GO — Email login is standalone. Safe to remove Firebase in G-2.

---

## G0.1 — Login Endpoint

**File**: `app.py:2069`
**Route**: `POST /login`
**Function**: `def login()`

**Auth mechanism**: `werkzeug.security.check_password_hash`
```python
if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
```

**User lookup**: `customer_verification.find_user_by_login(conn, identifier)` — pure SQL query on `users` table by email or phone.

**No Firebase in the login path.** The Firebase route (`/auth/firebase`) is a separate endpoint at `app.py:2097` that already returns 410 (dead).

## G0.2 — Session Mechanism

**Function**: `sign_in_user(user_id)` at `app.py:2007`

**Flow**:
1. `sign_out_customer(session)` — pops `customer_user_id` from session (pure dict op)
2. `_preserve_guest_session_keys(session)` — saves visitor keys
3. `session.clear()` + restore preserved keys
4. `apply_remember_device(session, remember)` — sets `session.permanent` (pure dict op)
5. `session["user_id"] = user_id` — the actual login
6. `csrf_token()` — regenerates CSRF token

**Zero database writes** during session creation. Zero Firebase calls.

## G0.3 — Test

**File**: `tests/test_email_login_standalone.py`

**Tests**:
1. `test_email_login_returns_redirect` — POST /login → 302
2. `test_email_login_sets_session` — session contains `user_id` after login
3. `test_email_login_no_firebase_call` — firebase_admin mocked to raise if called; login succeeds without triggering it
4. `test_wrong_password_rejected` — wrong password → 200 (re-renders login form)

## G0.4 — Test Output

```
test_email_login_no_firebase_call ... ok
test_email_login_returns_redirect ... ok
test_email_login_sets_session ... ok
test_wrong_password_rejected ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.965s

OK
```

## G0.5-G0.6 — Verdict

**GO** — Email login is fully standalone. The `/login` route depends only on:
- `werkzeug.security.check_password_hash` (stdlib-adjacent)
- SQLite via `db()` context manager
- Flask `session` (cookie-based)
- `customer_verification.find_user_by_login` (pure SQL)
- `session_remember.apply_remember_device` (pure session ops)

Firebase Admin SDK is imported at module level (`app.py:23-28`) but never called during email/password login. Safe to remove in G-2.

## Dependencies Confirmed Non-Blocking

| Component | Firebase? | Location |
|---|---|---|
| Password hashing | No | werkzeug.security |
| User lookup | No | SQLite users table |
| Session creation | No | Flask session dict |
| CSRF protection | No | secrets.compare_digest |
| Remember device | No | session permanent flag |
| 2FA redirect | No | session pending keys |
