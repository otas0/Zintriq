# Storefront UX Design — Owner Edit vs Customer View

Version: 1.0 · August 2026  
Reference: Uber Eats merchant storefront (Welcia-style layout)

This document defines **what store owners edit** in Business OS and **what customers see** when they scan a store QR — using Uber Eats as the layout and interaction reference, adapted for a QR-first Business OS (not a delivery marketplace).

---

## Product model

```
QR Scan
   ↓
Storefront (Shop)          ← Uber Eats “Shop” view
   ├── Store profile       ← sidebar identity card
   ├── Categories          ← numbered vertical nav
   ├── Deals               ← owner-set promotions carousel
   └── Product cards       ← catalog items

Optional: QR Experience landing page before shop
   ↓
Feedback / Survey / Info blocks
   ↓
“View shop” → Storefront
```

**One catalog source:** `items` + `item_groups` (existing).  
Product QR (`qr_products`) stays for spec sheets; priced menu lives in `items` only.

---

## Layout comparison

| Zone | Uber Eats (reference) | Business OS — Customer | Business OS — Owner preview |
|------|----------------------|------------------------|----------------------------|
| Top bar | Logo, location, **store search**, cart | Store name, search, contact CTA | Same + “Edit store” link |
| Left sidebar | Logo, name, ETA, fee, rating, address, Shop/Deals/List, category list | Logo, name, hours, address, contact, **Shop / Deals**, category list | Same + inline “Edit” on each block |
| Main area | Promo banner, Deals carousel, category rows | Deals carousel, all categories as scroll sections | Same with draft badges |
| Product card | Image, deal badge, + button, price, name, size | Image, deal badge, price, name, short desc | + status, SKU, stock, Edit |

### Target customer layout (wireframe)

