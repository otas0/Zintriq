# Business OS — Domain Model & Relationship Specification

> **Status:** Canonical source of truth  
> **Scope:** Business domain only — not UI, not features, not database DDL  
> **Code mirrors:** `bos/domain.py`, `static/bos/platform/domain-model.js`  
> **Companion:** [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md) — universal object behavior  
> **Architecture:** [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) — layer blueprint  
> **Data:** [DATA_ARCHITECTURE.md](./DATA_ARCHITECTURE.md) — ownership, references, sync

---

## Philosophy

Business OS is built around a small number of **reusable business objects**.

- Features do not own data.
- Platforms do not own data.
- **Business objects own data.**
- Platforms **operate on** business objects.

This ensures consistency, scalability, and long-term maintainability.

---

## Domain Hierarchy

```
Business OS
└── Workspace                          ← root container for all operational data
    ├── Store                          ← physical / logical location
    ├── Customer                       ← one business relationship
    ├── Product                        ← sellable / trackable item
    ├── Service                        ← non-physical offering
    ├── Employee                       ← internal user within workspace
    ├── QR                             ← access gateway (never owns data)
    ├── FeedbackTemplate               ← reusable feedback experience
    ├── Feedback                       ← customer response record
    ├── Event                          ← scheduled activity
    ├── Appointment                    ← scheduled customer interaction
    ├── Order                          ← commercial transaction
    ├── Membership                     ← customer program enrollment
    ├── Inventory                      ← stock level (references Product)
    ├── Document                       ← uploaded file
    ├── Notification                   ← system event (references only)
    ├── Task                           ← actionable work item
    ├── Automation                     ← workflow rule (future)
    ├── Analytics                      ← read-only views (never owns data)
    └── Settings                       ← workspace configuration
```

**Workspace is the root container.** Every operational object belongs to exactly one Workspace (directly or via Store).

---

## Root Objects

Only these objects exist outside a Workspace:

| Object | Responsibility | Status |
|--------|----------------|--------|
| **User** | Authentication identity, account holder | Implemented |
| **Organization** | Legal / billing grouping above workspaces | Partial |
| **Workspace** | Business operating environment | Implemented |

Everything else exists **inside** a Workspace.

---

## Object Catalog

### Workspace

Represents a business operating environment (company, clinic, restaurant chain, department).

| Attribute | Value |
|-----------|-------|
| **Owner** | Organization (via `organizationId`) |
| **References** | Organization |
| **Lifecycle** | active → archived → suspended |
| **Platform** | Workspaces |
| **Shared behaviors** | Activity, Settings, Archive |

Deleting a Workspace must **never immediately delete** child data. Archive first; hard delete is explicit.

---

### Store

A physical or logical operating location within a Workspace.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Workspace |
| **Lifecycle** | draft → active → archived |
| **Platform** | QR Workspace (Store Management) |
| **Shared behaviors** | Activity, Settings, Archive |

A Store cannot exist without a Workspace.

**Implementation:** `stores` table, `stores.workspace_id`

---

### Customer

One unified business relationship. Never duplicated within a Workspace.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Workspace, Store (many via store links) |
| **Owns** | Timeline, Notes, Tags, Files, Activities |
| **Lifecycle** | active → inactive → blocked → archived |
| **Platform** | Customer Platform |
| **Shared behaviors** | Timeline, Notes, Tags, Files, Search, Archive, Export |

Every module **references** Customer — never embeds duplicate identity.

**Implementation:** `customer_profiles` (migration: `owner_id` → `workspace_id` planned)

---

### Product

Sellable or trackable item. Defined once, referenced everywhere.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Workspace |
| **Lifecycle** | draft → active → archived |
| **Platform** | Catalog |
| **Shared behaviors** | Tags, Notes, Attachments, Search, Archive |

May appear in: Orders, Inventory, QR, Feedback, Analytics.

**Implementation:** BOS `catalog` collection; QR `qr_products`, `items`

---

### Service

Non-physical offering.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Workspace |
| **Lifecycle** | draft → active → archived |
| **Platform** | Catalog (future split) |
| **Shared behaviors** | Tags, Search, Archive |

May appear in: Appointments, Bookings, QR, Feedback.

**Status:** Planned (partial via catalog `type`)

---

### Employee

