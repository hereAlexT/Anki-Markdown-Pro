import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PKG = ROOT / "markdown_pro"


class FakeHooks:
    def __init__(self):
        self.profile_did_open = []
        self.editor_will_munge_html = []
        self.webview_will_set_content = []
        self.webview_did_inject_style_into_page = []
        self.editor_did_load_note = []
        self.editor_did_init_shortcuts = []
        self.webview_did_receive_js_message = []


class FakeMessageBox:
    def __init__(self):
        self.calls = []

    def warning(self, *args):
        self.calls.append(("warning", args))


class FakeAddonManager:
    def __init__(self):
        self.web_exports = []
        self.actions = []

    def setWebExports(self, mod, pattern):
        self.web_exports.append((mod, pattern))

    def setConfigAction(self, mod, fn):
        self.actions.append((mod, fn))

    def addonFromModule(self, mod):
        return mod


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)


class FakeAction:
    def __init__(self, text, parent=None):
        self.parent = parent
        self._text = text
        self.triggered = FakeSignal()

    def text(self):
        return self._text


class FakeMenu:
    def __init__(self):
        self.added = []

    def addAction(self, act):
        self.added.append(act)


class FakeMedia:
    def __init__(self, path: Path):
        self.path = path
        self.trashed = []
        self.added = []
        self.written = []

    def dir(self):
        return str(self.path)

    def trash_files(self, files):
        self.trashed.append(list(files))

    def add_file(self, path):
        self.added.append(path)

    def write_data(self, name, data):
        self.written.append((name, data))
        return name


class FakeModels:
    def __init__(self):
        self.models = {}
        self.saved = []
        self.added = []
        self.newed = []

    def by_name(self, name):
        return self.models.get(name)

    def save(self, model):
        self.saved.append(model)

    def new(self, name):
        self.newed.append(name)
        return {"name": name, "flds": [], "tmpls": []}

    def new_field(self, name):
        return {"name": name}

    def add_field(self, model, field):
        model["flds"].append(field)

    def new_template(self, name):
        return {"name": name}

    def add_template(self, model, template):
        model["tmpls"].append(template)

    def add(self, model):
        self.models[model["name"]] = model
        self.added.append(model)


class FakeWeb:
    def __init__(self):
        self.calls = []

    def eval(self, code):
        self.calls.append(code)


class FakeNote:
    def __init__(self, name):
        self.name = name

    def note_type(self):
        return None if self.name is None else {"name": self.name}


class FakeEditor:
    def __init__(self, note=None):
        self.note = note
        self.web = FakeWeb()


class FakeWebContent:
    def __init__(self):
        self.js = []
        self.css = []


class FakeBackend:
    def __init__(self):
        self.calls = []

    def get_stock_notetype_legacy(self, kind):
        self.calls.append(kind)
        return json.dumps(
            {
                "name": "Cloze",
                "type": 1,
                "flds": [{"name": "Text"}, {"name": "Back Extra"}],
                "tmpls": [{"name": "Cloze", "qfmt": "stock-front", "afmt": "stock-back"}],
            }
        )


