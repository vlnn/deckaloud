import subprocess
from pathlib import Path

import pytest

from deckaloud.engines import (
    SayEngine,
    Voice,
    encode_m4a,
    engine_named,
    parse_voices,
    resolve_voice,
)
from deckaloud.errors import ConfigError, SpeechError

VOICE_LISTING = """\
Daniel              en_GB    # Hello! My name is Daniel.
Lesya               uk_UA    # Привіт! Мене звуть Леся.
Eddy (English (US)) en_US    # Hello! My name is Eddy.
Bad News            en_US    # Hello! My name is Bad News.
Tingting            zh_CN    # 你好！我叫婷婷。
"""


@pytest.fixture
def run(mocker):
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=VOICE_LISTING, stderr="")
    return mocker.patch("deckaloud.engines.subprocess.run", return_value=completed)


def test_say_engine_renders_wav_reading_text_from_stdin(run):
    SayEngine().synthesize("-- hello", "Lesya", 165, Path("out.wav"))

    command = run.call_args.args[0]
    assert command[:5] == ["say", "-v", "Lesya", "-r", "165"], "say should get the voice and rate"
    assert command[5:7] == ["-o", "out.wav"], "say should write to the target file"
    assert "--file-format=WAVE" in command, "say should be asked for a WAVE file"
    assert "--data-format=LEI16@22050" in command, "say should be asked for 16-bit 22.05 kHz audio"
    assert "-- hello" not in command, "text should not travel as an argument where it could look like an option"
    assert run.call_args.kwargs["input"] == "-- hello", "text should be passed on stdin"


def test_encode_m4a_calls_afconvert(run):
    encode_m4a(Path("in.wav"), Path("out.m4a"))

    assert run.call_args.args[0] == [
        "afconvert",
        "-f",
        "m4af",
        "-d",
        "aac",
        "in.wav",
        "out.m4a",
    ], "afconvert should encode AAC into an m4a container"


@pytest.mark.parametrize(
    "failure, fragment",
    [
        (FileNotFoundError("say"), "not available"),
        (subprocess.TimeoutExpired("say", 120), "did not finish"),
        (subprocess.CalledProcessError(1, "say", stderr="Voice `Lesya' not found.\n"), "Voice `Lesya' not found."),
    ],
)
def test_tool_failures_become_speech_errors(mocker, failure, fragment):
    mocker.patch("deckaloud.engines.subprocess.run", side_effect=failure)

    with pytest.raises(SpeechError) as raised:
        SayEngine().synthesize("hello", "Lesya", 165, Path("out.wav"))

    assert fragment in str(raised.value), f"error should carry '{fragment}'"


def test_parse_voices_handles_names_with_spaces_and_brackets():
    assert parse_voices(VOICE_LISTING) == (
        Voice("Daniel", "en_GB"),
        Voice("Lesya", "uk_UA"),
        Voice("Eddy (English (US))", "en_US"),
        Voice("Bad News", "en_US"),
        Voice("Tingting", "zh_CN"),
    ), "every listed voice should be parsed with its full name and locale"


def test_say_engine_lists_installed_voices(run):
    assert Voice("Lesya", "uk_UA") in SayEngine().voices(), "voices should come from say's listing"
    assert run.call_args.args[0] == ["say", "-v", "?"], "voices should be listed with say -v ?"


def test_engine_named_returns_say():
    assert isinstance(engine_named("say"), SayEngine), "'say' should select the macOS engine"


@pytest.mark.parametrize("name", ["piper", "ukrainian-tts", ""])
def test_unsupported_engine_is_a_config_error(name):
    with pytest.raises(ConfigError) as raised:
        engine_named(name)

    assert "say" in str(raised.value), "error should list the engines that do work"


INSTALLED = (
    Voice("Daniel", "en_GB"),
    Voice("Eddy (English (UK))", "en_GB"),
    Voice("Eddy (English (US))", "en_US"),
    Voice("Samantha (English (US))", "en_US"),
    Voice("Ava (Enhanced)", "en_US"),
    Voice("Ava (Premium)", "en_US"),
    Voice("Lesya", "uk_UA"),
    Voice("Lesya (Enhanced)", "uk_UA"),
)


@pytest.mark.parametrize(
    "wanted, locale, expected",
    [
        ("Daniel", "en_GB", "Daniel"),
        ("Samantha", "en_US", "Samantha (English (US))"),
        ("Samantha (English (US))", "en_US", "Samantha (English (US))"),
        ("Eddy", "en_US", "Eddy (English (US))"),
        ("Eddy", "en_GB", "Eddy (English (UK))"),
        ("Ava", "en_US", "Ava (Premium)"),
        ("Ava (Enhanced)", "en_US", "Ava (Enhanced)"),
        ("Lesya", "uk_UA", "Lesya (Enhanced)"),
    ],
)
def test_resolve_voice_finds_the_installed_name(wanted, locale, expected):
    assert (
        resolve_voice(wanted, locale, INSTALLED) == expected
    ), f"'{wanted}' for {locale} should resolve to '{expected}'"


@pytest.mark.parametrize("wanted", ["Milena", "Sam", "samantha"])
def test_resolve_voice_rejects_what_is_not_installed(wanted):
    with pytest.raises(SpeechError) as raised:
        resolve_voice(wanted, "en_US", INSTALLED)

    assert f"'{wanted}' is not installed" in str(raised.value), "error should name the missing voice"


def test_say_engine_asks_for_the_voice_list_once(run):
    engine = SayEngine()

    engine.voices()
    engine.voices()

    assert run.call_count == 1, "the installed voice list should be read once per engine"
