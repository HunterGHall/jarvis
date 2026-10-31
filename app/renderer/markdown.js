// A small, safe Markdown renderer: everything is escaped first, then formatting is added.
(function () {
  const escapeHtml = (text) =>
    text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  function inline(text) {
    const codes = [];
    text = text.replace(/`([^`]+)`/g, (_, code) => `\u0000${codes.push(`<code>${code}</code>`) - 1}\u0000`);
    text = text
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
      .replace(/!?\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" rel="noreferrer">$1</a>')
      .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" rel="noreferrer">$2</a>');
    return text.replace(/\u0000(\d+)\u0000/g, (_, index) => codes[Number(index)]);
  }

  function render(markdown) {
    const lines = escapeHtml(markdown).split("\n");
    const out = [];
    let list = null;
    let paragraph = [];

    const flushParagraph = () => {
      if (paragraph.length) out.push(`<p>${inline(paragraph.join("<br>"))}</p>`);
      paragraph = [];
    };
    const closeList = () => {
      if (list) out.push(`</${list}>`);
      list = null;
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^```/.test(line)) {
        flushParagraph();
        closeList();
        const code = [];
        for (i++; i < lines.length && !/^```/.test(lines[i]); i++) code.push(lines[i]);
        out.push(`<pre><code>${code.join("\n")}</code></pre>`);
        continue;
      }
      if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
        flushParagraph();
        closeList();
        const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((cell) => inline(cell.trim()));
        const head = cells(line);
        const rows = [];
        for (i += 2; i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i]); i++) rows.push(cells(lines[i]));
        i--;
        out.push(
          `<div class="table"><table><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
            rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") +
            "</tbody></table></div>"
        );
        continue;
      }
      let match;
      if ((match = line.match(/^(#{1,6})\s+(.*)$/))) {
        flushParagraph();
        closeList();
        const level = Math.min(match[1].length + 1, 5);
        out.push(`<h${level}>${inline(match[2])}</h${level}>`);
      } else if ((match = line.match(/^\s*[-*•]\s+(.*)$/))) {
        flushParagraph();
        if (list !== "ul") (closeList(), out.push("<ul>"), (list = "ul"));
        out.push(`<li>${inline(match[1])}</li>`);
      } else if ((match = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
        flushParagraph();
        if (list !== "ol") (closeList(), out.push("<ol>"), (list = "ol"));
        out.push(`<li>${inline(match[1])}</li>`);
      } else if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
        flushParagraph();
        closeList();
        out.push("<hr>");
      } else if (!line.trim()) {
        flushParagraph();
        closeList();
      } else {
        closeList();
        paragraph.push(line);
      }
    }
    flushParagraph();
    closeList();
    return out.join("");
  }

  window.renderMarkdown = render;
})();
