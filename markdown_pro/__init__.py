import base64
import hashlib
import json
import re
from pathlib import Path

from aqt import mw, gui_hooks
from aqt.qt import QAction, QMessageBox
from aqt.editor import Editor
from aqt.webview import WebContent

from .shiki import store, get_config, generate_config_json
from .settings import show_settings

ADDON_DIR = Path(__file__).parent
NOTETYPE = "Markdown Pro"
NOTETYPE_CLOZE = "Markdown Pro Cloze"
NOTETYPE_REVERSED = "Markdown Pro (and reversed)"
NOTETYPE_OPT_REVERSED = "Markdown Pro (optional reversed)"
NOTETYPE_TYPE = "Markdown Pro (type in the answer)"
ALL_NOTETYPES = (
    NOTETYPE,
    NOTETYPE_CLOZE,
    NOTETYPE_REVERSED,
    NOTETYPE_OPT_REVERSED,
    NOTETYPE_TYPE,
)
MENU = "Markdown Pro"

# Bump when the managed template block changes incompatibly.
TEMPLATE_VERSION = 2

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "svg", "webp", "ico", "avif", "bmp"}


def is_markdown_pro(notetype) -> bool:
    """Check if a note type is any Markdown Pro variant."""
    return bool(notetype) and notetype["name"] in ALL_NOTETYPES


def read(name: str) -> str:
    return (ADDON_DIR / name).read_text(encoding="utf-8")


