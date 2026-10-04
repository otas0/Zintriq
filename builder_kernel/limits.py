"""Kernel numeric limits.

Public list pagination and invoke body size are enforced on published routes.
Compose step/depth caps apply when a package registers a compose action.

Desktop anonymous-write rate limiting uses the in-process RateLimiter in
builder_kernel.rate_limit. Cloud deploys with more than one worker process
must replace get_rate_limiter() with a shared backend; per-process counters
are not enough.
"""

COMPOSE_MAX_DEPTH = 4
COMPOSE_MAX_STEPS = 16
PUBLIC_LIST_DEFAULT_LIMIT = 50
PUBLIC_LIST_MAX_LIMIT = 100
PUBLIC_INVOKE_MAX_BYTES = 64 * 1024
PUBLIC_INVOKE_MAX_FIELD_BYTES = 32 * 1024
KERNEL_EVENTS_MAX_PER_PROJECT = 1000
PUBLIC_INVOKE_MINUTE_LIMIT = 10
PUBLIC_INVOKE_MINUTE_WINDOW = 60
PUBLIC_INVOKE_HOUR_LIMIT = 100
PUBLIC_INVOKE_HOUR_WINDOW = 3600
HONEYPOT_FIELD = "website"
