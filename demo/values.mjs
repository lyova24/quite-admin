// Presentation helpers only: canonical record values stay unchanged in the Store.
export const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g,
  char => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[char]);

function prettyJSON(text) {
  JSON.parse(text);
  let output = "", depth = 0, quoted = false, escaped = false;
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (quoted) {
      output += char;
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (/\s/.test(char)) continue;
    else if (char === '"') { quoted = true; output += char; }
    else if (char === "{" || char === "[") {
      output += char;
      const next = text.slice(index + 1).trimStart()[0];
      if (next === "}" || next === "]") { output += next; index = text.indexOf(next, index + 1); }
      else { if (++depth > 40) throw new RangeError("depth"); output += "\n" + "  ".repeat(depth); }
    } else if (char === "}" || char === "]") output += "\n" + "  ".repeat(--depth) + char;
    else if (char === ",") output += ",\n" + "  ".repeat(depth);
    else if (char === ":") output += ": ";
    else output += char;
  }
  return output;
}

export function valueModel(field, value) {
  const kind = field.display || (field.urlTemplate ? "url" : "text");
  let text = value == null ? "" : String(value);
  if (field.urlTemplate && text) {
    const encoded = encodeURIComponent(text).replace(/[!'()*]/g,
      char => "%" + char.charCodeAt(0).toString(16).toUpperCase());
    text = field.urlTemplate.replaceAll("{value}", encoded);
  }
  if (kind === "json" && text && text.length <= 200000) {
    try { text = prettyJSON(text); } catch (_) { /* Invalid data remains escaped text. */ }
  }
  let href = null;
  if (kind === "url" && /^https?:\/\/[^/?#]/i.test(text)
    && text === text.trim() && !/[\u0000-\u001f\u007f\\]/.test(text)) {
    try {
      const url = new URL(text);
      if (["http:", "https:"].includes(url.protocol) && url.hostname) href = text;
    } catch (_) { /* Unsafe or relative addresses stay plain text. */ }
  }
  const preview = text.replace(/\s+/g, " ").trim();
  return {kind, text, href, preview: preview.slice(0, 90) + (preview.length > 90 ? "…" : ""),
    expandable: text.length > 90 || text.includes("\n")};
}

export function renderValue(field, value, {compact = false, t = text => text, e = escapeHTML} = {}) {
  const model = valueModel(field, value);
  let content;
  if (!model.text) content = '<span class="null-value" data-copy-source>—</span>';
  else if (model.kind === "url") content = model.href
    ? `<a class="value-url" data-copy-source href="${e(model.href)}" target="_blank" rel="noopener noreferrer" title="${e(model.text)}">${e(model.text)}</a>`
    : `<span class="value-url" data-copy-source>${e(model.text)}</span>`;
  else {
    content = `<pre class="value-pre" data-copy-source>${e(model.text)}</pre>`;
    if (compact && model.expandable) content = `<details class="value-details"><summary><span class="sr-only">${e(t("Show full value"))}: </span>${e(model.preview)}</summary>${content}</details>`;
  }
  return `<div class="field-display" data-field-display="${e(model.kind)}" data-empty="${!model.text}" data-expand-label="${e(t("Show full value"))}"><div class="value-content">${content}</div><button type="button" hidden class="value-copy button small secondary" data-copy-value data-copied="${e(t("Value copied"))}" data-copy-failed="${e(t("Copy the selected value with Ctrl+C or ⌘C."))}" aria-label="${e(t("Copy value") + ": " + field.label)}">${e(t("Copy"))}</button><span class="sr-only" data-copy-status role="status" aria-live="polite"></span></div>`;
}
