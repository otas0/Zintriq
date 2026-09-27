# Observability Guide

Operational reference for the observability system implemented in Phase 1.0.

## Overview

The observability system provides structured logging, request tracing, and error capture across the Flask monolith. All logs are JSON-formatted with PII redaction.

## Components

### 1. Structured Logging (Step 2.1)

**Location**: `observability/logging_config.py`

All logs use JSON format with automatic PII redaction:
- Tokens: first 8 chars only (e.g., `token_prefix=abc12345`)
- Emails: omitted or replaced with domain only
- Passwords/secrets: never logged

**Logger naming**: `app.<module>` (e.g., `app.checkout`, `app.payment`, `app.core`)

**Pattern A** (for except blocks):
```python
_log.debug("event_name", exc_info=True, extra={"op": "function_name"})
```

**Pattern B** (for warnings/errors):
```python
_log.warning("event_name", field1=value1, field2=value2)
```

### 2. Request Context (Step 2.2)

**Location**: `observability/context.py`

Every request gets a unique `request_id` (from X-Request-ID header or generated UUID).

Context is automatically attached to all logs within the request:
- `request_id`: unique per request
- `route`: request path
- `method`: HTTP method
- `user_id`: if authenticated

### 3. Error Capture (Step 2.3)

**Location**: `observability/error_handler.py`

Global 500 error handler logs uncaught exceptions with full context:
```python
_log.error("unhandled_exception", exc_info=True, extra={"op": route})
```

### 4. External Call Tracing (Step 2.6)

**Location**: `observability/trace.py`

#### trace() context manager

Wraps outbound HTTP calls with duration tracking:

```python
from observability.trace import trace

with trace("payment.stripe.create_session", provider="stripe", op="create_session"):
    resp = urllib.request.urlopen(req, timeout=15)
```

**Logs**:
- `trace_start` (DEBUG) when entering
- `trace_ok` (INFO) with `duration_ms` on success
- `trace_fail` (ERROR) with `duration_ms` and `exc_info` on failure

**Applied to**: 14 urllib.request.urlopen calls across 7 files

#### slow_query() context manager

Warns when DB queries exceed threshold (default 500ms):

```python
from observability.trace import slow_query

with slow_query("storefront_top_items"):
    rows = conn.execute("SELECT ...").fetchall()
```

**Logs**:
- `slow_query_warn` (WARNING) when duration >= threshold
- `slow_query_fail` (WARNING) with `exc_info` on failure

**Threshold**: Configurable via `SLOW_QUERY_MS` env var (default: 500)

**Applied to**: 2 strategic DB operations (storefront top_items, QR analytics backfill)

### 5. Access Logging (Step 2.7)

**Location**: `app.py` — `observability_access_log()` after_request hook

One line per request with:
- `method`: HTTP method
- `path`: request path
- `status`: HTTP status code
- `duration_ms`: request duration
- `request_id`: from context

**Skips**: `/static/*`, `/health`, `/healthz`, `/ready`

**Log levels by status**:
- 2xx → INFO
- 3xx → DEBUG
- 4xx → WARNING
- 5xx → ERROR

### 6. Frontend Error Capture (Step 2.8)

**Location**: `templates/base.html` (inline JS) + `app.py` `/api/client-errors` endpoint

Captures:
- `window.onerror` (syntax errors, runtime errors)
- `unhandledrejection` (Promise failures)

**Client-side rate limiting**:
- 5 seconds between sends
- Max 10 errors per minute

**Endpoint**: POST `/api/client-errors`
- Logs as WARNING with structured fields
- Always returns `{"ok": True}` to prevent retry loops
- No authentication required (rate-limited)

## Health Endpoints (Step 2.4)

- `GET /health` — basic health check (returns 200)
- `GET /healthz` — alias for /health
- `GET /ready` — readiness check (verifies DB connection)

## Configuration

### Environment Variables

- `SLOW_QUERY_MS`: Slow query threshold in milliseconds (default: 500)
- `LOG_LEVEL`: Global log level (default: INFO)

### Log Levels

- **DEBUG**: Detailed diagnostic info (trace_start, pattern A except blocks)
- **INFO**: Normal operations (trace_ok, access logs for 2xx)
- **WARNING**: Recoverable issues (slow queries, 4xx errors, client errors)
- **ERROR**: Failures (trace_fail, 5xx errors, unhandled exceptions)

## Log Aggregation

All logs are JSON-formatted and can be parsed by standard log aggregation tools:
- Each log entry has `level`, `message`, `timestamp`, and structured fields
- PII is automatically redacted by PIIFilter
- Request context (request_id, route, method) is attached to all logs within a request

## Monitoring Recommendations

1. **Error rate**: Monitor `level=ERROR` logs
2. **Slow queries**: Alert on `slow_query_warn` events
3. **External call failures**: Monitor `trace_fail` events
4. **Frontend errors**: Monitor `client_error` events
5. **Request duration**: Track `duration_ms` in access logs

## Files Modified

### Phase 1.0 Step 2

- `observability/logging_config.py` — JSON formatter, PII filter
- `observability/context.py` — request context management
- `observability/error_handler.py` — global 500 handler
- `observability/trace.py` — trace() and slow_query() context managers
- `app.py` — before_request/after_request hooks, /api/client-errors endpoint
- `templates/base.html` — inline error capture script
- 7 files with trace() wrapping (14 HTTP call sites)
- 2 files with slow_query() wrapping (2 DB operations)

## Zero Behavior Changes

All observability additions are logging-only. No business logic, error handling, or data flow has been modified. All exceptions are re-raised, never swallowed.
