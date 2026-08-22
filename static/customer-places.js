/** Places page — search and sort saved shops (Places-only tools). */

function sortItems(items, mode) {
  const copy = [...items];
  switch (mode) {
    case "name":
      return copy.sort((a, b) => (a.dataset.name || "").localeCompare(b.dataset.name || ""));
    case "open":
      return copy.sort((a, b) => {
        const openDiff = Number(b.dataset.open || 0) - Number(a.dataset.open || 0);
        if (openDiff !== 0) return openDiff;
        return (b.dataset.visited || "").localeCompare(a.dataset.visited || "");
      });
    case "visits":
      return copy.sort((a, b) => {
        const v = Number(b.dataset.visits || 0) - Number(a.dataset.visits || 0);
        if (v !== 0) return v;
        return (b.dataset.visited || "").localeCompare(a.dataset.visited || "");
      });
    case "recent":
    default:
      return copy.sort((a, b) => (b.dataset.visited || "").localeCompare(a.dataset.visited || ""));
  }
}

function initPlacesPage() {
  const list = document.getElementById("places-list");
  const search = document.getElementById("places-search");
  const sort = document.getElementById("places-sort");
  const empty = document.getElementById("places-empty-filter");
  if (!list) return;

  const items = () => [...list.querySelectorAll(".places-list__item")];

  const apply = () => {
    const q = (search?.value || "").trim().toLowerCase();
    const mode = sort?.value || "recent";
    const sorted = sortItems(items(), mode);
    sorted.forEach((el) => list.appendChild(el));

    let visible = 0;
    sorted.forEach((el) => {
      const name = el.dataset.name || "";
      const show = !q || name.includes(q);
      el.hidden = !show;
      if (show) visible += 1;
    });

    if (empty) empty.hidden = visible > 0 || !q;
  };

  search?.addEventListener("input", apply);
  sort?.addEventListener("change", apply);
  apply();
}

initPlacesPage();
