/** Event Pass owner UI — attendee table, batch select, scanner wiring */

function initAttendeeTable() {
  const search = document.getElementById("ep-attendee-search");
  const filter = document.getElementById("ep-attendee-filter");
  const rows = () => [...document.querySelectorAll(".ep-table tbody tr[data-name]")];
  const actionBar = document.getElementById("ep-action-bar");
  const countEl = document.getElementById("ep-selected-count");
  const selectAll = document.getElementById("ep-select-all");

  const applyFilters = () => {
    const q = (search?.value || "").toLowerCase();
    const st = filter?.value || "";
    rows().forEach((tr) => {
      const matchQ = !q || tr.dataset.name.includes(q);
      const matchS = !st || tr.dataset.status === st;
      tr.hidden = !(matchQ && matchS);
    });
  };

  search?.addEventListener("input", applyFilters);
  filter?.addEventListener("change", applyFilters);

  const syncSelection = () => {
    const checks = [...document.querySelectorAll(".ep-row-check:checked")];
    if (actionBar) actionBar.classList.toggle("hidden", checks.length === 0);
    if (countEl) countEl.textContent = `${checks.length} selected`;
  };

  document.querySelectorAll(".ep-row-check").forEach((cb) => {
    cb.addEventListener("change", syncSelection);
  });

  selectAll?.addEventListener("change", () => {
    document.querySelectorAll(".ep-row-check").forEach((cb) => {
      if (!cb.closest("tr")?.hidden) cb.checked = selectAll.checked;
    });
    syncSelection();
  });

  document.querySelectorAll(".ep-share").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.getAttribute("data-url");
      if (!url) return;
      if (navigator.share) {
        try {
          await navigator.share({ title: "Event Pass", url });
          return;
        } catch {
          /* fall through */
        }
      }
      await navigator.clipboard.writeText(url);
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = "Share"; }, 1500);
    });
  });
}

function initScanner() {
  const boot = window.EVENT_SCANNER_BOOT;
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

  const scanner = window.createQrScanner({
    onScan: (code) => validate(code),
  });

  if (noticeEl && !scanner.cameraSupported()) {
    noticeEl.classList.remove("hidden");
    noticeEl.innerHTML = `<strong>Camera unavailable on this URL.</strong> Browsers block camera on HTTP network addresses. Use <strong>127.0.0.1:5001</strong> on this device, scan from photo, or enter the pass code manually.`;
    startBtn?.classList.remove("os-btn-primary");
    startBtn?.classList.add("os-btn-ghost");
    manualInput?.focus();
  }

  if (startBtn && !scanner.cameraSupported()) {
    startBtn.title = "Requires HTTPS or localhost";
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
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": boot.csrf,
        },
        credentials: "same-origin",
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      const labels = {
        valid: "Valid",
        used: "Already used",
        expired: "Expired",
        cancelled: "Cancelled",
        invalid: "Invalid",
      };
      setResult(
        data.result,
        labels[data.result] || data.result,
        data.message,
        data.attendee?.name || ""
      );
      if (data.checked_in) {
        const checked = document.getElementById("ep-stat-checked");
        const remaining = document.getElementById("ep-stat-remaining");
        if (checked) checked.textContent = String(Number(checked.textContent) + 1);
        if (remaining) remaining.textContent = String(Math.max(0, Number(remaining.textContent) - 1));
      }
      setTimeout(() => {
        setResult("idle", "Ready to scan", "Point camera at attendee pass");
        busy = false;
      }, 1800);
    } catch {
      setResult("invalid", "Error", "Could not validate pass");
      busy = false;
    }
  }

  startBtn?.addEventListener("click", async () => {
    try {
      await scanner.start();
      startBtn.classList.add("hidden");
      stopBtn?.classList.remove("hidden");
      flashBtn?.classList.remove("hidden");
      setResult("idle", "Scanning", "Hold pass in frame");
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
    setResult("idle", "Ready to scan", "Point camera at attendee pass");
  });

  flashBtn?.addEventListener("click", () => scanner.toggleFlash());
  fileInput?.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!scanner.hasDetector()) {
      setResult("invalid", "Not supported", "Enter the pass code manually in this browser.");
      return;
    }
    try {
      await scanner.scanFromFile(file);
      fileInput.value = "";
    } catch (err) {
      const label = err?.message === "no_code" ? "No QR found" : "Scan failed";
      setResult("invalid", label, "Try a clearer photo or enter the code manually.");
      fileInput.value = "";
    }
  });
  manualSubmit?.addEventListener("click", () => {
    validate((manualInput?.value || "").trim().toLowerCase());
    if (manualInput) manualInput.value = "";
  });
  manualInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") validate((manualInput?.value || "").trim().toLowerCase());
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initAttendeeTable();
  initScanner();
});
