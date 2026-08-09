# Business OS — Data Architecture Specification

> **Status:** Platform-wide data principles (not database DDL)  
> **Code mirrors:** `bos/data_architecture.py`, `static/bos/platform/data-architecture.js`  
> **Object ownership:** [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) · [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md)  
> **Sync & history:** [EVENT_BUS.md](./EVENT_BUS.md) · [WORKFLOW_ENGINE.md](./WORKFLOW_ENGINE.md)  
> **Layers:** [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)

## Objective

Define how business data is created, stored, referenced, synchronized, searched, versioned, and consumed throughout Business OS.

This is a **platform-wide data architecture specification** — not a database schema. Every platform must comply.

---

## Philosophy

| Principle | Rule |
|-----------|------|
| Single source of truth | Every business object exists **once** |
| Reference, don't duplicate | Platforms reference objects; they never copy business data |
| One owner | Every piece of information has exactly one authoritative owner |
| Event propagation | Updates propagate through the Event Bus — not manual sync |

---

## Data Hierarchy

```
Workspace                          ← root of all business data
    │
    ├── Stores
    ├── Customers
    ├── Products / Services
    ├── Employees
    ├── Orders
    ├── Appointments
    ├── Feedback (+ Templates)
    ├── Documents
    ├── Tasks (workflow_tasks)
    └── Events (domain + scheduled)
```

**Workspace is always the root.** Operational objects belong to one workspace (directly via `workspace_id` or indirectly via Store).

Canonical object catalog: [DOMAIN_MODEL.md](./DOMAIN_MODEL.md).

---

## Single Source of Truth

Each business object has exactly **one authoritative record**.

| Object | Authoritative store | Referenced by |
|--------|---------------------|-------------|
| Customer | `customer_profiles` | Feedback, Orders, Events, QR check-in, Workflows |
| Store | `stores` | Items, Feedback, QR, Customers (store links) |
| Product | Catalog / items | Orders, Inventory, QR |
| Feedback | `feedback_records` | Customer timeline (via events), Analytics |
| Workspace | `workspaces` | All workspace-scoped objects |

**Anti-pattern:** Storing customer name/email on `feedback_records` when `customer_id` is set — use reference + denormalized display cache only at read time if needed for anonymous submissions.

**Current state:** Feedback keeps `customer_name` / `customer_email` for anonymous submissions; linked records use `customer_id` reference.

---

## References

Objects relate via **foreign keys and IDs** — never duplicated object payloads.

```
Order
  ├── customer_id  → Customer (one profile)
  ├── store_id     → Store
  └── line items   → Product references
```

When a Customer updates their name, all platforms read the same `customer_profiles` row — no per-platform copies to sync.

**Reference fields in implementation:**

| From | Field | To |
|------|-------|-----|
| `feedback_records` | `customer_id` | `customer_profiles.id` |
| `feedback_records` | `store_id` | `stores.id` |
| `customer_profiles` | `workspace_id` | `workspaces.id` |
| `stores` | `workspace_id` | `workspaces.id` |
| `event_attendees` | `customer_id` | `customer_profiles.id` |

---

## Immutable History

Business objects hold **current state** only.

Historical changes live in separate, append-only layers:

| Layer | Table / Store | Mutable? |
|-------|---------------|----------|
| Domain Events | `domain_events` | Append-only, immutable |
| Activity projections | `customer_activities`, `workspace_activity` | Written by event subscribers |
| Feedback audit | `feedback_activity` | Append-only per record |
| Workflow runs | `workflow_executions` | Read-only after completion |

**Rule:** Never mix historical audit rows into the primary object table.

---

## Versioning

Critical objects support version history (spec); implementation maturity varies:

| Object | Versioning approach | Status |
|--------|---------------------|--------|
| Feedback templates | Template row + publish snapshots | Partial |
| Documents | File revision (planned) | Planned |
| Product specs | Catalog version field (planned) | Planned |
| Domain events | Full change log via events | ✅ |

Older versions remain accessible for audit and rollback without overwriting current state.

---

## Derived Data

Analytics, dashboards, AI summaries, and search indexes are **derived** — never authoritative.

| Derived store | Source of truth | Rebuild strategy |
|---------------|-----------------|------------------|
| `event_analytics` | Domain events | Re-aggregate from `domain_events` |
| Feedback summary API | `feedback_records` | Recompute on read |
| Global search results | Business objects + API | Re-index from objects |
| BOS mock `store.js` | Local seed | **Not authoritative** — migrate to API |

**Rule:** If derived data is lost, it must be reproducible from primary objects and events.

---

## Search Index

Search indexes are **generated from business objects** and are **disposable**.

| Index | Implementation |
|-------|----------------|
| Workspace API search | `/api/workspaces/{id}/search` — queries live tables |
| Global command palette | `global-search.js` + workspace API |
| BOS local search | `store.js` globalSearch — mock only |

Indexes may lag; objects win on conflict. Full re-index = re-run queries against source tables.

