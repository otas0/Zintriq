/** Shared QR capability UI — search, filter, share, batch select, check-in scanner */

function initEntityFilters() {
  const search = document.getElementById("qr-entity-search");
  const statusFilter = document.getElementById("qr-entity-filter");
  const groupFilter = document.getElementById("qr-group-filter");
  const categoryFilter = document.getElementById("qr-category-filter");
  const cards = () => [...document.querySelectorAll(".ep-entity-card[data-name]")];
  const rows = () => [...document.querySelectorAll("#qr-product-table tbody tr[data-name]")];

  const apply = () => {
    const q = (search?.value || "").toLowerCase();
    const st = statusFilter?.value || "";
    const group = groupFilter?.value || "";
    const cat = categoryFilter?.value || "";
    cards().forEach((el) => {
      const matchQ = !q || el.dataset.name.includes(q);
      const matchS = !st || el.dataset.status === st;
      const matchG = !group || el.dataset.group === group;
      el.hidden = !(matchQ && matchS && matchG);
    });
    rows().forEach((tr) => {
      const matchQ = !q || tr.dataset.name.includes(q);
      const matchS = !st || tr.dataset.status === st;
      const matchC = !cat || tr.dataset.category === cat;
      tr.hidden = !(matchQ && matchS && matchC);
    });
  };

  search?.addEventListener("input", apply);
  statusFilter?.addEventListener("change", apply);
  groupFilter?.addEventListener("change", apply);
  categoryFilter?.addEventListener("change", apply);
}

function initShareButtons() {
  document.querySelectorAll(".ep-share").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.getAttribute("data-url");
      if (!url) return;
      if (navigator.share) {
        try {
          await navigator.share({ title: "QR link", url });
          return;
        } catch {
          /* fall through */
        }
      }
      await navigator.clipboard.writeText(url);
      const prev = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = prev; }, 1500);
    });
  });
}

function initProductBatch() {
  const form = document.getElementById("qr-batch-form");
  const idsField = document.getElementById("qr-batch-ids");
  const countEl = document.getElementById("qr-batch-count");
  const selectAll = document.getElementById("qr-select-all");
  if (!form) return;

  const sync = () => {
    const checks = [...document.querySelectorAll(".qr-row-check:checked")];
    form.classList.toggle("hidden", checks.length === 0);
    if (idsField) idsField.value = checks.map((c) => c.value).join(",");
    if (countEl) countEl.textContent = `${checks.length} selected`;
  };

  document.querySelectorAll(".qr-row-check").forEach((cb) => cb.addEventListener("change", sync));
  selectAll?.addEventListener("change", () => {
    document.querySelectorAll(".qr-row-check").forEach((cb) => {
      if (!cb.closest("tr")?.hidden) cb.checked = selectAll.checked;
    });
    sync();
  });
}

function initCheckinScanner() {
  const boot = window.CHECKIN_SCANNER_BOOT;
  if (!boot || !window.createQrScanner) return;

  const resultEl = document.getElementById("ep-scan-result");
  const labelEl = resultEl?.querySelector(".ep-scan-result__label");
  const msgEl = resultEl?.querySelector(".ep-scan-result__msg");
  const nameEl = resultEl?.querySelector(".ep-scan-result__name");
  const startBtn = document.getElementById("ep-scanner-start");
  const stopBtn = document.getElementById("ep-scanner-stop");
  const flashBtn = document.getElementById("ep-scanner-flash");
  const manualInput = document.getElementById("ep-manual-code");
  const manualSubmit = document.getElementById("ep-manual-submit");
  const fileInput = document.getElementById("ep-scan-file");
  const noticeEl = document.getElementById("ep-scanner-notice");
  let busy = false;

  const scanner = window.createQrScanner({ onScan: (code) => validate(code) });

  if (noticeEl && !scanner.cameraSupported()) {
    noticeEl.classList.remove("hidden");
    noticeEl.innerHTML = "<strong>Camera unavailable on this URL.</strong> Use photo upload or manual entry.";
  }

  const setResult = (state, label, msg, name = "") => {
    if (!resultEl) return;
    resultEl.dataset.state = state;
    if (labelEl) labelEl.textContent = label;
    if (msgEl) msgEl.textContent = msg;
    if (nameEl) nameEl.textContent = name;
  };

  async function validate(code) {
    if (busy || !code) return;
    busy = true;
    setResult("pending", "Validating…", code);
    try {
      const res = await fetch(boot.scanUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": boot.csrf },
        credentials: "same-origin",
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      const labels = { valid: "Success", invalid: "Invalid", expired: "Inactive" };
      setResult(
        data.checked_in ? "valid" : data.result,
        labels[data.result] || data.result,
        data.message,
        data.point?.name || ""
      );
      if (data.checked_in) {
        const el = document.getElementById("ci-stat-checked");
        if (el) el.textContent = String(Number(el.textContent) + 1);
      }
      setTimeout(() => {
        setResult("idle", "Ready to scan", "Point camera at check-in QR");
        busy = false;
      }, 1800);
    } catch {
      setResult("invalid", "Error", "Could not process check-in");
      busy = false;
    }
  }

  startBtn?.addEventListener("click", async () => {
    try {
      await scanner.start();
      startBtn.classList.add("hidden");
      stopBtn?.classList.remove("hidden");
      flashBtn?.classList.remove("hidden");
      setResult("idle", "Scanning", "Hold QR in frame");
    } catch (err) {
      const msg = scanner.cameraErrorMessage(err);
      setResult("invalid", msg.label, msg.msg);
    }
  });

  stopBtn?.addEventListener("click", () => {
    scanner.stop();
    stopBtn.classList.add("hidden");
    flashBtn?.classList.add("hidden");
    startBtn?.classList.remove("hidden");
    setResult("idle", "Ready to scan", "Point camera at check-in QR");
  });

  flashBtn?.addEventListener("click", () => scanner.toggleFlash());
  fileInput?.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file || !scanner.hasDetector()) return;
    try {
      await scanner.scanFromFile(file);
    } catch {
      setResult("invalid", "No QR found", "Try a clearer photo");
    }
    fileInput.value = "";
  });
  manualSubmit?.addEventListener("click", () => validate((manualInput?.value || "").trim().toLowerCase()));
  manualInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") validate((manualInput?.value || "").trim().toLowerCase());
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initEntityFilters();
  initShareButtons();
  initProductBatch();
  initCheckinScanner();
});
