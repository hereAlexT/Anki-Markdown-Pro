// Editor integration for Markdown Pro note types.
// Forces plain-text mode, disables HTML syntax highlighting, and adds
// paste/drop media support plus markdown formatting shortcuts.
import "./editor.css";

declare function require(name: string): any;
declare function pycmd(cmd: string, cb?: (result: unknown) => void): void;
declare const globalThis: any;

interface CodeMirrorAPI {
  setOption(key: string, value: unknown): Promise<void>;
}

interface PlainTextInputAPI {
  codeMirror: CodeMirrorAPI;
}

const { loaded } = require("anki/ui") as { loaded: Promise<void> };
const { instances } = require("anki/NoteEditor");
const { lifecycle, instances: plainTexts } = require("anki/PlainTextInput") as {
  lifecycle: { onMount(cb: (api: PlainTextInputAPI) => (() => void) | void): void };
  instances: PlainTextInputAPI[];
};
const active = () => document.body.classList.contains("mdpro-active");

// Editor settings to force-disable for markdown notes
const settings = ["setCloseHTMLTags", "setShrinkImages", "setMathjaxEnabled"];

// Get boolean array matching field count
const fields = async (val: boolean) => (await instances[0]?.fields)?.map(() => val);

async function setPlainText(val: boolean): Promise<void> {
  const list = await fields(val);
  if (list && globalThis.setPlainTexts) globalThis.setPlainTexts(list);
}

// Set a CodeMirror option on all plain-text inputs
async function setOption(key: string, value: unknown): Promise<void> {
  await Promise.all(plainTexts.map((pt) => pt.codeMirror.setOption(key, value)));
}

globalThis.mdproActivate = async () => {
  await loaded;
  document.body.classList.add("mdpro-active");
  for (const fn of settings) globalThis[fn]?.(false);
  await setPlainText(true);
  await setOption("mode", "null");
};

globalThis.mdproDeactivate = async () => {
  await loaded;
  document.body.classList.remove("mdpro-active");
  for (const fn of settings) globalThis[fn]?.(true);
  await setPlainText(false);
};

// Wrap editor globals to force correct values when active
loaded.then(() => {
  for (const fn of settings) {
    const orig = globalThis[fn];
    if (!orig) continue;
    globalThis[fn] = (val: boolean) => orig(active() ? false : val);
  }
  const orig = globalThis.setPlainTexts;
  if (orig) {
    globalThis.setPlainTexts = (vals: boolean[]) => orig(active() ? vals.map(() => true) : vals);
  }
});

// Disable highlighting on any plain-text input that mounts while active
lifecycle.onMount((api: PlainTextInputAPI) => {
  if (active()) api.codeMirror.setOption("mode", "null");
});

// Media paste/drop
////////////////////////////////////////////////////////////////////////////

const IMAGE_EXTS = ["jpg", "jpeg", "png", "gif", "svg", "webp", "ico", "avif", "bmp"];
const MEDIA_EXTS = [
  ...IMAGE_EXTS,
  "3gp", "aac", "avi", "flac", "flv", "m4a", "mkv", "mov", "mp3", "mp4",
  "mpeg", "mpg", "oga", "ogg", "ogv", "opus", "wav", "webm",
];
const MIME_EXT: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/gif": "gif",
  "image/svg+xml": "svg",
  "image/webp": "webp",
  "image/avif": "avif",
  "image/bmp": "bmp",
  "audio/mpeg": "mp3",
  "audio/mp4": "m4a",
  "audio/ogg": "ogg",
  "audio/wav": "wav",
  "video/mp4": "mp4",
  "video/webm": "webm",
  "video/quicktime": "mov",
};

const extOf = (name: string) => (name.includes(".") ? name.split(".").pop()!.toLowerCase() : "");

function isMediaFile(file: File): boolean {
  return (
    file.type.startsWith("image/") ||
    file.type.startsWith("audio/") ||
    file.type.startsWith("video/") ||
    MEDIA_EXTS.includes(extOf(file.name))
  );
}

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let out = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    out += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(out);
}

