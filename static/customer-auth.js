/** Customer auth — OTP verification, onboarding wizard, password login. */

const AUTH_HEADER = "X-Customer-Auth";

const state = {
  panel: "login",
  signupChannel: "email",
  loginChannel: "email",
  verifyTarget: "",
  verifyMasked: "",
  setupDraft: {},
  panelStack: [],
  skipPassword: false,
  signupMode: "new",
};

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || "";
}

function rememberDeviceChecked(root) {
  const scope = root || authRoot() || document;
  const cb = scope.querySelector('input[name="remember_device"]');
  return cb ? cb.checked : true;
}

function authRoot() {
  return document.getElementById("customer-auth-root");
}

function setNextUrl(path) {
  document.querySelectorAll("[data-auth-next]").forEach((el) => {
    el.value = path || window.location.pathname + window.location.search;
  });
}

function showError(id, message) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message || "";
  el.hidden = !message;
}

function clearErrors(prefix) {
  document.querySelectorAll(`[id^="${prefix}"]`).forEach((el) => {
    if (el.classList.contains("ig-auth__error")) showError(el.id, "");
  });
}

function showPanel(name, { push = true } = {}) {
  const root = authRoot();
  if (!root) return;
  if (push && state.panel && state.panel !== name) {
    state.panelStack.push(state.panel);
  }
  state.panel = name;
  root.querySelectorAll("[data-auth-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.authPanel !== name;
  });
  const back = document.getElementById("ig-auth-back");
  if (back) back.hidden = state.panelStack.length === 0;
}

function goBack() {
  const prev = state.panelStack.pop();
  if (prev) showPanel(prev, { push: false });
  else showPanel("login", { push: false });
}

async function authFetch(url, { method = "POST", body } = {}) {
  const headers = { [AUTH_HEADER]: "1", "X-CSRF-Token": csrfToken() };
  const opts = { method, credentials: "same-origin", headers };
  if (method !== "GET" && body !== undefined) {
    if (body instanceof FormData) {
      if (!body.get("csrf_token")) body.set("csrf_token", csrfToken());
      opts.body = body;
    } else {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify({ csrf_token: csrfToken(), ...body });
    }
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

function authErrorMessage(data, fallback) {
  if (data?.error) return data.error;
  if (data?.csrf) return "Session expired. Refresh the page and try again.";
  return fallback;
}

function otpValue(containerId) {
  return [...document.querySelectorAll(`#${containerId} .ig-auth__otp-digit`)]
    .map((el) => el.value)
    .join("");
}

function bindOtpInputs(containerId) {
  const inputs = [...document.querySelectorAll(`#${containerId} .ig-auth__otp-digit`)];
  inputs.forEach((input, idx) => {
    input.addEventListener("input", () => {
      input.value = input.value.replace(/\D/g, "").slice(-1);
      if (input.value && inputs[idx + 1]) inputs[idx + 1].focus();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !input.value && inputs[idx - 1]) inputs[idx - 1].focus();
    });
    input.addEventListener("paste", (e) => {
      e.preventDefault();
      const text = (e.clipboardData?.getData("text") || "").replace(/\D/g, "").slice(0, 6);
      text.split("").forEach((ch, i) => {
        if (inputs[i]) inputs[i].value = ch;
      });
      inputs[Math.min(text.length, 5)]?.focus();
    });
  });
}

function startResendTimer(btnId, seconds = 60) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  let left = seconds;
  btn.disabled = true;
  btn.textContent = `Resend code (${left}s)`;
  const timer = setInterval(() => {
    left -= 1;
    if (left <= 0) {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = "Resend code";
      return;
    }
    btn.textContent = `Resend code (${left}s)`;
  }, 1000);
}

