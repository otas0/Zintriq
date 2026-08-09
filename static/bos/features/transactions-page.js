/** Business OS — Transactions / orders (API-backed). */

import { statusBadge } from "../components/index.js";
import { showToast, openDrawer, closeDrawer } from "../services/api.js";
import { fetchJson, esc, wsQuery, money } from "../services/bos-api.js";
import { getActiveWorkspaceId } from "../services/workspace-context.js";

async function loadOrders() {
  return fetchJson(`/api/transactions${wsQuery()}`);
}

function orderRow(o) {
  return `<tr data-id="${o.id}"><td>${esc(o.reference)}</td><td>${esc(o.customer_name || "—")}</td>
    <td>${money(o.amount)}</td><td>${statusBadge(o.status)}</td><td>${esc((o.created_at || "").slice(0, 10))}</td></tr>`;
}

function createForm() {
  return `<form id="order-create" class="bos-form">
    <label class="bos-field"><span>Reference</span><input name="reference" placeholder="ORD-001"></label>
    <label class="bos-field"><span>Amount</span><input name="amount" type="number" step="0.01" min="0" required></label>
    <label class="bos-field"><span>Status</span><select name="status"><option value="pending">Pending</option><option value="completed">Completed</option></select></label>
    <label class="bos-field"><span>Notes</span><textarea name="notes" rows="2"></textarea></label>
    <button type="submit" class="bos-btn bos-btn-primary">Create order</button>
  </form>`;
}

export async function mountTransactionsPage(root) {
  const render = async () => {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Loading…</p></div>`;
    try {
      const orders = await loadOrders();
      root.innerHTML = `
        <div class="bos-panel-head" style="margin-bottom:12px"><button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="tx-create">New order</button></div>
        ${orders.length ? `<div class="bos-table-wrap"><table class="bos-table"><thead><tr><th>Reference</th><th>Customer</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead><tbody>${orders.map(orderRow).join("")}</tbody></table></div>`
          : `<div class="bos-empty"><p class="bos-empty__title">No orders yet</p><p>Create your first order to track sales in this workspace.</p></div>`}`;
      root.querySelector("#tx-create")?.addEventListener("click", () => {
        openDrawer("New order", createForm());
        document.getElementById("order-create")?.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(e.target);
          try {
            await fetchJson("/api/transactions", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                workspace_id: getActiveWorkspaceId(),
                reference: fd.get("reference"),
                amount: parseFloat(String(fd.get("amount"))),
                status: fd.get("status"),
                notes: fd.get("notes"),
              }),
            });
            closeDrawer();
            showToast("Order created");
            render();
          } catch (err) {
            showToast(err instanceof Error ? err.message : "Create failed");
          }
        });
      });
    } catch (err) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load orders</p></div>`;
    }
  };
  await render();
}
