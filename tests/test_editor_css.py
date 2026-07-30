"""Guards on editor.css selectors that are easy to get wrong.

Anki portals every popover to <body> with class .floating (see
ts/lib/components/WithFloating.svelte), so a blanket `.floating { display: none }`
also hides the tag autocomplete dropdown — a bug inherited from upstream.
"""

import re
from pathlib import Path

CSS = (Path(__file__).parent.parent / "src" / "editor.css").read_text(encoding="utf-8")


def rules() -> list[str]:
    """Selector lines, comments stripped."""
    text = re.sub(r"/\*.*?\*/", "", CSS, flags=re.DOTALL)
    return [line.strip() for line in text.splitlines() if line.strip()]


def test_does_not_blanket_hide_floating_popovers():
    for line in rules():
        assert not re.match(r"^\.floating\s*[,{]", line), (
            "hiding all .floating elements also hides the tag autocomplete dropdown"
        )


def test_floating_rule_keeps_the_autocomplete_menu():
    selectors = [line for line in rules() if ".floating" in line]

    assert selectors, "expected a rule scoping the rich-text popovers"
    assert all(":has(.autocomplete-menu)" in line for line in selectors), (
        "every .floating rule must exempt the tag autocomplete dropdown"
    )


def test_rich_text_input_stays_focusable_for_drag_and_drop():
    # display: none would stop drag/drop events from firing at all
    assert "clip-path: inset(50%)" in CSS
    assert not re.search(r"rich-text-input[\s\S]{0,200}display:\s*none", CSS)
