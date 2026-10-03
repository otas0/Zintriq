# Business App

Official Universal Builder template for the **business / operations** surface only.

This is not Zintriq the product. It is one composed application operators use
to run stores, QR, CRM, bookings, team and workflows.

## Separate from Customer App

Do **not** mix this with the Customer App template (`zintriq-customer`).
Install and publish them as independent projects that share workspace data
through Data Adapters — not as one combined “Business & Customer” silo.

| Template | Audience | Entry |
|---|---|---|
| Business App (`zintriq-business`) | Operators | `/app/store` |
| Customer App (`zintriq-customer`) | Shoppers / guests | `/` after publish |

## Route ownership

Published Business App may claim **`/app/store`** (and related `/app/*`,
`/manage/*`, `/business/*` surfaces) via the hybrid strangler.

Legacy Jinja / BOS fallback: **`/app/store?legacy=1`**.

## Primitives

Business App composition baseline: **Data + Interface + Logic + Connection + Publish**.
