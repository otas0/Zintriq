/** Feedback Builder — owner canvas + customer renderer */

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

const BLOCK_LABELS = {
  rating: "Rating", short_text: "Short text", long_text: "Long text",
  single_choice: "Single choice", multiple_choice: "Multiple choice",
  dropdown: "Dropdown", yes_no: "Yes / No", number: "Number", date: "Date",
  email: "Email", phone: "Phone", image_upload: "Image upload",
  file_upload: "File upload", heading: "Heading", description: "Description",
  divider: "Divider", section: "Section",
};

function defaultBlock(type) {
  const id = uid();
  const base = { id, type, label: BLOCK_LABELS[type] || type };
  if (type === "rating") return { ...base, required: true, max: 5 };
  if (type === "single_choice" || type === "multiple_choice" || type === "dropdown") {
    return { ...base, required: true, options: ["Option 1", "Option 2"] };
  }
  if (type === "yes_no") return { ...base, required: false };
  if (["short_text", "long_text", "email", "phone", "number"].includes(type)) {
    return { ...base, required: false };
  }
  if (type === "image_upload" || type === "file_upload") return { ...base, required: false };
  return base;
}

function renderBuilderBlock(block, index, blocks, container) {
  const el = document.createElement("div");
  el.className = "fb-block-item";
  el.dataset.index = index;
  const isLayout = ["heading", "description", "divider", "section"].includes(block.type);
  el.innerHTML = `
    <div class="fb-block-item__head">
      <span class="fb-block-type">${(block.type || "").replace(/_/g, " ")}</span>
      <div class="fb-block-actions">
        <button type="button" class="fb-icon-btn" data-move="up" title="Up">↑</button>
        <button type="button" class="fb-icon-btn" data-move="down" title="Down">↓</button>
        <button type="button" class="fb-icon-btn" data-remove title="Remove">×</button>
      </div>
    </div>
    ${isLayout ? `<input class="os-input fb-block-label" value="${block.label || ""}" placeholder="Label">` : `
      <input class="os-input fb-block-label" value="${block.label || ""}" placeholder="Question label">
      <label class="fb-check"><input type="checkbox" class="fb-block-req" ${block.required ? "checked" : ""}> Required</label>
      ${block.options ? `<input class="os-input fb-block-options" value="${block.options.join(", ")}" placeholder="Options (comma separated)">` : ""}
    `}
  `;
  el.querySelector(".fb-block-label")?.addEventListener("input", (e) => { block.label = e.target.value; });
  el.querySelector(".fb-block-req")?.addEventListener("change", (e) => { block.required = e.target.checked; });
  el.querySelector(".fb-block-options")?.addEventListener("input", (e) => {
    block.options = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
  });
  el.querySelector("[data-remove]")?.addEventListener("click", () => {
    blocks.splice(index, 1);
    renderBuilderCanvas(blocks, container);
  });
  el.querySelector("[data-move=up]")?.addEventListener("click", () => {
    if (index > 0) { [blocks[index - 1], blocks[index]] = [blocks[index], blocks[index - 1]]; renderBuilderCanvas(blocks, container); }
  });
  el.querySelector("[data-move=down]")?.addEventListener("click", () => {
    if (index < blocks.length - 1) { [blocks[index + 1], blocks[index]] = [blocks[index], blocks[index + 1]]; renderBuilderCanvas(blocks, container); }
  });
  container.appendChild(el);
}

function renderBuilderCanvas(blocks, container) {
  container.innerHTML = "";
  blocks.forEach((block, i) => renderBuilderBlock(block, i, blocks, container));
}

function initBuilder() {
  const boot = window.FB_BUILDER_BOOT;
  const container = document.getElementById("fb-builder-blocks");
  const form = document.getElementById("fb-builder-form");
  const jsonField = document.getElementById("fb-blocks-json");
  const palette = document.getElementById("fb-block-palette");
  if (!container || !boot) return;

  let blocks = JSON.parse(JSON.stringify(boot.blocks || []));
  renderBuilderCanvas(blocks, container);

  palette?.querySelectorAll(".fb-palette-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      blocks.push(defaultBlock(btn.dataset.blockType));
      renderBuilderCanvas(blocks, container);
    });
  });

  form?.addEventListener("submit", () => {
    if (jsonField) jsonField.value = JSON.stringify(blocks);
  });
}

function renderCustomerField(block, preview) {
  const id = block.id;
  const name = `field_${id}`;
  const req = block.required ? "required" : "";
  const label = block.label || "";
  switch (block.type) {
    case "heading":
      return `<h2 class="fb-field-heading">${label}</h2>`;
    case "description":
      return `<p class="fb-field-desc">${label}</p>`;
    case "divider":
      return `<hr class="fb-field-divider">`;
    case "section":
      return `<h3 class="fb-field-section">${label}</h3>`;
    case "rating":
      return `<fieldset class="fb-stars"><legend>${label}${block.required ? " *" : ""}</legend><div class="fb-star-row">${[5,4,3,2,1].map((n) => `<label class="fb-star-opt"><input type="radio" name="${name}" value="${n}" ${req}><span>★</span></label>`).join("")}</div></fieldset>`;
    case "long_text":
      return `<div class="mq-field"><label class="mq-label">${label}</label><textarea class="mq-input" name="${name}" rows="3" ${req}></textarea></div>`;
    case "short_text":
    case "email":
    case "phone":
    case "number":
    case "date":
      return `<div class="mq-field"><label class="mq-label">${label}</label><input class="mq-input" name="${name}" type="${block.type === "number" ? "number" : block.type === "date" ? "date" : block.type === "email" ? "email" : "text"}" ${req}></div>`;
    case "dropdown":
      return `<div class="mq-field"><label class="mq-label">${label}</label><select class="mq-input" name="${name}" ${req}>${(block.options||[]).map((o) => `<option value="${o}">${o}</option>`).join("")}</select></div>`;
    case "single_choice":
      return `<fieldset class="mq-field"><legend class="mq-label">${label}</legend>${(block.options||[]).map((o) => `<label class="fb-check"><input type="radio" name="${name}" value="${o}" ${req}> ${o}</label>`).join("")}</fieldset>`;
    case "multiple_choice":
      return `<fieldset class="mq-field"><legend class="mq-label">${label}</legend>${(block.options||[]).map((o) => `<label class="fb-check"><input type="checkbox" name="${name}" value="${o}"> ${o}</label>`).join("")}</fieldset>`;
    case "yes_no":
      return `<fieldset class="mq-field"><legend class="mq-label">${label}</legend><label class="fb-check"><input type="radio" name="${name}" value="yes" ${req}> Yes</label><label class="fb-check"><input type="radio" name="${name}" value="no"> No</label></fieldset>`;
    case "image_upload":
    case "file_upload":
      return `<div class="mq-field"><label class="mq-label">${label}</label><input class="mq-input" type="file" name="${name}" accept="${block.type === "image_upload" ? "image/*" : "*"}" ${req}></div>`;
    default:
      return "";
  }
}

function initCustomerRenderer() {
  const mount = document.getElementById("fb-customer-blocks");
  if (!mount) return;
  const blocks = JSON.parse(mount.dataset.blocks || "[]");
  const preview = mount.dataset.preview === "1";
  mount.innerHTML = blocks.map((b) => renderCustomerField(b, preview)).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  initBuilder();
  initCustomerRenderer();
});
