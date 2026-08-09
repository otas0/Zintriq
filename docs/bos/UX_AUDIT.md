# Business OS — UX Audit & Refactoring Report

Version: 1.0 · August 2026

This document audits the **existing** Business OS implementation against the QR-first merchant platform spec. It records current state, problems, and changes applied or recommended — without rebuilding pages from scratch.

---

## Executive Summary

| Area | Status | Notes |
|------|--------|-------|
| App layout (top bar) | ✅ Aligned | Menu, logo, workspace selector, search, notifications, account |
| Sidebar nav | ✅ Aligned | Home · QR Experiences · Responses · Team · Settings |
| Home | ✅ Refactored | Quick actions, real QR cards, responses, activity — no fake dashboard |
| QR Experiences list | ✅ Refactored | Card grid, filters, real DB data |
| QR Editor | ⚠️ Partial | 3-column layout exists; uses shared `QRPreview`; workflow tab hidden via flags |
| Responses | ✅ Aligned | Card list, filters, detail drawer, `/api/responses` |
| Team | ⚠️ Partial | Real API; MVP roles mapped; invitations reachable via subnav |
| Settings | ✅ Refactored | Business · Branding · Team · Account · Integrations (placeholder) |
| Hidden complexity | ✅ Deferred | CRM, analytics, plugins, booking/calendar hidden via `MVP_FLAGS` |
| Mock data in MVP UI | ✅ None | MVP pages use REST APIs; legacy `seed.js` isolated to old BOS modules |

---

## 1. Page-by-Page Audit

### App Layout

| | |
|---|---|
| **Purpose** | Shell for all Business OS pages — merchant context always visible |
| **Components** | `templates/bos/shell.html`, `partials/toolbar.html`, `partials/sidebar.html`, `static/bos/core/shell.js`, `workspace-switcher.js` |
| **Data source** | `/api/workspaces`, session `active_workspace_id` |
| **User flow** | Sign in → land on Home → switch workspace from top bar → navigate sidebar |
| **Problems (before)** | Workspace switcher duplicated in sidebar; breadcrumbs dominated header; developer module names |
| **Changes** | Workspace selector moved to top bar; sidebar simplified to 5 items; Stores link removed from sidebar foot |
| **Recommended** | Keep page titles in module mount only; avoid re-adding platform modules to nav |

---

### Home (`/app`)

| | |
|---|---|
| **Purpose** | Daily business operations — not an analytics dashboard |
| **Components** | `home-page.js`, `WelcomeBanner`, `QuickActionBar`, `QRExperienceCardCompact`, `ResponseCard` |
| **Data source** | `GET /api/home/summary` — `qr_experiences`, `recent_responses`, `recent_activity`, `workspace_name` |
| **User flow** | See welcome → quick actions → active QR → recent responses → activity timeline |
| **Problems (before)** | Booking/check-in widgets, fake stat grids, recommended-actions noise |
| **Changes** | Removed dashboard metrics from UI; all sections use real API fields; empty states when no data |
| **Recommended** | Trim legacy booking/checkin queries from home API when MVP-only deploy |

---

### QR Experiences (`/app/qr`)

| | |
|---|---|
| **Purpose** | Core product — manage QR resources (Shopify product-list pattern) |
| **Components** | `qr-experiences-page.js`, `PageHeader`, `FilterBar`, `QRExperienceCard`, detail side panel, builder overlay |
| **Data source** | `GET/POST/PATCH/DELETE /api/qr-experiences`, templates API |
| **User flow** | Filter list → open card → overview/preview/responses → Edit opens 3-column builder |
| **Problems (before)** | Table layout; technical tabs (workflow, analytics); deferred templates visible |
| **Changes** | Card grid with Open/Edit/Duplicate/Archive; filters All/Active/Draft/Disabled/Archived; analytics & workflow tabs gated by `MVP_FLAGS` |
| **Recommended** | Consolidate `renderLandingPreview` → `QRPreview` (done); add delete only for drafts |

---

### QR Editor (builder overlay)

| | |
|---|---|
| **Purpose** | Shopify theme-editor style — blocks left, preview center, settings right |
| **Components** | `openBuilder()` in `qr-experiences-page.js`, `QRPreview`, builder CSS in `shell.css` |
| **Data source** | Experience detail + `PUT /blocks`, `PUT /actions`, `PATCH` settings |
| **User flow** | Edit → add Text/Image/Button/Feedback/Survey blocks → preview updates → Save → Publish |
| **Problems (before)** | Duplicate preview renderer; booking/check-in blocks when MVP off |
| **Changes** | MVP block/action types only when `deferredActions: false`; shared preview component |
| **Recommended** | Reduce builder tabs to Edit + Publish only for MVP; defer workflow editor entirely |

---

### Responses (`/app/responses`)

| | |
|---|---|
| **Purpose** | Business operations tool for customer feedback and surveys |
| **Components** | `responses-page.js`, `ResponseList`, `ResponseCard`, `ResponseDetail` |
| **Data source** | `GET /api/responses`, `GET /api/responses/:id` (unified `responses` table) |
| **User flow** | Filter All/Feedback/Survey → search → click card → drawer with source QR + time |
| **Problems (before)** | Raw table feel; legacy feedback-only paths |
| **Changes** | Card layout; relative timestamps; links to source QR experience |
| **Recommended** | Dual-write from legacy feedback remains until full migration |