```
┌─────────────────────────────────────────────────────────────┐
│  [Store name]          [ Search products…        ]  [Contact]│
├──────────────┬──────────────────────────────────────────────┤
│  (logo)      │  ┌─ Deals ──────────────────────────── ▶ ─┐  │
│  Store name  │  │ [20% off] [20% off] [20% off] …       │  │
│  4.9 ★ (350) │  └───────────────────────────────────────┘  │
│  Open · 9–6  │                                              │
│  Address     │  01. Beverages                    See all ▶ │
│              │  ┌────┐ ┌────┐ ┌────┐ ┌────┐               │
│  Shop        │  │img │ │img │ │img │ │img │  → scroll      │
│  Deals ●     │  │¥176│ │¥208│ │…   │ │    │               │
│              │  └────┘ └────┘ └────┘ └────┘               │
│  Categories  │                                              │
│  01 Beverages│  02. Food                        See all ▶ │
│  02 Food     │  …                                           │
│  03 Sweets   │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

**MVP scope:** No cart/checkout, no delivery ETA/fees, no ratings (placeholder optional).  
**Contact CTA** replaces “Add to cart” — customers tap product for detail, then contact/order offline (matches current `_store_contact.html`).

---

## Owner vs customer — by section

### 1. Store profile (sidebar identity card)

| Field | Owner edits | Customer sees | DB / route today |
|-------|-------------|---------------|------------------|
| Store name | ✅ Settings form | ✅ Large title | `stores.name` |
| Logo | ✅ Upload / URL | ✅ Circle avatar | **New:** `stores.logo_url` |
| Cover / banner | ✅ Upload / URL | ✅ Top banner strip | `stores.background_image` |
| Description | ✅ Settings | ✅ Subtitle under name | `stores.description` |
| Address | ✅ Settings | ✅ With map link optional | `stores.address` |
| Business hours | ✅ Settings | ✅ “Open · 9am–6pm” | `stores.business_hours` |
| Contact (phone/email/WhatsApp) | ✅ Settings | ✅ Contact button | `stores.contact` |
| Rating | ❌ Not editable (future) | ★ + count when available | **Future** |
| Delivery ETA / fee | ❌ N/A (not delivery app) | Hidden or “Visit us” | — |

**Owner surface:** Settings → **Store** (extend `templates/owner/store_settings.html`)  
**Preview:** `/store/<slug>?preview=1`

---

### 2. Navigation modes (Shop / Deals)

| Mode | Owner | Customer |
|------|-------|----------|
| **Shop** | Default catalog view; reorder categories | Full menu, all categories as scroll sections |
| **Deals** | Manage which items are on promotion | Filtered view: only discounted items, grouped by category |

Owner toggles deals on/off per item (see §4). “Shop your list” is **deferred** (saved lists need accounts).

---

### 3. Categories (`item_groups`)

| Action | Owner | Customer |
|--------|-------|----------|
| Create / rename category | ✅ Item Groups page | Sees numbered label + name |
| Reorder categories | ✅ Drag sort | Sidebar order + main scroll order |
| Assign item to category | ✅ Item edit | Item appears under that section |
| Hide empty category | Auto | Category hidden if no published items |

**Owner surface:** `/manage/<slug>/groups` (`item_groups.html`) — keep; add **number prefix** field (e.g. `08`) for Uber-style labels.

**Customer surface:** Left sidebar anchor links; main content = one **horizontal row per category** (Uber “See all” + arrows), not one category at a time via `?group=`.

**Schema addition (optional):**

```sql
ALTER TABLE item_groups ADD COLUMN prefix TEXT;  -- e.g. "08"
ALTER TABLE item_groups ADD COLUMN visible INTEGER DEFAULT 1;
```

---

### 4. Products (`items`)

| Field | Owner edits | Customer sees |
|-------|-------------|---------------|
| Name | ✅ | Card title |
| Image | ✅ | Card hero |
| Description | ✅ | Card subtitle + detail page |
| Price | ✅ | Bold price |
| Size / unit | ✅ **New** | “900 ml”, “10 ct” under name |
| Category | ✅ | Determines section |
| Status (draft/hidden/published) | ✅ | Only `published` shown |
| SKU, inventory, internal notes | ✅ Owner only | Hidden |
| Display order | ✅ Drag in manage | Row order within category |

**Owner surfaces:**
- List: `/manage/<slug>` — table/cards with drag reorder
- Edit: `/manage/<slug>/items/<id>/edit`
- Quick add: inline on manage page

**Customer surfaces:**
- Card in grid/row (`_product_card.html` — extend)
- Detail: `/store/<slug>/items/<id>`

**Card component (customer):**

```
┌─────────────────┐
│ [20% off]       │  ← deal badge (if active)
│                 │
│    [ product ]  │
│              [+]│  ← MVP: opens detail or contact, not cart
├─────────────────┤
│ ¥176  ~~¥220~~  │  ← sale + compare-at
│ Product name    │
│ 900 ml          │
└─────────────────┘
```

---

### 5. Deals (new — owner-set promotions)

**Owner capabilities:**

| Setting | Description |
|---------|-------------|
| Enable deal on item | Toggle per product |
| Discount type | `percent` (e.g. 20%) or `fixed` (e.g. ¥50 off) |
| Sale price | Computed or manual override |
| Compare-at price | Original price for strikethrough |
| Deal label | Default “20% off”; custom text optional |
| Schedule | Start / end date (optional MVP+) |
| Featured in Deals carousel | Pin to top of Deals row |

**Customer sees:**
- Red badge top-left on card (e.g. `20% off`)
- Sale price bold; original struck through
- **Deals** nav mode = carousel + filtered grid
- Deals section at top of Shop view (pink header band optional)

**Proposed schema:**

```sql
CREATE TABLE store_deals (
  id INTEGER PRIMARY KEY,
  store_id INTEGER NOT NULL,
  item_id INTEGER NOT NULL,
  discount_type TEXT NOT NULL DEFAULT 'percent',  -- percent | fixed
  discount_value REAL NOT NULL,                   -- 20 or 50
  label TEXT,                                     -- "20% off"
  starts_at TEXT,
  ends_at TEXT,
  featured INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',                   -- active | scheduled | expired
  created_at TEXT,
  UNIQUE(store_id, item_id)
);
```

**Owner surface (new):** `/manage/<slug>/deals`  
- Table: product, discount, dates, featured, on/off  
- Bulk: “Apply 20% to category”  
- Live preview panel (customer card mock)

**API:**
- `GET /api/stores/<slug>/deals` — active deals for storefront
- `POST/PATCH/DELETE /api/stores/<slug>/deals` — owner CRUD

---

### 6. Search (within store)

| | Owner | Customer |
|---|-------|----------|
| Store search | N/A | Top bar filters products by name/description |
| Global BOS search | Finds stores/QR | — |

**Implementation:** Client-side filter on loaded catalog (MVP); server `?q=` later.

---

### 7. Contact & ordering (replaces cart)

Uber Eats uses **+ → cart**. Business OS MVP uses **tap card → detail → Contact owner**.

| Uber Eats | Business OS MVP |
|-----------|-----------------|
| Add to cart | View product detail |
| Checkout | Contact (phone / email / WhatsApp / form) |
| Order tracking | Response via feedback QR or direct contact |

**Future:** `orders` table + simple “Request order” form (out of scope for this layout spec).

---

## Owner edit map (Business OS + legacy manage)

```
Business OS (/app)
├── QR Experiences     → landing before shop (optional)
├── Responses          → feedback from QR
└── Settings
    └── Store profile  → name, logo, banner, hours, contact

