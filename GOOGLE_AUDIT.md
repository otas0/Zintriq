# Google-Owned Service Touchpoints Audit

**Date**: 2026-10-01
**Scope**: All Python, templates, JS, CSS, config, and dependency files
**Method**: A1–A8 grep checks (see task prompt)

---

## STOP Condition: Firebase Credentials in Git

**`static/firebase-auth.js`** is committed to git and contains a hardcoded Firebase client config:

```
apiKey: "AIzaSy..."
authDomain: "business-copilot-877a3.firebaseapp.com"
projectId: "business-copilot-877a3"
storageBucket: "business-copilot-877a3.firebasestorage.app"
messagingSenderId: "813195132440"
appId: "1:813195132440:web:..."
```

The `apiKey` is a Google API key. While Firebase client config is designed to be public (security is in Firestore/Auth rules, not the key itself), it identifies a specific GCP project and is a dependency on Google infrastructure. **Report only — do not remove until human decision on auth strategy.**

---

## 1. Python Imports

| # | File | Line | Service | Category | Severity |
|---|------|------|---------|----------|----------|
| 1 | `app.py` | 24–28 | Firebase Admin SDK (`firebase_admin`, `firebase_admin.auth`, `firebase_admin.credentials`) | AUTH | **BLOCKER** |
| 2 | `integrations/auth/__init__.py` | 42–64 | Firebase Auth provider class | AUTH | HIGH |
| 3 | `integrations/config.py` | 9, 21, 26–27 | Auth provider config (default: firebase), Calendar provider config (default: google) | AUTH | HIGH |
| 4 | `integrations/platform.py` | 42 | Firebase UID lookup for auth provider detection | AUTH | HIGH |
| 5 | `integrations/user_profile.py` | 90–91 | Firebase UID extraction from user row | AUTH | HIGH |
| 6 | `reputation_connect_plugin.py` | 55–75 | Google Reviews + Google Customer Reviews OAuth (accounts.google.com, oauth2.googleapis.com, mybusinessaccountmanagement.googleapis.com, shoppingcontent.googleapis.com) | AUTH | HIGH |
| 7 | `reputation_connect_plugin.py` | 140–150 | Google profile fetch (My Business API, Shopping Content API) | OTHER | MEDIUM |
| 8 | `calendar_platform.py` | 14, 90–94, 717–795 | Google Calendar data model + conflict resolution | OTHER | MEDIUM |
| 9 | `storefront_platform.py` | 587 | Google Maps URL builder (`google.com/maps/search`) | MAP | LOW |
| 10 | `customer_verification.py` | 817–819 | `/account/onboarding/google` → 410 (dead route) | AUTH | LOW |
| 11 | `customer_account_platform.py` | 304, 515–517 | Imports `verify_firebase_token`; `/auth/firebase/customer` → 410 (dead route) | AUTH | LOW |
| 12 | `integration_platform.py` | 15, 17 | Integration slugs: `google_calendar`, `google_business` | OTHER | LOW |
| 13 | `feedback_core_platform.py` | 30 | `REMOVED_REPUTATION_SLUGS = ("google_business",)` | OTHER | LOW |
| 14 | `integration_catalog.py` | 92–245, 2052–2393 | Google Reviews, Google Customer Reviews, Google Pay catalog entries | OTHER | LOW |
| 15 | `integration_catalog_batch3.py` | 64–80, 312–360 | Google Pay catalog entry + brand metadata | OTHER | LOW |
| 16 | `payment_registry_adapters.py` | 300, 485 | Google Pay via Stripe Checkout (wallet passthrough) | OTHER | LOW |
| 17 | `integration_credential_verify.py` | 339 | Comment mentioning Google OAuth | OTHER | LOW |
| 18 | `app.py` | 244, 272–274 | DB schema: `firebase_uid` column on `users` table | AUTH | HIGH |
| 19 | `app.py` | 894 | Webhook CSRF skip for `/api/integrations/google-calendar/webhook` | AUTH | MEDIUM |
| 20 | `app.py` | 1842–1849 | `verify_firebase_token()` — Firebase Admin token verification | AUTH | **BLOCKER** |
| 21 | `app.py` | 2097–2099 | `POST /auth/firebase` → 410 (dead endpoint) | AUTH | LOW |

---

## 2. Route Handlers

