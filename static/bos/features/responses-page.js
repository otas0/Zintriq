/** Business OS MVP — Responses page (uses component library). */

import { fetchJson, wsQuery } from "../services/bos-api.js";
import { openDrawer } from "../services/api.js";
import {
  EmptyState,
  Skeleton,
  PageHeader,
  Button,
  setPageActions,
  ResponseList,
  ResponseDetail,
} from "../components/index.js";

function typeLabel(record) {
  const t = record.type || record.feedback_type || record.source_type || record.source || "";
  if (String(t).includes("survey")) return "Survey";
  return "Feedback";
}

/** @param {HTMLElement} root @param {{ embedded?: boolean }} [opts] */
export async function mountResponsesPage(root, opts = {}) {
  const { embedded = false } = opts;
  root.innerHTML = Skeleton("page");
  if (!embedded) {
    setPageActions(Button({ variant: "primary", label: "Add customer QR", tag: "a", href: "/app/store#experiences", sm: true }));
  }

  let filter = "all";
  let searchQ = "";

  const load = async () => {
    const qParams = new URLSearchParams();
    if (searchQ.trim()) qParams.set("q", searchQ.trim());
    const listUrl = qParams.toString() ? `/api/responses?${qParams}` : "/api/responses";
    const records = await fetchJson(listUrl).catch(() => []);

    let list = Array.isArray(records) ? records : [];
    if (filter === "feedback") list = list.filter((r) => typeLabel(r) === "Feedback");
    else if (filter === "survey") list = list.filter((r) => typeLabel(r) === "Survey");

    root.innerHTML = embedded
      ? `<div id="resp-embedded"><div id="resp-list-mount"></div></div>`
      : `<div class="merchant-page">
      ${PageHeader({ title: "Responses", subtitle: "Customer feedback and survey answers from your experiences" })}
      <div id="resp-list-mount"></div>
    </div>`;

    ResponseList(root.querySelector("#resp-list-mount"), {
      records: list,
      filter,
      searchQ,
      onFilterChange: (id) => {
        filter = id;
        load().catch((err) => {
          root.innerHTML = EmptyState({ title: "Could not load responses", text: err.message });
        });
      },
      onSearch: (q) => {
        searchQ = q;
        load().catch((err) => {
          root.innerHTML = EmptyState({ title: "Could not load responses", text: err.message });
        });
      },
      onSelect: async (id) => {
        try {
          const record = await fetchJson(`/api/responses/${id}`);
          openDrawer(`Response #${record.id}`, ResponseDetail(record));
        } catch (err) {
          openDrawer("Response", EmptyState({ title: "Could not load", text: err.message }));
        }
      },
    });
  };

  try {
    await load();
  } catch (err) {
    root.innerHTML = EmptyState({ title: "Could not load responses", text: err.message });
  }
}
