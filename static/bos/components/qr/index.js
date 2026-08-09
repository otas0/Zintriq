/** QR domain components. */

import { esc } from "../ui/_utils.js";
import { Button } from "../ui/Button.js";
import { StatusBadge } from "../ui/Badge.js";

function fmtRelative(value) {
  if (!value) return "";
  const raw = String(value);
  const d = new Date(raw.includes("T") ? raw : raw.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return raw.slice(0, 10);
  const diff = Date.now() - d.getTime();
  if (diff < 3600000) return `${Math.max(1, Math.floor(diff / 60000))}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return raw.slice(0, 10);
}

export function QRStatus(status) {
  return StatusBadge(status === "paused" ? "active" : status);
}

export function QRExperienceCard(exp) {
  const views = exp.total_views ?? exp.analytics?.scan_count ?? exp.scans_today ?? 0;
  const responses = exp.response_count ?? exp.analytics?.response_count ?? exp.analytics?.completed_actions ?? 0;
  const typeLabel = exp.mvp_type || exp.type_label || exp.type || "QR";
  const updated = fmtRelative(exp.updated_at || exp.last_updated);
  const preview = exp.qr_image
    ? `<img class="merchant-qr-card__preview-img" src="${esc(exp.qr_image)}" alt="">`
    : `<div class="merchant-qr-card__preview-placeholder"><span aria-hidden="true">⬡</span></div>`;

  return `<article class="merchant-qr-card bos-ui-qr-card" data-id="${exp.id}">
    <div class="merchant-qr-card__preview">${preview}</div>
    <div class="merchant-qr-card__body">
      <div class="merchant-qr-card__head">
        <h3 class="merchant-qr-card__title">${esc(exp.name)}</h3>
        ${QRStatus(exp.status)}
      </div>
      <p class="merchant-qr-card__type">${esc(typeLabel)}</p>
      <div class="merchant-qr-card__stats">
        <span>${views} scans</span>
        <span>${responses} responses</span>
        ${updated ? `<span>Updated ${esc(updated)}</span>` : ""}
      </div>
      <div class="merchant-qr-card__actions">
        ${Button({ variant: "primary", label: "Open", sm: true, attrs: `data-act="open" data-id="${exp.id}"` })}
        ${Button({ variant: "ghost", label: "Edit", sm: true, attrs: `data-act="edit" data-id="${exp.id}"` })}
        ${Button({ variant: "ghost", label: "Duplicate", sm: true, attrs: `data-act="duplicate" data-id="${exp.id}"` })}
        ${exp.status !== "archived" ? Button({ variant: "ghost", label: "Archive", sm: true, attrs: `data-act="archive" data-id="${exp.id}"` }) : ""}
        ${exp.status === "draft" || exp.status === "archived"
    ? Button({ variant: "ghost", label: "Delete", sm: true, attrs: `data-act="delete" data-id="${exp.id}"` })
    : ""}
      </div>
    </div>
  </article>`;
}

export function QRExperienceCardCompact(exp) {
  const views = exp.total_views ?? exp.scans_today ?? 0;
  const responses = exp.response_count ?? 0;
  const status = exp.status === "paused" ? "active" : exp.status;
  const updated = fmtRelative(exp.updated_at || exp.last_updated);
  return `<article class="merchant-qr-card merchant-qr-card--compact bos-ui-qr-card" data-id="${exp.id}">
    <div class="merchant-qr-card__body">
      <div class="merchant-qr-card__head">
        <h3 class="merchant-qr-card__title">${esc(exp.name)}</h3>
        ${QRStatus(status)}
      </div>
      <p class="merchant-qr-card__stats">${views} scans · ${responses} responses${updated ? ` · ${esc(updated)}` : ""}</p>
      <a class="merchant-link" href="/app/store#experience/${exp.id}">Open</a>
    </div>
  </article>`;
}

/** Customer-facing mobile preview from real experience payload. */
export function QRPreview(payload, { mode = "mobile" } = {}) {
  const b = payload.branding || {};
  const width = mode === "desktop" ? "100%" : "280px";
  const blocks = (payload.blocks || []).map((block) => {
    const c = block.content || {};
    if (block.type === "header") {
      return `<div style="margin-bottom:16px">
        ${b.logo_url ? `<img src="${esc(b.logo_url)}" alt="" style="max-height:40px;margin-bottom:8px">` : ""}
        <p class="cp-muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.06em">${esc(b.business_name || "")}</p>
        <h3 style="margin:6px 0">${esc(c.title || payload.name)}</h3>
        ${c.subtitle ? `<p class="cp-muted" style="font-size:13px">${esc(c.subtitle)}</p>` : ""}
      </div>`;
    }
    if (block.type === "text" || block.type === "info") {
      return `<div style="margin-bottom:14px">
        ${c.title ? `<strong style="display:block;margin-bottom:4px">${esc(c.title)}</strong>` : ""}
        <p class="cp-muted" style="font-size:13px;margin:0">${esc(c.body || "")}</p>
      </div>`;
    }
    if (block.type === "image" && c.src) {
      return `<img src="${esc(c.src)}" alt="" style="width:100%;border-radius:8px;margin-bottom:14px">`;
    }
    if (block.type === "actions") {
      return `<div style="margin-bottom:14px">
        ${c.title ? `<p style="margin:0 0 8px;font-weight:600">${esc(c.title)}</p>` : ""}
        ${(payload.actions || []).map((a) =>
          `<div style="padding:10px;margin:6px 0;border-radius:8px;background:#111;color:#fff;text-align:center;font-size:13px">${esc(a.label)}</div>`
        ).join("")}
      </div>`;
    }
    if (["survey", "booking", "check_in", "contact"].includes(block.type)) {
      return `<div style="margin-bottom:14px;padding:12px;border:1px dashed var(--color-border,#ddd);border-radius:8px;font-size:13px">
        <strong>${esc(c.title || block.type)}</strong>
        <p class="cp-muted" style="margin:4px 0 0">Connected block</p>
      </div>`;
    }
    return "";
  }).join("");

  return `<div class="bos-ui-qr-preview" style="max-width:${width};margin:0 auto;border:1px solid var(--color-border,#e5e5e5);border-radius:16px;padding:20px;background:${esc(b.background || "var(--sheet-bg,#fff)")}">${blocks}</div>`;
}

/** @deprecated aliases */
export const qrExperienceCard = QRExperienceCard;
export const qrExperienceCardCompact = QRExperienceCardCompact;
