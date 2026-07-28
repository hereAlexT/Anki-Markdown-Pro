// Audio/video passthrough: Anki injects playback controls into the raw field
// text before our renderer runs. Extract them ahead of markdown parsing so the
// pipeline (and sanitizer) never mangles them, then restore after rendering.
//
// What arrives in the field text, per platform:
// - Desktop: [sound:x] is stripped by the backend and replaced with
//   [anki:play:q:0] markers, which aqt converts to <a class="replay-button">
//   anchors before the card reaches the webview.
// - AnkiDroid/AnkiMobile: their own replay markup or raw markers.
// - AnkiWeb / edge cases: raw [sound:x] may survive; we render a native
//   <audio>/<video> element pointing at collection.media.

const VIDEO_EXTS = new Set(["mp4", "webm", "mov", "mkv", "mpeg", "mpg", "ogv", "avi", "3gp", "flv"]);

const REPLAY_RE = /<a\s[^>]*class="[^"]*replay-button[^"]*"[\s\S]*?<\/a>/gi;
const MARKER_RE = /\[anki:play:[qa]:\d+\]/gi;
const SOUND_RE = /\[sound:[^\]\n]+\]/gi;

const token = (i: number) => `MDPROAV${i}X`;
const TOKEN_RE = /MDPROAV(\d+)X/g;

export function extractAv(text: string): { text: string; items: string[] } {
  const items: string[] = [];
  let out = text;
  for (const re of [REPLAY_RE, MARKER_RE, SOUND_RE]) {
    out = out.replace(re, (m) => {
      items.push(m);
      return token(items.length - 1);
    });
  }
  return { text: out, items };
}

/** Keep Anki's own replay anchor, but strip any event handler that doesn't
 * match the exact pycmd play pattern — fields are untrusted input. */
function sanitizeReplayAnchor(html: string): string {
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  const anchor = tpl.content.firstElementChild as HTMLElement | null;
  if (!anchor || anchor.tagName.toLowerCase() !== "a") return "";
  const onclick = (anchor.getAttribute("onclick") || "").trim();
  const validClick = /^pycmd\('play:[qa]:\d+'\);\s*return\s+false;?$/.test(onclick);
  for (const el of [anchor, ...anchor.querySelectorAll("*")]) {
    for (const attr of [...el.attributes]) {
      if (/^on/i.test(attr.name)) el.removeAttribute(attr.name);
    }
  }
  anchor.setAttribute("href", "#");
  if (validClick) anchor.setAttribute("onclick", onclick);
  return anchor.outerHTML;
}

function renderSound(raw: string): string {
  const fname = raw.slice("[sound:".length, -1);
  const ext = fname.includes(".") ? fname.split(".").pop()!.toLowerCase() : "";
  const src = encodeURI(fname);
  if (VIDEO_EXTS.has(ext)) {
    return `<video controls src="${src}"></video>`;
  }
  return `<audio controls src="${src}"></audio>`;
}

function renderItem(raw: string): string {
  if (raw.startsWith("[sound:")) return renderSound(raw);
  if (raw.startsWith("[anki:play:")) return raw; // platform will handle it
  return sanitizeReplayAnchor(raw);
}

export function restoreAv(html: string, items: string[]): string {
  if (!items.length) return html;
  return html.replace(TOKEN_RE, (m, n) => {
    const raw = items[Number(n)];
    return raw === undefined ? m : renderItem(raw);
  });
}
