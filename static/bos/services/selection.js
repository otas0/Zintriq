/** @typedef {import('../services/search.js').BosItem} BosItem */

export class SelectionService {
  constructor() {
    /** @type {Set<string|number>} */
    this.selected = new Set();
    /** @type {Set<(count: number) => void>} */
    this.listeners = new Set();
  }

  /** @param {string|number} id */
  toggle(id) {
    if (this.selected.has(id)) this.selected.delete(id);
    else this.selected.add(id);
    this.notify();
  }

  clear() {
    this.selected.clear();
    this.notify();
  }

  /** @param {(string|number)[]} ids */
  setAll(ids) {
    this.selected = new Set(ids);
    this.notify();
  }

  /** @param {(count: number) => void} fn */
  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  notify() {
    this.listeners.forEach((fn) => fn(this.selected.size));
  }

  get size() {
    return this.selected.size;
  }

  /** @param {string|number} id */
  has(id) {
    return this.selected.has(id);
  }
}

export const selection = new SelectionService();
