import pytest

from deckaloud.language import detect_language


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
