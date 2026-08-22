# Zintriq — Object Standards

> **Status:** Mandatory for every implementation  
> **Scope:** Universal object behavior — not domain ownership (see [DOMAIN_MODEL.md](./DOMAIN_MODEL.md))  
> **Architecture:** [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) — layer blueprint  
> **Code mirrors:** `bos/object_standards.py`, `static/bos/platform/object-standards.js`

---

## Philosophy

Zintriq is **object-driven**.

- Every object follows the same **lifecycle**.
- Every object follows the same **interaction model**.
- Every object follows the same **design language**.

Modules introduce new **business capabilities**, not new interaction patterns.

**Consistency is more important than customization.**

---

## Universal Object Foundation

Every Business Object extends this foundation:

```
Business Object
├── Identity        → id, name, description, icon, coverImage
├── Metadata        → createdAt, updatedAt, createdBy, updatedBy
├── Ownership       → ownerType, ownerId (see Domain Model)
├── Relationships   → references to other objects (never duplicates)
├── Activity        → immutable chronological timeline
├── Notes           → internal rich-text annotations
├── Attachments     → shared file system
├── Tags            → shared tagging system
├── Permissions     → action-based access control
├── Status          → lifecycle state
└── Audit History   → who / what / when for important changes
```

Objects **extend** this foundation — they do not redefine it.

---

## Identity

| Field | Required | Notes |
|-------|----------|-------|
| `id` | Yes | Globally unique within type |
| `name` | Yes | User-editable display name |
| `description` | No | Rich text where appropriate |
| `icon` | No | Optional visual identifier |
| `coverImage` | No | Optional hero/thumbnail |

**Implementation:** BOS uses string IDs (`cus-1`); API-backed objects use integer PK + `customer_code` etc.

---

## Metadata

System-managed. Users cannot edit directly.

| Field | Required |
|-------|----------|
| `createdAt` | Yes |
| `updatedAt` | Yes |
| `createdBy` | Yes (when auth available) |
| `updatedBy` | Yes (when auth available) |

---

## Status

Every object supports lifecycle management.

### Minimum (all objects)

| Status | Purpose |
|--------|---------|
| `draft` | Not yet live |
| `active` | Normal operating state |
| `archived` | Soft removal — **preferred over delete** |

### Object-specific extensions

| Object | Additional statuses |
|--------|---------------------|
| Order | pending, paid, completed, cancelled |
| Feedback | new, read, replied, hidden, flagged |
| Event | published, completed |
| Customer | inactive, blocked |
| Employee | invited |

**Rule:** Archive is always available. Delete requires explicit intent and permission.

---

## Ownership & Relationships

See [DOMAIN_MODEL.md](./DOMAIN_MODEL.md).

- Exactly **one owner** per object.
- **References** — never embedded duplicates.
- Relationships must remain traceable.

---

## Tags

Every object supports tags via the shared tagging system.

| Capability | Required |
|------------|----------|
| Add tag | Yes |
| Remove tag | Yes |
| Edit tag (global tag entity) | Yes |
| Search by tag | Yes |
| Filter by tag | Yes |

**Implementation:** `static/bos/platform/tags.js`, `customer_tag_links`, `tagIds` on BOS collections

---

## Notes

Internal only — never visible to external customers.

| Capability | Required |
|------------|----------|
| Rich text body | Yes |
| Edit | Yes |
| Delete | Yes |
| Pin | Yes |
| Author | Yes |
| Timestamp | Yes |

**Implementation:** `static/bos/platform/notes.js`, `customer_notes` API

---

## Attachments

Shared attachment system across all objects.

| Type | Support |
|------|---------|
| Images | Yes |
| PDFs | Yes |
| Documents | Yes |
| Videos | Future |

Attachments belong to the object via `(entityType, entityId)`.

**Implementation:** `static/bos/platform/attachments.js`, `customer_files`

---

## Activity Timeline

