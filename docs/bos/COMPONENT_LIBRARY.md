# Business OS — MVP Component Library

Version 1.0 · Vanilla JS (ES modules)

## Philosophy

Build the design foundation first. All pages compose from these components — no page-specific UI patterns.

Inspired by Shopify Polaris (consistency) and Uber Eats merchant UI (operational clarity).

## Structure

```
static/bos/components/
├── ui/           Button, Card, Badge, EmptyState, Skeleton, Modal, Dropdown, Form
├── layout/       PageHeader, SearchBar, FilterBar, Sidebar, TopBar, WorkspaceSelector
├── business/     WelcomeBanner, QuickActionBar, SettingsNav, CardGrid
├── qr/           QRExperienceCard, QRPreview, QRStatus
├── response/     ResponseCard, ResponseList, ResponseDetail
├── team/         MemberCard, InviteMemberModal
└── index.js      Barrel export (import from here)
```

Legacy shims (deprecated): `design-system.js`, `merchant.js`

## Usage

```javascript
import {
  PageHeader,
  Button,
  QRExperienceCard,
  ResponseList,
  MemberCard,
  Skeleton,
  EmptyState,
} from "../components/index.js";
```

## Rules

- **No mock data** inside components — pass props / API data only
- **Loading**: `Button({ loading: true })`, `Skeleton("page")`
- **Empty**: `EmptyState({ title, text, actionHtml })`
- **Status**: `StatusBadge("active")` everywhere
- **Create** not Add/Generate/New

## Layout

Shell is server-rendered (`templates/bos/shell.html`). JS initializes:

- `initWorkspaceSelector()` — real workspace list from API
- Sidebar nav from `sidebarNavItems()` + `product-focus.js`

## Checklist

- [x] Layout (TopBar, Sidebar, WorkspaceSelector)
- [x] UI primitives (Button, Card, Badge, Modal, Form, Skeleton, EmptyState)
- [x] Page (PageHeader, SearchBar, FilterBar)
- [x] QR (QRExperienceCard, QRPreview)
- [x] Response (ResponseCard, ResponseList, ResponseDetail)
- [x] Team (MemberCard, InviteMemberModal)
- [x] Mobile responsive (merchant.css)
- [x] Backward-compatible exports

## Verify

```bash
node --experimental-vm-modules scripts/verify_component_library.js
```
