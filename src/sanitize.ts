// HTML sanitizer for raw HTML embedded in markdown fields.
// Tag + attribute allowlist with URL scheme checks. Unknown elements are
// unwrapped (children kept); dangerous elements are dropped entirely.

const ALLOWED: Record<string, Set<string>> = {
  img: new Set(["src", "alt", "title", "width", "height"]),
  a: new Set(["href", "title"]),
  b: new Set(),
  i: new Set(),
  em: new Set(),
  strong: new Set(),
  br: new Set(),
  kbd: new Set(),
  sub: new Set(),
  sup: new Set(),
  u: new Set(),
  mark: new Set(),
  audio: new Set(["src", "controls", "loop", "muted", "preload"]),
  video: new Set(["src", "controls", "loop", "muted", "preload", "width", "height", "poster"]),
  source: new Set(["src", "type"]),
};

// Elements whose content must never render
const DROP = new Set(["script", "style", "iframe", "object", "embed", "link", "meta", "base", "form"]);

const URL_ATTRS = new Set(["src", "href", "poster"]);

export function safeUrl(value: string, tag: string): boolean {
  // Strip whitespace/control chars that could obfuscate the scheme
  const v = value.replace(/[\s\x00-\x1f]/g, "").toLowerCase();
  if (v.startsWith("javascript:") || v.startsWith("vbscript:")) return false;
  if (v.startsWith("data:")) return tag === "img" && v.startsWith("data:image/");
  return true;
}

function escapeAttr(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const TAG_RE = /^<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^"'>])*?)(\/?)\s*>$/;
const ATTR_RE = /([a-zA-Z][a-zA-Z0-9-]*)(?:\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;

/** Sanitize a single inline tag token like `<img src="x.png">` or `</b>`. */
export function sanitizeInline(token: string): string {
  const match = TAG_RE.exec(token.trim());
  if (!match) return "";
  const [, closing, rawTag, rawAttrs, selfClose] = match;
  const tag = rawTag.toLowerCase();
  const allowed = ALLOWED[tag];
  if (!allowed) return "";
  if (closing) return `</${tag}>`;

  const attrs: string[] = [];
  for (const am of rawAttrs.matchAll(ATTR_RE)) {
    const name = am[1].toLowerCase();
    if (!allowed.has(name)) continue;
    const value = am[3] ?? am[4] ?? am[5] ?? "";
    if (URL_ATTRS.has(name) && !safeUrl(value, tag)) continue;
    attrs.push(am[2] === undefined ? name : `${name}="${escapeAttr(value)}"`);
  }
  return `<${tag}${attrs.length ? " " + attrs.join(" ") : ""}${selfClose ? " /" : ""}>`;
}

function filterChildren(parent: Node): void {
  for (const child of [...parent.childNodes]) {
    if (child.nodeType === 8 /* COMMENT */) {
      parent.removeChild(child);
      continue;
    }
    if (child.nodeType !== 1 /* ELEMENT */) continue;
    const el = child as Element;
    const tag = el.tagName.toLowerCase();

    if (DROP.has(tag)) {
      parent.removeChild(el);
      continue;
    }

    const allowed = ALLOWED[tag];
    if (!allowed) {
      // Unwrap: sanitize children first, then hoist them in place
      filterChildren(el);
      while (el.firstChild) parent.insertBefore(el.firstChild, el);
      parent.removeChild(el);
      continue;
    }

    for (const attr of [...el.attributes]) {
      const name = attr.name.toLowerCase();
      if (!allowed.has(name)) {
        el.removeAttribute(attr.name);
        continue;
      }
      if (URL_ATTRS.has(name) && !safeUrl(attr.value, tag)) {
        el.removeAttribute(attr.name);
      }
    }
    filterChildren(el);
  }
}

/** Sanitize an HTML block (may contain multiple/nested elements). */
export function sanitizeBlock(html: string): string {
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  filterChildren(tpl.content);
  return tpl.innerHTML;
}
