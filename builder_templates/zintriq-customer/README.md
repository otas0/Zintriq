# Customer App

Official Universal Builder template for the **customer-facing** surface only.

This is not Zintriq the product. Zintriq is the five-primitive system
(Data, Interface, Logic, Connection, Publish). The Customer App is one
composed output you install, edit and publish.

## Separate from Business App

Do **not** mix this with the Business App template (`zintriq-business`).
Customer Interface routes and Business Interface routes are different projects.

| Template | Audience | Entry |
|---|---|---|
| Customer App (`zintriq-customer`) | Shoppers / guests | `/` after publish |
| Business App (`zintriq-business`) | Operators | `/app/store` |

## Route ownership

Published Customer App may claim **`/`** (and alias `/home`) via the hybrid
strangler. Until a published revision owns `/`, Zintriq product root redirects
to Builder / login — it does **not** show the customer hub by default.

Force the legacy Jinja customer hub with **`/?legacy=1`** (debug / preview only).

Other customer routes stay available as template Connection/Interface surfaces:

- `/places`, `/venues`, `/store/*`, `/account`, `/help/*`, `/qr/*`, `/e/*`

## Primitives

Customer App composition baseline: **Data + Interface + Connection + Publish**
(and Logic where booking / feedback / check-in rules apply).
