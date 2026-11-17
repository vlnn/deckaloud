import pytest

from deckaloud.config import Config, config_from_mapping, load_config
from deckaloud.errors import ConfigError


def test_defaults_cover_english_and_ukrainian():
    config = Config()

    assert config.gap_style == "blank", "default gap style should be the spoken word"
    assert (config.lead_in, config.tail) == (0.25, 0.5), "clips should be padded with silence by default"
    assert config.languages["uk"].voice == "Lesya", "default Ukrainian voice should be Lesya"
    assert set(config.languages) == {"en", "uk"}, "defaults should configure en and uk"


@pytest.mark.parametrize(
    "data, read, expected",
    [
        ({"gap": {"style": "tone"}}, lambda c: c.gap_style, "tone"),
        ({"pauses": {"cloze_answer": 1.5}}, lambda c: c.cloze_pause, 1.5),
        ({"pauses": {"lead_in": 0.4}}, lambda c: c.lead_in, 0.4),
        ({"pauses": {"lead_in": 0.4}}, lambda c: c.tail, 0.5),
        ({"pauses": {"tail": 0}}, lambda c: c.tail, 0),
        ({"engine": "piper"}, lambda c: c.engine, "piper"),
        ({"tone": {"frequency": 440}}, lambda c: c.tone.frequency, 440),
        ({"tone": {"frequency": 440}}, lambda c: c.tone.duration, 0.25),
        ({"languages": {"uk": {"rate": 150}}}, lambda c: c.languages["uk"].rate, 150),
        ({"languages": {"uk": {"rate": 150}}}, lambda c: c.languages["uk"].voice, "Lesya"),
        ({"languages": {"en": {"voice": "Daniel"}}}, lambda c: c.languages["uk"].voice, "Lesya"),
        (
            {"languages": {"de": {"voice": "Anna", "locale": "de_DE"}}},
            lambda c: c.languages["de"].gap_word,
            "blank",
        ),
    ],
)
def test_mapping_overrides_only_what_it_names(data, read, expected):
    assert read(config_from_mapping(data)) == expected, f"{data} should yield {expected}"


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"gap": {"style": "whistle"}}, "gap.style"),
        ({"languages": {"de": {"voice": "Anna"}}}, "locale"),
        ({"languages": {"de": {"locale": "de_DE"}}}, "voice"),
        ({"languages": {"x y": {"voice": "V", "locale": "de_DE"}}}, "language code"),
        ({"languages": {"DE": {"voice": "V", "locale": "de_DE"}}}, "language code"),
        ({"languages": {"de": {"voice": "V", "locale": "}}{{Front"}}}, "locale"),
        ({"languages": {"en": {"locale": "en US"}}}, "locale"),
        (
            {"languages": {code: {"voice": "V", "locale": "xx_XX"} for code in ("aa", "bb", "cc", "dd", "ee")}},
            "at most 6",
        ),
    ],
)
def test_invalid_mapping_is_rejected(data, fragment):
    with pytest.raises(ConfigError) as raised:
        config_from_mapping(data)

    assert fragment in str(raised.value), f"error should mention {fragment}"


def test_load_config_reads_toml(tmp_path):
    path = tmp_path / "deckaloud.toml"
    path.write_text('[gap]\nstyle = "tone"\n', encoding="utf-8")

    assert load_config(path).gap_style == "tone", "load_config should read the TOML file"


def test_load_config_without_file_uses_defaults(tmp_path):
    assert load_config(tmp_path / "absent.toml") == Config(), "a missing file should mean defaults"
