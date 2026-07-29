"""Integration tests against the real Anki backend (no GUI).

These create a real Collection, install the Markdown Pro note types through
the add-on's own ensure_* functions (real template files, real ModelManager),
and verify rendering semantics that unit tests with fakes can't cover:
card generation counts and — critically — which side's audio autoplays.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PKG = ROOT / "markdown_pro"


class Signal:
    def connect(self, fn):
        pass


class Action:
    def __init__(self, *args):
        self.triggered = Signal()


@pytest.fixture
def real(monkeypatch, tmp_path):
    """Load the add-on module wired to a real Anki collection."""
    from anki.collection import Collection

    col = Collection(str(tmp_path / "test.anki2"))

    cfg = {
        "languages": ["python"],
        "themes": {"light": "vitesse-light", "dark": "vitesse-dark"},
        "cardless": False,
        "extra_notetypes": [],
    }

    mw = types.SimpleNamespace(col=col, addonManager=None, form=None)

    aqt = types.ModuleType("aqt")
    aqt.mw = mw
    aqt.gui_hooks = types.SimpleNamespace()

    qt = types.ModuleType("aqt.qt")
    qt.QAction = Action
    qt.QMessageBox = types.SimpleNamespace(warning=lambda *a: None, information=lambda *a: None)

    editor = types.ModuleType("aqt.editor")
    editor.Editor = type("Editor", (), {})

    webview = types.ModuleType("aqt.webview")
    webview.WebContent = type("WebContent", (), {})

    shiki = types.ModuleType("markdown_pro.shiki")
    shiki.store = types.SimpleNamespace(sync=lambda _cfg: ([], []))
    shiki.get_config = lambda: cfg
    shiki.generate_config_json = lambda: json.dumps(cfg, separators=(",", ":"))

    settings = types.ModuleType("markdown_pro.settings")
    settings.show_settings = lambda: None

    for name, mod in {
        "aqt": aqt,
        "aqt.qt": qt,
        "aqt.editor": editor,
        "aqt.webview": webview,
        "markdown_pro.shiki": shiki,
        "markdown_pro.settings": settings,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    spec = importlib.util.spec_from_file_location(
        "markdown_pro", PKG / "__init__.py", submodule_search_locations=[str(PKG)]
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "markdown_pro", mod)
    spec.loader.exec_module(mod)

    mod.ensure_all_notetypes()

    yield types.SimpleNamespace(mod=mod, col=col, cfg=cfg)
    col.close()


def add_note(col, notetype_name, **fields):
    note = col.new_note(col.models.by_name(notetype_name))
    for key, value in fields.items():
        note[key.replace("_", " ")] = value
    col.add_note(note, col.decks.get_current_id())
    return note


def av_filenames(tags):
    return [t.filename for t in tags if hasattr(t, "filename")]


class TestNotetypeCreation:
    def test_all_notetypes_exist(self, real):
        names = {nt.name for nt in real.col.models.all_names_and_ids()}
        assert {
            "Markdown Pro",
            "Markdown Pro Cloze",
            "Markdown Pro (and reversed)",
            "Markdown Pro (optional reversed)",
            "Markdown Pro (type in the answer)",
        } <= names

    def test_ensure_is_idempotent_against_real_backend(self, real):
        before = {
            nt.name: real.col.models.get(nt.id)["mod"]
            for nt in real.col.models.all_names_and_ids()
        }
        real.mod.ensure_all_notetypes()
        after = {
            nt.name: real.col.models.get(nt.id)["mod"]
            for nt in real.col.models.all_names_and_ids()
        }
        assert before == after


class TestAudioSides:
    """Anki autoplays question_av_tags on the front and answer_av_tags on the
    back. The template structure must keep each side's audio on its side."""

    def test_basic_front_audio_only_on_question(self, real):
        note = add_note(
            real.col, "Markdown Pro", Front="q [sound:front.mp3]", Back="a [sound:back.mp3]"
        )
        out = note.cards()[0].render_output()

        assert av_filenames(out.question_av_tags) == ["front.mp3"]
        assert av_filenames(out.answer_av_tags) == ["back.mp3"]

    def test_question_text_never_contains_answer_content(self, real):
        note = add_note(real.col, "Markdown Pro", Front="q", Back="SECRET-ANSWER")
        out = note.cards()[0].render_output()

        assert "SECRET-ANSWER" not in out.question_text
        assert "SECRET-ANSWER" in out.answer_text

    def test_reversed_card_swaps_audio_sides(self, real):
        note = add_note(
            real.col,
            "Markdown Pro (and reversed)",
            Front="q [sound:front.mp3]",
            Back="a [sound:back.mp3]",
        )
        cards = sorted(note.cards(), key=lambda c: c.ord)
        assert len(cards) == 2

        forward = cards[0].render_output()
        assert av_filenames(forward.question_av_tags) == ["front.mp3"]
        assert av_filenames(forward.answer_av_tags) == ["back.mp3"]

        reverse = cards[1].render_output()
        assert av_filenames(reverse.question_av_tags) == ["back.mp3"]
        assert av_filenames(reverse.answer_av_tags) == ["front.mp3"]

    def test_type_in_back_audio_does_not_leak_to_question(self, real):
        note = add_note(
            real.col,
            "Markdown Pro (type in the answer)",
            Front="q [sound:front.mp3]",
            Back="answer [sound:back.mp3]",
        )
        out = note.cards()[0].render_output()

        assert av_filenames(out.question_av_tags) == ["front.mp3"]
        assert av_filenames(out.answer_av_tags) == ["back.mp3"]

    def test_cloze_extra_audio_only_on_answer(self, real):
        note = add_note(
            real.col,
            "Markdown Pro Cloze",
            Text="{{c1::x}} [sound:text.mp3]",
            Extra="[sound:extra.mp3]",
        )
        out = note.cards()[0].render_output()

        q = av_filenames(out.question_av_tags)
        a = av_filenames(out.answer_av_tags)
        assert "extra.mp3" not in q
        assert a.count("text.mp3") == 1, "FrontSide embed must not re-extract Text audio"
        assert a.count("extra.mp3") == 1


