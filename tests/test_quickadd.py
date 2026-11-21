from pathlib import Path

import pytest

from deckaloud.config import Config, Language
from deckaloud.errors import DeckaloudError
from deckaloud.quickadd import add_cards, as_cards, new_card_count
from deckaloud.source import parse_source

CLOZE = "booo is {{c1::doo}}"
QA = "Q: Test: what is booo?\nA: Doo."
ENGLISH_ONLY = Config(languages={"en": Language(voice="Samantha", locale="en_US")})


@pytest.fixture
def deck(tmp_path):
    return tmp_path / "test.txt"


@pytest.mark.parametrize(
    "typed, expected",
    [
        (CLOZE, f"C: {CLOZE}"),
        (f"  {CLOZE}  ", f"C: {CLOZE}"),
        (f"C: {CLOZE}", f"C: {CLOZE}"),
        (f"  C: {CLOZE}", f"C: {CLOZE}"),
        (QA, QA),
        ("first {{c1::line}}\nsecond line", "C: first {{c1::line}}\nsecond line"),
        (f"{CLOZE}\n\n\n{QA}", f"C: {CLOZE}\n\n{QA}"),
        (f"lang: uk\n{CLOZE}", f"lang: uk\n{CLOZE}"),
    ],
)
def test_bare_cloze_text_becomes_a_cloze_card(typed, expected):
    assert as_cards(typed) == expected, "typed text should be normalised to card blocks"


def test_first_card_creates_the_deck_with_its_header(deck):
    added = add_cards(deck, CLOZE, Config())

    assert added == 1, "one card should be reported as added"
    assert deck.read_text(encoding="utf-8") == f"deck: Test\n\nC: {CLOZE}\n", "the deck should start with its header"


@pytest.mark.parametrize("existing", ["deck: Test\n\nid: a1\nC: old {{c1::card}}\n", "deck: Test\n\nid: a1\nC: old {{c1::card}}"])
def test_later_cards_are_appended_as_their_own_blocks(deck, existing):
    deck.write_text(existing, encoding="utf-8")

    added = add_cards(deck, f"{CLOZE}\n\n{QA}", Config())
    source = parse_source(deck.read_text(encoding="utf-8"), Path("test.txt"))

    assert added == 2, "both cards should be reported as added"
    assert [entry.id for entry in source.entries] == ["a1", None, None], "old cards should be kept and new ones appended"
    assert new_card_count(deck) == 2, "the new cards should be counted as not built yet"


@pytest.mark.parametrize(
    "typed, fragment",
    [
        ("", "nothing to add"),
        ("   \n ", "nothing to add"),
        ("just some words", "expected a line starting with"),
        ("Q: only a question", "needs 'Q:' with 'A:'"),
        ("C: no deletion here", "has no {{c1::...}} deletion"),
        ("deck: Other", "belongs in the header"),
        ("щось {{c1::українською}}", "no voice configured for language 'uk'"),
    ],
)
def test_invalid_text_is_rejected_and_nothing_is_written(deck, typed, fragment):
    with pytest.raises(DeckaloudError) as rejection:
        add_cards(deck, typed, ENGLISH_ONLY)

    assert fragment in str(rejection.value), f"the rejection should mention '{fragment}'"
    assert not deck.exists(), "nothing should be written for rejected text"
