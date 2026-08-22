# Zintriq — Platform Specification

> **Status:** Mandatory for every platform implementation  
> **Code mirrors:** `bos/platform_spec.py`, `static/bos/platform/platform-spec.js`  
> **Architecture:** [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) · [APPLICATION_SHELL.md](./APPLICATION_SHELL.md)  
> **Objects:** [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) · [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md) · [EVENT_BUS.md](./EVENT_BUS.md)

## Objective

Define universal standards every Zintriq Platform must follow.

Platforms are major capabilities — not separate applications. They must feel like different areas of the **same operating system**.

---

## What is a Platform?

A Platform is a **complete business capability**.

| A Platform… | A Platform does NOT… |
|-------------|----------------------|
| Operates on one or more Business Objects | Own global system capabilities |
| Implements business workflows and rules | Implement authentication, navigation, or search engines |
| Integrates with other platforms via objects and events | Directly call unrelated platforms |
| Follows shared Zintriq standards | Duplicate Foundation or Core logic |

**Example — Customer Platform**

- **Owns:** customer management, customer interactions
- **Uses:** Notifications, Search, Files, Permissions, Events (from Foundation/Core)

---

## Standard Platform Structure

Every platform follows the same internal structure. Not every section is mandatory, but the layout must feel familiar.

```
Platform
├── Overview          ← dashboard, stats, quick actions
├── Object List       ← searchable, filterable collection
├── Detail            ← drawer-first object view
├── Activity          ← event-derived timeline (read-only)
├── Analytics         ← read-only metrics
├── Settings          ← platform configuration
└── Integrations      ← extension hooks (future)
```

Implementation pattern: `bos-subnav` sections in `static/bos/features/*-page.js`.

---

## Platform Responsibilities

### Responsible for

- Business workflows
- Business rules
- Object management (CRUD, batch, lifecycle)
- User interactions within its domain

### Not responsible for

| Capability | Owner |
|------------|-------|
| Authentication | Core |
| Application Shell / Navigation | Core |
| Notifications | Foundation (event subscribers) |
| File storage | Foundation (attachment service) |
| Global Search engine | Foundation |
| Permission engine | Foundation |

---

## Platform Navigation

Every platform provides:

1. **Overview** — entry point with stats and recent activity
2. **Primary Object List** — main collection view
3. **Detail View** — drawer or inline panel
4. **Settings** — platform-specific configuration

Navigation lives **inside the Application Shell**. Platforms never create independent nav chrome (sidebar, top bar, workspace switcher).

**Nav levels:** Workspace → Platform → Object List → Object Detail

---

## Object Lists

Platforms managing business objects must provide:

| Capability | Shared implementation |
|------------|----------------------|
| Search | Filter bar `#bos-search-input` or platform search |
| Filters | `renderFilterBar()` / status chips |
| Sorting | Sort select in module toolbar |
| Batch actions | `selection.js` + bottom action bar |
| Pagination / scroll | Progressive render; preserve scroll via `continuity.js` |
| Saved views | Future |

Reuse: `static/bos/features/module-page.js`, `static/bos/components/advanced-table.js`.

---

## Object Details

Standard interaction model:

```
List → Drawer → Edit → Save
```

- Preferred: `openObjectDetail()` / `openDrawer()` from `object-detail.js`
- Avoid full-page navigation for view/edit when a drawer suffices
- Tabs: Overview, Properties, Related, Activity, Attachments, Notes (per [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md))

---

## Batch Operations

Minimum support for collection platforms:

| Action | Required |
|--------|----------|
| Select / Select All | ✅ |
| Archive | ✅ |
| Delete | ✅ |
| Export | ✅ |
| Add Tags | When object supports tags |

Implementation: `static/bos/services/batch-actions.js`, `#bos-action-bar`.

---

## Activity Integration

Platforms **emit domain events**. They must **not** directly create:

- Notifications
- Activity records (projections are written by event subscribers)
- Analytics counters

```
Action → Domain Event → Event Bus → Subscribers
```

Use `emit()` in Python platform modules. Client-side mock modules dispatch `bos:domain-event`.

---

## Search Integration

- Platforms register searchable object types in [DOMAIN_MODEL.md](./DOMAIN_MODEL.md)
- Global Search indexes objects via `/api/workspaces/{id}/search` and `global-search.js`
- Platforms do **not** implement standalone search engines
- List-level filter search is allowed (scoped to current collection)

---

## Notification Integration

Platforms emit events. Notification delivery is handled by the Notification Framework (`_subscriber_notifications` in `bos/events.py`).