Immutable chronological log. Auto-generated where possible.

| Event type | When |
|------------|------|
| created | Object created |
| updated | Field changed |
| renamed | Name changed |
| status_changed | Lifecycle transition |
| tagged | Tag added/removed |
| attached | File uploaded |
| noted | Note added |
| archived | Soft deleted |
| restored | Un-archived |
| deleted | Hard deleted |

**Implementation:** `customer_activities`, `feedback_activity`, BOS `store.js` activity log

---

## Audit History

Records important changes:

- **Who** — actor (user, system, customer)
- **What** — action + detail
- **When** — timestamp

Audit entries are **not editable**.

---

## Search

Minimum searchable fields for every object:

- Name
- ID / code
- Description
- Tags

Additional fields per object type are allowed but search **UX must stay consistent**.

**Implementation:** BOS command palette, module search inputs, `/api/*/q` query param

---

## Filters

Standard filters on every list:

| Filter | Required |
|--------|----------|
| Status | Yes |
| Tags | Yes |
| Created date | Yes |
| Updated date | Yes |

Object-specific filters (rating, store, group) extend — never replace — the standard set.

---

## Batch Operations

Every object list supports:

| Action | Required |
|--------|----------|
| Multi-select | Yes |
| Select all | Yes |
| Archive | Yes |
| Delete | Yes |
| Export | Yes |
| Add tags | Yes |
| Remove tags | Yes |

**Implementation:** `#bos-action-bar`, `renderActionBar()`, `selection` service

---

## Context Menu

Default actions (consistent order):

1. Open
2. Rename
3. Duplicate
4. Archive
5. Delete

Optional: Export, Share, Move, Assign

**Implementation:** `showContextMenu()` in `components/index.js`

---

## Detail Experience

Preferred workflow:

```
List → Drawer → Edit → Save
```

Use **Drawer** for simple management. Full page only for dedicated workspaces or complex flows.

### Standard drawer tabs

1. Overview
2. Properties
3. Related
4. Activity
5. Attachments
6. Notes

**Implementation:** `object-detail.js`, Customer Platform drawer, Feedback side panel

---

## Editing Principles

Prefer inline editing:

- Click to rename
- Inline status change
- Quick tags
- Quick notes

Minimize dialogs and page navigation.

### Navigation model

```
Select → View → Edit → Done
```

Avoid: Select → Page → Modal → Confirm → Return → Refresh

---

## Empty, Loading & Error States

### Empty states
- Explanation text
- Primary action (create/import)
- Optional secondary action

### Loading
- Skeleton rows
- Progressive / lazy load
- No layout shift

### Errors
- Retry
- Cancel
- Preserve in-progress edits

**Implementation:** `bos-empty`, `renderSkeletonRows()`, toast + undo

---

## Permissions

Action-based — not module-based.

| Action | Description |
|--------|-------------|
| view | Read object |
| create | Create new |
| edit | Update fields |
| archive | Soft lifecycle end |
| delete | Permanent removal |
| export | Download data |
| assign | Assign to user/task |

Roles compose grants. Modules check actions.

---

## Notifications

Objects **emit events** — they do not manage notification UI.

Examples: `customer.created`, `product.updated`, `feedback.submitted`, `event.published`

**Implementation:** `platform/notifications.js`, `createNotification()`

---

## API Philosophy

Every object exposes a consistent REST shape:

| Operation | Method | Pattern |
|-----------|--------|---------|
| Create | POST | `/api/{type}` |
| Read | GET | `/api/{type}/{id}` |
| Update | PATCH | `/api/{type}/{id}` |
| Archive | POST | `/api/{type}/{id}/archive` |
| Delete | DELETE | `/api/{type}/{id}` |
| Restore | POST | `/api/{type}/{id}/restore` |
| List | GET | `/api/{type}?status=&q=&tag=` |
| Search | GET | `/api/{type}?q=` |
| Export | GET | `/api/{type}/export` |
| Batch | POST | `/api/{type}/batch` |