def html_to_markdown(content: str) -> str:
    """Normalize editor HTML before saving.

    Keeps `<img>` tags as-is: Anki's media reference scanner only recognizes
    HTML media tags and [sound:...], so rewriting to markdown image syntax
    would make Check Media report the file as unused (data-loss risk).
    """
    text = content

    text = re.sub(
        r"<(b|strong)>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r"<(i|em)>(.*?)</\1>", r"*\2*", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # A literal </script> in a field would terminate the template's
    # <script type="text/plain"> data block. Store it entity-escaped; the
    # renderer's decode() restores it before markdown parsing.
    text = re.sub(r"</(script)", r"&lt;/\1", text, flags=re.IGNORECASE)
    return text


def on_munge_html(txt: str, editor: Editor) -> str:
    """Convert HTML to markdown before saving."""
    if not editor.note:
        return txt
    if not is_markdown_pro(editor.note.note_type()):
        return txt
    return html_to_markdown(txt)


def on_profile_loaded():
    # Download any missing language/theme files
    _, errors = store.sync(get_config())
    if errors:
        details = "\n".join(f"- {err}" for err in errors)
        QMessageBox.warning(
            mw,
            "Markdown Pro",
            "Failed to download some syntax highlighting files.\n"
            "Open the add-on settings to retry.\n\n"
            f"{details}",
        )
    # Sync all media files to collection.media
    sync_media()
    # Create/update note types with current config
    ensure_all_notetypes()
    # Register web exports and settings action
    mw.addonManager.setWebExports(__name__, r"(web/.*|_.*)")
    mw.addonManager.setConfigAction(__name__, show_settings)
    add_menu()


def sync_media(removed: list[str] = None):
    """Copy web assets to collection.media, skipping files that are unchanged.

    Args:
        removed: Optional list of filenames that were removed and should be deleted.
    """
    media_dir = Path(mw.col.media.dir())

    # Delete removed files directly (trash_files doesn't work on _ prefixed files)
    if removed:
        for name in removed:
            media_file = media_dir / name
            if media_file.exists():
                media_file.unlink()

    # Only rewrite assets whose content actually changed, to avoid pushing
    # the full asset set through media sync on every startup.
    files = [f for f in ADDON_DIR.glob("_*") if f.is_file()]
    stale = []
    for file in files:
        target = media_dir / file.name
        try:
            if target.exists() and target.read_bytes() == file.read_bytes():
                continue
        except OSError:
            pass
        stale.append(file)

    if not stale:
        return
    mw.col.media.trash_files([f.name for f in stale])
    for file in stale:
        mw.col.media.add_file(str(file))


def add_menu():
    """Add the settings dialog to the Tools menu once per session."""
    if getattr(mw, "_mdpro_menu", None):
        return
    menu = getattr(getattr(mw, "form", None), "menuTools", None)
    if not menu:
        return
    act = QAction(MENU, mw)
    act.triggered.connect(lambda _=False: show_settings())
    menu.addAction(act)
    mw._mdpro_menu = act


# Managed template blocks
############################################################

BLOCK_RE = re.compile(
    r"<!--\s*markdown-pro:begin\b.*?-->.*?<!--\s*markdown-pro:end\s*-->",
    re.DOTALL,
)


def managed_block(inner: str) -> str:
    digest = hashlib.sha1(inner.encode("utf-8")).hexdigest()[:10]
    return (
        f"<!-- markdown-pro:begin v{TEMPLATE_VERSION} {digest} -->\n"
        f"{inner}\n"
        f"<!-- markdown-pro:end -->"
    )


def merge_template(existing: str, inner: str) -> str:
    """Replace the managed block, preserving everything outside the markers.

    User additions outside the block — e.g. a {{tts}} tag added by HyperTTS
    or manual customizations — survive template updates. Templates without
    markers (fresh installs or upgrades from the full-overwrite era) are
    replaced entirely, matching the previous behavior.
    """
    block = managed_block(inner)
    if existing:
        match = BLOCK_RE.search(existing)
        if match:
            return existing[: match.start()] + block + existing[match.end() :]
    return block


def get_template(name: str, wrap_condition: str = None) -> str:
    """Read template inner content and inject current config."""
    template = read(f"templates/{name}")
    config_json = generate_config_json()
    config_script = f'<script type="application/json" id="mdpro-config">{config_json}</script>'
    inner = config_script + "\n" + template
    if wrap_condition:
        inner = f"{{{{#{wrap_condition}}}}}\n{inner}\n{{{{/{wrap_condition}}}}}"
    return inner


def apply_template(tmpl: dict, front_inner: str, back_inner: str) -> bool:
    """Merge managed blocks into one card template. Returns True if changed."""
    changed = False
    for key, inner in (("qfmt", front_inner), ("afmt", back_inner)):
        merged = merge_template(tmpl.get(key, ""), inner)
        if tmpl.get(key) != merged:
            tmpl[key] = merged
            changed = True
    return changed


def apply_fields(model: dict) -> bool:
    """Force plain text editing on all fields. Returns True if changed."""
    changed = False
    for field in model["flds"]:
        if field.get("plainText") is not True:
            field["plainText"] = True
            changed = True
    return changed


DEFAULT_CSS = (
    "/* Uncomment to customize:\n"
    ".card {\n"
    "  --font-size: 16px;\n"
    "  --font-size-mobile: 14px;\n"
    "  --line-height: 1.5;\n"
    "  --content-max-width: 34rem;\n"
    "  --note: #2563eb;\n"
    "  --tip: #16a34a;\n"
    "  --important: #7c3aed;\n"
    "  --warning: #ca8a04;\n"
    "  --caution: #dc2626;\n"
    "}\n"
    "\n"
    ".card.night-mode {\n"
    "  --note: #318aff;\n"
    "  --tip: #19be56;\n"
    "  --important: #965bfb;\n"
    "  --warning: #dc9703;\n"
    "}\n"
    "*/"
)


def ensure_all_notetypes():
    ensure_notetype()
    ensure_cloze_notetype()
    ensure_reversed_notetype()
    ensure_optional_reversed_notetype()
    ensure_type_notetype()


def _ensure_front_back_notetype(name: str, template_name: str, front_file: str, back_file: str):
    mm = mw.col.models
    m = mm.by_name(name)

    if m:
        changed = apply_template(
            m["tmpls"][0], get_template(front_file), get_template(back_file)
        )
        changed |= apply_fields(m)
        if changed:
            mm.save(m)
        return

    m = mm.new(name)
    m["css"] = DEFAULT_CSS
    front = mm.new_field("Front")
    front["plainText"] = True
    mm.add_field(m, front)
    back = mm.new_field("Back")
    back["plainText"] = True
    mm.add_field(m, back)

    t = mm.new_template(template_name)
    t["qfmt"] = merge_template("", get_template(front_file))
    t["afmt"] = merge_template("", get_template(back_file))
    mm.add_template(m, t)

    mm.add(m)


def ensure_notetype():
    _ensure_front_back_notetype(NOTETYPE, "Default", "front.html", "back.html")


def ensure_type_notetype():
    _ensure_front_back_notetype(
        NOTETYPE_TYPE, "Card 1", "type-front.html", "type-back.html"
    )


def _reversed_pairs(wrap_condition: str = None):
    """Template inner pairs for a two-card (forward + reverse) note type."""
    return [
        (get_template("front.html"), get_template("back.html")),
        (
            get_template("reverse-front.html", wrap_condition),
            get_template("reverse-back.html"),
        ),
    ]


def _ensure_two_card_notetype(
    name: str, extra_fields: list[str], wrap_condition: str = None
):
    mm = mw.col.models
    m = mm.by_name(name)
    pairs = _reversed_pairs(wrap_condition)

    if m:
        changed = False
        for tmpl, (front_inner, back_inner) in zip(m["tmpls"], pairs):
            changed |= apply_template(tmpl, front_inner, back_inner)
        changed |= apply_fields(m)
        if changed:
            mm.save(m)
        return

    m = mm.new(name)
    m["css"] = DEFAULT_CSS
    for field_name in ["Front", "Back", *extra_fields]:
        field = mm.new_field(field_name)
        field["plainText"] = True
        mm.add_field(m, field)

    for i, (front_inner, back_inner) in enumerate(pairs):
        t = mm.new_template(f"Card {i + 1}")
        t["qfmt"] = merge_template("", front_inner)
        t["afmt"] = merge_template("", back_inner)
        mm.add_template(m, t)

    mm.add(m)


def ensure_reversed_notetype():
    _ensure_two_card_notetype(NOTETYPE_REVERSED, [])


def ensure_optional_reversed_notetype():
    _ensure_two_card_notetype(
        NOTETYPE_OPT_REVERSED, ["Add Reverse"], wrap_condition="Add Reverse"
    )


def fix_cloze_fields(mm, model):
    fields = model["flds"]
    if not fields:
        mm.add_field(model, mm.new_field("Text"))
        fields = model["flds"]
    if len(fields) == 1:
        mm.add_field(model, mm.new_field("Extra"))
        fields = model["flds"]
    fields[0]["name"] = "Text"
    fields[1]["name"] = "Extra"
    for field in fields:
        field["plainText"] = True


def ensure_cloze_notetype():
    mm = mw.col.models
    m = mm.by_name(NOTETYPE_CLOZE)

    if m:
        changed = m.get("type") != 1
        m["type"] = 1
        changed |= apply_template(
            m["tmpls"][0],
            get_template("cloze-front.html"),
            get_template("cloze-back.html"),
        )
        before = json.dumps(m["flds"], sort_keys=True)
        fix_cloze_fields(mm, m)
        changed |= json.dumps(m["flds"], sort_keys=True) != before
        if changed:
            mm.save(m)
        return

    from anki.stdmodels import StockNotetypeKind
    from anki.utils import from_json_bytes

    m = from_json_bytes(
        mw.col._backend.get_stock_notetype_legacy(StockNotetypeKind.KIND_CLOZE)
    )
    m["name"] = NOTETYPE_CLOZE
    m["css"] = DEFAULT_CSS
    m["tmpls"][0]["qfmt"] = merge_template("", get_template("cloze-front.html"))
    m["tmpls"][0]["afmt"] = merge_template("", get_template("cloze-back.html"))
    fix_cloze_fields(mm, m)

    mm.add(m)


# Editor media bridge
############################################################


def filename_to_link(fname: str) -> str:
    """Field text for a media file, matching Anki's own conventions.

    Images use an HTML tag (recognized by Anki's media scanner and rendered
    by the markdown pipeline); everything else uses [sound:...] so Anki
    handles playback natively.
    """
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext in IMAGE_EXTS:
        return f'<img src="{fname.replace(" ", "%20")}">'
    return f"[sound:{fname}]"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip().strip(".")
    return name[:120] or "pasted"


def add_media_data(payload: dict) -> dict:
    """Store base64 file data in collection.media."""
    data = base64.b64decode(payload["data"])
    if len(data) > 50 * 1024 * 1024:
        return {"error": "file too large (50MB limit)"}
    name = sanitize_filename(payload.get("name", ""))
    fname = mw.col.media.write_data(name, data)
    return {"fname": fname, "link": filename_to_link(fname)}


def add_media_url(payload: dict, context) -> dict:
    """Download a pasted image URL via Anki's own retriever (editor context)."""
    url = payload.get("url", "")
    if not url.lower().startswith(("http://", "https://")):
        return {"error": f"unsupported URL: {url[:80]}"}
    retrieve = getattr(context, "_retrieveURL", None)
    if not callable(retrieve):
        return {"error": "URL download not supported in this editor"}
    fname = retrieve(url)
    if not fname:
        return {"error": f"download failed: {url[:80]}"}
    return {"fname": fname, "link": filename_to_link(fname)}


def on_js_message(handled, message: str, context):
    """Handle mdpro:<cmd>:<json> messages from the editor webview.

    Returns {"fname", "link"} (or {"error"}) to the JS pycmd callback, which
    inserts the link at the cursor.
    """
    if handled and handled[0]:
        return handled
    if not isinstance(message, str) or not message.startswith("mdpro:"):
        return handled
    cmd, _, raw = message[len("mdpro:") :].partition(":")
    if cmd not in ("addmedia", "addmediaurl"):
        return handled
    try:
        payload = json.loads(raw)
        if cmd == "addmedia":
            return (True, add_media_data(payload))
        return (True, add_media_url(payload, context))
    except Exception as e:
        return (True, {"error": str(e)})


# Editor integration
############################################################


def on_webview_set_content(content: WebContent, context):
    """Inject editor JS/CSS (legacy editor, Anki <= 26.05)."""
    if isinstance(context, Editor):
        addon = mw.addonManager.addonFromModule(__name__)
        content.js.append(f"/_addons/{addon}/web/editor.js")
        content.css.append(f"/_addons/{addon}/web/editor.css")


def on_style_injected(webview):
    """Inject editor JS/CSS into the SvelteKit editor (Anki 26.08+).

    The new editor loads via load_sveltekit_page(), which bypasses stdHtml()
    and therefore never fires webview_will_set_content.
    """
    try:
        from aqt.webview import AnkiWebViewKind

        if getattr(webview, "kind", None) != AnkiWebViewKind.EDITOR:
            return
    except Exception:
        return
    addon = mw.addonManager.addonFromModule(__name__)
    webview.eval(
        "(function () {"
        "  if (window.__mdproEditorLoaded) return;"
        "  window.__mdproEditorLoaded = true;"
        '  var l = document.createElement("link");'
        '  l.rel = "stylesheet";'
        f' l.href = "/_addons/{addon}/web/editor.css";'
        "  document.head.appendChild(l);"
        f' import("/_addons/{addon}/web/editor.js");'
        "})();"
    )


def on_editor_load_note(editor: Editor):
    """Notify JS when a Markdown Pro note is loaded."""
    if not editor.note:
        return
    if is_markdown_pro(editor.note.note_type()):
        editor.web.eval("window.mdproActivate && mdproActivate()")
    else:
        editor.web.eval("window.mdproDeactivate && mdproDeactivate()")


def on_editor_shortcuts(shortcuts: list, editor):
    """Remap Ctrl+B / Ctrl+I to markdown wrapping on Markdown Pro notes."""

    def make(marker: str, orig):
        def run():
            note = getattr(editor, "note", None)
            if note and is_markdown_pro(note.note_type()):
                editor.web.eval(f"window.mdproWrap && mdproWrap({json.dumps(marker)})")
            elif callable(orig):
                orig()

        return run

    markers = {"ctrl+b": "**", "ctrl+i": "*"}
    for i, entry in enumerate(shortcuts):
        if not isinstance(entry, tuple) or len(entry) < 2:
            continue
        marker = markers.get(str(entry[0]).lower())
        if marker:
            shortcuts[i] = (entry[0], make(marker, entry[1]), *entry[2:])


def _hook(name: str, fn):
    hook = getattr(gui_hooks, name, None)
    if hook is not None:
        hook.append(fn)


_hook("profile_did_open", on_profile_loaded)
_hook("editor_will_munge_html", on_munge_html)
_hook("webview_will_set_content", on_webview_set_content)
_hook("webview_did_inject_style_into_page", on_style_injected)
_hook("editor_did_load_note", on_editor_load_note)
_hook("editor_did_init_shortcuts", on_editor_shortcuts)
_hook("webview_did_receive_js_message", on_js_message)
