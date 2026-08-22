# Zintriq — System Architecture Specification

> **Status:** Canonical architectural blueprint  
> **Code mirrors:** `bos/architecture.py`, `static/bos/platform/system-architecture.js`  
> **Companion specs:** [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) · [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md) · [APPLICATION_SHELL.md](./APPLICATION_SHELL.md) · [EVENT_BUS.md](./EVENT_BUS.md)

## Objective

Define how every platform, module, object, shared service, and future capability is organized.

Zintriq behaves as **one operating system** — not a collection of independent applications.

Every implementation must follow this specification.

---

## Architecture Principles

| Principle | Meaning |
|-----------|---------|
| **Domain First** | Business objects own data; platforms operate on them |
| **Platform First** | Capabilities are grouped into reusable platforms |
| **Object Driven** | All features work through standardized business objects |
| **Event Driven** | Platforms communicate via domain events, not direct calls |
| **Component Driven** | UI is composed from shared, business-agnostic components |

Business logic must never be tightly coupled to UI.

---

## High-Level Architecture

```
Zintriq

Foundation
│   Domain · Objects · Events · Permissions · Search · Notifications · Files · Settings
│
Core
│   Workspace · Application Shell · Navigation · Auth · Authorization · Plugin Manager
│
Platforms
│   Customer · QR · Feedback · Product · Inventory · Order · Appointment · Membership · Analytics
│
Shared
│   Design System · Components · Tokens · Hooks · Services · Utilities · API Client
│
Extensions
    Integrations · Plugins · Marketplace · AI Copilot
```

Every layer has a **single responsibility**. Dependencies flow **downward only**.

---

## Dependency Rules

```
Extensions → Platforms → Core → Foundation
```

| Rule | Detail |
|------|--------|
| Foundation never depends on Platforms | No imports from `*_platform.py` in `bos/events.py` subscribers beyond projections |
| Platforms never depend on Extensions | Stripe, OpenAI, etc. are optional adapters |
| Core depends only on Foundation | Shell uses events, domain, object standards — not platform logic |
| Avoid circular dependencies | Use event bus for cross-platform reactions |

---

## Layer Responsibilities

### Foundation Layer

Reusable system capabilities. **No business-specific logic.**

| Capability | Spec | Implementation |
|------------|------|----------------|
| Domain Models | [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) | `bos/domain.py`, `static/bos/platform/domain-model.js` |
| Object Standards | [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md) | `bos/object_standards.py`, `static/bos/platform/object-standards.js` |
| Event Bus | [EVENT_BUS.md](./EVENT_BUS.md) | `bos/events.py`, `event_platform.py`, `static/bos/platform/event-bus.js` |
| Permission Engine | Action-based (create, read, update, archive, delete, export, publish, assign) | `bos/domain.py` `PERMISSION_ACTIONS` |
| Global Search | Workspace-scoped object search | `static/bos/services/global-search.js`, `/api/workspaces/{id}/search` |
| Notification Framework | Event subscribers only | `event_notifications`, `static/bos/platform/notifications.js` |
| File Management | Attachments on objects | `static/bos/platform/attachments.js` (shared attachment model) |
| Settings Framework | Workspace / platform settings | `workspace_platform.py`, per-platform settings tables |

### Core Layer

How Zintriq operates. **Every platform depends on Core.**

| Capability | Spec | Implementation |
|------------|------|----------------|
| Workspace Management | Root operating container | `workspace_platform.py`, `static/bos/services/workspace-context.js` |
| Application Shell | Persistent OS chrome | [APPLICATION_SHELL.md](./APPLICATION_SHELL.md), `static/bos/core/shell.js` |
| Navigation | Shell-owned nav | `static/bos/core/shell-nav.js`, `static/bos/core/nav.js` |
| Authentication | User identity | `app.py` (login, 2FA, Firebase) |
| Authorization | Workspace membership + roles | `workspace_members`, route guards |
| Plugin Manager | Extension registration | `static/bos/platform/system-architecture.js` (planned hooks) |

