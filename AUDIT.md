# AUDIT.md — Zintriq Universal Builder Platform

**Date:** 2026-09-27  
**Auditor:** Qorder (automated + manual browser verification)  
**Scope:** Full codebase — backend, frontend, static assets, design system, runtime health

---

## 1. REPO MAP

### Tech Stack
| Layer | Technology |
|-------|-----------|
| Backend | Flask >= 3.0 (Python 3.9.6) |
| Database | SQLite (WAL mode, 116 tables, ~9.7 MB) |
| Templates | Jinja2 (119 templates) |
| Frontend | Vanilla JS (ES modules), no build step |
| CSS | Custom properties (design tokens), no preprocessor |
| Mobile | Capacitor 7.x (Android + iOS shell) |
| Auth | Session-based + Firebase (Google) + 2FA |
| Payments | Braintree + integration catalogs (360K+ of provider data) |
| i18n | Custom system, 16 locales |
| Public URL | Cloudflare tunnel (dev/staging) |

### Folder Structure
```
i-want-to-build-a-site/
├── app.py                        # 4,773 lines — Flask monolith (90 routes)
├── *_platform.py (30+ files)     # Feature modules (~450 total routes)
├── universal_builder_*.py (8)    # Visual builder subsystem
├── qr_experience_*.py (7)        # QR experience subsystem
├── payment_*.py (4)              # Payment adapters
├── integration_catalog*.py (4)   # 360K+ of payment provider data
├── customer_*.py (5)             # Customer-facing modules
├── feedback_*.py (3)             # Feedback/reputation
├── bos/                          # Business OS sub-package
├── integrations/                 # Integration service layer
├── templates/                    # 119 Jinja2 templates
│   ├── builder/ (6)              # Editor, home, marketplace
│   ├── customer/ (20)            # Storefront, checkout, QR
│   ├── owner/ (38)               # Management pages
│   ├── zintriq/ (3+partials)     # Zintriq-branded shell
│   └── partials/ (10)            # Shared nav, footer, theme
├── static/                       # 178 JS/CSS files + assets
│   ├── builder/ (12)             # Universal builder JS
│   ├── bos/ (~70)                # BOS front-end framework
│   ├── brand/ (~25)              # Favicons, logos
│   ├── integrations/logos/ (150+) # Provider SVG logos
│   └── i18n/ (4)                 # Client-side i18n
├── scripts/ (69)                 # Utility/verification scripts
├── mobile/                       # Capacitor native shell
├── i18n/locales/ (16 JSON)       # Translation files
└── docs/                         # Architecture documentation
```

### Entry Points
- **Main app:** `app.py` → `python3 app.py` (port 5001, debug=True)
- **Builder editor:** `/app/builder/<project_id>`
- **Workspace dashboard:** `/app/builder`
- **Marketplace:** `/app/marketplace`
- **Settings:** `/app/settings`
- **Public storefront:** `/store/<slug>`
- **QR runtime:** `/qr/<code>`, `/pass/<code>`, `/card/<code>`

### Key Modules (by size)
| Module | Lines | Purpose |
|--------|-------|---------|
| `app.py` | 4,773 | God file — auth, stores, items, QR, places |
| `integration_catalog_batch2.py` | ~238K | Payment provider data |
| `integration_catalog.py` | ~123K | Payment provider data |
| `universal_builder_core.py` | ~135K | Visual builder engine |
| `customer_platform.py` | ~43K | Customer storefront |
| `feedback_platform.py` | ~47K | Feedback management |
| `qr_experience_platform.py` | ~57K | QR experiences |

### Dead Code / Orphaned Files
| Item | Issue |
|------|-------|
| `zintriq.db` | 0-byte empty file, never referenced |
| `outputs/` | Empty directory |
| `work/` | Empty directory |
| `.tmp_logo_fix/` | 12 scratch images (gitignored) |
| `.cloudflared-tunnel.{log,pid}` | Tunnel artifacts (gitignored) |
| `legal/` (root) | Static HTML duplicate of `templates/legal/` |
| `templates/account.html` | Exists but no route renders it |
| `templates/zintriq/marketplace.html` | Exists but no route renders it |
| Multiple favicon iterations | v1-v4 + variants in `static/brand/` — most stale |

