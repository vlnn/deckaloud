import pytest

from deckaloud.speech import Beep, Pause, Say, Speech, plain_text


@pytest.mark.parametrize(
    "segments, expected",
    [
        ((Say("What is TCP?"),), "What is TCP?"),
        ((Say("Kyiv"), Pause(0.6), Say("Kyiv is the capital.")), "Kyiv. Kyiv is the capital."),
        ((Say("The capital is"), Beep(), Say("city")), "The capital is blank city"),
    ],
)
def test_plain_text_flattens_segments_for_runtime_speech(segments, expected):
    assert (
        plain_text(Speech("en", segments), "blank") == expected
    ), f"{segments} should flatten to '{expected}'"