| # | File | Line | Route | Google Service | Category | Severity |
|---|------|------|-------|---------------|----------|----------|
| 1 | `app.py` | 2097 | `POST /auth/firebase` | Firebase Auth (returns 410) | AUTH | LOW |
| 2 | `customer_verification.py` | 817 | `POST /account/onboarding/google` | Google sign-in (returns 410) | AUTH | LOW |
| 3 | `customer_account_platform.py` | 515 | `POST /auth/firebase/customer` | Firebase Auth (returns 410) | AUTH | LOW |
| 4 | `storefront_platform.py` | 587 | (helper) | Google Maps URL | MAP | LOW |
| 5 | `app.py` | 894 | (middleware) | Google Calendar webhook CSRF skip | AUTH | MEDIUM |

**Note**: Routes 1–3 all return HTTP 410 (Gone). They are dead endpoints but still registered in the URL map. The Firebase import and `verify_firebase_token()` are still load-bearing because `integrations/config.py` defaults `AUTH_PROVIDER` to `"firebase"`.

---

## 3. Templates

| # | File | Line | Google Service | Category | Severity |
|---|------|------|---------------|----------|----------|
| 1 | `templates/login.html` | 22–34 | "Continue with Google" button + loads `firebase-auth.js` | AUTH | **BLOCKER** |
| 2 | `templates/register.html` | 30–41 | "Sign up with Google" button + loads `firebase-auth.js` | AUTH | **BLOCKER** |
| 3 | `templates/customer/login.html` | 23–36 | "Continue with Google" button + loads `firebase-auth.js` | AUTH | **BLOCKER** |
| 4 | `templates/customer/register.html` | 35–46 | "Sign up with Google" button + loads `firebase-auth.js` | AUTH | **BLOCKER** |
| 5 | `templates/customer/_auth_sheet.html` | 14, 33–34, 107–108, 182–197 | Google auth buttons (login + signup) + Google setup form | AUTH | **BLOCKER** |
| 6 | `templates/customer/account_setup.html` | 11 | Form posting to `customer_onboarding_google_complete` | AUTH | MEDIUM |
| 7 | `templates/two_factor_settings.html` | 40 | Text mention: "Google Authenticator" | OTHER | LOW |
| 8 | `templates/owner/business_card_detail.html` | 46 | YouTube social link key | MEDIA | LOW |
| 9 | `templates/legal/terms.html` | 59 | Legal text mentioning Google | OTHER | LOW |
| 10 | `templates/legal/cookies.html` | 42 | Legal text mentioning Google Reviews | OTHER | LOW |
| 11 | `templates/legal/privacy.html` | 60 | Legal text mentioning Google | OTHER | LOW |

---

## 4. Static Assets (JS/CSS Referencing Google)

| # | File | Line | Google Service | Category | Severity |
|---|------|------|---------------|----------|----------|
| 1 | `static/firebase-auth.js` | 1–2 | `gstatic.com/firebasejs/11.6.1` — Firebase SDK loaded from Google CDN | AUTH | **BLOCKER** |
| 2 | `static/firebase-auth.js` | 4–11 | Hardcoded Firebase config (apiKey, projectId `business-copilot-877a3`) | AUTH | **BLOCKER** |
| 3 | `static/firebase-auth.js` | 14–67 | Google sign-in popup flow (`GoogleAuthProvider`, `signInWithPopup`) | AUTH | **BLOCKER** |
| 4 | `static/customer-auth.js` | 198 | Dynamic import of `firebase-auth.js` | AUTH | HIGH |
| 5 | `static/customer-auth.js` | 206–526 | Google setup form handling, `openGoogleOnboarding()` | AUTH | HIGH |
| 6 | `static/bos/features/calendar-page.js` | 25–408 | Google Calendar sync UI (conflict resolution, sync button) | OTHER | MEDIUM |
| 7 | `static/bos/product-focus.js` | 21 | `googleCalendarSync: false` feature flag | OTHER | LOW |
| 8 | `static/style.css` | 911–928 | `.google-button` CSS class | AUTH | LOW |
| 9 | `static/marketing.css` | 500–516 | `.mq-google-btn` CSS class | AUTH | LOW |
| 10 | `static/guest.css` | 1542 | `.ig-auth__google` CSS class | AUTH | LOW |

---

## 5. Config / Env Keys (Names Only)

