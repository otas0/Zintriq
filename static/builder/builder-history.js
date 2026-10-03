/** Small immutable history stack for Builder undo/redo. */

const clone = (value) => structuredClone(value);

export function createBuilderHistory(initial, limit = 80) {
  let current = clone(initial);
  let past = [];
  let future = [];

  return {
    get value() { return current; },
    replace(value, { record = true } = {}) {
      if (record) {
        past.push(clone(current));
        if (past.length > limit) past.shift();
        future = [];
      }
      current = clone(value);
      return current;
    },
    update(mutator) {
      const next = clone(current);
      mutator(next);
      return this.replace(next);
    },
    commitFrom(previous, value) {
      past.push(clone(previous));
      if (past.length > limit) past.shift();
      future = [];
      current = clone(value);
      return clone(current);
    },
    undo() {
      if (!past.length) return null;
      future.push(clone(current));
      current = past.pop();
      return clone(current);
    },
    redo() {
      if (!future.length) return null;
      past.push(clone(current));
      current = future.pop();
      return clone(current);
    },
    get canUndo() { return past.length > 0; },
    get canRedo() { return future.length > 0; },
  };
}
