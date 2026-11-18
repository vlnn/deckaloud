import pytest

from deckaloud.speech import Beep, Pause, Say, SayIn, Speech, plain_text, spoken_languages


@pytest.mark.parametrize(
    "segments, expected",
    [
        ((Say("What is TCP?"),), "What is TCP?"),
        ((Say("Kyiv"), Pause(0.6), Say("Kyiv is the capital.")), "Kyiv. Kyiv is the capital."),
        ((Say("The capital is"), Beep(), Say("city")), "The capital is blank city"),
        ((Say("ua months:"), SayIn("Січень:", "uk"), Say("in english?")), "ua months: Січень: in english?"),
    ],
)
def test_plain_text_flattens_segments_for_runtime_speech(segments, expected):
    assert (
        plain_text(Speech("en", segments), "blank") == expected
    ), f"{segments} should flatten to '{expected}'"


@pytest.mark.parametrize(
    "speech, expected",
    [
        (Speech("en", (Say("hello"),)), ("en",)),
        (Speech("en", (Say("month"), SayIn("Січень", "uk"), Pause(0.6), SayIn("Грудень", "uk"))), ("en", "uk")),
        (Speech("uk", (SayIn("TCP", "en"), Beep(), SayIn("Hallo", "de"))), ("uk", "en", "de")),
    ],
)
def test_spoken_languages_start_with_the_speech_language_and_name_each_other_one_once(speech, expected):
    assert spoken_languages(speech) == expected, f"{speech} should be spoken in {expected}"