function setChannelTabs(kind, channel) {
  const prefix = kind === "signup" ? "signup" : "login";
  document.querySelectorAll(`[data-${prefix}-channel]`).forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset[`${prefix}Channel`] === channel);
  });
  const field = document.getElementById(`ig-${prefix}-target-field`);
  const input = field?.querySelector("input");
  if (!input) return;
  if (channel === "phone") {
    input.type = "tel";
    input.placeholder = "Phone (+60123456789)";
    input.autocomplete = "tel";
  } else {
    input.type = "email";
    input.placeholder = "Email";
    input.autocomplete = "email";
  }
  const phoneNote = document.getElementById("ig-signup-phone-note");
  if (phoneNote && prefix === "signup") {
    phoneNote.hidden = channel !== "phone";
  }
}

async function checkUsername(inputEl, hintEl) {
  const q = inputEl.value.trim().toLowerCase();
  if (!q) {
    hintEl.textContent = "";
    return;
  }
  const { data } = await authFetch(`/account/username/check?q=${encodeURIComponent(q)}`, { method: "GET" });
  if (data.available) {
    hintEl.textContent = `@${data.username} is available`;
    hintEl.className = "ig-auth__hint ig-auth__hint--ok";
  } else {
    hintEl.textContent = data.error || "Username taken";
    hintEl.className = "ig-auth__hint ig-auth__hint--bad";
  }
}

function setSignupPasswordFields(skip) {
  state.skipPassword = skip;
  const wrap = document.getElementById("ig-signup-password-fields");
  const title = document.getElementById("ig-signup-setup-title");
  const lead = document.getElementById("ig-signup-setup-lead");
  if (wrap) wrap.hidden = skip;
  wrap?.querySelectorAll("input").forEach((el) => {
    el.required = !skip;
    if (skip) el.value = "";
  });
  if (title) title.textContent = skip ? "Set up shopping" : "Set up account";
  if (lead && !skip) lead.textContent = "Pick a username and password.";
  if (lead && skip) lead.textContent = "Pick a username for personal mode. Your business password stays the same.";
}

export function openCustomerAuth(mode = "login", opts = {}) {
  const root = authRoot();
  if (!root) {
    window.location.href = "/account?open=" + (mode === "signup" ? "signup" : "login");
    return;
  }
  state.panelStack = [];
  state.setupDraft = {};
  state.skipPassword = false;
  state.signupMode = "new";
  setSignupPasswordFields(false);
  setNextUrl(opts.next || window.location.pathname + window.location.search);
  clearErrors("ig-");
  const start = mode === "signup" ? "signup-start" : "login";
  showPanel(start, { push: false });
  if (opts.email) {
    const loginInput = document.querySelector("#ig-auth-login-form input[name=identifier]");
    if (loginInput) loginInput.value = opts.email;
    const signupInput = document.querySelector("#ig-signup-send-form input[name=target]");
    if (signupInput) signupInput.value = opts.email;
  }
  root.hidden = false;
  root.setAttribute("aria-hidden", "false");
  document.body.classList.add("ig-auth-open");
}

export function closeCustomerAuth() {
  const root = authRoot();
  if (!root) return;
  root.hidden = true;
  root.setAttribute("aria-hidden", "true");
  document.body.classList.remove("ig-auth-open");
  state.panelStack = [];
}

