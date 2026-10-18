# Production deployment checklist

Use this when moving from local `python3 app.py` to a real host.

## 1. Environment variables

Copy [`.env.example`](../.env.example) and set values on the host (or use `.env.local` locally — loaded automatically by `app.py`).

| Variable | Required | Purpose |
|----------|----------|---------|
| `SECRET_KEY` | **Yes** | Flask session signing — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `PUBLIC_BASE_URL` | **Yes** | Absolute base URL for QR codes, magic links, email links (e.g. `https://app.example.com`) |
| `SESSION_COOKIE_SECURE` | **Yes** (HTTPS) | Set `true` in production so cookies are HTTPS-only |
| `SMTP_HOST` | Recommended | Without it, no email is sent (dev fallback logs links to console) |
| `SMTP_PORT` | Recommended | Usually `587` (STARTTLS) or `465` (SSL — set `SMTP_USE_SSL=1`) |
| `SMTP_USER` / `SMTP_PASSWORD` | Recommended | Provider credentials |
| `SMTP_FROM` | Recommended | From address, e.g. `Zintriq <noreply@your-domain.com>` |
| `AUTH_PROVIDER` | Production | `auth0` for Auth0 Universal Login; omit/`local` for SQLite password auth |
| `AUTH0_DOMAIN` / `AUTH0_CLIENT_ID` / `AUTH0_CLIENT_SECRET` | With Auth0 | Auth0 application credentials (EU tenant preferred) |
| `AUTH0_CALLBACK_URL` | With Auth0 | Must match Auth0 app callback, e.g. `https://app.example.com/auth/callback` |
| `DATABASE_URL` | Production | AWS RDS Postgres URL with `sslmode=require` |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Production auth forms | Cloudflare Turnstile widget + server verify (login/register) |
| `TURNSTILE_REQUIRED` | Optional | `1` to fail closed if keys are missing |

## 1b. Auth0 + RDS (recommended production)

1. Create an Auth0 application (Regular Web App), enable Database connection, enforce MFA in the Auth0 dashboard.
2. Allowed Callback URLs: `https://your-domain.com/auth/callback`. Logout URL: `https://your-domain.com/`.
3. **Auth0 Bot Detection:** Security → Attack Protection → Bot Detection → enable CAPTCHA on signup/login; prefer Cloudflare Turnstile as the provider when offered (covers Universal Login).
4. Provision RDS PostgreSQL (Multi-AZ, encryption at rest, `eu-central-1` if matching Frankfurt residency).
5. Set `DATABASE_URL` and Auth0 env vars; install `psycopg[binary]`.
6. Run app once so `init_db()` creates/migrates schema, or copy from SQLite:
   `DATABASE_URL=… python3 scripts/migrate_sqlite_to_postgres.py`
7. Emergency local form: `/login?local=1` (only while Auth0 is configured) — protected by Turnstile when keys are set.

## 1c. Cloudflare (edge + Turnstile)

1. Add the domain to Cloudflare (DNS proxy orange-cloud).
2. Turnstile → Add widget (Managed mode) for your domain → set `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY`.
3. Optional: WAF managed rules + rate limiting on `/login`, `/register`, `/account/login`, `/account/verify/send`.

## 2. SMTP — what gets emailed

| Flow | Recipient | Trigger |
|------|-----------|---------|
| **Guest Remember me** | Customer | `/places` → email save link |
| **New store inquiry** | Store owner | Customer submits inquire form (Discover / shop / QR) |
| **Place tenant apply** | Venue owner | Shop applies to list in a food hall / mall |
| **Tenant approved / rejected** | Shop owner | Venue approves or rejects application |

Dev behaviour: if SMTP is not configured, inquiry notifications log a warning with the inbox URL instead of sending mail.

### Provider examples

**SendGrid** (API relay via SMTP):

```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<your SendGrid API key>
SMTP_FROM="Your Brand <noreply@your-domain.com>"
SMTP_USE_TLS=1
```

**AWS SES** (STARTTLS):

```
SMTP_HOST=email-smtp.<region>.amazonaws.com
SMTP_PORT=587
SMTP_USER=<SES SMTP username>
SMTP_PASSWORD=<SES SMTP password>
SMTP_FROM="Your Brand <verified@your-domain.com>"
SMTP_USE_TLS=1
```

**AWS SES** (SSL wrapper port):

```
SMTP_PORT=465
SMTP_USE_SSL=1
SMTP_USE_TLS=0
```

Verify DNS: SPF, DKIM, and (recommended) DMARC on the sending domain.

### Smoke test

```bash
# Set SMTP_* in .env.local or export, then:
SMTP_TEST_TO=you@example.com python3 scripts/verify_smtp.py
```

## 3. Server setup

### Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database

- Default: SQLite file `marketqr.db` in the project root (created on first run via `init_db()`).
- For production traffic, plan a move to PostgreSQL later; SQLite is fine for early MVP if the host has persistent disk.
- Ensure the process user can write `marketqr.db`, `marketqr.db-wal`, and `static/uploads/`.

### Process manager (do not use Flask dev server in production)

Example with **gunicorn** (add to `requirements.txt` or install on host):

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5001 "app:app"
```

Put **nginx** or **Caddy** in front for TLS termination and static file caching.

### Reverse proxy essentials

- Terminate TLS at the proxy; set `SESSION_COOKIE_SECURE=true`.
- Set `PUBLIC_BASE_URL` to the public HTTPS origin (no trailing slash).
- Proxy headers: `X-Forwarded-For`, `X-Forwarded-Proto` if the app needs them later.
- Cache `/static/` aggressively; do not cache authenticated `/manage/` or `/app/` HTML.

## 4. Post-deploy verification

Run with Flask **stopped** to avoid SQLite lock errors.

```bash
python3 scripts/verify_smtp.py
python3 scripts/verify_merchant_phase10a.py
python3 scripts/verify_discover_phase9a.py
python3 scripts/verify_customer_qr_phase10c.py
```

Manual smoke test in browser:

1. Open `PUBLIC_BASE_URL` — marketing/home loads.
2. Register / login → `/app/store`.
3. Create store → `/manage/<slug>/qr` — create Shop QR; scan URL uses `PUBLIC_BASE_URL`.
4. Customer inquire on storefront → owner receives email (or check server logs if SMTP off).
5. `/discover` — list and map load; opt-in store appears when `discoverable=1` and address set.

## 5. Optional integrations

| Feature | Extra config |
|---------|----------------|
| Cloudflare tunnel (local dev) | `scripts/start_public_tunnel.sh` (or equivalent) updates `PUBLIC_BASE_URL` |

Google sign-in, Calendar, Reviews, Merchant, and Pay integrations are not offered.

## 6. Security checklist

- [ ] `SECRET_KEY` is unique per environment, not committed.
- [ ] `.env.local` / secrets not in git (see `.gitignore`).
- [ ] HTTPS everywhere; `SESSION_COOKIE_SECURE=true`.
- [ ] SMTP credentials stored in host secret manager, not in repo.
- [ ] `static/uploads/` writable but not executable; size limit 5 MB (Flask `MAX_CONTENT_LENGTH`).
- [ ] Regular backups of `marketqr.db` (and upload images if used).

## 7. Monitoring

- Watch application logs for `Dev: new inquiry` — means SMTP did not send.
- Watch for `database is locked` — usually multiple writers on SQLite; use one gunicorn worker or migrate DB.
- Set up uptime check on `/` and `/app/store` (401/302 to login is OK).
