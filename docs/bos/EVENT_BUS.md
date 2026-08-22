# Zintriq — Event Bus & Activity Architecture

> **Status:** Canonical event architecture  
> **Code:** `bos/events.py`, `event_platform.py`, `static/bos/platform/event-bus.js`

## Philosophy

Zintriq is **event-driven**. Objects perform actions → actions emit domain events → platforms subscribe and react. Modules never call each other directly.

## Event Flow

```
Business Object → Action → Domain Event → Event Bus → Subscribers → Platform Reactions
```

## Event Schema

Every event includes:

| Field | Description |
|-------|-------------|
| `event_id` | Unique immutable ID |
| `event_type` | e.g. `customer.created`, `feedback.submitted` |
| `object_type` | Domain object type |
| `object_id` | Object primary key |
| `workspace_id` | Operating container |
| `store_id` | Optional store scope |
| `user_id` | Acting user |
| `actor` | Actor label |
| `title` / `detail` | Human-readable summary |
| `metadata` | JSON payload |
| `href` | Deep link |
| `created_at` | Timestamp |

Events are **immutable** and **append-only** (`domain_events` table).

## Standard Events

Lifecycle verbs: `created`, `updated`, `archived`, `restored`, `deleted`, `assigned`, `published`, `completed`, `cancelled`, `submitted`, `replied`, `scanned`.

Combined with object type: `{object_type}.{verb}`

## Subscribers (Python)

| Platform | Handler | Behavior |
|----------|---------|----------|
| Notification Center | `_subscriber_notifications` | Creates `event_notifications` from rules |
| Analytics | `_subscriber_analytics` | Updates `event_analytics` counters |
| Customer Timeline | `_subscriber_customer_timeline` | Projects into `customer_activities` |
| Workspace Activity | `_subscriber_workspace_activity` | Projects into `workspace_activity` |

## API

| Route | Purpose |
|-------|---------|
| `GET /api/events` | Workspace activity feed |
| `GET /api/events/{type}/{id}/timeline` | Object timeline |
| `GET /api/notifications` | Server notifications |
| `GET /api/analytics/summary` | Event-derived metrics |

## Client Event Bus

`event-bus.js` provides `on()`, `emit()`, and `syncServerEvents()`. Store mutations dispatch `bos:domain-event`. Notifications subscribe — never triggered manually by modules.

## Integration Points

- `log_customer_activity()` → emits domain events
- `log_workspace_activity()` → emits domain events
- Feedback `log_activity()` → emits + keeps per-record audit
- Future automation, AI, webhooks subscribe to the same bus

## Related

- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)
- [WORKFLOW_ENGINE.md](./WORKFLOW_ENGINE.md)
- [APPLICATION_SHELL.md](./APPLICATION_SHELL.md)
- [OBJECT_STANDARDS.md](./OBJECT_STANDARDS.md)
- [DOMAIN_MODEL.md](./DOMAIN_MODEL.md)