Nested resources: `/api/{type}/{id}/notes`, `/api/{type}/{id}/attachments`, `/api/{type}/{id}/timeline`

Consistency beats object-specific endpoints.

---

## UI Consistency

Reuse Zintriq Design System components only:

| Component | Use |
|-----------|-----|
| Tables / Advanced table | Lists |
| Cards | Grid views |
| Drawer | Detail / edit |
| Timeline | Activity |
| Search + filter bar | Discovery |
| Context menu | Row actions |
| Bottom action bar | Batch selection |
| Empty / skeleton states | Zero & loading |
| Status badges | Lifecycle |
| Tags | Classification |

**No unique interaction patterns** without platform-level approval.

---

## Extensibility

Adding a new object requires defining only:

1. Business-specific **fields**
2. Business-specific **relationships**
3. Business-specific **workflows**

Everything else is **inherited** from this standard.

---

## Validation Checklist

Every new Business Object must pass before shipping:

- [ ] Uses universal object foundation
- [ ] Globally unique ID
- [ ] Lifecycle management (draft / active / archived minimum)
- [ ] Tags
- [ ] Notes
- [ ] Attachments
- [ ] Activity timeline
- [ ] Audit history
- [ ] Search
- [ ] Filters
- [ ] Batch operations
- [ ] Standard context menu
- [ ] Drawer detail (where appropriate)
- [ ] Shared components only
- [ ] Platform events emitted
- [ ] Standard permission model
- [ ] Global search integration
- [ ] Notification framework integration
- [ ] No duplicate domain objects

---

## Conformance Matrix (Current)

| Object | Foundation | Tags | Notes | Attach | Timeline | Drawer | Batch | API |
|--------|------------|------|-------|--------|----------|--------|-------|-----|
| Customer | Partial | Yes | Yes | Partial | Yes | Yes | Yes | Yes |
| Feedback | Partial | Yes | No | Yes | Yes | Partial | Partial | Yes |
| Product/Catalog | BOS mock | Yes | Yes | Yes | Yes | Yes | Yes | Planned |
| Workspace | Partial | Yes | No | No | Partial | Yes | Yes | Partial |
| Store | Partial | No | No | No | Partial | Page | No | Partial |
| Event | Partial | No | No | No | Partial | Page | Partial | Partial |
| Task/Operations | BOS mock | Yes | Yes | Yes | Yes | Yes | Yes | Planned |

**Target:** Every row fully green as platforms migrate from mock/localStorage to API-backed objects.

---

## Non-Negotiable Rules

1. Every business object follows the **same interaction model**.
2. Every business object **inherits the same core behaviors**.
3. Shared functionality must **never be reimplemented** per module.
4. **Archive** is the default lifecycle action — not Delete.
5. Relationships use **references** — never duplicated data.
6. Every future module must comply **before development begins**.
7. Update this document and both code registries when extending the standard.

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | Layer blueprint — Foundation, Core, Platforms, Shared, Extensions |
| [DATA_ARCHITECTURE.md](./DATA_ARCHITECTURE.md) | Data ownership, references, sync, derived data |
| [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) | What objects exist, who owns them, how they relate |
| `bos/domain.py` | Domain registry (Python) |
| `static/bos/platform/domain-model.js` | Domain registry (JS) |
| `bos/object_standards.py` | Object standard registry (Python) |
| `static/bos/platform/object-standards.js` | Object standard registry (JS) |
| `static/bos/platform/object-types.js` | UI property schema per collection |

---

## Completion Criteria

- [x] Universal foundation defined
- [x] Interaction model documented
- [x] API shape standardized
- [x] Validation checklist defined
- [x] Machine-readable registries exist
- [x] Conformance matrix tracks current vs. target
- [ ] All API-backed objects pass full checklist
- [ ] All modules use shared drawer / batch / context menu
- [ ] Unified timeline API across object types