function bindAuthSheet() {
  const root = authRoot();
  if (!root) return;

  bindOtpInputs("ig-signup-otp");
  bindOtpInputs("ig-login-otp");

  root.querySelectorAll("[data-auth-close]").forEach((el) => {
    el.addEventListener("click", closeCustomerAuth);
  });
  document.getElementById("ig-auth-back")?.addEventListener("click", goBack);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !root.hidden) closeCustomerAuth();
  });

  document.body.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-auth-open]");
    if (!trigger) return;
    e.preventDefault();
    openCustomerAuth(trigger.dataset.authOpen || "login", {
      email: trigger.dataset.authEmail || "",
    });
  });

  root.querySelectorAll("[data-auth-goto]").forEach((btn) => {
    btn.addEventListener("click", () => showPanel(btn.dataset.authGoto));
  });

  document.querySelectorAll("[data-signup-channel]").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.signupChannel = tab.dataset.signupChannel;
      setChannelTabs("signup", state.signupChannel);
    });
  });
  document.querySelectorAll("[data-login-channel]").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.loginChannel = tab.dataset.loginChannel;
      setChannelTabs("login", state.loginChannel);
    });
  });

  const loginForm = document.getElementById("ig-auth-login-form");
  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("ig-auth-login-error", "");
    const fd = new FormData(loginForm);
    fd.set("email", fd.get("identifier") || "");
    fd.set("remember_device", rememberDeviceChecked(loginForm) ? "1" : "0");
    fd.set("csrf_token", csrfToken());
    const submit = loginForm.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const res = await fetch("/account/login", {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: { [AUTH_HEADER]: "1", "X-CSRF-Token": csrfToken() },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        showError("ig-auth-login-error", authErrorMessage(data, "Could not sign in."));
        return;
      }
      closeCustomerAuth();
      window.location.assign(data.redirect || "/home");
    } finally {
      submit.disabled = false;
    }
  });

  document.getElementById("ig-signup-send-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("ig-signup-send-error", "");
    const consent = e.target.querySelector('input[name="legal_consent"]');
    if (consent && !consent.checked) {
      showError("ig-signup-send-error", "Please accept the Terms of Service and Privacy Policy to continue.");
      return;
    }
    const target = e.target.querySelector('input[name="target"]').value.trim();
    const { res, data } = await authFetch("/account/verify/send", {
      body: { channel: state.signupChannel, target, purpose: "signup", legal_consent: true },
    });
    if (!res.ok || !data.ok) {
      showError("ig-signup-send-error", authErrorMessage(data, "Could not send code."));
      return;
    }
    state.signupMode = data.mode || "new";
    if (data.hint) {
      showError("ig-signup-send-error", "");
      const lead = document.querySelector('[data-auth-panel="signup-start"] .ig-auth__lead');
      if (lead) lead.textContent = data.hint;
    }
    state.verifyTarget = target;
    state.verifyMasked = data.masked;
    document.getElementById("ig-signup-code-lead").textContent = `Code sent to ${data.masked}`;
    showPanel("signup-code");
    startResendTimer("ig-signup-resend", data.resend_seconds || 60);
  });

  document.getElementById("ig-signup-resend")?.addEventListener("click", async () => {
    await authFetch("/account/verify/send", {
      body: { channel: state.signupChannel, target: state.verifyTarget, purpose: "signup" },
    });
    startResendTimer("ig-signup-resend", 60);
  });

  document.getElementById("ig-signup-code-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("ig-signup-code-error", "");
    const code = otpValue("ig-signup-otp");
    const { res, data } = await authFetch("/account/verify/check", {
      body: { channel: state.signupChannel, target: state.verifyTarget, code, purpose: "signup" },
    });
    if (!res.ok || !data.ok) {
      showError("ig-signup-code-error", authErrorMessage(data, "Invalid code."));
      return;
    }
    state.signupMode = data.mode || "new";
    setSignupPasswordFields(Boolean(data.skip_password));
    if (data.lead) {
      const lead = document.getElementById("ig-signup-setup-lead");
      if (lead) lead.textContent = data.lead;
    }
    const usernameInput = document.getElementById("ig-signup-username");
    if (usernameInput) usernameInput.value = data.username || "";
    showPanel("signup-setup");
  });

  const usernameInput = document.getElementById("ig-signup-username");
  const usernameHint = document.getElementById("ig-username-hint");
  let usernameTimer;
  usernameInput?.addEventListener("input", () => {
    clearTimeout(usernameTimer);
    usernameTimer = setTimeout(() => checkUsername(usernameInput, usernameHint), 350);
  });

  document.getElementById("ig-signup-setup-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("ig-signup-setup-error", "");
    const fd = new FormData(e.target);
    if (!state.skipPassword) {
      if (fd.get("password") !== fd.get("confirm_password")) {
        showError("ig-signup-setup-error", "Passwords do not match.");
        return;
      }
      if ((fd.get("password") || "").length < 12) {
        showError("ig-signup-setup-error", "Use a password with at least 12 characters.");
        return;
      }
    }
    state.setupDraft = Object.fromEntries(fd.entries());
    state.setupDraft.remember_device = fd.has("remember_device");
    document.getElementById("ig-photo-username").value = state.setupDraft.username || "";
    document.getElementById("ig-photo-password").value = state.setupDraft.password || "";
    document.getElementById("ig-photo-confirm").value = state.setupDraft.confirm_password || "";
    document.getElementById("ig-photo-display").value = state.setupDraft.display_name || "";
    showPanel("signup-photo");
  });

  async function finishSignup(form, skipAvatar = false) {
    showError("ig-signup-photo-error", "");
    const fd = new FormData(form);
    fd.set("csrf_token", csrfToken());
    if (state.setupDraft && "remember_device" in state.setupDraft) {
      fd.set("remember_device", state.setupDraft.remember_device ? "1" : "0");
    }
    if (skipAvatar) fd.delete("avatar");
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const res = await fetch("/account/onboarding/complete", {
        method: "POST",
        body: fd,
        credentials: "same-origin",
        headers: { [AUTH_HEADER]: "1", "X-CSRF-Token": csrfToken() },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        showError("ig-signup-photo-error", data.error || "Could not finish signup.");
        return;
      }
      closeCustomerAuth();
      window.location.assign(data.redirect || "/home");
    } finally {
      submit.disabled = false;
    }
  }

  document.getElementById("ig-signup-photo-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    finishSignup(e.target, false);
  });
  document.getElementById("ig-signup-skip-photo")?.addEventListener("click", () => {
    finishSignup(document.getElementById("ig-signup-photo-form"), true);
  });

  document.querySelector("#ig-signup-photo-form input[type=file]")?.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    const preview = document.getElementById("ig-avatar-preview");
    if (!file || !preview) return;
    preview.style.backgroundImage = `url(${URL.createObjectURL(file)})`;
    preview.textContent = "";
  });

  document.getElementById("ig-login-send-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("ig-login-send-error", "");
    const target = e.target.querySelector('input[name="target"]').value.trim();
    const { res, data } = await authFetch("/account/verify/send", {
      body: { channel: state.loginChannel, target, purpose: "login" },
    });
    if (!res.ok || !data.ok) {
      showError("ig-login-send-error", authErrorMessage(data, "Could not send code."));
      return;
    }
    state.verifyTarget = target;
    document.getElementById("ig-login-code-lead").textContent = `Code sent to ${data.masked}`;
    document.getElementById("ig-login-send-form").hidden = true;
    document.getElementById("ig-login-code-form").hidden = false;
    startResendTimer("ig-login-resend", data.resend_seconds || 60);
  });

  document.getElementById("ig-login-resend")?.addEventListener("click", async () => {
    await authFetch("/account/verify/send", {
      body: { channel: state.loginChannel, target: state.verifyTarget, purpose: "login" },
    });
    startResendTimer("ig-login-resend", 60);
  });

  document.getElementById("ig-login-code-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("ig-login-code-error", "");
    const code = otpValue("ig-login-otp");
    const next = document.querySelector("[data-auth-next]")?.value || "/home";
    const loginCodeForm = document.getElementById("ig-login-code-form");
    const { res, data } = await authFetch("/account/verify/check", {
      body: {
        channel: state.loginChannel,
        target: state.verifyTarget,
        code,
        purpose: "login",
        next,
        remember_device: rememberDeviceChecked(loginCodeForm),
      },
    });
    if (!res.ok || !data.ok) {
      showError("ig-login-code-error", authErrorMessage(data, "Invalid code."));
      return;
    }
    closeCustomerAuth();
    window.location.assign(data.redirect || "/home");
  });

  const params = new URLSearchParams(window.location.search);
  const open = params.get("open");
  if (open === "login" || open === "signup" || open === "signup-start") {
    openCustomerAuth(open === "login" ? "login" : "signup", { email: params.get("email") || "" });
    params.delete("open");
    params.delete("email");
    const qs = params.toString();
    window.history.replaceState({}, "", window.location.pathname + (qs ? `?${qs}` : ""));
  }
}

bindAuthSheet();