@pytest.fixture
def addon(monkeypatch, tmp_path):
    cfg = {
        "languages": ["python"],
        "themes": {"light": "vitesse-light", "dark": "vitesse-dark"},
        "cardless": False,
    }
    def cfg_json():
        return json.dumps(cfg, separators=(",", ":"))

    tpl = tmp_path / "templates"
    tpl.mkdir()
    (tpl / "front.html").write_text("<div>front</div>", encoding="utf-8")
    (tpl / "back.html").write_text("<div>back</div>", encoding="utf-8")
    (tpl / "cloze-front.html").write_text("<div>cloze-front</div>", encoding="utf-8")
    (tpl / "cloze-back.html").write_text("<div>cloze-back</div>", encoding="utf-8")
    (tpl / "reverse-front.html").write_text("<div>rev-front</div>", encoding="utf-8")
    (tpl / "reverse-back.html").write_text("<div>rev-back</div>", encoding="utf-8")

    media = FakeMedia(tmp_path / "media")
    media.path.mkdir()
    models = FakeModels()
    backend = FakeBackend()
    addon_manager = FakeAddonManager()
    menu = FakeMenu()
    mw = types.SimpleNamespace(
        col=types.SimpleNamespace(media=media, models=models, _backend=backend),
        addonManager=addon_manager,
        form=types.SimpleNamespace(menuTools=menu),
    )
    box = FakeMessageBox()
    hooks = FakeHooks()

    aqt = types.ModuleType("aqt")
    aqt.mw = mw
    aqt.gui_hooks = hooks

    qt = types.ModuleType("aqt.qt")
    qt.QAction = FakeAction
    qt.QMessageBox = box

    editor = types.ModuleType("aqt.editor")
    editor.Editor = FakeEditor

    webview = types.ModuleType("aqt.webview")
    webview.WebContent = FakeWebContent

    shiki = types.ModuleType("markdown_pro.shiki")
    shiki.store = types.SimpleNamespace(sync=lambda _cfg: ([], []))
    shiki.get_config = lambda: cfg
    shiki.generate_config_json = cfg_json

    settings = types.ModuleType("markdown_pro.settings")
    settings.show_settings = lambda: None

    anki = types.ModuleType("anki")
    stdmodels = types.ModuleType("anki.stdmodels")
    stdmodels.StockNotetypeKind = types.SimpleNamespace(KIND_CLOZE="cloze")
    utils = types.ModuleType("anki.utils")
    utils.from_json_bytes = json.loads

    for name in [
        "anki",
        "anki.stdmodels",
        "anki.utils",
        "markdown_pro",
        "markdown_pro.shiki",
        "markdown_pro.settings",
        "aqt",
        "aqt.qt",
        "aqt.editor",
        "aqt.webview",
    ]:
        sys.modules.pop(name, None)

    monkeypatch.setitem(sys.modules, "aqt", aqt)
    monkeypatch.setitem(sys.modules, "aqt.qt", qt)
    monkeypatch.setitem(sys.modules, "aqt.editor", editor)
    monkeypatch.setitem(sys.modules, "aqt.webview", webview)
    monkeypatch.setitem(sys.modules, "anki", anki)
    monkeypatch.setitem(sys.modules, "anki.stdmodels", stdmodels)
    monkeypatch.setitem(sys.modules, "anki.utils", utils)
    monkeypatch.setitem(sys.modules, "markdown_pro.shiki", shiki)
    monkeypatch.setitem(sys.modules, "markdown_pro.settings", settings)

    spec = importlib.util.spec_from_file_location(
        "markdown_pro",
        PKG / "__init__.py",
        submodule_search_locations=[str(PKG)],
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "markdown_pro", mod)
    spec.loader.exec_module(mod)

    monkeypatch.setattr(mod, "ADDON_DIR", tmp_path)

    return types.SimpleNamespace(
        mod=mod,
        cfg=cfg,
        box=box,
        mw=mw,
        models=models,
        media=media,
        hooks=hooks,
        addon_manager=addon_manager,
        backend=backend,
        menu=menu,
    )


class TestHtmlToMarkdown:
    def test_converts_basic_html(self, addon):
        result = addon.mod.html_to_markdown(
            '<IMG src="foo bar.png"><STRONG>x</STRONG><em>y</em><br>z',
        )

        # <img> must stay HTML: Anki's media scanner does not recognize
        # markdown image syntax, so rewriting would break Check Media.
        assert result == '<IMG src="foo bar.png">**x***y*\nz'

    def test_escapes_closing_script_tag(self, addon):
        result = addon.mod.html_to_markdown("a</script>b</SCRIPT>c")

        assert result == "a&lt;/script>b&lt;/SCRIPT>c"


class TestOnMungeHtml:
    def test_converts_only_markdown_pro_notes(self, addon):
        txt = "<strong>x</strong>"

        assert addon.mod.on_munge_html(txt, FakeEditor()) == txt
        assert addon.mod.on_munge_html(txt, FakeEditor(FakeNote(None))) == txt
        assert addon.mod.on_munge_html(txt, FakeEditor(FakeNote("Basic"))) == txt
        assert addon.mod.on_munge_html(txt, FakeEditor(FakeNote("Markdown Pro"))) == "**x**"
        assert addon.mod.on_munge_html(txt, FakeEditor(FakeNote("Markdown Pro Cloze"))) == "**x**"


