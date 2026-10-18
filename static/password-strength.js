const LABELS = {
  0: "Very weak",
  1: "Weak",
  2: "Fair",
  3: "Strong",
  4: "Very strong",
};

let zxcvbnFn = null;
let timer = null;

async function loadZxcvbn() {
  const [{ zxcvbn, zxcvbnOptions }, common] = await Promise.all([
    import("https://cdn.jsdelivr.net/npm/@zxcvbn-ts/core@3.0.4/+esm"),
    import("https://cdn.jsdelivr.net/npm/@zxcvbn-ts/language-common@3.0.4/+esm"),
  ]);
  zxcvbnOptions.setOptions({
    dictionary: { ...common.dictionary },
    graphs: common.adjacencyGraphs,
  });
  zxcvbnFn = zxcvbn;
}

function bind(input) {
  const hint =
    (input.form && input.form.querySelector("[data-password-hint]")) ||
    document.querySelector("[data-password-hint]");
  if (!hint) return;
  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      const value = input.value || "";
      if (!value) {
        hint.textContent = "";
        return;
      }
      if (!zxcvbnFn) {
        hint.textContent = value.length < 10 ? "Use at least 10 characters." : "";
        return;
      }
      const result = zxcvbnFn(value);
      const score = result && typeof result.score === "number" ? result.score : 0;
      hint.textContent = LABELS[score] || LABELS[0];
    }, 500);
  });
}

loadZxcvbn().catch(() => {});
document.querySelectorAll("[data-password-input]").forEach(bind);