Internal user scoped to a Workspace.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Workspace, User (optional link) |
| **Lifecycle** | invited → active → inactive → archived |
| **Platform** | Team |
| **Shared behaviors** | Roles, Permissions, Notes, Tasks |

**Implementation:** BOS `team` collection

---

### QR

Access gateway. **Never owns business data.**

| Attribute | Value |
|-----------|-------|
| **Owner** | Store (`storeId`) |
| **References** | Store, Target object (polymorphic) |
| **Target types** | Product, FeedbackTemplate, Event, CheckInPoint, BusinessCard, Storefront |
| **Lifecycle** | draft → active → archived |
| **Platform** | QR Platform |
| **Shared behaviors** | Publish, Scan count, Archive |

```
QR → Product
QR → FeedbackTemplate
QR → Event
QR → Check-in
QR → Business Card
QR → Storefront
```

**Implementation:** `qr_codes`, `feedback_publications`, entity codes on domain tables

---

### FeedbackTemplate

Reusable feedback experience definition.

| Attribute | Value |
|-----------|-------|
| **Owner** | Store (`storeId`) |
| **References** | Workspace (via Store), Store |
| **Lifecycle** | draft → published → archived |
| **Platform** | Feedback Platform |
| **Shared behaviors** | Versioning (future), Duplicate, Archive |

Examples: Review, Survey, Complaint, Suggestion, Custom.

**Implementation:** `feedback_templates`

---

### Feedback

Customer response record. References — never owns — Customer.

| Attribute | Value |
|-----------|-------|
| **Owner** | Store (`storeId`) |
| **References** | Workspace (via Store), Store, FeedbackTemplate, Customer (optional), QR/Publication |
| **Lifecycle** | new → read → replied → archived / hidden / flagged |
| **Platform** | Feedback Platform |
| **Shared behaviors** | Timeline, Reply, Tags, Search, Archive, Export |

**Implementation:** `feedback_records`, `customer_id` reference

---

### Event

Scheduled business activity.

| Attribute | Value |
|-----------|-------|
| **Owner** | Store (`storeId`) |
| **References** | Workspace (via Store), Store, Customer (attendees), Employee, QR |
| **Lifecycle** | draft → published → completed → archived |
| **Platform** | QR Platform (Event Passes) |
| **Shared behaviors** | Activity, Archive, Export |

**Implementation:** `events`, `event_attendees`

---

### Appointment

Scheduled customer interaction.

| Attribute | Value |
|-----------|-------|
| **Owner** | Store (`storeId`) |
| **References** | Customer, Employee, Service, Store, Workspace |
| **Lifecycle** | scheduled → confirmed → completed → cancelled → archived |
| **Platform** | Booking (planned) |
| **Shared behaviors** | Timeline, Notes, Reminders |

**Status:** Planned

---

### Order

Commercial transaction connecting customer to products/services.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Customer, Product(s), Service(s), Store, Employee |
| **Lifecycle** | pending → completed → refunded → archived |
| **Platform** | Transactions (planned → Orders) |
| **Shared behaviors** | Timeline, Notes, Export |

Orders never duplicate product rows — reference Product IDs only.

**Implementation:** BOS `transactions` (partial)

---

### Membership

Customer program enrollment.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Customer, Workspace |
| **Lifecycle** | active → expiring → expired → cancelled → archived |
| **Platform** | Membership (planned) |
| **Shared behaviors** | Timeline, Notifications |

**Status:** Planned

---

### Inventory

Stock level for a Product at a Store.

| Attribute | Value |
|-----------|-------|
| **Owner** | Store (`storeId`) |
| **References** | Product, Store, Workspace |
| **Lifecycle** | active → low → out → archived |
| **Platform** | Inventory (planned) |
| **Shared behaviors** | Alerts, History |

Inventory references Product — never owns product definition.

**Status:** Planned

---

### Document

Uploaded business file.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Workspace; optional: Customer, Employee, Product, Order, Event |
| **Lifecycle** | active → archived |
| **Platform** | Documents |
| **Shared behaviors** | Attachments, Search, Archive |

**Implementation:** BOS `documents`; `customer_files` for customer-scoped files

---

### Notification

System event. References objects — **never contains business payload**.

