/** Capture scroll position for a scrollable element. */
export function captureScroll(el) {
  if (!el) return 0;
  return el.scrollTop;
}

/** Restore scroll position after DOM update. */
export function restoreScroll(el, top) {
  if (!el || top == null) return;
  requestAnimationFrame(() => {
    el.scrollTop = top;
  });
}

/** Toggle body class for action vs browse mode. */
export function setActionMode(active) {
  document.body.classList.toggle("bos-action-mode", active);
}
