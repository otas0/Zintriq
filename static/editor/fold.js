/**
 * Indentation-based folding helpers for the textarea editor.
 */
(function (global) {
  function lineIndent(line) {
    const m = /^(\s*)/.exec(line || "");
    return m ? m[1].replace(/\t/g, "  ").length : 0;
  }

  /** @returns {{start:number,end:number}[]} 0-based inclusive ranges that can fold */
  function computeFolds(text) {
    const lines = (text || "").split("\n");
    const folds = [];
    for (let i = 0; i < lines.length; i++) {
      const indent = lineIndent(lines[i]);
      const trimmed = (lines[i] || "").trim();
      if (!trimmed) continue;
      let j = i + 1;
      let end = -1;
      while (j < lines.length) {
        const t = (lines[j] || "").trim();
        if (!t) {
          j += 1;
          continue;
        }
        const ind = lineIndent(lines[j]);
        if (ind > indent) {
          end = j;
          j += 1;
          continue;
        }
        break;
      }
      if (end > i) folds.push({ start: i, end });
    }
    return folds;
  }

  /**
   * Apply active folds (by start line) to produce display text + line map.
   * @param {string} full
   * @param {Set<number>|number[]} foldedStarts
   */
  function applyFolds(full, foldedStarts) {
    const starts = foldedStarts instanceof Set ? foldedStarts : new Set(foldedStarts || []);
    const lines = (full || "").split("\n");
    const all = computeFolds(full);
    const byStart = new Map(all.map((f) => [f.start, f]));
    const out = [];
    const map = []; // displayLine -> sourceLine
    let i = 0;
    while (i < lines.length) {
      out.push(lines[i]);
      map.push(i);
      const fold = byStart.get(i);
      if (fold && starts.has(i)) {
        const n = fold.end - fold.start;
        out[out.length - 1] = `${lines[i]}  ⋯ ${n} lines`;
        i = fold.end + 1;
        continue;
      }
      i += 1;
    }
    return { text: out.join("\n"), map, folds: all };
  }

  /**
   * Map caret offset in display text back to full-text offset (approx).
   */
  function displayOffsetToFull(full, foldedStarts, displayOffset) {
    const { text, map } = applyFolds(full, foldedStarts);
    const dLines = text.slice(0, Math.max(0, displayOffset)).split("\n");
    const dLine = dLines.length - 1;
    const dCol = dLines[dLines.length - 1].length;
    const srcLine = map[dLine] != null ? map[dLine] : 0;
    const fullLines = full.split("\n");
    let off = 0;
    for (let i = 0; i < srcLine && i < fullLines.length; i++) off += fullLines[i].length + 1;
    const maxCol = (fullLines[srcLine] || "").length;
    off += Math.min(dCol, maxCol);
    return off;
  }

  global.ZintriqFold = { computeFolds, applyFolds, displayOffsetToFull, lineIndent };
})(typeof window !== "undefined" ? window : globalThis);