async function sha1hex(buf: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-1", buf);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function linkFor(fname: string): string {
  if (IMAGE_EXTS.includes(extOf(fname))) {
    return `<img src="${encodeURI(fname)}">`;
  }
  return `[sound:${fname}]`;
}

// --- Anki 26.08+ backend RPC (POST /_anki/addMediaFile, protobuf body) ---
// AddMediaFileRequest { string desired_name = 1; bytes data = 2; }
// Response: generic.String { string val = 1; }

function varint(n: number): number[] {
  const out: number[] = [];
  while (n > 0x7f) {
    out.push((n & 0x7f) | 0x80);
    n >>>= 7;
  }
  out.push(n);
  return out;
}

function encodeAddMediaFile(name: string, data: Uint8Array): Uint8Array {
  const nameBytes = new TextEncoder().encode(name);
  const head = [0x0a, ...varint(nameBytes.length), ...nameBytes, 0x12, ...varint(data.length)];
  const out = new Uint8Array(head.length + data.length);
  out.set(head);
  out.set(data, head.length);
  return out;
}

function decodeGenericString(buf: Uint8Array): string {
  if (buf.length === 0 || buf[0] !== 0x0a) return "";
  let i = 1;
  let len = 0;
  let shift = 0;
  while (i < buf.length) {
    const b = buf[i++];
    len |= (b & 0x7f) << shift;
    if (!(b & 0x80)) break;
    shift += 7;
  }
  return new TextDecoder().decode(buf.subarray(i, i + len));
}

let rpcUnavailable = false;

async function rpcAddMediaFile(name: string, buf: ArrayBuffer): Promise<string> {
  const body = encodeAddMediaFile(name, new Uint8Array(buf));
  const resp = await fetch("/_anki/addMediaFile", {
    method: "POST",
    body: body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength) as ArrayBuffer,
  });
  if (!resp.ok) throw new Error(`addMediaFile: ${resp.status}`);
  const fname = decodeGenericString(new Uint8Array(await resp.arrayBuffer()));
  if (!fname) throw new Error("addMediaFile: empty response");
  return fname;
}

// --- Legacy bridge (Anki <= 26.05): base64 over pycmd, handled in Python ---

function pycmdRequest(cmd: string, payload: unknown): Promise<string> {
  return new Promise((resolve, reject) => {
    if (typeof pycmd !== "function") {
      reject(new Error("pycmd unavailable"));
      return;
    }
    pycmd(`mdpro:${cmd}:${JSON.stringify(payload)}`, (result: any) => {
      if (result && result.link) resolve(result.link);
      else reject(new Error(result?.error || `${cmd} failed`));
    });
  });
}

function pycmdAddMedia(name: string, buf: ArrayBuffer): Promise<string> {
  return pycmdRequest("addmedia", { name, data: toBase64(buf) });
}

async function addMedia(name: string, buf: ArrayBuffer): Promise<string> {
  if (!rpcUnavailable) {
    try {
      return linkFor(await rpcAddMediaFile(name, buf));
    } catch {
      rpcUnavailable = true;
    }
  }
  return await pycmdAddMedia(name, buf);
}

// Track the last focused editable so we can restore focus if the async
// media roundtrip (or the user's click on a toolbar button) dropped it.
let lastEditable: HTMLElement | null = null;
document.addEventListener(
  "focusin",
  (e) => {
    const target = e.target as HTMLElement | null;
    if (target?.isContentEditable) lastEditable = target;
  },
  true,
);

function insertText(text: string): void {
  const active = document.activeElement as HTMLElement | null;
  if (!active?.isContentEditable && lastEditable?.isConnected) {
    lastEditable.focus();
  }
  document.execCommand("insertText", false, text);
}

globalThis.mdproInsertText = insertText;

// Wrap the current selection in a markdown marker (Ctrl+B / Ctrl+I).
globalThis.mdproWrap = (marker: string) => {
  const sel = document.getSelection()?.toString() ?? "";
  insertText(marker + sel + marker);
};

