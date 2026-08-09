# Business OS — MVP UX Refactoring Implementation Plan

Version: 1.0 · August 2026

Transforms [UX Audit](./UX_AUDIT.md) findings into actionable tasks. **Refactor only** — no feature expansion, no rebuild.

**Reference:** Uber Eats Merchant (operational simplicity) · Shopify Admin (resource management)

**Core journey:**

```
Login → Workspace → Create QR → Customize → Publish → Scan → Response → Review
```

---

## Status Summary

| Phase | Focus | Status |
|-------|--------|--------|
| 1 | Codebase review | ✅ Documented below |
| 2 | Remove product noise | ✅ `MVP_FLAGS` + hidden nav |
| 3 | App layout | ✅ Top bar + sidebar |
| 4 | Home | ✅ Command center |
| 5 | QR Experiences | ✅ Cards + detail tabs |
| 6 | QR Editor | ✅ 3-column + `QRPreview` |
| 7 | Responses | ✅ Cards + drawer |
| 8 | Team | ✅ Members + invite + MVP roles |
| 9 | Settings | ✅ 5 categories + integrations placeholder |
| 10 | Components | ✅ `static/bos/components/` |
| 11 | Real data | ✅ API-backed MVP pages |
| 12 | Mobile | ⚠️ Responsive CSS; device QA open |
| 13 | Performance | ✅ Batch queries, lazy modules, WAL |

---

## Phase 1 — Implementation Report (Pages)

### Login (`/login`)

| | |
|---|---|
| **Components** | `templates/login.html`, Firebase/auth forms |
| **Data** | `users`, session |
| **API** | POST login, magic link, Firebase |
| **Problems** | None blocking MVP |
| **Changes** | — |

### Workspace (selector)

| | |
|---|---|
| **Components** | `workspace-switcher.js`, `workspace-context.js` |
| **Data** | `GET /api/workspaces`, session `active_workspace_id` |
| **Bootstrap** | `BOS_BOOTSTRAP` in shell template |
| **Problems** | Was duplicate API on load — fixed |
| **Changes** | Cache + server inject active workspace |

### Home (`/app`)

| | |
|---|---|
| **Components** | `home-page.js`, `WelcomeBanner`, `QuickActionBar`, `QRExperienceCardCompact`, `ResponseCard` |
| **Data** | `GET /api/home/summary` |
| **DB** | `qr_experiences`, `responses`, `workspace_activity` |
| **Problems** | Was analytics dashboard — fixed |
| **Changes** | Quick actions, real QR/responses/activity only |

### QR Experiences (`/app/qr`)

| | |
|---|---|
| **Components** | `qr-experiences-page.js`, `QRExperienceCard`, `PageHeader`, `FilterBar` |
| **Data** | `GET /api/qr-experiences` |
| **DB** | `qr_experiences`, analytics events, `responses` |
| **Problems** | Was table + workflow noise — fixed |
| **Changes** | Card grid, filters, Open/Edit/Duplicate/Archive/Delete |

### QR Editor (overlay)

| | |
|---|---|
| **Components** | `openBuilder()`, `QRPreview`, builder CSS |
| **Data** | `PATCH` experience, `PUT /blocks`, `PUT /actions` |
| **Layout** | Components · Preview · Settings |
| **Blocks (MVP)** | Text, Image, Button, Feedback, Survey |
| **Changes** | Shared preview; deferred blocks via flags |

### Responses (`/app/responses`)

| | |
|---|---|
| **Components** | `responses-page.js`, `ResponseList`, `ResponseCard`, `ResponseDetail` |
| **Data** | `GET /api/responses`, `GET /api/responses/:id` |
| **DB** | `responses` (unified) |
| **Changes** | Card UI, All/Feedback/Survey filters |

### Team (`/app/team`)

| | |
|---|---|
| **Components** | `team-page.js`, `MemberCard`, `InviteMemberModal` |
| **Data** | `/api/team/members`, `/api/team/invitations` |
| **Roles (UI)** | Owner, Admin, Member |
| **Changes** | MVP subnav; role labels |

### Settings (`/app/settings`)

| | |
|---|---|
| **Components** | `workspaces-page.js`, `SettingsNav` |
| **Data** | `/api/workspaces/:id/settings` |
| **Sections** | Business, Branding, Team, Account, Integrations |
| **Changes** | MVP stats; integrations placeholder; fixed parser error |

---

## Phase 2 — Remove Product Noise

| Item | Action | Mechanism |
|------|--------|-----------|
| Advanced Analytics | Hidden | `MVP_FLAGS.advancedAnalytics = false` |
| Workflow engine | Hidden | `MVP_FLAGS.workflowEngine = false` |
| CRM / Customers | Hidden | Nav redirect → Responses |
| Plugins marketplace | Hidden | `PRODUCT_FLAGS.plugins = false` |
| Booking / Calendar / Check-in | Hidden | Legacy nav `hidden: true` |
| Operations | Hidden | Redirect |
| Mock BOS store | Isolated | `seed.js` not used by MVP pages |

