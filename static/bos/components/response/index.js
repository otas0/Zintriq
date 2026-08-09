/** Response domain components. */

import { esc } from "../ui/_utils.js";
import { StatusBadge } from "../ui/Badge.js";
import { EmptyState } from "../ui/EmptyState.js";
import { Button } from "../ui/Button.js";
import { mountCardGrid } from "../ui/Card.js";
import { mountFilterBar } from "../layout/FilterBar.js";
import { SearchBar, bindSearchBar } from "../layout/SearchBar.js";

function fmtRelative(value) {
  if (!value) return "";
  const raw = String(value);
  const d = new Date(raw.includes("T") ? raw : raw.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return raw.slice(0, 16).replace("T", " ");
  const diff = Date.now() - d.getTime();
  if (diff < 3600000) return `${Math.max(1, Math.floor(diff / 60000))} minutes ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} hours ago`;
  return raw.slice(0, 10);
}

export function ResponseCard(record) {
  const type = (record.type || "").includes("survey") ? "Survey" : "Feedback";
  const rating = record.rating ? "★".repeat(Math.min(5, Number(record.rating))) : "";
  const comment = (record.content || record.comment || "").slice(0, 120);
  const when = fmtRelative(record.created_at);

  return `<article class="merchant-response-card bos-ui-response-card" data-id="${record.id}">
    <div class="merchant-response-card__head">
      <span class="merchant-response-card__type">${esc(type)}</span>
      ${rating ? `<span class="merchant-response-card__rating" aria-label="${record.rating} stars">${rating}</span>` : ""}
    </div>
    <p class="merchant-response-card__comment">${esc(comment || "—")}</p>
    <div class="merchant-response-card__meta">
      <span>Source: ${esc(record.experience_name || "Experience")}</span>
      <time datetime="${esc(record.created_at || "")}">${esc(when)}</time>
    </div>
  </article>`;
}

export function ResponseDetail(record) {
  const stars = record.rating ? "★".repeat(Math.min(5, Number(record.rating))) : "—";
  const type = (record.type || "").includes("survey") ? "Survey" : "Feedback";
  return `
    <p>${stars} · ${esc(type)} · ${StatusBadge(record.status)}</p>
    <p class="bos-drawer-body" style="margin:12px 0">${esc(record.content || record.comment || "—")}</p>
    <dl class="cp-meta">
      <dt>Customer</dt><dd>${esc(record.customer_name || "Anonymous")}</dd>
      <dt>Source QR</dt><dd>${esc(record.experience_name || "—")}</dd>
      <dt>Time</dt><dd>${esc((record.created_at || "").slice(0, 16))}</dd>
    </dl>
    ${record.experience_id ? `<a class="bos-btn bos-btn-ghost bos-btn-sm" href="/app/store#experience/${record.experience_id}">View experience</a>` : ""}`;
}

const TYPE_FILTERS = [
  { id: "all", label: "All" },
  { id: "feedback", label: "Feedback" },
  { id: "survey", label: "Survey" },
];

/**
 * Mount response list with search + filters. All data from props/API — no mock data.
 * @param {HTMLElement} root
 * @param {object} opts
 */
export function ResponseList(root, {
  records = [],
  filter = "all",
  searchQ = "",
  onFilterChange,
  onSearch,
  onSelect,
}) {
  root.innerHTML = `
    <div class="bos-toolbar-inline bos-ui-response-list" style="margin-bottom:16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center">
      ${SearchBar({ id: "resp-search", placeholder: "Search responses…", value: searchQ, ariaLabel: "Search responses" })}
      <div id="resp-filters"></div>
    </div>
    <div id="resp-list-body"></div>`;

  mountFilterBar(root.querySelector("#resp-filters"), TYPE_FILTERS, filter, onFilterChange);
  bindSearchBar(root.querySelector("#resp-search"), onSearch);

  const body = root.querySelector("#resp-list-body");
  if (!records.length) {
    body.innerHTML = EmptyState({
      title: "No responses yet",
      text: "When customers complete your experiences and submit feedback, responses appear here.",
      actionHtml: Button({ variant: "primary", label: "Create Experience", tag: "a", href: "/app/store#experiences" }),
    });
    return;
  }
  mountCardGrid(body, records, ResponseCard);
  body.classList.add("merchant-grid--responses");
  body.querySelectorAll(".merchant-response-card").forEach((card) => {
    card.addEventListener("click", () => onSelect(Number(card.dataset.id)));
  });
}

export const responseCard = ResponseCard;
