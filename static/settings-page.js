/**
 * Workspace Settings — section nav + Team members via workspace API.
 */
(function () {
  const navItems = Array.from(document.querySelectorAll(".zw-settings__nav-item"));
  const panels = {
    workspace: document.getElementById("settings-workspace"),
    team: document.getElementById("settings-team"),
    account: document.getElementById("settings-account"),
  };
  const memberList = document.getElementById("zw-settings-members");
  const inviteForm = document.getElementById("zw-settings-invite");
  const inviteStatus = document.getElementById("zw-invite-status");
  const teamCard = document.querySelector("#settings-team .zw-settings__card");
  const workspaceCard = document.querySelector("#settings-workspace .zw-settings__card");
  const workspaceId =
    (teamCard && teamCard.getAttribute("data-workspace-id")) ||
    (workspaceCard && workspaceCard.getAttribute("data-workspace-id"));
  const workspaceNameInput = document.getElementById("zw-settings-workspace-name");
  const workspaceSaveBtn = document.getElementById("zw-settings-workspace-save");
  const workspaceSaveStatus = document.getElementById("zw-workspace-save-status");
  let membersLoaded = false;

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function setInviteStatus(message, isError) {
    if (!inviteStatus) return;
    inviteStatus.hidden = !message;
    inviteStatus.textContent = message || "";
    inviteStatus.classList.toggle("zw-settings__status--error", !!isError);
  }

  function renderMembers(rows) {
    if (!memberList) return;
    if (!rows || !rows.length) {
      memberList.innerHTML = '<li class="zw-settings__empty-text">No members yet.</li>';
      return;
    }
    memberList.innerHTML = rows
      .map((row) => {
        const email = row.email || "Unknown";
        const role = row.role || "member";
        const status = row.status || "active";
        return (
          '<li class="zw-settings__member">' +
          '<span class="zw-settings__member-email">' +
          email.replace(/</g, "&lt;") +
          "</span>" +
          '<span class="zw-settings__member-meta">' +
          role +
          (status !== "active" ? " · " + status : "") +
          "</span>" +
          "</li>"
        );
      })
      .join("");
  }

  function loadMembers() {
    if (!memberList || !workspaceId) {
      if (memberList) {
        memberList.innerHTML =
          '<li class="zw-settings__empty-text">Select an active workspace to manage team.</li>';
      }
      return;
    }
    fetch("/api/workspaces/" + encodeURIComponent(workspaceId) + "/members", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load members");
        return res.json();
      })
      .then((rows) => {
        membersLoaded = true;
        renderMembers(rows);
      })
      .catch(() => {
        memberList.innerHTML =
          '<li class="zw-settings__empty-text">Could not load team members.</li>';
      });
  }

  function showSection(section) {
    const key = panels[section] ? section : "workspace";
    Object.entries(panels).forEach(([name, panel]) => {
      if (!panel) return;
      panel.classList.toggle("hidden", name !== key);
    });
    navItems.forEach((item) => {
      const on = item.dataset.section === key;
      item.classList.toggle("zw-settings__nav-item--active", on);
      if (on) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    if (key === "team" && !membersLoaded) loadMembers();
  }

  navItems.forEach((item) => {
    item.addEventListener("click", (event) => {
      event.preventDefault();
      const section = item.dataset.section || "workspace";
      showSection(section);
      if (history.replaceState) {
        history.replaceState(null, "", "#" + section);
      }
    });
  });

  if (inviteForm) {
    inviteForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!workspaceId) {
        setInviteStatus("No active workspace.", true);
        return;
      }
      const email = (document.getElementById("zw-invite-email") || {}).value || "";
      const role = (document.getElementById("zw-invite-role") || {}).value || "member";
      setInviteStatus("Sending…", false);
  const csrf = csrfToken();
      fetch("/api/workspaces/" + encodeURIComponent(workspaceId) + "/members", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRF-Token": csrf,
        },
        body: JSON.stringify({ email: email.trim(), role: role, csrf_token: csrf }),
      })
        .then(async (res) => {
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            throw new Error(data.error || "Invite failed");
          }
          return data;
        })
        .then(() => {
          setInviteStatus("Invite sent.", false);
          inviteForm.reset();
          membersLoaded = false;
          loadMembers();
        })
        .catch((err) => {
          setInviteStatus(err.message || "Invite failed", true);
        });
    });
  }

  function setWorkspaceSaveStatus(message, isError) {
    if (!workspaceSaveStatus) return;
    workspaceSaveStatus.hidden = !message;
    workspaceSaveStatus.textContent = message || "";
    workspaceSaveStatus.classList.toggle("zw-settings__status--error", !!isError);
  }

  function saveWorkspaceName() {
    if (!workspaceId) {
      setWorkspaceSaveStatus("No active workspace.", true);
      return;
    }
    const name = ((workspaceNameInput && workspaceNameInput.value) || "").trim();
    if (!name) {
      setWorkspaceSaveStatus("Enter a workspace name.", true);
      return;
    }
    setWorkspaceSaveStatus("Saving…", false);
    if (workspaceSaveBtn) workspaceSaveBtn.disabled = true;
    const csrf = csrfToken();
    fetch("/api/workspaces/" + encodeURIComponent(workspaceId), {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRF-Token": csrf,
      },
      body: JSON.stringify({ name: name, csrf_token: csrf }),
    })
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Save failed");
        return data;
      })
      .then((data) => {
        const next = data.name || name;
        if (workspaceNameInput) workspaceNameInput.value = next;
        document.querySelectorAll(".zw-workspace-name").forEach((el) => {
          el.textContent = next;
        });
        document.querySelectorAll(".zw-workspace-icon").forEach((el) => {
          el.textContent = next[0] ? next[0].toUpperCase() : "W";
        });
        setWorkspaceSaveStatus("Saved.", false);
      })
      .catch((err) => {
        setWorkspaceSaveStatus(err.message || "Save failed", true);
      })
      .finally(() => {
        if (workspaceSaveBtn) workspaceSaveBtn.disabled = false;
      });
  }

  if (workspaceSaveBtn) {
    workspaceSaveBtn.addEventListener("click", saveWorkspaceName);
  }
  if (workspaceNameInput) {
    workspaceNameInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        saveWorkspaceName();
      }
    });
  }

  const hash = (location.hash || "").replace(/^#/, "");
  showSection(hash || "workspace");

  const integrationNotice = document.getElementById("zw-settings-integration-notice");
  const params = new URLSearchParams(location.search);
  const integration = params.get("integration");
  if (integrationNotice && integration) {
    const err = params.get("integration_error");
    const connected = params.get("step") === "connected";
    integrationNotice.classList.remove("hidden");
    integrationNotice.classList.toggle("zw-settings__notice--error", !!err);
    integrationNotice.textContent = err
      ? "Connection to " + integration + " failed: " + err.replace(/_/g, " ")
      : connected
        ? integration + " connected — configure it on your published store or in Builder Connection."
        : "Finish connecting " + integration + " from your store Manage hub or Builder Connection.";
    if (history.replaceState) {
      history.replaceState(null, "", location.pathname + (hash ? "#" + hash : ""));
    }
  }
})();
