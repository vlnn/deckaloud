from dataclasses import replace
from pathlib import Path

import pytest

from deckaloud.cards import cards_from_source
from deckaloud.config import Config
from deckaloud.source import parse_source
from deckaloud.speech import Beep, Pause, Say, SayIn, Speech

PATH = Path("geo.txt")
BLANK = Config()
TONE = replace(Config(), gap_style="tone")
TWO_GAPS = "id: p7a2\nC: The capital of Ukraine is {{c1::Kyiv::city}}, on the {{c2::Dnipro}} river.\n"


def cards(text, config=BLANK):
    return cards_from_source(parse_source(text, PATH), config)


def test_question_card_speaks_question_then_only_answer():
    (card,) = cards("deck: Geo\n\nid: a1\nQ: What is the capital of Ukraine?\nA: Kyiv.\n")

    assert card.guid == "deckaloud-a1", "guid should come from the stamped id"
    assert card.deck == "Geo", "card should carry its deck"
    assert card.origin == "geo.txt:3", "origin should point at the source block"
    assert card.front.text == "What is the capital of Ukraine?", "front should show the question"
    assert card.front.speech == Speech(
        "en", (Say("What is the capital of Ukraine?"),)
    ), "front should speak the question"
    assert card.back.speech == Speech("en", (Say("Kyiv."),)), "back should speak only the answer"


def test_each_deletion_number_becomes_its_own_card():
    first, second = cards(TWO_GAPS)

    assert (first.guid, second.guid) == (
        "deckaloud-p7a2-c1",
        "deckaloud-p7a2-c2",
    ), "cloze guids should add the deletion number to the note id"


@pytest.mark.parametrize(
    "config, index, expected",
    [
        (BLANK, 0, (Say("The capital of Ukraine is blank, city, on the Dnipro river."),)),
        (BLANK, 1, (Say("The capital of Ukraine is Kyiv, on the blank river."),)),
        (
            TONE,
            0,
            (Say("The capital of Ukraine is"), Beep(), Say("city"), Say("on the Dnipro river.")),
        ),
        (
            TONE,
            1,
            (Say("The capital of Ukraine is Kyiv, on the"), Beep(), Say("river.")),
        ),
    ],
)
def test_cloze_front_speaks_the_gap_in_the_configured_style(config, index, expected):
    card = cards(TWO_GAPS, config)[index]

    assert card.front.speech.segments == expected, f"gap style {config.gap_style} should give {expected}"


@pytest.mark.parametrize(
    "index, text",
    [
        (0, "The capital of Ukraine is [city], on the Dnipro river."),
        (1, "The capital of Ukraine is Kyiv, on the [...] river."),
    ],
)
def test_cloze_front_text_marks_the_gap(index, text):
    assert cards(TWO_GAPS)[index].front.text == text, f"front text should read '{text}'"


def test_cloze_back_speaks_deleted_part_pause_then_full_sentence():
    back = cards(TWO_GAPS)[0].back
    sentence = "The capital of Ukraine is Kyiv, on the Dnipro river."

    assert back.text == sentence, "back should show the full sentence"
    assert back.speech.segments == (
        Say("Kyiv"),
        Pause(BLANK.cloze_pause),
        Say(sentence),
    ), "back should speak the deletion, pause, then the full sentence"


def test_same_numbered_gaps_share_one_card():
    (card,) = cards("id: s1\nC: {{c1::Kyiv}} lies on the {{c1::Dnipro}}.\n")

    assert card.front.speech.segments == (
        Say("blank lies on the blank."),
    ), "both same-numbered gaps should be hidden on one card"
    assert card.back.speech.segments[0] == Say("Kyiv, Dnipro"), "back should name every hidden part"


def test_gap_ending_a_sentence_leaves_no_silent_fragment_in_tone_style():
    (card,) = cards("id: e1\nC: The capital is {{c1::Kyiv}}.\n", TONE)

    assert card.front.speech.segments == (
        Say("The capital is"),
        Beep(),
    ), "punctuation-only fragments should not be sent to the voice"