---

## 2. RUNTIME HEALTH

### Build / Dev Server
- **No frontend build step** — pure server-rendered Flask app
- **Dev server:** `python3 app.py` → runs on `0.0.0.0:5001` (debug=True)
- **No production WSGI** — uses Flask built-in dev server (security risk if deployed)
- **No test suite** — relies on 40+ `scripts/verify_*.py` smoke tests

### Browser Console Errors (Live Test)
| Page | Console Errors | Status |
|------|---------------|--------|
| `/app/builder` (dashboard) | 0 | Clean |
| `/app/builder/123` (editor) | 0 | Clean |
| `/app/marketplace` | 0 | Clean |
| `/app/settings` | 0 | Clean |

### Bundle Size
- **No bundling** — all JS/CSS served as individual files
- **Largest files:**
  - `static/bos/features/qr-experiences-page.js` — ~180 KB
  - `static/builder/universal-builder.js` — ~140 KB
  - `static/style.css` — ~95 KB
  - `static/bos/polish.css` — ~85 KB
  - `static/bos/shell.css` — ~70 KB

### Database
- **Engine:** SQLite with WAL mode
- **Tables:** 116
- **Size:** ~9.7 MB
- **Migrations:** Inline in `init_db()` — no versioning, no rollback
- **Concurrency:** Retry logic for locked DB (known concern)

---

## 3. BUG INVENTORY

### P0 — Blockers (will crash at runtime)

#### 3.1 Missing Customer Auth Templates
**Route:** `/customer/login`, `/customer/forgot-password`, etc.  
**Steps:** Hit any customer auth flow that falls back to template rendering  
**Expected:** Render login/forgot/reset/magic-link page  
**Actual:** `jinja2.exceptions.TemplateNotFound` → 500 error  
**Evidence:** `customer_account_platform.py` lines 187, 531, 561, 579 reference:
- `templates/customer/login.html` — MISSING
- `templates/customer/forgot_password.html` — MISSING
- `templates/customer/reset_password.html` — MISSING
- `templates/customer/magic_link.html` — MISSING

**Severity:** P0  
**Fix:** Create the 4 templates or redirect to owner-level equivalents

#### 3.2 Circular Import in Payment Adapters
**Route:** Any payment flow  
**Steps:** Import `payment_registry_adapters` before `payment_checkout_adapters`  
**Expected:** Clean import  
**Actual:** `ImportError` — `_basic`, `_cents`, etc. not yet defined  
**Evidence:**
- `payment_registry_adapters.py:19` imports from `payment_checkout_adapters` at top level
- `payment_checkout_adapters.py:1415` imports from `payment_registry_adapters` at bottom

**Severity:** P0 (fragile — works by accident of import order)  
**Fix:** Move imports inside functions or restructure

---

### P1 — Major Issues

#### 3.3 Secrets in `.env.local`
**Route:** N/A (security)  
**Steps:** Read `.env.local`  
**Expected:** Secrets managed securely  
**Actual:** Google OAuth client ID + secret stored in plaintext file  
**Evidence:** `.env.local` contains `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`  
**Severity:** P1 (security risk if directory is copied/archived)  
**Fix:** Rotate credentials, use proper secret management

#### 3.4 Corrupted Filipino i18n Strings
**Route:** Any page with `?lang=fil`  
**Steps:** Switch to Filipino locale  
**Expected:** Clean translated strings  
**Actual:** Every string has spurious `\n<` appended → visible line break + stray `<`  
**Evidence:** `static/i18n/messages.js` lines ~6805-6830+  
**Severity:** P1 (broken UI for Filipino users)  
**Fix:** Clean the corruption from `messages.js`

#### 3.5 Massive Hardcoded Colors (762+ instances)
**Route:** All pages  
**Steps:** Inspect CSS files  
**Expected:** All colors use design tokens (`var(--color-*)`)  
**Actual:** 634 hardcoded hex values + 128 hardcoded `rgb()`/`rgba()` values  
**Evidence:**
| File | Hex | rgba() |
|------|-----|--------|
| `bos/polish.css` | 117 | 11 |
| `bos/shell.css` | 49 | 2 |
| `bos/merchant.css` | 61 | 9 |
| `style.css` | 58 | 23 |
| `insights.css` | 32 | 1 |
| `feedback.css` | 42 | 0 |
| `storefront.css` | 37 | 8 |

