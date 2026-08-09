/** Form — Input, TextArea, Select, Checkbox, Switch, ImageUpload. */

import { esc } from "./_utils.js";
import { Button } from "./Button.js";

/**
 * @param {object} opts
 * @param {string} opts.label
 * @param {string} opts.name
 * @param {string} [opts.type]
 * @param {string} [opts.value]
 * @param {string} [opts.placeholder]
 * @param {string} [opts.help]
 * @param {string} [opts.error]
 * @param {boolean} [opts.required]
 */
export function Input({
  label, name, type = "text", value = "", placeholder = "", help = "", error = "", required = false,
}) {
  const id = `bos-field-${name}`;
  return `<div class="bos-field bos-ui-field${error ? " bos-ui-field--error" : ""}">
    <label class="bos-label" for="${id}">${esc(label)}${required ? " *" : ""}</label>
    <input class="bos-input bos-ui-input" type="${esc(type)}" id="${id}" name="${esc(name)}" value="${esc(value)}" placeholder="${esc(placeholder)}"${required ? " required" : ""}${error ? ` aria-invalid="true" aria-describedby="${id}-error"` : ""}>
    ${help ? `<p class="bos-field-help cp-muted" id="${id}-help">${esc(help)}</p>` : ""}
    ${error ? `<p class="bos-ui-field__error" id="${id}-error" role="alert">${esc(error)}</p>` : ""}
  </div>`;
}

export function TextArea({ label, name, value = "", placeholder = "", help = "", error = "", rows = 3, required = false }) {
  const id = `bos-field-${name}`;
  return `<div class="bos-field bos-ui-field${error ? " bos-ui-field--error" : ""}">
    <label class="bos-label" for="${id}">${esc(label)}${required ? " *" : ""}</label>
    <textarea class="bos-input bos-ui-input" id="${id}" name="${esc(name)}" placeholder="${esc(placeholder)}" rows="${rows}"${required ? " required" : ""}>${esc(value)}</textarea>
    ${help ? `<p class="bos-field-help cp-muted">${esc(help)}</p>` : ""}
    ${error ? `<p class="bos-ui-field__error" role="alert">${esc(error)}</p>` : ""}
  </div>`;
}

export function Select({ label, name, optionsHtml = "", value = "", help = "", error = "", required = false }) {
  const id = `bos-field-${name}`;
  return `<div class="bos-field bos-ui-field${error ? " bos-ui-field--error" : ""}">
    <label class="bos-label" for="${id}">${esc(label)}${required ? " *" : ""}</label>
    <select class="bos-input bos-ui-input" id="${id}" name="${esc(name)}"${required ? " required" : ""}>${optionsHtml}</select>
    ${help ? `<p class="bos-field-help cp-muted">${esc(help)}</p>` : ""}
    ${error ? `<p class="bos-ui-field__error" role="alert">${esc(error)}</p>` : ""}
  </div>`;
}

export function Checkbox({ label, name, checked = false, help = "" }) {
  const id = `bos-field-${name}`;
  return `<label class="bos-ui-checkbox" for="${id}">
    <input type="checkbox" id="${id}" name="${esc(name)}"${checked ? " checked" : ""}>
    <span>${esc(label)}</span>
    ${help ? `<span class="bos-field-help cp-muted">${esc(help)}</span>` : ""}
  </label>`;
}

export function Switch({ label, name, checked = false }) {
  const id = `bos-field-${name}`;
  return `<label class="bos-ui-switch" for="${id}">
    <input type="checkbox" role="switch" id="${id}" name="${esc(name)}"${checked ? " checked" : ""}>
    <span class="bos-ui-switch__track" aria-hidden="true"></span>
    <span>${esc(label)}</span>
  </label>`;
}

export function ImageUpload({ label, name, value = "", help = "" }) {
  const id = `bos-field-${name}`;
  return `<div class="bos-field bos-ui-field">
    <label class="bos-label" for="${id}">${esc(label)}</label>
    <input class="bos-input bos-ui-input" type="url" id="${id}" name="${esc(name)}" value="${esc(value)}" placeholder="https://…">
    ${value ? `<img class="bos-ui-image-preview" src="${esc(value)}" alt="">` : ""}
    ${help ? `<p class="bos-field-help cp-muted">${esc(help)}</p>` : ""}
  </div>`;
}

/** Standard form action row. */
export function FormActions({ primary = "Save", secondary = "Cancel", primaryId = "", danger = "", loading = false }) {
  return `<div class="bos-form-actions bos-ui-form-actions">
    ${secondary ? Button({ variant: "ghost", label: secondary, id: "bos-form-cancel", type: "button" }) : ""}
    ${danger ? Button({ variant: "danger", label: danger, id: "bos-form-danger", type: "button" }) : ""}
    ${Button({ variant: "primary", label: primary, id: primaryId || "bos-form-submit", type: "submit", loading })}
  </div>`;
}

/** @deprecated */
export function formField(opts) {
  if (opts.type === "textarea") return TextArea({ label: opts.title, name: opts.name, value: opts.value, placeholder: opts.placeholder, help: opts.help });
  if (opts.type === "select") return Select({ label: opts.title, name: opts.name, optionsHtml: opts.optionsHtml, help: opts.help });
  return Input({ label: opts.title, name: opts.name, type: opts.type, value: opts.value, placeholder: opts.placeholder, help: opts.help });
}

export const formActions = FormActions;
