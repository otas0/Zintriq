import { api, toast } from "./universal-api.js";

const dialog = document.getElementById("ub-create-dialog");
const form = document.getElementById("ub-create-form");
const projectList = document.getElementById("ub-project-list");
const templateList = document.getElementById("ub-template-list");

function openCreate(starter = "Website") {
  form.elements.starter.value = starter;
  form.elements.name.value = starter === "Something else" ? "" : `My ${starter}`;
  dialog.showModal(); setTimeout(() => form.elements.name.select(), 20);
}

document.querySelector("[data-create-blank]")?.addEventListener("click", () => openCreate());
document.querySelectorAll("[data-starter]").forEach((button) => button.addEventListener("click", () => openCreate(button.dataset.starter)));
document.querySelector("[data-scroll-templates]")?.addEventListener("click", () => document.getElementById("templates").scrollIntoView({ behavior: "smooth" }));
form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector('[value="default"]'); submit.disabled = true; submit.textContent = "Creating…";
  try {
    const project = await api.createProject({ name: form.elements.name.value.trim(), starter: form.elements.starter.value });
    location.href = `/app/builder/${project.id}`;
  } catch (error) { toast(error.message, "error"); submit.disabled = false; submit.textContent = "Create project"; }
});

async function load() {
  try {
    const [{ projects }, { templates }] = await Promise.all([api.projects(), api.templates()]);
    projectList.innerHTML = projects.length ? projects.map((project) => `
      <button class="ub-project-card ${project.legacy_source_type === "workspace_system" ? "ub-project-card--template" : ""}" data-project="${project.id}"><div><span class="ub-badge">${project.legacy_source_type === "workspace_system" ? "Official template" : project.status}</span><h3>${escapeHtml(project.name)}</h3><p>${escapeHtml(project.legacy_source_type === "workspace_system" ? "Business app + customer site · all existing functions" : project.description || "Open and continue building")}</p></div><div class="ub-project-card__meta"><span>${project.surface_count || 0} surfaces</span><span>${project.document_count || 0} documents</span></div></button>`).join("") : '<div class="ub-empty-panel"><strong>No projects yet</strong><p>Start blank and publish your first page.</p></div>';
    projectList.querySelectorAll("[data-project]").forEach((button) => button.addEventListener("click", () => location.href = `/app/builder/${button.dataset.project}`));
    templateList.innerHTML = templates
      .filter((item) => item.id !== "zintriq-system")
      .map((item) => `<article class="ub-project-card"><div><span class="ub-badge ${item.is_official ? "ub-badge--official" : ""}">${item.is_official ? "Official" : "Community"}</span><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.description)}</p></div><button class="ub-btn ub-btn--primary" data-template="${escapeHtml(item.id)}">Use template</button></article>`)
      .join("");
    templateList.querySelectorAll("[data-template]").forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true; button.textContent = "Creating…";
      try { const template = templates.find((item) => item.id === button.dataset.template); const project = await api.createProject({ template_id: button.dataset.template, name: `My ${template?.name || "Project"}` }); location.href = `/app/builder/${project.id}`; }
      catch (error) { toast(error.message, "error"); button.disabled = false; button.textContent = "Use template"; }
    }));
  } catch (error) { projectList.innerHTML = `<div class="ub-empty-panel"><strong>Could not load projects</strong><p>${escapeHtml(error.message)}</p></div>`; }
}

function escapeHtml(value = "") { const el = document.createElement("span"); el.textContent = value; return el.innerHTML; }
load();