**Severity:** P1 (dark mode inconsistent, theme switching broken for many elements)  
**Fix:** Migrate all hardcoded colors to design tokens

#### 3.6 Hardcoded Colors in JS Inline Styles
**Route:** QR experiences page  
**Steps:** View QR experience builder  
**Expected:** Colors from tokens  
**Actual:** Inline `style="background:#111;color:#fff"` etc.  
**Evidence:**
- `static/bos/components/qr/index.js:101`
- `static/bos/features/qr-experiences-page.js:358,381,401`

**Severity:** P1  
**Fix:** Use CSS classes with token values instead of inline styles

#### 3.7 Silent Exception Swallowing (35+ instances)
**Route:** Checkout, payments, customer verification  
**Steps:** Trigger an error in affected code paths  
**Expected:** Error logged, user notified  
**Actual:** `except Exception: pass` — error silently swallowed  
**Evidence:** 35+ bare `except Exception:` blocks with no logging:
- `checkout_platform.py`: 6 instances
- `payment_connect_plugin.py`: 5 instances
- `customer_verification.py`: 2 instances
- `app.py`: 4 instances
- And 18+ more across other modules

**Severity:** P1 (debugging impossible, security-relevant errors hidden)  
**Fix:** Add logging at minimum, re-raise or handle properly

---

### P2 — Minor Issues

#### 3.8 `console.error` in Production JS
**Route:** Dashboard, BOS shell  
**Steps:** Trigger API errors  
**Expected:** Errors handled gracefully  
**Actual:** `console.error()` leaks internal details to browser console  
**Evidence:**
- `static/workspace-dashboard.js:89,311`
- `static/bos/main.js:64,171`

**Severity:** P2  
**Fix:** Remove or replace with proper error reporting

#### 3.9 Unsafe `innerHTML` Usage (XSS risk)
**Route:** Multiple pages  
**Steps:** Inject malicious data via API  
**Expected:** Data escaped before rendering  
**Actual:** Many `innerHTML` assignments without escaping  
**Evidence:**
- `workspace-dashboard.js:135,328`
- `marketplace-page.js:52,80`
- `workspace.js:150,158,183,248,262,311`
- `account.js:22,25,35`
- And 10+ more files

**Severity:** P2 (security risk)  
**Fix:** Use `escapeHtml()` consistently or switch to `textContent` / DOM APIs

#### 3.10 `SELECT *` in Production SQL
**Route:** Team, checkout, events, check-in  
**Steps:** Query affected tables  
**Expected:** Explicit column selection  
**Actual:** `SELECT * FROM` — schema changes silently break downstream code  
**Evidence:** 20+ instances across `team_platform.py`, `checkout_platform.py`, `event_platform.py`, `checkin_platform.py`  
**Severity:** P2 (fragile, performance impact)  
**Fix:** Specify explicit columns

#### 3.11 Orphaned Templates
**Route:** N/A  
**Steps:** Search for `render_template("account.html")` or `render_template("zintriq/marketplace.html")`  
**Expected:** Templates used by routes  
**Actual:** Templates exist but no route renders them  
**Evidence:** `templates/account.html`, `templates/zintriq/marketplace.html`  
**Severity:** P2 (dead code, confusing)  
**Fix:** Delete or wire up routes

#### 3.12 `transition: all` Anti-Pattern
**Route:** Builder editor  
**Steps:** Inspect CSS  
**Expected:** Specific property transitions  
**Actual:** `transition: all` forces browser to animate every property change  
**Evidence:** 9 instances in `universal-builder.css` (7), `style.css` (1), `system.css` (1)  
**Severity:** P2 (performance jank)  
**Fix:** Specify exact properties

---

### P3 — Polish

#### 3.13 `!important` Overuse
**Evidence:** ~20 instances across CSS files  
**Severity:** P3  
**Fix:** Increase selector specificity instead

