from pathlib import Path

import pytest

from deckaloud.errors import ParseError
from deckaloud.source import ClozeEntry, QaEntry, parse_source

PATH = Path("notes/tcp.txt")

FULL = """\
deck: Networking::TCP
lang: uk

id: k3f9
Q: What does the handshake establish?
A: Sequence numbers
   for both directions.

id: p7a2
lang: en
C: The capital of Ukraine is {{c1::Kyiv::city}}.
"""


def test_header_sets_deck_and_language():
    source = parse_source(FULL, PATH)

    assert source.deck == "Networking::TCP", "header deck should name the deck"
    assert source.lang == "uk", "header lang should set the default language"


def test_entries_keep_order_ids_and_lines():
    question, cloze = parse_source(FULL, PATH).entries

    assert question == QaEntry(
        id="k3f9",
        lang=None,
        line=4,
        question="What does the handshake establish?",
        answer="Sequence numbers for both directions.",
    ), "Q/A block should become a QaEntry with continuation lines joined"
    assert cloze == ClozeEntry(
        id="p7a2",
        lang="en",
        line=9,
        text="The capital of Ukraine is {{c1::Kyiv::city}}.",
    ), "C block should become a ClozeEntry with its own language"


@pytest.mark.parametrize(
    "text, deck, lang",
    [
        ("Q: a\nA: b\n", "tcp", "en"),
        ("lang: uk\n\nQ: a\nA: b\n", "tcp", "uk"),
        ("deck: Custom\n\nQ: a\nA: b\n", "Custom", "en"),
    ],
)
def test_missing_header_values_fall_back(text, deck, lang):
    source = parse_source(text, PATH)

    assert source.deck == deck, f"deck should fall back to {deck}"
    assert source.lang == lang, f"language should fall back to {lang}"
    assert len(source.entries) == 1, "the card block should still be parsed"


def test_unstamped_entry_has_no_id():
    (entry,) = parse_source("Q: a\nA: b\n", PATH).entries

    assert entry.id is None, "a card without an id line should have id None"


@pytest.mark.parametrize(
    "text, line, fragment",
    [
        ("deck: D\n\nQ: only a question\n", 3, "needs"),
        ("deck: D\n\nQ: a\nA: b\nC: {{c1::x}}\n", 3, "needs"),
        ("deck: D\n\nstray words\nQ: a\nA: b\n", 3, "expected"),
        ("deck: D\n\nQ: a\nQ: again\nA: b\n", 4, "twice"),
        ("deck: D\n\nQ:\nA: b\n", 3, "empty"),
        ("deck: D\n\nC: no deletion here\n", 3, "deletion"),
        ("deck: D\n\ndeck: Other\nQ: a\nA: b\n", 3, "header"),
    ],
)
def test_malformed_blocks_report_their_line(text, line, fragment):
    with pytest.raises(ParseError) as raised:
        parse_source(text, PATH)

    message = str(raised.value)
    assert message.startswith(f"{PATH}:{line}:"), f"error should point at line {line}: {message}"
    assert fragment in message, f"error should mention '{fragment}': {message}"


@pytest.mark.parametrize("card_id", ["../../escape", "a b", "a-c1", "a/b", "tag:x", "ід"])
def test_ids_outside_letters_digits_and_underscores_are_rejected(card_id):
    with pytest.raises(ParseError) as raised:
        parse_source(f"id: {card_id}\nQ: a\nA: b\n", PATH)

    assert "letters, digits and underscores" in str(raised.value), f"id '{card_id}' should be rejected"


@pytest.mark.parametrize("card_id", ["k3f9", "3f9a1c20", "Chapter_2_card_10"])
def test_plain_ids_are_accepted(card_id):
    (entry,) = parse_source(f"id: {card_id}\nQ: a\nA: b\n", PATH).entries

    assert entry.id == card_id, f"id '{card_id}' should be accepted"