class TestCardGeneration:
    def test_basic_generates_one_card(self, real):
        note = add_note(real.col, "Markdown Pro", Front="q", Back="a")
        assert len(note.cards()) == 1

    def test_optional_reversed_respects_add_reverse(self, real):
        without = add_note(
            real.col, "Markdown Pro (optional reversed)", Front="q1", Back="a1"
        )
        with_reverse = add_note(
            real.col,
            "Markdown Pro (optional reversed)",
            Front="q2",
            Back="a2",
            Add_Reverse="y",
        )
        assert len(without.cards()) == 1
        assert len(with_reverse.cards()) == 2

    def test_cloze_generates_one_card_per_ordinal(self, real):
        note = add_note(
            real.col, "Markdown Pro Cloze", Text="{{c1::a}} {{c2::b}} {{c2::c}}", Extra=""
        )
        assert len(note.cards()) == 2

    def test_type_in_keeps_native_marker_on_both_sides(self, real):
        note = add_note(
            real.col, "Markdown Pro (type in the answer)", Front="q", Back="answer"
        )
        out = note.cards()[0].render_output()

        assert "[[type:Back]]" in out.question_text
        assert "[[type:Back]]" in out.answer_text


class TestManagedTemplates:
    def test_user_additions_outside_block_survive_and_render(self, real):
        mm = real.col.models
        m = mm.by_name("Markdown Pro")
        m["tmpls"][0]["qfmt"] += "\n{{tts en_US:Front}}"
        mm.save(m)

        # Force a managed-block rewrite via a config change
        real.cfg["cardless"] = True
        real.mod.ensure_notetype()

        m = mm.by_name("Markdown Pro")
        assert m["tmpls"][0]["qfmt"].endswith("{{tts en_US:Front}}")
        assert '"cardless":true' in m["tmpls"][0]["qfmt"]

        # And the real renderer produces a TTS av tag from the user's addition
        note = add_note(real.col, "Markdown Pro", Front="hello", Back="a")
        out = note.cards()[0].render_output()
        tts = [t for t in out.question_av_tags if not hasattr(t, "filename")]
        assert len(tts) == 1