#### 3.14 Inconsistent Token Adoption
**Evidence:** Some files well-tokenized (200+ `var()` uses), others poorly (117 hex in one file)  
**Severity:** P3  
**Fix:** Complete token migration (see P1 #3.5)

#### 3.15 No TODO/FIXME Comments
**Status:** Positive — zero TODO/FIXME/HACK markers found

#### 3.16 No Broken JS Module Imports
**Status:** Positive — all `import ... from` targets verified to exist

#### 3.17 No Duplicate Function Names
**Status:** Positive — `register_*` / `init_*` naming convention is consistent

---

## 4. STATIC ASSET & FILE CLEANUP REPORT

### Duplicate / Orphaned Assets
| Asset | Issue |
|-------|-------|
| `static/favicon.ico` | Duplicates in `static/brand/` — root may be stale |
| `static/apple-touch-icon*.png` | Duplicates in `static/brand/` |
| `static/brand/favicon-v1.png` through `v4.png` | Favicon sprawl — most likely stale |
| `static/brand/z-fav-*.png` | Multiple variants, unclear which is canonical |
| `static/uploads/` | 13 user-uploaded PNGs — no cleanup policy |
| `static/integrations/logos/` | 150+ SVGs — no optimization, no unused detection |

### Legacy Customer Platform Files
The customer platform was partially cleaned up in previous sessions, but:
- `customer_home_platform.py` (896 bytes, ~25 lines) — extremely thin wrapper, could be inlined
- `mvp_responses_platform.py` (1,834 bytes) — minimal helper, possibly dead
- `email_delivery.py` (1,646 bytes) — unclear if used vs. `integrations/email/`

### Public Directory Hygiene
- No `/public` directory — all static served from `/static/`
- No asset optimization (no WebP/AVIF conversion, no image compression)
- No asset manifest or cache-busting hashes

### Image Optimization Gaps
- `static/uploads/` — 13 PNGs, no optimization
- `static/brand/` — mixed PNG/SVG, no size optimization
- `static/integrations/logos/` — 150+ SVGs, no deduplication or optimization
- `audit/` — 45 screenshot PNGs at root, should be in `docs/` or deleted

---

## 5. DESIGN SYSTEM DRIFT REPORT

### Token System Status
**Defined:** `static/tokens.css` defines CSS custom properties for:
- Colors (light + dark themes)
- Spacing (8pt baseline)
- Radius (module, button, input)
- Shadows (elevation levels)
- Motion (duration, easing)
- Typography (font family, weight, size scale)

### Hardcoded Values vs Tokens
| Category | Token Uses | Hardcoded | Status |
|----------|-----------|-----------|--------|
| Colors | ~1,200 `var(--color-*)` | 634 hex + 128 rgb/rgba | **Poor** — 35% hardcoded |
| Spacing | ~800 `var(--space-*)` | ~200 hardcoded px/rem | **Fair** — 20% hardcoded |
| Radius | ~300 `var(--*-radius)` | ~50 hardcoded px | **Good** — 85% tokenized |
| Shadow | ~150 `var(--elevation-*)` | ~30 hardcoded box-shadow | **Good** — 83% tokenized |
| Motion | ~100 `var(--motion-*)` | ~40 hardcoded ms/easing | **Fair** — 71% tokenized |

### Inconsistencies
| Issue | Examples |
|-------|----------|
| Hardcoded colors in CSS | `bos/polish.css` (117 hex), `bos/merchant.css` (61 hex) |
| Hardcoded colors in JS | Inline `style="background:#111"` in QR components |
| Inconsistent radius | Some buttons use `var(--button-radius)`, others use `8px` |
| Mixed motion values | Some use `var(--motion-duration-200)`, others use `200ms` |
| Dark mode gaps | Hardcoded `#fff` / `#111` don't respond to theme switch |

### Missing Token Coverage
- No token for sidebar width (hardcoded `260px` in multiple places)
- No token for topbar height (hardcoded `64px`)
- No token for canvas max-width (hardcoded `1200px`)
- No token for z-index layers (scattered hardcoded values)

---

## 6. MISSING PIECE CHECK

### 6.1 Team Collaboration (#77) — NOT DONE
**What exists:**
- `team_platform.py` — basic team routes (19 routes)
- `templates/zintriq/settings.html` — "Team management is coming soon" placeholder
- Database tables: `team_members`, `team_invitations` (assumed from `team_platform.py`)

**What's missing (from #77 spec):**
- Member list + detail UI (avatar, role, presence, last active)
- Invite flow: email invite → token → accept → join workspace
- Resend / cancel invitation
- Role edit (Owner / Admin / Manager / Member / Viewer)
- Suspend / restore member
- Batch actions on members
- Team Activity feed (domain events)
- Team Presence (online / idle / offline)
- Transfer Ownership (with confirmation + audit log)
- Fine-grained permissions matrix
- Realtime: presence + activity via websocket or polling
- Notifications: invite, role change, removal, ownership transfer

**Status:** Backend routes may exist but frontend UI is completely missing. Settings page shows placeholder text.

### 6.2 Customer Platform Cleanup (#46) — NOT DONE
**What exists:**
- Previous sessions deleted some customer routes and templates
- `zintriq/base.html` + partials created for unified shell
- Workspace dashboard, marketplace, settings rebuilt with Zintriq template

**What's left:**
- Remove orphaned `customer_*.py` modules if no longer used
- Delete `templates/customer/` if all customer pages now use `zintriq/` shell
- Consolidate duplicate static assets (favicons, logos)
- Move `audit/` screenshots to `docs/` or delete
- Clean up `.tmp_logo_fix/`, `outputs/`, `work/` directories
- Verify all customer-facing routes still render correctly
- Add asset audit script for CI

**Status:** Partially done. Need to verify what's actually orphaned vs. still in use.

---

## 7. SUMMARY

### Critical Counts
| Severity | Count | Category |
|----------|-------|----------|
| **P0 Blocker** | 2 | Missing templates, circular import |
| **P1 Major** | 5 | Secrets, i18n corruption, 762+ hardcoded colors, silent exceptions |
| **P2 Minor** | 5 | console.error, XSS risk, SELECT *, orphan templates, transition:all |
| **P3 Polish** | 5 | !important, token inconsistency, no TODOs (good), no broken imports (good) |

### Recommended Phase 1 Actions (P0 + P1 only)
1. **Create 4 missing customer auth templates** (or redirect to owner equivalents)
2. **Fix circular import** in payment adapters
3. **Rotate Google OAuth credentials** in `.env.local`
4. **Fix Filipino i18n corruption** in `messages.js`
5. **Migrate hardcoded colors to tokens** (762 instances — large but mechanical)
6. **Add logging to silent exception handlers** (35 instances)

### Estimated Effort
- **Phase 1 (Stabilize):** 2-3 days
- **Phase 2 (Complete missing work):** 5-7 days
- **Phase 3 (Builder UX overhaul):** 5-7 days
- **Phase 4 (Dashboard UX overhaul):** 3-5 days
- **Phase 5 (Polish pass):** 2-3 days

**Total:** 17-25 days of focused work

---

## 8. NEXT STEPS

1. **Review this audit** — confirm priorities, adjust scope
2. **Execute Phase 1** — fix all P0 + P1 bugs
3. **Execute Phase 2** — complete team collaboration + customer cleanup
4. **Execute Phase 3** — builder UX overhaul
5. **Execute Phase 4** — dashboard UX overhaul
6. **Execute Phase 5** — final polish pass

**Deliverables per phase:**
- `PHASE_REPORT.md` with done/not-done/tech-debt/blockers
- PR-ready branch with focused commits
- Before/after screenshots for UI changes
- Zero new console errors, zero new lint errors

---

## Correction — Route Count (2026-09-30)

Line 29 states "~450 total routes" for the `*_platform.py` feature modules. This was an estimate that undercounted the actual total.

**Actual route count** from `app.url_map.iter_rules()`: **514 total routes** (including app.py)

**Breakdown**:
- 154 GET routes without URL parameters
- 139 GET routes with URL parameters
- 66 POST-only routes without URL parameters
- 102 POST-only routes with URL parameters
- 52 other method routes (PUT/DELETE) with URL parameters
- 1 static file route

**app.py alone**: 91-92 routes (line 28 states "90 routes" — close)  
**All *_platform.py files combined**: ~422 routes (not ~450)

The "~450" estimate appears to have included app.py routes in the platform file count, causing double-counting. The actual total across all files is 514.
