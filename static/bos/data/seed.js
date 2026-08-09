/** @typedef {import('../core/store.js').BosRecord} BosRecord */

/** Empty initial state — business data lives on the server. */
export const SEED_DATA = {
  organizations: [],
  workspaces: [],
  catalog: [],
  transactions: [],
  customers: [],
  team: [],
  assets: [],
  operations: [],
  documents: [],
  tags: [],
  activities: [],
};

export const COLLECTIONS = Object.keys(SEED_DATA);

export const BUSINESS_COLLECTIONS = COLLECTIONS.filter((c) => c !== "activities");
