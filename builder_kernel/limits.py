"""Kernel numeric limits.

Public list pagination and invoke body size are enforced when those routes
land. Compose step/depth caps apply when a package registers a compose
action. Desktop rate limiting is in-process; a cloud deploy with more than
one worker must replace that backend (see RateLimiter in a later step).
"""

COMPOSE_MAX_DEPTH = 4
COMPOSE_MAX_STEPS = 16
PUBLIC_LIST_DEFAULT_LIMIT = 50
PUBLIC_LIST_MAX_LIMIT = 100
PUBLIC_INVOKE_MAX_BYTES = 64 * 1024
PUBLIC_INVOKE_MAX_FIELD_BYTES = 32 * 1024
KERNEL_EVENTS_MAX_PER_PROJECT = 1000
