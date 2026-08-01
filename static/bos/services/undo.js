/** @type {{ label: string, run: () => void } | null} */
let pendingUndo = null;

export function pushUndo(label, run) {
  pendingUndo = { label, run };
}

export function consumeUndo() {
  const action = pendingUndo;
  pendingUndo = null;
  return action;
}

export function peekUndo() {
  return pendingUndo;
}

export function clearUndo() {
  pendingUndo = null;
}
