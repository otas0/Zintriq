/** Customer hub — flash messages as bottom toasts. */

function dismissToast(toast) {
  if (!toast || toast.classList.contains("ch-toast--out")) return;
  toast.classList.add("ch-toast--out");
  window.setTimeout(() => toast.remove(), 280);
}

function initCustomerToasts() {
  const stack = document.getElementById("ch-toast-stack");
  if (!stack) return;

  stack.querySelectorAll(".ch-toast").forEach((toast) => {
    toast.querySelector(".ch-toast__close")?.addEventListener("click", () => dismissToast(toast));
    window.setTimeout(() => dismissToast(toast), 4200);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initCustomerToasts, { once: true });
} else {
  initCustomerToasts();
}