class TestEnsureNotetype:
    def test_updates_existing_model(self, addon):
        model = {
            "tmpls": [{"qfmt": "old-front", "afmt": "old-back"}],
            "flds": [{"name": "Front"}, {"name": "Back", "plainText": False}],
        }
        addon.models.models["Markdown Pro"] = model

        addon.mod.ensure_notetype()

        assert addon.models.saved == [model]
        assert "<div>front</div>" in model["tmpls"][0]["qfmt"]
        assert "<div>back</div>" in model["tmpls"][0]["afmt"]
        assert "markdown-pro:begin" in model["tmpls"][0]["qfmt"]
        assert model["tmpls"][0]["qfmt"].endswith("<!-- markdown-pro:end -->")
        assert all(field["plainText"] is True for field in model["flds"])

    def test_second_run_is_a_noop(self, addon):
        addon.mod.ensure_notetype()
        addon.models.saved.clear()

        addon.mod.ensure_notetype()

        assert addon.models.saved == []

    def test_preserves_user_content_outside_managed_block(self, addon):
        addon.mod.ensure_notetype()
        model = addon.models.added[0]
        # Simulate HyperTTS appending a tts tag after the managed block
        model["tmpls"][0]["qfmt"] += "\n{{tts en_US:Front}}"

        # Force a template change by altering the config
        addon.cfg["cardless"] = True
        addon.mod.ensure_notetype()

        qfmt = model["tmpls"][0]["qfmt"]
        assert qfmt.endswith("{{tts en_US:Front}}")
        assert qfmt.count("markdown-pro:begin") == 1

    def test_creates_missing_model(self, addon):
        addon.mod.ensure_notetype()

        assert len(addon.models.added) == 1
        model = addon.models.added[0]
        assert model["name"] == "Markdown Pro"
        assert [field["name"] for field in model["flds"]] == ["Front", "Back"]
        assert all(field["plainText"] is True for field in model["flds"])
        assert model["tmpls"][0]["name"] == "Default"
        assert "<div>front</div>" in model["tmpls"][0]["qfmt"]
        assert "<div>back</div>" in model["tmpls"][0]["afmt"]
        assert model["css"] == addon.mod.DEFAULT_CSS


class TestEnsureReversedNotetypes:
    def test_creates_reversed_model(self, addon):
        addon.mod.ensure_reversed_notetype()

        model = addon.models.added[0]
        assert model["name"] == "Markdown Pro (and reversed)"
        assert [f["name"] for f in model["flds"]] == ["Front", "Back"]
        assert [t["name"] for t in model["tmpls"]] == ["Card 1", "Card 2"]
        assert "<div>front</div>" in model["tmpls"][0]["qfmt"]
        assert "<div>rev-front</div>" in model["tmpls"][1]["qfmt"]
        assert "<div>rev-back</div>" in model["tmpls"][1]["afmt"]

    def test_creates_optional_reversed_model(self, addon):
        addon.mod.ensure_optional_reversed_notetype()

        model = addon.models.added[0]
        assert model["name"] == "Markdown Pro (optional reversed)"
        assert [f["name"] for f in model["flds"]] == ["Front", "Back", "Add Reverse"]
        qfmt2 = model["tmpls"][1]["qfmt"]
        assert "{{#Add Reverse}}" in qfmt2
        assert "{{/Add Reverse}}" in qfmt2
        assert "<div>rev-front</div>" in qfmt2

    def test_reversed_second_run_is_a_noop(self, addon):
        addon.mod.ensure_reversed_notetype()
        addon.mod.ensure_optional_reversed_notetype()
        addon.models.saved.clear()

        addon.mod.ensure_reversed_notetype()
        addon.mod.ensure_optional_reversed_notetype()

        assert addon.models.saved == []


class TestEnsureClozeNotetype:
    def test_creates_cloze_model(self, addon):
        addon.mod.ensure_cloze_notetype()

        assert len(addon.models.added) == 1
        model = addon.models.added[0]
        assert model["name"] == "Markdown Pro Cloze"
        assert model["type"] == 1
        assert [f["name"] for f in model["flds"]] == ["Text", "Extra"]
        assert all(f["plainText"] is True for f in model["flds"])
        assert model["tmpls"][0]["name"] == "Cloze"
        assert "<div>cloze-front</div>" in model["tmpls"][0]["qfmt"]
        assert "<div>cloze-back</div>" in model["tmpls"][0]["afmt"]
        assert model["css"] == addon.mod.DEFAULT_CSS
        assert addon.backend.calls == ["cloze"]
        assert "Markdown Pro Cloze" not in addon.models.newed

    def test_updates_existing_cloze_model(self, addon):
        model = {
            "type": 1,
            "tmpls": [{"qfmt": "old", "afmt": "old"}],
            "flds": [{"name": "Texte"}, {"name": "Rückseite Extra", "plainText": False}],
        }
        addon.models.models["Markdown Pro Cloze"] = model

        addon.mod.ensure_cloze_notetype()

        assert addon.models.saved == [model]
        assert model["type"] == 1
        assert "<div>cloze-front</div>" in model["tmpls"][0]["qfmt"]
        assert "<div>cloze-back</div>" in model["tmpls"][0]["afmt"]
        assert [f["name"] for f in model["flds"]] == ["Text", "Extra"]
        assert all(f["plainText"] is True for f in model["flds"])

    def test_restores_missing_extra_field(self, addon):
        model = {
            "type": 1,
            "tmpls": [{"qfmt": "old", "afmt": "old"}],
            "flds": [{"name": "Texte", "plainText": False}],
        }
        addon.models.models["Markdown Pro Cloze"] = model

        addon.mod.ensure_cloze_notetype()

        assert addon.models.saved == [model]
        assert model["type"] == 1
        assert "<div>cloze-front</div>" in model["tmpls"][0]["qfmt"]
        assert "<div>cloze-back</div>" in model["tmpls"][0]["afmt"]
        assert [f["name"] for f in model["flds"]] == ["Text", "Extra"]
        assert all(f["plainText"] is True for f in model["flds"])


