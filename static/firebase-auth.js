import { initializeApp } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyAJNQEZi-tWkMKQrIBzLwULea40taW_wOw",
  authDomain: "business-copilot-877a3.firebaseapp.com",
  projectId: "business-copilot-877a3",
  storageBucket: "business-copilot-877a3.firebasestorage.app",
  messagingSenderId: "813195132440",
  appId: "1:813195132440:web:1e246dc0ebe161bb9bcd6d"
};

const defaultLabels = new Map([
  ["login", "Continue with Google"],
  ["signup", "Sign up with Google"],
]);

document.querySelectorAll("[data-google-intent]").forEach((button) => {
  const intent = button.dataset.googleIntent || "login";
  const defaultLabel = defaultLabels.get(intent) || "Continue with Google";
  const card = button.closest(".mq-auth-card") || button.closest(".ig-auth__panel");
  const message = card?.querySelector("#social-error, #ig-auth-social-error, .ig-auth__error[id]");

  button.addEventListener("click", async () => {
    if (message) message.hidden = true;
    button.disabled = true;
    button.textContent = "Opening Google…";
    try {
      const result = await signInWithPopup(getAuth(initializeApp(firebaseConfig)), new GoogleAuthProvider());
      const idToken = await result.user.getIdToken();
      const authUrl = button.dataset.authUrl || "/auth/firebase";
      const response = await fetch(authUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
        },
        credentials: "same-origin",
        body: JSON.stringify({
          idToken,
          intent,
          remember_device: (() => {
            const panel = button.closest(".ig-auth__panel") || button.closest(".mq-auth-card");
            const cb = panel?.querySelector('input[name="remember_device"]');
            return cb ? cb.checked : true;
          })(),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Google sign-in could not be completed.");
      if (data.needs_onboarding) {
        const { openGoogleOnboarding } = await import("./customer-auth.js");
        openGoogleOnboarding(data.username || "");
        return;
      }
      window.location.assign(data.next || "/home");
    } catch (error) {
      if (message) {
        message.textContent = error.message;
        message.hidden = false;
      }
      button.disabled = false;
      button.innerHTML = button.dataset.googleHtml || defaultLabel;
    }
  });

  button.dataset.googleHtml = button.innerHTML;
});
