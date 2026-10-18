(function (root) {
  function csrfToken() {
    const node = root.document.querySelector('meta[name="csrf-token"]');
    return node ? node.getAttribute("content") || "" : "";
  }

  function asResponse(result) {
    const status = result && result.status != null ? result.status : 0;
    return {
      ok: status >= 200 && status < 300,
      status: status,
      json: function () {
        return Promise.resolve(result && result.body);
      },
      text: function () {
        return Promise.resolve((result && result.text) || "");
      },
    };
  }

  function serializePost(body) {
    const token = csrfToken();
    if (body instanceof root.FormData) {
      const fields = {};
      const files = [];
      const tasks = [];
      body.forEach(function (value, key) {
        if (value && typeof value === "object" && typeof value.arrayBuffer === "function") {
          tasks.push(
            value.arrayBuffer().then(function (buf) {
              files.push({
                field: key,
                filename: value.name || "file",
                type: value.type || "application/octet-stream",
                data: Array.from(new Uint8Array(buf)),
              });
            })
          );
        } else {
          fields[key] = String(value);
        }
      });
      if (!fields.csrf_token) fields.csrf_token = token;
      return Promise.all(tasks).then(function () {
        return { kind: "form", fields: fields, files: files, csrf: token };
      });
    }
    return Promise.resolve({
      kind: "json",
      json: Object.assign({ csrf_token: token }, body || {}),
      csrf: token,
    });
  }

  function ipcHttp(invoke) {
    return {
      get: function (path) {
        return invoke({ method: "GET", path: path }).then(asResponse);
      },
      post: function (path, body) {
        return serializePost(body).then(function (payload) {
          payload.method = "POST";
          payload.path = path;
          return invoke(payload).then(asResponse);
        });
      },
    };
  }

  function fetchHttp() {
    function post(path, body) {
      const token = csrfToken();
      if (body instanceof root.FormData) {
        if (!body.has("csrf_token")) body.append("csrf_token", token);
        return root.fetch(path, {
          method: "POST",
          headers: { "X-CSRF-Token": token },
          credentials: "same-origin",
          body: body,
        });
      }
      return root.fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": token,
        },
        credentials: "same-origin",
        body: JSON.stringify(Object.assign({ csrf_token: token }, body || {})),
      });
    }
    function get(path) {
      return root.fetch(path, { method: "GET", credentials: "same-origin" });
    }
    return { get: get, post: post };
  }

  const invoke = typeof root.zintriqInvokeHttp === "function" ? root.zintriqInvokeHttp : null;
  const desktop = Boolean(root.zintriqDesktop && root.zintriqDesktop.isDesktop);
  root.zintriq = {
    http: invoke ? ipcHttp(invoke) : desktop ? ipcHttp(function () {
      return Promise.resolve({ status: 0, body: { error: "desktop http unavailable" }, text: "" });
    }) : fetchHttp(),
    engine: root.ZintriqEngine || null,
  };

  function zipFile(file) {
    const name = String((file && file.name) || "").toLowerCase();
    return name.endsWith(".zip") || name.endsWith(".zintriq-app") || (file && file.type === "application/zip");
  }

  if (desktop && root.document) {
    root.document.addEventListener("dragover", function (event) {
      if (!event.dataTransfer) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    });
    root.document.addEventListener("drop", function (event) {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      const file = Array.prototype.find.call(files, zipFile);
      if (!file) return;
      event.preventDefault();
      const desktopApi = root.zintriqDesktop;
      const filePath = desktopApi && desktopApi.pathForFile ? desktopApi.pathForFile(file) : "";
      if (filePath && desktopApi.openPack) {
        desktopApi.openPack(filePath);
        return;
      }
      const form = new root.FormData();
      form.append("site", file, file.name);
      root.zintriq.http.post("/api/builder-core/meta/sites/import", form).then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) return;
          if (data.studio) root.location.href = data.studio;
          else if (data.slug) root.location.href = "/studio/meta/" + encodeURIComponent(data.slug);
        });
      });
    });
  }
})(window);