**Never** call `createNotification()` from platform pages for business events.

---

## Permission Integration

- Platforms **consume** action-based permissions: create, read, update, archive, delete, export, publish, assign
- Defined in Foundation: `PERMISSION_ACTIONS` in `bos/domain.py`
- Enforced via workspace roles (`owner`, `administrator`, `manager`, `staff`, `viewer`)
- Platforms do **not** define custom permission systems

---

## File Integration

- Attach files through shared attachment service: `static/bos/platform/attachments.js`
- Upload infrastructure: `app.py` → `static/uploads/`
- Platforms reference files on objects; they do not manage storage paths

---

## Analytics Integration

- Platforms **expose** data via APIs and events
- Analytics **consumes** events (`event_analytics`, feedback summary APIs)
- Analytics never modifies platform objects

---

## Design Requirements

Every platform must use:

| Asset | Location |
|-------|----------|
| Design tokens | `static/tokens.css`, `static/materials.css` |
| Component library | `static/bos/components/` |
| Shell layout | `templates/bos/shell.html`, `static/bos/shell.css` |
| Status badges, tables, drawers | `static/bos/components/index.js` |

Custom components require approval and must be promoted to Shared if reused.

---

## Performance Requirements

- Lazy load large datasets (API pagination, deferred render)
- Optimistic updates where safe
- Preserve scroll position (`continuity.js`)
- Avoid unnecessary full page refreshes (workspace soft-switch, drawer remount)
- User interactions should feel immediate

---

## Accessibility

- Keyboard navigation (shell shortcuts: ⌘K, ⌘N, Esc, /)
- Focus management in drawers and command palette
- Screen reader labels on nav, buttons, tables
- High contrast themes (future — `data-theme` token swap)

---

## Extension Points

Platforms expose hooks for future plugins:

| Hook | Purpose |
|------|---------|
| Custom actions | Batch bar, object context menu |
| Sidebar items | Via plugin registry (planned) |
| Commands | `static/bos/platform/commands.js` |
| Event subscribers | `bos/events.py` `subscribe()` |
| Settings panels | Platform settings section |

Plugins integrate without modifying platform source.

---

## Platform Registry & Conformance

| Platform | Sections | Objects | Events | Drawer | Batch | API | Maturity |
|----------|----------|---------|--------|--------|-------|-----|----------|
| **Workspace** | Overview, Stores, Members, Modules, Activity, Settings | workspace, store | ✅ | Partial | — | ✅ | Implemented |
| **Customer** | Overview, Customers, Groups, Tags, Activity, Settings | customer | ✅ | ✅ | ✅ | ✅ | Implemented |
| **Feedback** | Overview, Templates, Inbox, Analytics, Settings | feedback, template | ✅ | ✅ | Partial | ✅ | Implemented |
| **QR** | Store workspace (owner UI) | store, qr, product, event | Partial | Owner pages | Partial | ✅ | Implemented |
| **Products** | Module list + drawer | catalog | Client only | ✅ | ✅ | Mock | Partial |
| **Orders** | Module list + drawer | transactions | Client only | ✅ | ✅ | Mock | Partial |
| **Team** | Module list + drawer | team | Client only | ✅ | ✅ | Mock | Partial |
| **Inventory** | — | inventory | — | — | — | — | Planned |
| **Documents** | Module list + drawer | documents | Client only | ✅ | ✅ | Mock | Partial |
| **Analytics** | Event-derived + feedback | — | Consumer | — | — | Partial | Partial |

Detailed conformance: `bos/platform_spec.py` → `PLATFORM_REGISTRY`.

---

## Completion Criteria

A platform is **complete** when:

- [ ] Follows shared platform structure (Overview + List + Detail + Settings minimum)
- [ ] Integrates with Core services (shell, workspace context)
- [ ] Emits standard domain events (no direct notification/activity writes)
- [ ] Reuses shared components (tables, drawers, filter bar, action bar)
- [ ] Follows Design System (tokens, materials, BOS components)
- [ ] Does not duplicate Foundation or Core functionality
- [ ] Behaves consistently with every other Zintriq platform
- [ ] Registered in `PLATFORM_REGISTRY`

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | Layer blueprint |
| [APPLICATION_SHELL.md](./APPLICATION_SHELL.md) | Shell that hosts all platforms |
| [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) | Objects platforms operate on |
| [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md) | Per-object behavior |
| [EVENT_BUS.md](./EVENT_BUS.md) | Event integration rules |
