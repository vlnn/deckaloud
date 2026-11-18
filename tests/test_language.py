import pytest

from deckaloud.language import detect_language, language_runs, voiced_by_script
from deckaloud.speech import Beep, Pause, Say, SayIn, Speech

MIXED = "ua months:  Січень: in english?"


@pytest.mark.parametrize(
    "text, default, expected",
    [
        ("What is TCP?", "uk", "en"),
        ("Що таке TCP?", "en", "uk"),
        ("Столиця України", "en", "uk"),
        ("1991", "uk", "uk"),
        ("1991", "en", "en"),
        ("", "en", "en"),
        ("Was ist das?", "de", "de"),
        ("Что это?", "ru", "ru"),
        ("Hello there", "ru", "en"),
        ("Привіт", "de", "uk"),
    ],
)
def test_detect_language_goes_by_script(text, default, expected):
    assert (
        detect_language(text, default) == expected
    ), f"'{text}' with default {default} should be read in {expected}"


@pytest.mark.parametrize(
    "text, default, expected",
    [
        (MIXED, "en", "en"),
        (MIXED, "uk", "en"),
        ("Протокол TCP надійний.", "en", "uk"),
        ("Was ist Привіт?", "de", "de"),
        ("IP це", "en", "en"),
        ("IP це", "uk", "uk"),
    ],
)
def test_mixed_text_belongs_to_the_script_with_most_letters(text, default, expected):
    assert (
        detect_language(text, default) == expected
    ), f"'{text}' with default {default} should mostly be read in {expected}"


@pytest.mark.parametrize(
    "text, default, expected",
    [
        (MIXED, "en", (("ua months:", "en"), ("Січень:", "uk"), ("in english?", "en"))),
        ("Що таке TCP?", "uk", (("Що таке", "uk"), ("TCP?", "en"))),
        ("Что такое TCP?", "ru", (("Что такое", "ru"), ("TCP?", "en"))),
        ("Was ist Привіт?", "de", (("Was ist", "de"), ("Привіт?", "uk"))),
        ("What is TCP?", "en", (("What is TCP?", "en"),)),
        ("1991 рік", "en", (("1991 рік", "uk"),)),
        ("«TCP» це протокол", "uk", (("«TCP»", "en"), ("це протокол", "uk"))),
        ("1991", "en", (("1991", None),)),
        ("", "en", ()),
    ],
)
def test_text_is_cut_where_the_script_changes(text, default, expected):
    assert (
        language_runs(text, default) == expected
    ), f"'{text}' with default {default} should be cut into {expected}"


@pytest.mark.parametrize(
    "speech, default, expected",
    [
        (
            Speech("en", (Say(MIXED),)),
            "en",
            (Say("ua months:"), SayIn("Січень:", "uk"), Say("in english?")),
        ),
        (
            Speech("uk", (Say("TCP"), Pause(0.6), Say("Протокол TCP надійний."))),
            "uk",
            (SayIn("TCP", "en"), Pause(0.6), Say("Протокол"), SayIn("TCP", "en"), Say("надійний.")),
        ),
        (Speech("uk", (Say("Що таке TCP?"),)), "en", (Say("Що таке"), SayIn("TCP?", "en"))),
        (Speech("uk", (Say("1991"), Beep(), Say("рік"))), "en", (Say("1991"), Beep(), Say("рік"))),
        (Speech("en", (Say("What is TCP?"),)), "en", (Say("What is TCP?"),)),
    ],
)
def test_each_stretch_is_voiced_by_the_language_of_its_script(speech, default, expected):
    voiced = voiced_by_script(speech, default)

    assert voiced.lang == speech.lang, "the speech should keep its own language"
    assert voiced.segments == expected, f"{speech.segments} should be voiced as {expected}"
