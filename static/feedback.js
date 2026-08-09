/* Feedback Platform — owner UI */

document.addEventListener("DOMContentLoaded", () => {
  const anon = document.getElementById("fb-anon");
  if (anon) {
    anon.addEventListener("change", () => {
      document.querySelectorAll(".fb-identified, [name=customer_name], [name=customer_email]").forEach((el) => {
        el.closest(".mq-field")?.style && (el.closest(".mq-field").style.display = anon.checked ? "none" : "");
      });
    });
  }

  const batchForm = document.getElementById("fb-batch-form");
  const idsField = document.getElementById("fb-batch-ids");
  const countEl = document.getElementById("fb-batch-count");
  const selectAll = document.getElementById("fb-select-all");
  if (!batchForm) return;

  const sync = () => {
    const checks = [...document.querySelectorAll(".fb-row-check:checked")];
    batchForm.classList.toggle("hidden", checks.length === 0);
    if (idsField) idsField.value = checks.map((c) => c.value).join(",");
    if (countEl) countEl.textContent = `${checks.length} selected`;
  };

  document.querySelectorAll(".fb-row-check").forEach((cb) => cb.addEventListener("change", sync));
  selectAll?.addEventListener("change", () => {
    document.querySelectorAll(".fb-row-check").forEach((cb) => { cb.checked = selectAll.checked; });
    sync();
  });
});
