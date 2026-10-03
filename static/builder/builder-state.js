import { componentDefaults } from "./component-registry.js";

export function newNodeKey(prefix = "blk") {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

export function createBuilderDraft(experience) {
  return {
    name: experience.name || "",
    description: experience.description || "",
    branding: {
      business_name: experience.branding?.business_name || "",
      logo_url: experience.branding?.logo_url || "",
      background: experience.branding?.background || "",
      theme: experience.branding?.theme || "light",
      language: experience.branding?.language || "en",
    },
    blocks: (experience.blocks || []).map((block) => ({
      ...block,
      key: block.key || block.block_id || newNodeKey(),
      content: { ...componentDefaults(block.type), ...(block.content || {}) },
    })),
    actions: (experience.actions || []).map((action) => ({
      ...action,
      key: action.key || action.action_id || newNodeKey("act"),
      configuration: { ...(action.configuration || {}) },
    })),
  };
}

export function addBlock(draft, type, preset = null) {
  const block = {
    key: newNodeKey(),
    type,
    content: { ...componentDefaults(type), ...(preset || {}) },
  };
  draft.blocks.push(block);
  return block;
}

export function serializeBlocks(blocks) {
  return blocks.map((block, order) => ({
    key: block.key,
    type: block.type,
    content: block.content || {},
    order,
  }));
}

export function serializeActions(actions) {
  return actions.map((action, order) => ({
    key: action.key,
    type: action.type,
    label: action.label,
    configuration: action.configuration || {},
    order,
  }));
}
