# Business OS — MVP Database Schema

Version 1.0 · QR Experience core

## Philosophy

Business OS MVP stores only what is needed for:

```
User → Workspace → QR Experience → Customer Interaction → Response
```

Authentication and payments are **external**. The database stores links and status, not secrets.

## Core Tables

| Spec name | SQLite table | Purpose |
|-----------|--------------|---------|
| UserProfile | `user_profiles` | Identity linked to external auth |
| Workspace | `workspaces` | Business account |
| WorkspaceMember | `workspace_members` | Team access |
| QRExperience | `qr_experiences` | Core product object |
| Response | `responses` | Customer submissions |
| Subscription | `workspace_subscriptions` | External billing status |

Implementation modules:

- `integrations/user_profile.py`
- `workspace_platform.py` / `team_platform.py`
- `qr_experience_platform.py`
- `bos/responses.py`
- `integrations/subscription.py`
- `bos/mvp_schema.py` — migrations and normalization

## UserProfile

```
user_profiles
  id
  user_id              → users (local session anchor)
  auth_provider
  auth_provider_id
  email
  full_name
  avatar_url
  created_at
  updated_at
```

Passwords stay in the auth provider only. Local `users.password_hash` remains for dev login but is not part of the MVP identity model.

## Workspace

```
workspaces
  id
  organization_id
  name
  slug
  description          (MVP migration)
  logo_url             (MVP migration)
  created_by           (MVP migration)
  status
  created_at
  updated_at
```

## WorkspaceMember

```
workspace_members
  id
  workspace_id
  user_id
  role
  status
  joined_at
```

MVP roles in product UI: **owner**, **admin**, **member**.

Legacy DB roles map via `normalize_mvp_role()`:

- `administrator` → admin
- `manager`, `viewer`, `staff` → member

## QRExperience

```
qr_experiences
  id
  workspace_id
  name
  type
  status
  content              (JSON — MVP migration from experience_config)
  public_url           (MVP migration; computed in API when empty)
  created_by
  created_at
  updated_at
```

MVP types: `information`, `feedback`, `survey` (legacy types map in API).

MVP statuses: `draft`, `active`, `disabled`, `archived` (`paused` → `disabled`).

## Response

```
responses
  id
  workspace_id         ← required for isolation
  experience_id
  type                 feedback | survey
  data                 JSON
  legacy_feedback_id   links to feedback_records during migration
  created_at
```

Example `data`:

```json
{ "rating": 5, "comment": "Great service", "customer_name": "Alex" }
```

API: `GET /api/responses`, `GET /api/responses/:id`

Writes: dual-write from `feedback_records` on customer submit; backfill on init.

## Subscription

```
workspace_subscriptions
  id
  workspace_id
  provider
  provider_customer_id
  provider_subscription_id
  plan
  status
  created_at
  updated_at
```

No card data or invoices.

## Security

Every business record includes `workspace_id`. Access flow:

1. Authenticate user
2. Resolve workspace membership
3. Check permission
4. Query with workspace scope

## Deferred (not MVP tables)

Do not build for MVP: CustomerCRM, Workflow, Automation, AnalyticsEvent, Plugin marketplace, PaymentTransaction, Invoice.

Legacy tables may exist for deferred features; they are hidden from MVP navigation via `MVP_FLAGS`.

## Verification

```bash
python3 scripts/verify_mvp_database_schema.py
python3 scripts/verify_integrations_architecture.py
python3 scripts/verify_qr_customer_data.py
```

## Checklist

- [x] External auth → UserProfile link
- [x] Workspace create / join
- [x] QR Experience CRUD
- [x] Customer submit → Response
- [x] Business view Responses
- [x] Subscription structure for future billing
- [x] Unified `responses` table with workspace isolation