**Rule:** Data preserved; UI hidden via flags and redirects.

---

## Phase 3 — Application Layout

### Top navigation ✅

Menu · Logo · Workspace selector · Search · Notifications · Account

Files: `templates/bos/partials/toolbar.html`, `shell.css`, `merchant.css`

### Workspace selector ✅

Real workspaces from `/api/workspaces`; create via modal; switch without full reload.

### Sidebar ✅

Home · QR Experiences · Responses · Team · Settings

---

## Phase 4 — Home Refactoring ✅

| Removed | Added |
|---------|-------|
| Fake stats, booking widgets | Quick actions |
| Empty charts | Active QR cards (real) |
| | Recent responses (real) |
| | Business activity (real) |

---

## Phase 5 — QR Experience Refactoring

### QR list ✅

Card layout · filters (All/Active/Draft/Disabled/Archived) · search · lazy templates on create

### QR card ✅

Preview · Name · Type · Status · Usage · Updated · Actions

### QR detail ✅

Tabs: **Overview · Preview · Responses · Settings**

### QR overview ✅

QR image · Public URL · Status · Views · Responses · Created date · Actions

---

## Phase 6 — QR Editor ✅

3-column: Components | Customer Preview | Settings

MVP blocks: Text, Image, Button, Feedback, Survey (booking/check-in hidden)

---

## Phase 7 — Responses ✅

Filters: All / Feedback / Survey · cards · detail drawer with source QR + time

---

## Phase 8 — Team ✅

Members grid · Invite modal · Invitations tab · MVP roles in UI

Verify: invitation accept flow, workspace isolation via API

---

## Phase 9 — Settings ✅

Business · Branding · Team · Account · Integrations (placeholder cards only)

---

## Phase 10 — Component Standardization ✅

Library: `static/bos/components/` — ui, layout, business, qr, response, team

Rule: MVP pages import from `components/index.js`

---

## Phase 11 — Real Data Verification ✅

| Entity | Source |
|--------|--------|
| User | Session + `users` |
| Workspace | `workspaces` + `/api/workspaces` |
| QR | `qr_experiences` |
| Responses | `responses` |
| Team | `workspace_members` |

Verify: `python3 scripts/verify_mvp_database_schema.py` · `node scripts/verify_ux_audit.js`

---

## Phase 12 — Mobile Optimization ⚠️

| Check | Status |
|-------|--------|
| Sidebar hamburger | ✅ |
| Card grids stack | ✅ `merchant.css` |
| QR preview | ✅ mobile width in editor |
| Notifications dropdown | ✅ panel in toolbar |
| Device QA | 🔲 Manual pass recommended |

---

## Phase 13 — Performance Optimization ✅

| Fix | File |
|-----|------|
| Batch QR stats query | `home_platform.py` |
| Slim home API | `home_platform.py` |
| Lazy feature modules | `main.js` |
| Workspace bootstrap | `shell.html`, `workspace-context.js` |
| Deferred palette/notifications sync | `main.js`, `notifications-ui.js` |
| SQLite WAL | `app.py` |
| Google watch refresh background | `google_calendar_plugin.py` |
| GET request dedupe | `bos-api.js` |

---

## Task Backlog (Optional Follow-ups)

| ID | Task | Priority |
|----|------|----------|
| T1 | Physical mobile QA on iOS Safari | Medium |
| T2 | Hard-delete draft QR (vs archive) | Low |
| T3 | Trim legacy booking queries from home API entirely | Low |
| T4 | Storefront Uber-style layout (separate spec) | Future |
| T5 | Single JSON `content` column for QR builder | Future |

---

## Final Verification Checklist

### UX
- [x] Clear business context (workspace in top bar)
- [x] Simple navigation (5 items)
- [x] QR is the center
- [x] Actions obvious (Create QR, View Responses)
- [x] Consistent UI (component library)

### Product
- [x] User can create QR
- [x] Customer can interact (public `/e/:slug`)
- [x] Business receives response
- [x] Team can collaborate

### Technical
- [x] Existing code reused
- [x] Real database connected
- [x] No mock data on MVP pages
- [x] Unnecessary systems hidden

---

## Verification Commands

```bash
python3 scripts/verify_mvp_database_schema.py
node scripts/verify_component_library.js
node scripts/verify_ux_audit.js
python3 app.py   # http://127.0.0.1:5001/app
```

---

## Related Docs

- [UX Audit](./UX_AUDIT.md)
- [Component Library](./COMPONENT_LIBRARY.md)
- [MVP Database Schema](./MVP_DATABASE_SCHEMA.md)
- [Storefront UX Design](./STOREFRONT_UX_DESIGN.md)