Store manage (/manage/<slug>)     ← primary catalog editor
├── Overview           → preview storefront, stats
├── Products           → items list, drag reorder, quick add
├── Categories         → item_groups, order, prefix
├── Deals              → NEW — promotions per item
└── Store settings     → profile fields (or link to BOS settings)
```

Owners should **preview customer view** from every edit screen (split pane or “Open customer view” tab).

---

## Customer view map (after QR scan)

```
/e/<slug>  or  /store/<slug>
│
├─ QR Experience (optional)
│    Header, info, feedback block
│    [ View shop ] button
│
└─ Storefront (/store/<slug>)
     Top: search + contact
     Sidebar: store card + Shop | Deals + categories
     Main:
       • Deals carousel (if any active)
       • Category sections (horizontal scroll rows)
       • Product cards
     Product detail: full image, price, deal, description, contact CTA
```

---

## Component reuse

| Component | Location | Notes |
|-----------|----------|-------|
| `StoreSidebar` | customer storefront | Logo, meta, nav, categories |
| `DealCarousel` | customer storefront | Horizontal scroll, pink header |
| `ProductCard` | `_product_card.html` | Extend: badge, compare-at, unit |
| `CategoryRow` | new partial | Heading + See all + scroll row |
| `StoreSearchBar` | customer top bar | Filter items |
| `DealEditor` | owner deals page | Item picker + discount form |
| `StorePreview` | owner manage | iframe `/store/<slug>?preview=1` |

Align styling with `static/bos/merchant.css` patterns (cards, grids) for owner tools; customer storefront keeps `marketing.css` / `system.css` but adopts Uber spacing and sidebar layout.

---

## Phased delivery

### Phase 1 — Layout refactor (no new tables)
- [ ] Two-column storefront template (sidebar + main)
- [ ] All categories on one scroll page with anchor nav
- [ ] Horizontal product rows per category
- [ ] Store search (client-side)
- [ ] Logo field on store settings

### Phase 2 — Deals
- [ ] `store_deals` table + API
- [ ] Owner deals page
- [ ] Deal badges + strikethrough pricing on cards
- [ ] Deals nav mode + carousel

### Phase 3 — Polish
- [ ] Owner live preview in manage
- [ ] Scheduled deals
- [ ] Connect QR Experience “View shop” block to storefront
- [ ] Optional: simple order request form

---

## What we are NOT building (MVP)

- Delivery fees, ETA, driver tracking
- Cart and payment checkout
- Customer accounts / “Shop your list”
- Multi-location franchise dashboard
- Plugin marketplace for storefront

---

## Acceptance criteria

**Owner**
- Can set store name, logo, banner, hours, address, contact
- Can create categories with order and optional number prefix
- Can add/edit products with image, price, unit, category
- Can enable a deal (e.g. 20% off) on any product and see it in preview
- Can open customer preview matching live storefront

**Customer**
- Sees Uber-style layout: sidebar store info, Shop/Deals, category list
- Sees deal badges and strikethrough pricing on discounted items
- Can search products within the store
- Can open product detail and contact the business
- All data from database — no mock products or fake deals
