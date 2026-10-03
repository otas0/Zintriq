(function () {
  const api = window.zintriqDesktop;
  if (!api || !api.exportProject) return;

  const statusEl = document.createElement("div");
  statusEl.className = "zw-transfer-status hidden";
  statusEl.setAttribute("role", "status");
  document.body.appendChild(statusEl);

  const dialog = document.createElement("div");
  dialog.className = "zw-transfer-dialog hidden";
  dialog.innerHTML = `
    <div class="zw-transfer-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="zw-transfer-title">
      <h2 id="zw-transfer-title">导入作品</h2>
      <p class="zw-transfer-warning">包内可能含个人信息。校验和只证明文件完整，不证明来源。</p>
      <div id="zw-transfer-summary"></div>
      <fieldset id="zw-transfer-automations" class="zw-transfer-automations"></fieldset>
      <p id="zw-transfer-progress" class="zw-transfer-progress"></p>
      <div class="zw-transfer-actions">
        <button type="button" class="zw-btn zw-btn--secondary" id="zw-transfer-cancel">取消</button>
        <button type="button" class="zw-btn zw-btn--primary" id="zw-transfer-confirm">导入为新作品</button>
      </div>
    </div>`;
  document.body.appendChild(dialog);

  let stagingId = "";
  let busy = false;

  function showStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.className = "zw-transfer-status" + (kind ? " zw-transfer-status--" + kind : "");
  }

  function hideDialog() {
    dialog.classList.add("hidden");
    stagingId = "";
  }

  if (typeof api.onTransferProgress === "function") {
    api.onTransferProgress((payload) => {
      const text = (payload && (payload.detail || payload.stage)) || "";
      if (text) showStatus(text, "progress");
      const live = document.getElementById("zw-transfer-progress");
      if (live) live.textContent = text;
    });
  }

  async function exportProject(project) {
    if (busy) return;
    busy = true;
    showStatus("正在导出…", "progress");
    try {
      const result = await api.exportProject({ projectId: project.id, name: project.name });
      if (result && result.canceled) {
        showStatus("");
        statusEl.classList.add("hidden");
        return;
      }
      if (!result || !result.ok) {
        showStatus((result && result.error) || "导出失败", "error");
        return;
      }
      showStatus("导出完成", "ok");
    } catch (err) {
      showStatus("导出失败", "error");
    } finally {
      busy = false;
    }
  }

  function renderPreview(preview) {
    const summary = document.getElementById("zw-transfer-summary");
    const ignored = (preview.ignored || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const redactions = (preview.needs_reconfiguration || []).map((item) => {
      const path = item.path || item;
      return `<li>${escapeHtml(path)} — 需要重新配置</li>`;
    }).join("");
    summary.innerHTML = `
      <p><strong>${escapeHtml(preview.project_name || "未命名作品")}</strong></p>
      <p>页面 ${Number(preview.page_count) || 0} · 数据集合 ${Number(preview.collection_count) || 0}</p>
      <p>将被忽略：</p>
      <ul>${ignored || "<li>无</li>"}</ul>
      <p>需要重新配置：</p>
      <ul>${redactions || "<li>无</li>"}</ul>`;
    const box = document.getElementById("zw-transfer-automations");
    const items = preview.automations || [];
    if (!items.length) {
      box.innerHTML = "<p>没有需要单独启用的自动化。</p>";
      return;
    }
    box.innerHTML = "<legend>工作流默认停用，勾选后才会启用</legend>" + items.map((item) => {
      const urls = (item.external_urls || []).map((url) => `<code>${escapeHtml(url)}</code>`).join(" ");
      return `<label class="zw-transfer-auto">
        <input type="checkbox" value="${escapeHtml(item.key)}">
        <span>${escapeHtml(item.kind)} ${escapeHtml(item.name || "")}</span>
        <span class="zw-transfer-urls">${urls || "无外部地址"}</span>
      </label>`;
    }).join("");
  }

  function selectedKeys() {
    return Array.from(dialog.querySelectorAll(".zw-transfer-auto input:checked")).map((input) => input.value);
  }

  async function startImport() {
    if (busy) return;
    busy = true;
    showStatus("正在打开作品包…", "progress");
    try {
      const result = await api.previewImport();
      if (result && result.canceled) {
        showStatus("");
        statusEl.classList.add("hidden");
        return;
      }
      if (!result || !result.ok) {
        showStatus((result && result.error) || "作品包未通过校验", "error");
        return;
      }
      stagingId = result.stagingId;
      renderPreview(result.preview || {});
      dialog.classList.remove("hidden");
      showStatus("请确认导入内容", "progress");
    } catch (err) {
      showStatus("无法预览作品包", "error");
    } finally {
      busy = false;
    }
  }

  async function confirmImport() {
    if (busy || !stagingId) return;
    busy = true;
    showStatus("正在写入…", "progress");
    try {
      const result = await api.commitImport({ stagingId, enableKeys: selectedKeys() });
      hideDialog();
      if (!result || !result.ok) {
        showStatus((result && result.error) || "导入失败，已回滚", "error");
        return;
      }
      showStatus("已导入为新作品", "ok");
      window.location.reload();
    } catch (err) {
      hideDialog();
      showStatus("导入失败，已回滚", "error");
    } finally {
      busy = false;
    }
  }

  async function cancelImport() {
    if (stagingId && api.cancelImport) await api.cancelImport({ stagingId });
    hideDialog();
    statusEl.classList.add("hidden");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  document.getElementById("zw-import-project")?.addEventListener("click", startImport);
  document.getElementById("zw-transfer-confirm")?.addEventListener("click", confirmImport);
  document.getElementById("zw-transfer-cancel")?.addEventListener("click", cancelImport);

  window.zintriqProjectTransfer = { exportProject };
})();