---

## Caching

Caches improve performance; they **never own business data**.

| Cache | Scope | Invalidation |
|-------|-------|--------------|
| `workspace-context.js` `_cache` | Workspace list | Reload on switch / `loadWorkspaceList()` |
| `store.js` localStorage | Mock BOS modules | Session-only; not source of truth |
| Browser session | Active workspace id | Server session wins |

**Rule:** If cache and source disagree, **source wins**.

---

## Synchronization

Changes propagate through the **Event Bus** — platforms never sync directly.

```
Customer Updated
    ↓
emit(customer.updated)
    ↓
├── Search (re-index on next query)
├── Analytics (event_analytics subscriber)
├── Customer timeline (customer_activities projection)
├── Notifications (event_notifications subscriber)
└── Workflows (workflow_subscriber)
```

See [EVENT_BUS.md](./EVENT_BUS.md). No platform-to-platform direct writes.

---

## Soft Delete

**Archive is the default lifecycle action.**

| Behavior | Rule |
|----------|------|
| Archived objects | Remain in database, recoverable, auditable |
| Search | Include/exclude archived via filter (platform setting) |
| Hard delete | Restricted — owner-only, explicit confirmation |
| Workspace delete | Moves stores/customers to fallback workspace; hard delete workspace row only when ≥2 workspaces |

Lifecycle statuses: `active` → `archived` → (optional) `deleted`.

---

## Data Ownership

Every object belongs to **one Workspace**. Ownership never changes implicitly.

| Object | Owner field | Owner type |
|--------|-------------|------------|
| Customer | `workspace_id` / `owner_id`* | Workspace |
| Store | `workspace_id` | Workspace |
| Feedback | via `store.workspace_id` | Workspace (indirect) |
| Workspace | `organization_id` | Organization |

\* Migration note: `customer_profiles.owner_id` is being aligned to `workspace_id` as canonical scope.

Objects may **reference** many others; references do not transfer ownership.

---

## Data Integrity

The system must prevent:

| Rule | Enforcement |
|------|-------------|
| Duplicate IDs | Auto-increment / UUID primary keys |
| Orphaned references | FK where SQLite pragma enabled; application checks on delete |
| Circular ownership | Domain model: workspace → objects only (no object owns workspace) |
| Invalid relationships | `bos/domain.py` reference graph |

**Import integrity:** Customer CSV import uses `find_or_create_customer()` with email/phone dedupe.

---

## Import & Export

| Requirement | Implementation |
|-------------|----------------|
| Detect duplicates | `dedupe_by_email`, `dedupe_by_phone` in customer settings |
| Validate references | Import maps to existing stores/tags/groups |
| Preserve relationships | Tag links, group membership on create |
| Stable export IDs | Customer export includes `customer_code`, numeric `id` |

Exports are snapshots; imports create or update authoritative records — never shadow copies.

---

## Future Compatibility

Built on the same principles without changing object ownership:

| Capability | Approach |
|------------|----------|
| Offline sync | Event log replication; conflict = server wins on scalar fields |
| Multi-region | Workspace-scoped partitions; events as replication unit |
| AI indexing | Read-only consumer of `domain_events` + object APIs |
| Plugin extensions | Extension tables reference core object IDs |
| External APIs | Webhooks emit/consume domain events |
| Data warehouse | ETL from `domain_events` + nightly object snapshots |

---

## Non-Negotiable Rules

1. One object = one source of truth
2. Relationships use references — never duplicated records
3. Events propagate changes
4. Derived data is never authoritative
5. Archived data remains recoverable
6. Every platform follows the same ownership model

---

## Implementation Conformance Matrix

| Principle | Status | Notes |
|-----------|--------|-------|
| Workspace root ownership | ✅ | `workspace_id` on stores, customers |
| Reference-based relations | ✅ | `customer_id` on feedback, attendees |
| Event-driven sync | ✅ | Event bus + subscribers |
| Immutable event history | ✅ | `domain_events` append-only |
| Soft delete / archive | ✅ | Status fields, batch archive |
| Derived analytics | ✅ | `event_analytics` |
| Disposable search index | ✅ | Live query, no separate index DB |
| No platform data duplication | Partial | Anonymous feedback fields; mock BOS store |
| Version history | Partial | Templates; documents planned |
| Import dedupe | ✅ | Customer platform |

Registry: `bos/data_architecture.py` → `DATA_PRINCIPLES`, `CONFORMANCE`.

---

## Completion Criteria

| Criterion | Status |
|-----------|--------|
| Every object has clear owner | ✅ Documented + domain registry |
| Data duplication eliminated | Partial — mock modules migrating |
| Sync through events | ✅ |
| Search/analytics consume shared objects | ✅ |
| Future platforms extend without redefining ownership | ✅ |

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) | Object catalog and relationships |
| [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md) | Per-object behavior |
| [EVENT_BUS.md](./EVENT_BUS.md) | Change propagation |
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | Layer responsibilities |