class TestSyncMedia:
    def test_deletes_removed_and_syncs_current_files(self, addon):
        (addon.mod.ADDON_DIR / "_mdpro-review.js").write_text("x", encoding="utf-8")
        (addon.mod.ADDON_DIR / "_mdpro-review.css").write_text("y", encoding="utf-8")
        removed = addon.media.path / "_old.js"
        removed.write_text("gone", encoding="utf-8")

        addon.mod.sync_media(["_old.js"])

        assert not removed.exists()
        assert set(addon.media.trashed[0]) == {"_mdpro-review.js", "_mdpro-review.css"}
        assert {Path(path).name for path in addon.media.added} == {
            "_mdpro-review.js",
            "_mdpro-review.css",
        }


class TestProfileLoaded:
    def test_adds_tools_menu_once(self, addon):
        addon.mod.on_profile_loaded()
        addon.mod.on_profile_loaded()

        assert [act.text() for act in addon.menu.added] == ["Markdown Pro"]

    def test_creates_all_notetypes(self, addon):
        addon.mod.on_profile_loaded()

        assert set(addon.models.models) == {
            "Markdown Pro",
            "Markdown Pro Cloze",
            "Markdown Pro (and reversed)",
            "Markdown Pro (optional reversed)",
        }


class TestSyncMediaSkipsUnchanged:
    def test_unchanged_files_are_not_rewritten(self, addon):
        (addon.mod.ADDON_DIR / "_mdpro-review.js").write_text("x", encoding="utf-8")
        (addon.media.path / "_mdpro-review.js").write_text("x", encoding="utf-8")

        addon.mod.sync_media()

        assert addon.media.trashed == []
        assert addon.media.added == []

    def test_changed_files_are_rewritten(self, addon):
        (addon.mod.ADDON_DIR / "_mdpro-review.js").write_text("new", encoding="utf-8")
        (addon.media.path / "_mdpro-review.js").write_text("old", encoding="utf-8")

        addon.mod.sync_media()

        assert addon.media.trashed == [["_mdpro-review.js"]]
        assert [Path(p).name for p in addon.media.added] == ["_mdpro-review.js"]


class TestMediaBridge:
    def test_addmedia_message_writes_file_and_returns_link(self, addon):
        import base64 as b64

        payload = json.dumps({"name": "shot.png", "data": b64.b64encode(b"bytes").decode()})
        handled = addon.mod.on_js_message((False, None), f"mdpro:addmedia:{payload}", None)

        assert handled[0] is True
        assert handled[1] == {"fname": "shot.png", "link": '<img src="shot.png">'}
        assert addon.media.written == [("shot.png", b"bytes")]

    def test_audio_gets_sound_tag(self, addon):
        import base64 as b64

        payload = json.dumps({"name": "clip.mp3", "data": b64.b64encode(b"x").decode()})
        handled = addon.mod.on_js_message((False, None), f"mdpro:addmedia:{payload}", None)

        assert handled[1]["link"] == "[sound:clip.mp3]"

    def test_ignores_other_messages(self, addon):
        original = (False, None)

        assert addon.mod.on_js_message(original, "other:cmd", None) is original
        assert addon.mod.on_js_message(original, "mdpro:unknown:{}", None) is original

    def test_addmediaurl_uses_editor_retriever(self, addon):
        class Ctx:
            def _retrieveURL(self, url):
                assert url == "https://example.com/pic.png"
                return "pic.png"

        payload = json.dumps({"url": "https://example.com/pic.png"})
        handled = addon.mod.on_js_message((False, None), f"mdpro:addmediaurl:{payload}", Ctx())

        assert handled[1] == {"fname": "pic.png", "link": '<img src="pic.png">'}

    def test_addmediaurl_rejects_non_http(self, addon):
        payload = json.dumps({"url": "file:///etc/passwd"})
        handled = addon.mod.on_js_message((False, None), f"mdpro:addmediaurl:{payload}", None)

        assert "error" in handled[1]

    def test_sanitizes_filename(self, addon):
        assert addon.mod.sanitize_filename('a/b\\c:d.png') == "a_b_c_d.png"
        assert addon.mod.sanitize_filename("") == "pasted"