@pytest.mark.parametrize(
    "text, front_lang, back_lang",
    [
        ("lang: uk\n\nid: a\nQ: Що таке TCP?\nA: Transmission Control Protocol\n", "uk", "en"),
        ("lang: uk\n\nid: a\nQ: Рік незалежності?\nA: 1991\n", "uk", "uk"),
        ("id: a\nlang: uk\nQ: TCP?\nA: Transmission Control Protocol\n", "uk", "uk"),
        ("id: a\nC: Столиця України це {{c1::Київ}}.\n", "uk", "uk"),
        ("lang: uk\n\nid: a\nC: Протокол {{c1::TCP}} надійний.\n", "uk", "uk"),
    ],
)
def test_language_is_override_then_script_then_file_default(text, front_lang, back_lang):
    card = cards(text)[0]

    assert card.front.speech.lang == front_lang, f"front should be read in {front_lang}"
    assert card.back.speech.lang == back_lang, f"back should be read in {back_lang}"


def test_ukrainian_gap_uses_the_ukrainian_word():
    (card,) = cards("id: a\nC: Столиця України це {{c1::Київ}}.\n")

    assert card.front.speech.segments == (
        Say("Столиця України це пропуск."),
    ), "gap word should follow the card language"


def test_unstamped_card_is_keyed_by_line():
    (card,) = cards("Q: a\nA: b\n")

    assert card.key == "line1", "a card without an id should be keyed by its line for sampling"


@pytest.mark.parametrize(
    "sentence, config, expected",
    [
        ("-5 degrees is {{c1::cold}}.", BLANK, (Say("-5 degrees is blank."),)),
        (".NET runs on the {{c1::CLR}}.", BLANK, (Say(".NET runs on the blank."),)),
        ("$100 is {{c1::cheap}}.", BLANK, (Say("$100 is blank."),)),
        (".NET runs on the {{c1::CLR}}.", TONE, (Say(".NET runs on the"), Beep())),
        ("It is {{c1::cold}}, -5 degrees.", TONE, (Say("It is"), Beep(), Say("-5 degrees."))),
        ("{{c1::Microsoft}} .NET is old.", TONE, (Beep(), Say(".NET is old."))),
        ("Is it {{c1::cold}}? Yes.", TONE, (Say("Is it"), Beep(), Say("Yes."))),
    ],
)
def test_only_dangling_punctuation_is_dropped_from_spoken_fragments(sentence, config, expected):
    (card,) = cards(f"id: a\nC: {sentence}\n", config)

    assert card.front.speech.segments == expected, f"'{sentence}' should be spoken as {expected}"


MONTH = "ua months:  Січень: in english?"


def test_foreign_word_inside_a_side_gets_the_voice_of_its_script():
    (card,) = cards(f"lang: en\n\nid: a9224079\nQ: {MONTH}\nA: January.\n")

    assert card.front.text == MONTH, "front should show the question as written"
    assert card.front.speech == Speech(
        "en", (Say("ua months:"), SayIn("Січень:", "uk"), Say("in english?"))
    ), "the Ukrainian word should be the only part handed to the Ukrainian voice"
    assert card.back.speech == Speech("en", (Say("January."),)), "a one-script answer should stay one utterance"


def test_card_language_override_keeps_the_whole_side_in_one_voice():
    (card,) = cards(f"id: a\nlang: en\nQ: {MONTH}\nA: January.\n")

    assert card.front.speech == Speech("en", (Say(MONTH),)), "a forced language should read every script itself"


@pytest.mark.parametrize(
    "config, front",
    [
        (BLANK, (Say("Протокол пропуск надійний."),)),
        (TONE, (Say("Протокол"), Beep(), Say("надійний."))),
    ],
)
def test_cloze_sides_switch_voice_for_a_foreign_term(config, front):
    (card,) = cards("lang: uk\n\nid: a\nC: Протокол {{c1::TCP}} надійний.\n", config)

    assert card.front.speech == Speech("uk", front), "the hidden term should leave a one-voice front"
    assert card.back.speech == Speech(
        "uk",
        (SayIn("TCP", "en"), Pause(config.cloze_pause), Say("Протокол"), SayIn("TCP", "en"), Say("надійний.")),
    ), "the English term should be spoken by the English voice inside the Ukrainian sentence"
