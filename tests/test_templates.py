from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SAMPLE = """1. 短期
   - NAT
   - L4, L7 反向代理
1. 中/长期
   - 逐步重新规划 IP"""


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = {}
        self.key = None

    def handle_starttag(self, tag, attrs):
        vals = dict(attrs)
        if tag == "script" and vals.get("type") == "text/plain":
            self.key = vals.get("id")
            self.out[self.key] = []

    def handle_data(self, data):
        if self.key:
            self.out[self.key].append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.key = None


def read(file, vals):
    text = (ROOT / "markdown_pro" / "templates" / file).read_text(encoding="utf-8")
    for raw, val in vals.items():
        text = text.replace(raw, val)
    parser = Scripts()
    parser.feed(text)
    return {key: "".join(val) for key, val in parser.out.items()}


@pytest.mark.parametrize(
    ("file", "vals", "keys"),
    [
        ("front.html", {"{{Front}}": SAMPLE}, ("data-question",)),
        ("back.html", {"{{Back}}": SAMPLE}, ("data-answer",)),
        ("reverse-front.html", {"{{Back}}": SAMPLE}, ("data-question",)),
        ("reverse-back.html", {"{{Front}}": SAMPLE}, ("data-answer",)),
        ("cloze-front.html", {"{{Text}}": SAMPLE}, ("data-text",)),
        ("cloze-back.html", {"{{Extra}}": SAMPLE}, ("data-extra",)),
    ],
)
def test_field_scripts_keep_raw_text(file, vals, keys):
    out = read(file, vals)

    for key in keys:
        assert out[key] == SAMPLE


FRONT_TEMPLATES = ["front.html", "reverse-front.html", "cloze-front.html"]
BACK_TEMPLATES = ["back.html", "reverse-back.html", "cloze-back.html"]


@pytest.mark.parametrize("file", FRONT_TEMPLATES)
def test_question_templates_never_reference_answer_fields(file):
    """Anki autoplays audio found in the rendered question template, so the
    answer field must not appear on the front (its audio would leak)."""
    text = (ROOT / "markdown_pro" / "templates" / file).read_text(encoding="utf-8")

    if file == "reverse-front.html":
        assert "{{Front}}" not in text
    elif file == "cloze-front.html":
        assert "{{Extra}}" not in text
    else:
        assert "{{Back}}" not in text


@pytest.mark.parametrize("file", BACK_TEMPLATES)
def test_answer_templates_embed_frontside(file):
    """The question side is embedded via {{FrontSide}} (audio pre-stripped by
    Anki) instead of re-rendering the raw field, so answer-side autoplay only
    includes the answer's own audio."""
    text = (ROOT / "markdown_pro" / "templates" / file).read_text(encoding="utf-8")

    assert "{{FrontSide}}" in text
    assert 'id="mdpro-frontside"' in text
    if file == "back.html":
        assert "{{Front}}" not in text.replace("{{FrontSide}}", "")
    elif file == "reverse-back.html":
        assert "{{Back}}" not in text
    elif file == "cloze-back.html":
        # {{cloze:Text}} stays for native revealed-audio autoplay, but the raw
        # {{Text}} block must come from the FrontSide embed.
        assert "{{Text}}" not in text.replace("{{cloze:Text}}", "")


@pytest.mark.parametrize("file", FRONT_TEMPLATES)
def test_front_scripts_skip_when_embedded(file):
    text = (ROOT / "markdown_pro" / "templates" / file).read_text(encoding="utf-8")

    assert 'getElementById("mdpro-frontside")' in text
