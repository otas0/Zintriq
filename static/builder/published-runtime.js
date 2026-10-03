(() => {
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const invokeMeta = document.querySelector('meta[name="ub-invoke"]');
  const documentMeta = document.querySelector('meta[name="ub-document-key"]');

  function csrfToken() {
    return csrfMeta ? csrfMeta.getAttribute("content") || "" : "";
  }

  function invokeUrl(node) {
    return (node && node.getAttribute("data-invoke")) || (invokeMeta && invokeMeta.getAttribute("content")) || "";
  }

  function documentKey() {
    return documentMeta ? documentMeta.getAttribute("content") || "" : "";
  }

  function fieldsFromForm(form) {
    const data = {};
    const skip = { csrf_token: true };
    new FormData(form).forEach((value, key) => {
      if (!skip[key]) data[key] = value;
    });
    return data;
  }

  function postInvoke(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken(),
      },
      body: JSON.stringify(payload),
    }).then((response) => response.json().then((body) => ({ ok: response.ok && body && body.ok, body })));
  }

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.classList.contains("ub-form")) return;
    const actionKey = form.getAttribute("data-action-key");
    if (!actionKey) return;
    event.preventDefault();
    const url = invokeUrl(form);
    if (!url) return;
    const success = form.querySelector(".ub-form-success");
    const failure = form.querySelector(".ub-form-failure");
    postInvoke(url, {
      csrf_token: csrfToken(),
      document_key: documentKey(),
      node_key: form.getAttribute("data-node") || "",
      action_key: actionKey,
      data: fieldsFromForm(form),
    }).then((result) => {
      if (success) success.hidden = !result.ok;
      if (failure) failure.hidden = result.ok;
    }).catch(() => {
      if (success) success.hidden = true;
      if (failure) failure.hidden = false;
    });
  });

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("[data-action-key]");
    if (!button || button.closest("form")) return;
    const actionKey = button.getAttribute("data-action-key");
    const url = invokeUrl(button);
    if (!actionKey || !url) return;
    event.preventDefault();
    postInvoke(url, {
      csrf_token: csrfToken(),
      document_key: documentKey(),
      node_key: button.getAttribute("data-node") || "",
      action_key: actionKey,
    });
  });
})();