### Platform Layer

Reusable business capabilities. **Operate on business objects; never own shared system logic.**

| Platform | Maturity | Backend | Frontend | Spec |
|----------|----------|---------|----------|------|
| Workspace | Implemented | `workspace_platform.py` | `static/bos/features/workspaces-page.js` | [PLATFORM_SPECIFICATION.md](./PLATFORM_SPECIFICATION.md) |
| Customer | Implemented | `customer_platform.py` | `static/bos/features/customers-page.js` |
| Feedback | Implemented | `feedback_platform.py` | `static/bos/features/feedback-page.js` |
| QR | Implemented | `app.py` (stores, QR entities) | Owner templates + `/my-stores` |
| Product (Catalog) | Partial (mock BOS) | — | `static/bos/features/module-page.js` + seed |
| Orders (Transactions) | Partial (mock BOS) | — | `static/bos/features/module-page.js` |
| Team | Partial (mock BOS) | — | `static/bos/features/module-page.js` |
| Inventory | Planned | — | — |
| Appointment | Planned | — | — |
| Membership | Planned | — | — |
| Analytics | Partial | `event_analytics`, feedback summary API | Home + feedback analytics |

### Shared Layer

Business-independent reusable code.

| Area | Location |
|------|----------|
| Design tokens | `static/tokens.css`, `static/materials.css`, `static/system.css` |
| Shell layout | `static/bos/shell.css`, `templates/bos/shell.html` |
| Components | `static/bos/components/`, `static/bos/components.css` |
| Services | `static/bos/services/` (api, search, selection, batch-actions, undo) |
| Platform utilities | `static/bos/platform/` (object-detail, commands, activity, tags, notes) |
| Core orchestration | `static/bos/core/` (store, shell, nav, command-palette) |

### Extension Layer

Optional. **Core never depends on Extensions.**

| Extension type | Status | Integration pattern |
|----------------|--------|---------------------|
| Integrations (Stripe, Slack, etc.) | Planned | Events + published API adapters |
| Plugins | Planned | Register pages, commands, objects via plugin manager |
| Marketplace | Planned | Plugin distribution |
| AI Copilot | Planned | Event consumer + read-only object access |

---

## Business Objects

Objects represent data and business rules. **Never contain UI logic.**

Canonical registry: [DOMAIN_MODEL.md](./DOMAIN_MODEL.md)

Examples: Workspace, Store, Customer, Product, Feedback, QR, Event, Order, Document.

Objects emit lifecycle events. Platforms consume them.

---

## Services

Services perform business operations and coordinate objects. **Independent from UI.**

| Pattern | Example |
|---------|---------|
| Python platform module | `customer_platform.py` — CRUD, batch, import |
| Python foundation service | `bos/services/workspace.py`, `bos/events.py` |
| JS API client | `static/bos/services/api.js` |
| JS workspace context | `static/bos/services/workspace-context.js` |

**Rule:** UI → Platform Service → Domain Objects → Infrastructure (SQLite, files).

Never access SQLite or raw fetch from presentational components.

---

## Components

Components render the interface. **Receive data, display data, emit actions.**

| Rule | Detail |
|------|--------|
| No business rules | Validation belongs in services / objects |
| Shared only | Use `static/bos/components/` — no platform-specific table clones |
| Drawer-first detail | `static/bos/platform/object-detail.js` |

---

## State Management

| Level | Scope | Examples | Location |
|-------|-------|----------|----------|
| **Global** | Entire OS | Workspace, user, theme, notifications | Session, `workspace-context.js`, `store.js` notifications |
| **Platform** | One module | Selected rows, filters, drawer | `selection.js`, `ui-state.js`, page modules |
| **Local** | One component | Form input, dialog open | Component closure / DOM |

State exists at the **lowest appropriate level**.

---

## Navigation Architecture

Owned by Application Shell. **Modules never implement independent navigation.**