| # | File | Key Name | Service | Category |
|---|------|----------|---------|----------|
| 1 | `.env.local` | `GOOGLE_CLIENT_ID` | Google OAuth | AUTH |
| 2 | `.env.local` | `GOOGLE_CLIENT_SECRET` | Google OAuth | AUTH |
| 3 | `.env.local` | `GOOGLE_OAUTH_REDIRECT_URI` | Google OAuth | AUTH |
| 4 | `.env.local` | `GOOGLE_CALENDAR_POLL_SECONDS` | Google Calendar | OTHER |
| 5 | `.env.example` | `FIREBASE_SERVICE_ACCOUNT` | Firebase Admin | AUTH |
| 6 | `.env.example` | `GOOGLE_REVIEWS_CLIENT_ID` | Google Reviews OAuth | AUTH |
| 7 | `.env.example` | `GOOGLE_REVIEWS_CLIENT_SECRET` | Google Reviews OAuth | AUTH |
| 8 | `.env.example` | `GOOGLE_REVIEWS_OAUTH_REDIRECT_URI` | Google Reviews OAuth | AUTH |
| 9 | `.env.example` | `GOOGLE_MERCHANT_CLIENT_ID` | Google Merchant Center OAuth | AUTH |
| 10 | `.env.example` | `GOOGLE_MERCHANT_CLIENT_SECRET` | Google Merchant Center OAuth | AUTH |
| 11 | `.env.example` | `GOOGLE_MERCHANT_OAUTH_REDIRECT_URI` | Google Merchant Center OAuth | AUTH |

**Note**: `.env.local` is gitignored. `.env.example` contains key names only (values are blank or `<redacted>`).

---

## 6. requirements.txt

| # | Package | Service | Category | Severity |
|---|---------|---------|----------|----------|
| 1 | `firebase-admin>=6.5` | Firebase Admin SDK | AUTH | **BLOCKER** |

---

## 7. Deployment

| # | File | Line | Reference | Category | Severity |
|---|------|------|-----------|----------|----------|
| — | — | — | No GCP hosting references found | — | — |

No `appspot.com`, `run.app`, `cloudfunctions.net`, `storage.googleapis.com`, or `storage.cloud.google.com` references in the codebase.

---

## Summary by Category

| Category | Count | Severity Breakdown |
|----------|-------|--------------------|
| AUTH | 28 | 7 BLOCKER, 7 HIGH, 3 MEDIUM, 11 LOW |
| MAP | 2 | 2 LOW |
| MEDIA | 1 | 1 LOW |
| OTHER | 13 | 1 MEDIUM, 12 LOW |
| FONT | 0 | — |
| ANALYTICS | 0 | — |
| CAPTCHA | 0 | — |
| STORAGE | 0 | — |
| DEPLOY | 0 | — |

---

## Summary by Severity

| Severity | Count | Description |
|----------|-------|-------------|
| **BLOCKER** | 7 | Active data flow to Google — user-facing auth dependency |
| **HIGH** | 7 | Functional dependency — requires replacement to remove |
| **MEDIUM** | 4 | UX dependency — can be replaced with minor effort |
| **LOW** | 18 | Cosmetic / dead code / legal text / catalog entries |

---

## Load-Bearing Dependencies (Non-Replaceable Without Auth Strategy Decision)

1. **Firebase Auth** — `integrations/config.py` defaults `AUTH_PROVIDER` to `"firebase"`. The entire login/register flow depends on Firebase SDK loading from `gstatic.com`. Cannot be removed without choosing a replacement auth provider.

2. **Firebase Admin SDK** (`firebase-admin>=6.5`) — server-side token verification in `app.py:1842–1849`. Required as long as Firebase Auth is the provider.

3. **Google Calendar sync** — feature-flagged OFF (`googleCalendarSync: false` in `product-focus.js:21`). Not load-bearing today but the data model and integration code are present.

4. **Google Maps URL** — `storefront_platform.py:587` generates `google.com/maps/search` links for storefronts. Replaceable with OpenStreetMap (already in codebase for other uses).

---

## Questions for Human Decision (Q1–Q3)

**Q1. Auth strategy**: Firebase Auth is the default and only working auth provider. The "Continue with Google" buttons on 5 templates load Firebase SDK from Google CDN. What is the replacement? Options:
- Self-hosted (e.g., email/phone only, no Google)
- Different OAuth provider (e.g., Auth0, Cognito)
- Keep Firebase but remove the Google popup (use phone/email only via Firebase)

**Q2. Google Calendar**: Integration code exists but is feature-flagged OFF. Keep for future use or remove entirely?

**Q3. Google Maps**: Storefront "Get directions" links use `google.com/maps`. Replace with OpenStreetMap (`openstreetmap.org`) which is already used elsewhere?
