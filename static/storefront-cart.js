/** Storefront cart — localStorage per store, checkout integration. */

const CART_KEY = "mq_store_cart";

function cartStorageKey(storeSlug) {
  return `${CART_KEY}:${storeSlug}`;
}

export function readCart(storeSlug) {
  try {
    const raw = localStorage.getItem(cartStorageKey(storeSlug));
    return raw ? JSON.parse(raw) : { items: [] };
  } catch {
    return { items: [] };
  }
}

export function writeCart(storeSlug, cart) {
  localStorage.setItem(cartStorageKey(storeSlug), JSON.stringify(cart));
}

export function cartCount(cart) {
  return (cart.items || []).reduce((n, line) => n + (line.qty || 0), 0);
}

export function addToCart(storeSlug, itemId, qty = 1) {
  const cart = readCart(storeSlug);
  const id = Number(itemId);
  const existing = cart.items.find((l) => l.item_id === id);
  if (existing) {
    existing.qty = (existing.qty || 0) + qty;
  } else {
    cart.items.push({ item_id: id, qty });
  }
  writeCart(storeSlug, cart);
  return cart;
}

export function updateCartQty(storeSlug, itemId, qty) {
  const cart = readCart(storeSlug);
  const id = Number(itemId);
  const line = cart.items.find((l) => l.item_id === id);
  if (!line) return cart;
  if (qty <= 0) {
    cart.items = cart.items.filter((l) => l.item_id !== id);
  } else {
    line.qty = qty;
  }
  writeCart(storeSlug, cart);
  return cart;
}

export function clearCart(storeSlug) {
  writeCart(storeSlug, { items: [] });
}

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || "";
}

export async function fetchQuote(storeSlug, items) {
  const res = await fetch(`/api/store/${encodeURIComponent(storeSlug)}/checkout/quote`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
    credentials: "same-origin",
    body: JSON.stringify({ items }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Could not quote cart");
  return data;
}

export async function startCheckout(storeSlug, payload) {
  const res = await fetch(`/api/store/${encodeURIComponent(storeSlug)}/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Checkout failed");
  return data;
}

function formatMoney(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

export function mountCartBar(root) {
  const slug = root.dataset.storeSlug;
  const enabled = root.dataset.checkoutEnabled === "1";
  if (!enabled || !slug) return;

  if (document.querySelector(".sf-cart-bar")) return;

  const bar = document.createElement("div");
  bar.className = "sf-cart-bar";
  bar.innerHTML = `
    <div class="sf-cart-bar__inner">
      <span class="sf-cart-bar__count" id="sf-cart-count">Cart empty</span>
      <a class="mq-btn mq-btn-primary mq-btn-sm" id="sf-cart-checkout" href="/store/${encodeURIComponent(slug)}/checkout">View cart</a>
    </div>`;
  document.body.appendChild(bar);

  const refresh = () => {
    const cart = readCart(slug);
    const count = cartCount(cart);
    const el = bar.querySelector("#sf-cart-count");
    const btn = bar.querySelector("#sf-cart-checkout");
    const badge = document.getElementById("sf-topbar-cart-badge");
    if (el) el.textContent = count === 0 ? "Cart empty" : (count === 1 ? "1 item" : `${count} items`);
    if (btn) btn.textContent = count > 0 ? "Checkout" : "View cart";
    if (badge) {
      if (count > 0) {
        badge.textContent = String(count);
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }
  };

  refresh();
  window.addEventListener("mq-cart-updated", refresh);
  return { refresh };
}

export function bindAddToCart(root) {
  const slug = root.dataset.storeSlug;
  const enabled = root.dataset.checkoutEnabled === "1";
  if (!enabled || !slug) return;

  root.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-add-cart]");
    if (!btn || !root.contains(btn)) return;
    e.preventDefault();
    e.stopPropagation();
    const itemId = btn.dataset.addCart;
    addToCart(slug, itemId, 1);
    window.dispatchEvent(new CustomEvent("mq-cart-updated"));
    btn.classList.add("sf-tile__add--done");
    setTimeout(() => btn.classList.remove("sf-tile__add--done"), 600);
  });
}

export { formatMoney, clearCart as clearStoreCart };
