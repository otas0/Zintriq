# Deprecated: Business & Customer App (`zintriq-system`)

**Do not use for new work.** Customer and Business are separate official templates:

- [`../zintriq-customer`](../zintriq-customer) — Customer App (shoppers; `/` after publish)
- [`../zintriq-business`](../zintriq-business) — Business App (operators; `/app/store`)

Kept only for compatibility with existing workspace projects that still reference
`zintriq-system`. New installs should create **two** projects from the split
templates, not one mixed application.

## Route ownership (legacy note)

Historically this umbrella claimed `/` as customer `public_url` and `/app/store`
as business. Zintriq product root `/` is no longer the customer hub by default:
only a **published Customer App** may own `/`. Use `/?legacy=1` to force the
legacy Jinja customer surface for debugging.