| Attribute | Value |
|-----------|-------|
| **Owner** | User (`userId`) |
| **References** | Any business object (polymorphic) |
| **Lifecycle** | unread → read → dismissed |
| **Platform** | Notifications |
| **Shared behaviors** | Read, Dismiss |

**Implementation:** BOS client `notifications.js`

---

### Task

Actionable work item.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Any business object (polymorphic assignee + subject) |
| **Lifecycle** | open → in_progress → done → archived |
| **Platform** | Operations |
| **Shared behaviors** | Assign, Timeline, Notes, Archive |

Examples: Customer follow-up → Customer; Review response → Feedback.

**Implementation:** BOS `operations`

---

### Automation

Workflow rule (future).

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace (`workspaceId`) |
| **References** | Trigger object, Action targets |
| **Lifecycle** | draft → active → paused → archived |
| **Platform** | Automation Engine (planned) |

**Status:** Planned

---

### Analytics

Read-only aggregation. **Never owns data.**

| Attribute | Value |
|-----------|-------|
| **Owner** | None (derived) |
| **References** | All queryable business objects |
| **Platform** | Analytics views per module |
| **Shared behaviors** | Export (read-only) |

**Implementation:** Feedback analytics, Customer insights, BOS dashboards

---

### Settings

Workspace or module configuration.

| Attribute | Value |
|-----------|-------|
| **Owner** | Workspace or Store (scoped) |
| **References** | Workspace, Store |
| **Platform** | Per-platform Settings sections |
| **Shared behaviors** | Read, Update |

**Implementation:** `feedback_settings`, `customer_settings`, store settings

---

## Relationship Graph

```
Organization
    └── Workspace
            ├── Store ──────────────────────┐
            ├── Customer ←──────────────────┼── Feedback, Order, Event, Appointment, Membership
            ├── Product ←── Inventory, Order, QR
            ├── Service ←── Appointment, Order
            ├── Employee ←── Task, Appointment
            ├── FeedbackTemplate ←── QR, Feedback
            ├── Feedback ←── Task, Customer (ref)
            ├── Event ←── QR, Customer (ref)
            ├── Order
            ├── Document
            ├── Task → (any object)
            └── Settings

QR (Store-owned gateway) → Product | FeedbackTemplate | Event | CheckIn | BusinessCard | Storefront
Analytics → reads all (no ownership)
Notification → references all (no ownership)
```

**Rule:** Every edge is a **reference**. No duplicated ownership.

---

## Ownership Rules

| Rule | Description |
|------|-------------|
| **One owner** | Each object has exactly one owning object |
| **Many references** | Objects may reference many other objects |
| **No confusion** | `ownerId` ≠ `referenceId` — ownership fields are never reused as references |
| **Cascade policy** | Archive cascades softly; delete requires explicit intent |
| **Workspace boundary** | Cross-workspace references are forbidden unless explicitly designed (future org-level) |

### Example: Order

```
Owner:     Workspace
References: Customer, Product[], Service[], Store, Employee
```

---

## Object Lifecycle (Universal)

Every business object follows:

```
Created → Active → Updated → Archived → Restored → Deleted
```

| Transition | Default? | Notes |
|------------|----------|-------|
| Archive | **Yes** — preferred soft removal | Reversible |
| Delete | Explicit only | Permanent; requires permission |
| Restore | From archived | Returns to active |

---

## Shared Behaviors

Every business object **should** support (where applicable):

| Behavior | Description |
|----------|-------------|
| Activity Timeline | Chronological audit of changes and events |
| Notes | Internal annotations |
| Attachments | Files linked to the object |
| Tags | Flexible classification |
| Search | Indexed by name, ID, tags, status |
| Filters | Consistent filter vocabulary |
| Archive | Soft lifecycle end |
| Restore | Undo archive |
| Permissions | Action-based access control |
| Audit History | Who changed what, when |

Platforms implement behaviors consistently — not per-feature one-offs.

---

## Platform → Object Mapping

Platforms operate on objects. They do not own them.

| Platform | Operates On | Owns Data? |
|----------|-------------|------------|
| QR Platform | QR, Store, Product QR, Event, Check-in, Business Card | QR metadata only |
| Feedback Platform | FeedbackTemplate, Feedback, Publication | Yes (feedback domain) |
| Customer Platform | Customer, Groups, Tags, Notes, Activities | Yes (customer domain) |
| Catalog | Product, Service | Yes |
| Team | Employee | Yes |
| Documents | Document | Yes |
| Operations | Task | Yes |
| Notifications | Notification | Yes (event refs only) |
| Analytics | All (read) | **No** |
| Business OS Shell | Navigation, Search, Permissions | **No** |