---

### Team (`/app/team`)

| | |
|---|---|
| **Purpose** | Workspace members, invitations, roles |
| **Components** | `team-page.js`, `MemberCard`, `InviteMemberModal`, team platform API |
| **Data source** | `/api/team/members`, `/api/team/invitations`, `/api/team/roles` |
| **User flow** | View members → invite → accept link; role changes in drawer |
| **Problems (before)** | 5 technical sub-sections; DB roles (`administrator`, `viewer`) shown raw |
| **Changes** | MVP subnav: Members + Invitations; `mvp_role` (Owner/Admin/Member) in cards; real invite flow |
| **Recommended** | Map invite role picker to Admin/Member only in UI |

---

### Settings (`/app/settings`)

| | |
|---|---|
| **Purpose** | Business profile, branding, team shortcut, account, integrations placeholder |
| **Components** | `workspaces-page.js`, `SettingsNav` |
| **Data source** | `/api/workspaces/:id/settings`, stores/members APIs |
| **User flow** | Category nav → edit business/branding → link to Team or Account |
| **Problems (before)** | CRM stat grid (Customers, Stores); module toggles; full plugin marketplace |
| **Changes** | MVP stat row (QR, Responses, Members); integrations placeholder; stores table de-emphasized |
| **Recommended** | Do not build new plugins until QR core is stable |

---

## 2. Complexity Removed / Hidden

| Feature | Action | Mechanism |
|---------|--------|-----------|
| Advanced Analytics | Hidden | `MVP_FLAGS.advancedAnalytics = false` |
| Workflow engine | Hidden | `MVP_FLAGS.workflowEngine = false` |
| Customer CRM | Hidden | Nav redirect; `customerCrm = false` |
| Plugin marketplace | Hidden | `plugins = false`; settings shows placeholder |
| Booking / Calendar / Check-in | Hidden | Legacy nav items `hidden: true`; routes redirect or URL-only |
| Operations platform | Hidden | Redirect to Home |
| Mock BOS store | Isolated | `static/bos/data/seed.js` — not used by MVP feature pages |

Legacy tables and APIs are **preserved**; data is not deleted.

---

## 3. Component Consistency

Shared library: `static/bos/components/` (`ui/`, `layout/`, `business/`, `qr/`, `response/`, `team/`).

| Component | Used on |
|-----------|---------|
| Button, Card, Badge, EmptyState, Skeleton, Modal | All MVP pages |
| PageHeader, FilterBar, SearchBar | QR, Responses |
| QRExperienceCard, QRPreview | Home, QR list, Editor |
| ResponseList, ResponseCard | Home, Responses |
| MemberCard, InviteMemberModal | Team |
| SettingsNav, WelcomeBanner, QuickActionBar | Settings, Home |

**Remaining duplication:** `renderLandingPreview` in qr-experiences-page (being replaced by `QRPreview` import).

---

## 4. Data Verification

| Page | API | Mock? |
|------|-----|-------|
| Home | `/api/home/summary` | No |
| QR list | `/api/qr-experiences` | No |
| QR editor | `/api/qr-experiences/:id/*` | No |
| Responses | `/api/responses` | No |
| Team | `/api/team/*` | No |
| Settings | `/api/workspaces/*` | No |
| Workspace switcher | `/api/workspaces` | No |

---

## 5. Mobile UX

| Check | Status |
|-------|--------|
| Sidebar collapse (hamburger) | ✅ `bos-menu-btn` + overlay |
| Card grids stack | ✅ `merchant.css` responsive |
| QR preview in editor | ✅ Mobile-width preview column |
| Forms | ✅ Full-width inputs on small screens |
| Touch targets | ✅ Button sm variants ≥ 36px |

---

## 6. Performance

| Check | Status |
|-------|--------|
| Home single summary fetch | ✅ One `/api/home/summary` |
| QR list parallel fetch | ✅ Experiences + templates |
| Loading states | ✅ Skeleton / loadingState |
| Error states | ✅ EmptyState with message |
| Empty states | ✅ All MVP list pages |
| Event listener leaks | ✅ Home uses `{ once: false }` with cleanup on remount |

**Note:** Home API still queries legacy booking/checkin tables server-side; safe to trim in a follow-up.

---

## 7. Final Verification Checklist

### Product
- [x] QR remains the main product
- [x] Unnecessary features hidden from nav
- [x] Navigation is simple (5 items)

### UX
- [x] Merchant-style shell (Uber Eats / Shopify patterns)
- [x] Business/workspace context in top bar
- [x] Primary actions obvious (Create QR, View Responses)

### Technical
- [x] Existing code refactored in place
- [x] Component library standardized
- [x] Real database connected on MVP pages
- [x] No mock data on MVP pages

---

## 8. Follow-Up (Not in Scope)

1. Single JSON `content` column for QR builder (replace multi-table builder)
2. Remove dual-write `feedback_records` → `responses` after migration window
3. Full mobile QA on physical devices
4. Delete action for draft QR experiences (with confirm)