async function desiredName(file: File, buf: ArrayBuffer): Promise<string> {
  const name = file.name || "";
  // Clipboard images arrive as a generic "image.png"; use a content-hash
  // name (Anki's own convention) so identical pastes dedupe.
  if (!name || /^(image|unknown|blob)\.[a-z0-9]+$/i.test(name)) {
    const ext = MIME_EXT[file.type] || extOf(name) || "png";
    return `paste-${await sha1hex(buf)}.${ext}`;
  }
  return name;
}

async function handleFiles(files: File[]): Promise<void> {
  for (const file of files) {
    try {
      const buf = await file.arrayBuffer();
      if (buf.byteLength > 50 * 1024 * 1024) {
        console.log(`[mdpro] Skipping ${file.name}: over 50MB limit`);
        continue;
      }
      const link = await addMedia(await desiredName(file, buf), buf);
      insertText(link);
    } catch (e) {
      console.log(`[mdpro] Failed to add media: ${e}`);
    }
  }
}

function mediaFiles(data: DataTransfer | null): File[] {
  if (!data) return [];
  const files = [...(data.files || [])].filter(isMediaFile);
  if (files.length) return files;
  // Some sources expose clipboard images only via items
  return [...(data.items || [])]
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((f): f is File => !!f && isMediaFile(f));
}

// Images copied from a browser arrive as HTML markup (no File objects):
// data: URIs are decoded locally, http(s) URLs are downloaded by Anki.
function imageSrcsFromHtml(html: string): string[] {
  if (!html || !/<img/i.test(html)) return [];
  const srcs: string[] = [];
  const re = /<img\s[^>]*?src\s*=\s*("([^"]*)"|'([^']*)')/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    const src = m[2] ?? m[3] ?? "";
    if (src.startsWith("data:image/") || /^https?:\/\//i.test(src)) srcs.push(src);
  }
  return srcs;
}

function dataUriToBytes(uri: string): { buf: ArrayBuffer; ext: string } | null {
  const m = /^data:image\/([a-z0-9+.-]+);base64,(.*)$/is.exec(uri);
  if (!m) return null;
  try {
    const binary = atob(m[2].trim());
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const ext = m[1] === "jpeg" ? "jpg" : m[1] === "svg+xml" ? "svg" : m[1];
    return { buf: bytes.buffer as ArrayBuffer, ext };
  } catch {
    return null;
  }
}

async function handleHtmlImages(srcs: string[]): Promise<void> {
  for (const src of srcs) {
    try {
      if (src.startsWith("data:")) {
        const decoded = dataUriToBytes(src);
        if (!decoded) continue;
        const name = `paste-${await sha1hex(decoded.buf)}.${decoded.ext}`;
        insertText(await addMedia(name, decoded.buf));
      } else {
        insertText(await pycmdRequest("addmediaurl", { url: src }));
      }
    } catch (e) {
      console.log(`[mdpro] Failed to add image from HTML clipboard: ${e}`);
    }
  }
}

function handleDataTransfer(e: Event, data: DataTransfer | null): boolean {
  const files = mediaFiles(data);
  if (files.length) {
    e.preventDefault();
    (e as ClipboardEvent).stopImmediatePropagation();
    handleFiles(files);
    return true;
  }
  const srcs = imageSrcsFromHtml(data?.getData("text/html") || "");
  if (srcs.length) {
    e.preventDefault();
    (e as ClipboardEvent).stopImmediatePropagation();
    handleHtmlImages(srcs);
    return true;
  }
  return false;
}

document.addEventListener(
  "paste",
  (e: ClipboardEvent) => {
    if (!active()) return;
    handleDataTransfer(e, e.clipboardData);
  },
  true,
);

document.addEventListener(
  "dragover",
  (e: DragEvent) => {
    if (active() && e.dataTransfer?.types.includes("Files")) e.preventDefault();
  },
  true,
);

document.addEventListener(
  "drop",
  (e: DragEvent) => {
    if (!active()) return;
    const target = e.target as HTMLElement | null;
    target?.focus?.();
    handleDataTransfer(e, e.dataTransfer);
  },
  true,
);