---

## Global Search

Every business object type must be searchable by:

- Name / title
- ID / code
- Tags
- Status
- Related object names

Search behavior and result shape remain consistent across modules.

**Implementation:** BOS command palette, per-module search, `/api/*/q` pattern

---

## Global Activity

Every object contributes to one queryable activity stream:

```
Customer Created · Product Updated · Feedback Submitted · QR Published · Event Completed
```

Activity records store: `objectType`, `objectId`, `action`, `actor`, `timestamp`, `workspaceId`.

**Implementation:** `customer_activities`, `feedback_activity`; unified feed planned

---

## Permissions Model

Permissions apply to **actions**, not modules:

| Action | Applies To |
|--------|------------|
| create | All mutable objects |
| read | All objects |
| update | All mutable objects |
| archive | All objects with lifecycle |
| delete | All objects (restricted) |
| export | Customer, Feedback, Orders, Analytics |
| assign | Task, Customer |
| reply | Feedback |
| publish | QR, FeedbackTemplate, Event |

Roles compose action grants. Modules check actions — not bespoke flags.

**Status:** Partial (owner-scoped today; role matrix planned)

---

## Non-Negotiable Rules

1. **One object = one responsibility.**
2. **Every object has one owner.**
3. **Relationships use references — never duplicated data.**
4. **Platforms operate on objects; they do not own business domain data** (except their own config/metadata).
5. **Shared behaviors stay consistent across all objects.**
6. **Every new module must comply with this spec before implementation.**
7. **No new domain object may be introduced without updating this document and the code registries.**

---

## Implementation Registry

When adding a module, update **all registries**:

1. `docs/bos/DOMAIN_MODEL.md` — what the object is
2. `docs/bos/OBJECT_STANDARDS.md` — how it behaves
3. `bos/domain.py` + `static/bos/platform/domain-model.js`
4. `bos/object_standards.py` + `static/bos/platform/object-standards.js`

### Current implementation map

| Domain Type | Code / Table | Platform | Maturity |
|-------------|--------------|----------|----------|
| User | `users` | Auth | Implemented |
| Organization | `organizations` | Organization | Partial |
| Workspace | `workspaces` | Workspaces | Implemented |
| Store | `stores` | QR Workspace | Implemented |
| Customer | `customer_profiles` | Customer Platform | Implemented |
| Product | `items`, `catalog`, `qr_products` | Catalog / QR | Partial |
| Service | — | — | Planned |
| Employee | `team` (BOS) | Team | Partial |
| QR | `qr_codes`, publications | QR Platform | Implemented |
| FeedbackTemplate | `feedback_templates` | Feedback | Implemented |
| Feedback | `feedback_records` | Feedback | Implemented |
| Event | `events`, `event_attendees` | QR Event Passes | Implemented |
| Appointment | — | — | Planned |
| Order | `transactions` (BOS) | Transactions | Planned |
| Membership | — | — | Planned |
| Inventory | — | — | Planned |
| Document | `documents`, `customer_files` | Documents | Partial |
| Notification | BOS notifications | Notifications | Partial |
| Task | `operations` (BOS) | Operations | Partial |
| Automation | — | — | Planned |
| Analytics | per-module views | Analytics | Partial |
| Settings | per-module tables | Settings | Partial |

---

## Future Compatibility

These platforms must **consume existing objects** — not create parallel models:

- AI Copilot
- Automation Engine
- Workflow Builder
- Reports
- Loyalty
- Marketing
- Finance
- Integrations
- Marketplace
- Plugins

---

## Completion Criteria

This specification is complete when:

- [x] Every business object has a clearly defined responsibility
- [x] Ownership and relationships are unambiguous
- [x] Platforms share the same object model
- [x] Machine-readable registries exist in Python and JavaScript
- [x] Implementation map tracks maturity vs. target domain
- [ ] All persisted objects use Workspace as ownership root (migration in progress)
- [ ] Unified global activity feed spans all object types
- [ ] Action-based permissions enforced across modules
