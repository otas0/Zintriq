# Zintriq — Workflow Engine Specification

> **Status:** Canonical workflow model  
> **Code:** `bos/workflows.py`, `workflow_platform.py`, `static/bos/platform/workflow-engine.js`  
> **Integrates with:** [EVENT_BUS.md](./EVENT_BUS.md) · [PLATFORM_SPECIFICATION.md](./PLATFORM_SPECIFICATION.md) · [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)

## Objective

Define a universal workflow model. Zintriq manages how work flows across objects — not as isolated platform features.

Every business process is a **workflow**: trigger → conditions → actions → completion.

The Workflow Engine is the execution layer for Automation, AI Copilot, Notifications, Tasks, and integrations.

---

## Philosophy

| Layer | Role |
|-------|------|
| **Objects** | Store business information |
| **Platforms** | Provide business capabilities |
| **Workflows** | Connect capabilities into operational processes |

One engine supports every business type: restaurants, clinics, retail, logistics, professional services.

**Platforms never hard-code automation** — they emit events; workflows react.

---

## Workflow Structure

```
Trigger → Conditions → Actions → Completion
```

| Part | Purpose |
|------|---------|
| **Trigger** | What starts the workflow |
| **Conditions** | Whether execution continues |
| **Actions** | Work performed on business objects |
| **Completion** | Recorded in execution history |

---

## Triggers

| Type | Source | Status |
|------|--------|--------|
| `event` | Domain event from Event Bus | ✅ Implemented |
| `manual` | User via API / UI | ✅ Implemented |
| `scheduled` | Cron / time-based | Planned |
| `api` | External webhook | Planned |

Event triggers match `trigger_config.event_type` (e.g. `feedback.submitted`, `customer.joined`).

---

## Conditions

JSON rule list (implicit AND). Operators: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `contains`, `exists`.

Examples:

```json
[
  {"field": "metadata.rating", "op": "lt", "value": 3},
  {"field": "event_type", "op": "eq", "value": "feedback.submitted"}
]
```

Context fields use dot paths: `metadata.rating`, `object_type`, `store_id`, `workspace_id`.

---

## Actions

| Action | Status | Description |
|--------|--------|-------------|
| `send_notification` | ✅ | Creates notification via event_notifications |
| `create_task` | ✅ | Creates workflow_tasks record |
| `add_tag` | ✅ | Tags customer when customer_id in context |
| `update_status` | ✅ | Updates customer/feedback status |
| `assign_employee` | Stub | Future |
| `move_object` | Stub | Future |
| `generate_document` | Stub | Future |
| `send_email` | Future | Extension layer |
| `call_api` | Future | Extension layer |

Actions operate on existing Business Objects — never duplicate domain data.

---

## Workflow Lifecycle

```
Draft → Active → Paused → Archived
```

Executions are separate: `running → completed | failed | cancelled`

---

## Manual Workflows

Start via `POST /api/workflows/{id}/start`:

```json
{
  "object_type": "customer",
  "object_id": 42,
  "metadata": {}
}
```

Example: Customer onboarding checklist.

---

## Automatic Workflows

Event Bus subscriber `workflow_subscriber` matches active workflows when domain events emit.

Example (seeded template):

```
feedback.submitted → rating < 3 → notify team + create follow-up task
```

---

## Workflow History

Table `workflow_executions` — read-only audit:

- Start / end time
- Trigger type + event id
- Actions executed (JSON)
- Result / errors

---

## Workflow Templates

Seeded per workspace on creation:

| Template | Trigger | Actions |
|----------|---------|---------|
| Negative feedback follow-up | `feedback.submitted` + rating < 3 | Notify + task |
| New customer welcome | `customer.joined` | Notify |
| Customer onboarding | Manual | Profile + welcome tasks |

Templates are editable; completed runs are immutable.

---

## API

| Route | Purpose |
|-------|---------|
| `GET /api/workflows` | List workspace workflows |
| `GET /api/workflows/templates` | List templates |
| `POST /api/workflows` | Create workflow |
| `PATCH /api/workflows/{id}` | Update definition |
| `POST /api/workflows/{id}/start` | Manual start |
| `POST /api/workflows/{id}/activate` | Set active |
| `POST /api/workflows/{id}/pause` | Pause |
| `POST /api/workflows/{id}/archive` | Archive |
| `GET /api/workflows/executions` | Execution history |
| `GET /api/workflows/tasks` | Open workflow tasks |

---

## Integration

```
Domain Event → Event Bus → workflow_subscriber → execute_workflow → Actions
                                                                    ├── Notifications
                                                                    ├── Tasks
                                                                    └── Object updates
```

Engine does **not** depend on any single business module.

---

## Design Principles

- Workflows are reusable and event-driven
- Platform-independent configuration
- Business logic configured in workflows, not embedded in modules
- Every execution observable through history
- Extensible for AI and external integrations

---

## Completion Criteria

| Criterion | Status |
|-----------|--------|
| Trigger, conditions, actions, lifecycle | ✅ |
| Cross-platform via Event Bus | ✅ |
| Execution history recorded | ✅ |
| Manual + automatic workflows | ✅ |
| Templates seeded per workspace | ✅ |
| Automation UI / builder | Planned |
| Scheduled + API triggers | Planned |

---

## Related

- [EVENT_BUS.md](./EVENT_BUS.md)
- [PLATFORM_SPECIFICATION.md](./PLATFORM_SPECIFICATION.md)
- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)
