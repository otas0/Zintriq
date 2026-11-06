/** Minimal self-hosted syntax highlighter (no CDN). */
window.ZintriqSyntax = (() => {
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };
  function escape(s) {
    return String(s).replace(/[&<>]/g, (c) => ESC[c]);
  }

  const KEYWORDS = {
    python: /\b(False|True|None|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b/g,
    javascript: /\b(async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|false|finally|for|function|if|import|in|instanceof|let|new|null|return|static|super|switch|this|throw|true|try|typeof|undefined|var|void|while|with|yield)\b/g,
    typescript: /\b(async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|false|finally|for|function|if|import|in|instanceof|interface|let|new|null|return|static|super|switch|this|throw|true|try|type|typeof|undefined|var|void|while|with|yield)\b/g,
  };

  function paint(text, language) {
    let html = escape(text);
    html = html.replace(/(^|[^:])(\/\/.*)$/gm, "$1<span class=\"tok-com\">$2</span>");
    html = html.replace(/(#.*)$/gm, "<span class=\"tok-com\">$1</span>");
    html = html.replace(/(&quot;|&#39;|")(?:\\.|(?!\1)[^\\])*\1/g, (m) => `<span class="tok-str">${m}</span>`);
    html = html.replace(/`(?:\\.|[^\\`])*`/g, (m) => `<span class="tok-str">${m}</span>`);
    const re = KEYWORDS[language];
    if (re) {
      html = html.replace(re, '<span class="tok-kw">$1</span>');
    }
    html = html.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="tok-num">$1</span>');
    return html + (text.endsWith("\n") ? "" : "\n");
  }

  return { paint, escape };
})();