```
Workspace → Platform → Object List → Object Detail (drawer)
```

Implementation: `shell-nav.js`, sidebar template, breadcrumbs via `nav.js` + `bos:object-opened`.

---

## API Architecture

```
UI (feature-page.js)
  ↓ fetch /api/*
Platform Service (customer_platform.py)
  ↓ emit events, domain rules
Domain Objects (domain.py)
  ↓
Infrastructure (SQLite, uploads/)
```

All business operations pass through service interfaces.

---

## Event Architecture

See [EVENT_BUS.md](./EVENT_BUS.md).

Actions emit domain events. Consumers: Activity, Notifications, Analytics, Automation (future), AI (future), Integrations (future).

**Modules never directly trigger unrelated modules.**

---

## Search Architecture

- **Global Search:** Command palette + `/api/workspaces/{id}/search` — centralized
- **Platform list filter:** Module-local search in filter bar
- Platforms register searchable types via domain model + object standards

---

## Permission Architecture

Action-based permissions defined in Foundation (`PERMISSION_ACTIONS`).

Platforms **consume** permissions via workspace roles (`owner`, `administrator`, `manager`, `staff`, `viewer`).

Platforms do **not** define new permission verbs without updating Foundation.

---

## File Architecture

One shared attachment model: `static/bos/platform/attachments.js`.

Objects reference files; objects do not manage storage paths directly.

Upload storage: `static/uploads/` via `app.py` `save_uploaded_image`.

---

## Notification Architecture

Notifications **subscribe to events** — never generated directly by business modules.

Implementation: `_subscriber_notifications` in `bos/events.py`, `static/bos/platform/notifications.js`.

---

## Plugin Architecture (Future)

Extension points (planned):

- Register pages, objects, commands, events, menu items, settings, integrations
- Plugins never modify Core directly
- Registry: `PLUGIN_HOOKS` in `bos/architecture.py`

---

## Coding Principles

- Single Responsibility
- Reusable Components
- Composition over Duplication
- Event-driven Communication
- Shared Object Standards
- Shared Design System
- Predictable Navigation

Avoid module-specific implementations when a shared solution exists.

---

## Scalability

Designed for:

- Multiple workspaces per user
- Large datasets (paginated APIs, lazy loading)
- Multiple business types (platform plugin pattern)
- Third-party integrations (extension layer)
- AI capabilities (event consumer)
- Marketplace plugins (registry without core changes)

No architectural redesign required as platforms grow — **add platforms, register objects, subscribe to events**.

---

## Non-Negotiable Rules

1. Foundation owns shared capabilities
2. Core owns application behavior
3. Platforms own business capabilities
4. Shared owns reusable code
5. Extensions remain optional
6. Business objects are the single source of truth
7. Components never contain business logic
8. Services never contain presentation logic
9. Platforms communicate through objects and events
10. Every new module must conform to this architecture

---

## Completion Checklist

| Criterion | Status |
|-----------|--------|
| Every layer has defined responsibility | ✅ Documented + code registry |
| Dependencies flow one direction | ✅ Enforced by layer map |
| Business logic separated from UI | ✅ Platform py modules + feature js pages |
| Shared functionality centralized | ✅ Foundation + Shared layers |
| Future platforms addable without restructure | ✅ Platform registry + plugin hooks |
| Maintainable, scalable architecture | ✅ In progress — mock platforms migrating to API |

---

## Related Documents

| Document | Layer |
|----------|-------|
| [DATA_ARCHITECTURE.md](./DATA_ARCHITECTURE.md) | Foundation — data principles |
| [PLATFORM_SPECIFICATION.md](./PLATFORM_SPECIFICATION.md) | Platform |
| [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) | Foundation |
| [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md) | Foundation |
| [EVENT_BUS.md](./EVENT_BUS.md) | Foundation |
| [APPLICATION_SHELL.md](./APPLICATION_SHELL.md) | Core |
