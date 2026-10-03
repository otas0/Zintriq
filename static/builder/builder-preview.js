/** Standalone iframe document used by the visual Builder. */

const esc = (value) => String(value ?? "")
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function translatedValue(base, translations, locale, field) {
  return translations?.[locale]?.[field] ?? base?.[field] ?? "";
}

function renderBlock(block, draft, locale) {
  const c = block.content || {};
  const value = (field) => esc(translatedValue(c, c.translations, locale, field));
  if (block.type === "header") return `<header class="block header">${draft.branding.logo_url ? `<img src="${esc(draft.branding.logo_url)}" alt="">` : ""}<small>${esc(translatedValue(draft.branding, draft.translations, locale, "business_name"))}</small><h1>${value("title") || esc(translatedValue(draft, draft.translations, locale, "name"))}</h1><p>${value("subtitle")}</p></header>`;
  if (block.type === "text") return `<section class="block"><p>${value("body")}</p></section>`;
  if (block.type === "image") return `<section class="block image">${c.src ? `<img src="${esc(c.src)}" alt="${value("alt")}">` : `<div class="placeholder">Image</div>`}</section>`;
  if (block.type === "info") return `<section class="block"><h2>${value("title")}</h2><p>${value("body")}</p></section>`;
  if (block.type === "shop") return `<section class="block"><p>${value("subtitle")}</p><button>${value("label") || "View shop"}</button></section>`;
  if (block.type === "actions") return `<section class="block"><h2>${value("title")}</h2><div class="actions">${draft.actions.map((action) => `<button>${esc(translatedValue({ label: action.label }, action.configuration?.translations, locale, "label"))}</button>`).join("")}</div></section>`;
  if (["survey", "booking", "check_in"].includes(block.type)) return `<section class="block"><h2>${value("title")}</h2>${value("body") ? `<p>${value("body")}</p>` : ""}<button>${block.type === "booking" ? "Book now" : block.type === "check_in" ? "Check in" : "Start"}</button></section>`;
  if (block.type === "contact") return `<section class="block"><h2>${value("title")}</h2><p class="muted">Contact details from your store</p></section>`;
  return "";
}

export function previewDocument(draft, locale = "en") {
  const dir = locale === "ar" ? "rtl" : "ltr";
  const bg = draft.branding.background || (draft.branding.theme === "dark" ? "#151515" : "#f5f5f3");
  const fg = draft.branding.theme === "dark" ? "#f7f7f5" : "#171717";
  return `<!doctype html><html lang="${esc(locale)}" dir="${dir}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
  *{box-sizing:border-box}body{margin:0;background:${esc(bg)};color:${fg};font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}.page{max-width:720px;margin:auto;padding:36px 24px 72px}.block{margin:0 0 30px}.header small{display:block;opacity:.62;text-transform:uppercase;letter-spacing:.08em;font-size:11px}.header h1{font-size:clamp(28px,6vw,48px);line-height:1.08;margin:10px 0}.header p,.block p{line-height:1.6;opacity:.78}.header img{max-height:52px;max-width:160px;margin-bottom:18px}.block h2{font-size:20px;margin:0 0 10px}.image img{display:block;width:100%;border-radius:16px}.placeholder{height:220px;display:grid;place-items:center;border:1px dashed #999;border-radius:16px;opacity:.5}.actions{display:grid;gap:10px}button{width:100%;border:0;border-radius:12px;padding:15px 18px;background:${draft.branding.theme === "dark" ? "#fff" : "#111"};color:${draft.branding.theme === "dark" ? "#111" : "#fff"};font:inherit;font-weight:650}.muted{opacity:.5}@media(max-width:520px){.page{padding:26px 18px 56px}.header h1{font-size:30px}}
  </style></head><body><main class="page">${draft.blocks.map((block) => renderBlock(block, draft, locale)).join("")}</main></body></html>`;
}

export function updatePreviewFrame(frame, draft, locale) {
  if (frame) frame.srcdoc = previewDocument(draft, locale);
}
