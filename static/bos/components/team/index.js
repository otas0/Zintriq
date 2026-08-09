/** Team domain components. */

import { esc } from "../ui/_utils.js";
import { StatusBadge } from "../ui/Badge.js";
import { openModal } from "../ui/Modal.js";
import { Input, Select } from "../ui/Form.js";

export function MemberCard(member) {
  const name = member.display_name || member.email || "Member";
  const initials = name.trim().split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  const role = member.mvp_role ? String(member.mvp_role).charAt(0).toUpperCase() + String(member.mvp_role).slice(1) : (member.role === "administrator" || member.role === "manager" ? "Admin" : member.role === "owner" ? "Owner" : "Member");

  return `<article class="merchant-member-card bos-ui-member-card" data-id="${member.user_id}">
    <div class="merchant-member-card__avatar" aria-hidden="true">${esc(initials)}</div>
    <div class="merchant-member-card__body">
      <h3 class="merchant-member-card__name">${esc(name)}</h3>
      <p class="merchant-member-card__email">${esc(member.email || "")}</p>
      <div class="merchant-member-card__foot">
        ${StatusBadge(member.status)}
        <span class="merchant-member-card__role">${esc(role)}</span>
      </div>
    </div>
  </article>`;
}

/**
 * Invite member modal — real invitation flow via onSubmit callback.
 * @param {{ roles: string[], onSubmit: (data: { email: string, role: string }) => Promise<void> }} opts
 */
export function InviteMemberModal({ roles = ["administrator", "member"], onSubmit }) {
  const roleLabel = (r) => {
    if (r === "administrator" || r === "admin" || r === "manager") return "Admin";
    if (r === "member" || r === "viewer") return "Member";
    return r;
  };
  const roleOptions = roles.filter((r) => r !== "owner").map((r) =>
    `<option value="${esc(r)}">${esc(roleLabel(r))}</option>`
  ).join("");

  openModal({
    title: "Invite member",
    bodyHtml: `<form id="bos-invite-member-form" class="bos-form bos-ui-form">
      ${Input({ label: "Email", name: "email", type: "email", placeholder: "colleague@company.com", required: true })}
      ${Select({ label: "Role", name: "role", optionsHtml: roleOptions, help: "They must sign in with this email to accept." })}
    </form>`,
    primaryLabel: "Send invitation",
    onPrimary: async () => {
      const form = document.getElementById("bos-invite-member-form");
      if (!(form instanceof HTMLFormElement)) return;
      const fd = new FormData(form);
      const email = String(fd.get("email") || "").trim();
      const role = String(fd.get("role") || "member");
      if (!email) throw new Error("Email required");
      await onSubmit({ email, role });
    },
  });
}

export const memberCard = MemberCard;
