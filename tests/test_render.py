from dataclasses import replace

import pytest
from conftest import SECONDS_PER_CHARACTER

from deckaloud.audio import SAMPLE_RATE, read_frames, silence_frames, write_wav
from deckaloud.config import Config, Language
from deckaloud.errors import SpeechError
from deckaloud.render import clip_name, installed_language, render_clip
from deckaloud.speech import Beep, Pause, Say, SayIn, Speech

HELLO = Speech("en", (Say("hello"),))


def seconds(path):
    return len(read_frames(path)) / 2 / SAMPLE_RATE


def padding(config):
    return config.lead_in + config.tail


def test_clip_is_rendered_into_the_cache_with_the_configured_voice(studio, engine):
    clip = render_clip(HELLO, studio)

    assert clip.parent == studio.cache_dir, "clip should be stored in the cache directory"
    assert clip.name == clip_name(
        HELLO, installed_language(HELLO.lang, studio), studio.config
    ), "clip should be named by its fingerprint"
    assert clip.suffix == ".m4a", "clip should be an m4a file"
    assert engine.spoken == [
        ("hello", "Samantha (English (US))", 175)
    ], "engine should get the installed name of the configured voice, and its rate"


def test_second_render_reuses_the_cached_clip(studio, engine):
    first = render_clip(HELLO, studio)
    second = render_clip(HELLO, studio)

    assert first == second, "the same speech should map to the same clip"
    assert len(engine.spoken) == 1, "a cached clip should not be synthesized again"


def test_segments_are_joined_in_order(studio):
    speech = Speech("en", (Say("ab"), Pause(0.5), Say("abcd")))

    clip = render_clip(speech, studio)

    assert seconds(clip) == pytest.approx(
        6 * SECONDS_PER_CHARACTER + 0.5 + padding(studio.config), abs=0.001
    ), "clip should contain both utterances with the pause between them, inside the padding"


def test_beep_adds_tone_with_padding_on_both_sides(studio):
    tone = studio.config.tone

    clip = render_clip(Speech("en", (Beep(),)), studio)

    assert seconds(clip) == pytest.approx(
        tone.duration + 2 * tone.padding + padding(studio.config), abs=0.001
    ), "beep should be the tone surrounded by its own padding"


ENGLISH = Language("Samantha", "en_US")


@pytest.mark.parametrize("lead_in, tail", [(0.0, 0.0), (0.25, 0.5), (1.0, 0.0), (0.0, 2.0)])
def test_every_clip_is_wrapped_in_the_configured_silence(studio, lead_in, tail):
    padded = replace(studio, config=replace(studio.config, lead_in=lead_in, tail=tail))

    clip = render_clip(HELLO, padded)
    frames = read_frames(clip)
    lead_bytes = round(lead_in * SAMPLE_RATE) * 2

    assert seconds(clip) == pytest.approx(
        5 * SECONDS_PER_CHARACTER + lead_in + tail, abs=0.001
    ), f"clip should be the speech plus {lead_in}s before and {tail}s after"
    assert not any(frames[:lead_bytes]), "the lead-in should be silence"


@pytest.mark.parametrize(
    "language, config",
    [
        (Language("Daniel", "en_GB"), Config()),
        (Language("Samantha (Enhanced)", "en_US"), Config()),
        (replace(ENGLISH, rate=120), Config()),
        (ENGLISH, replace(Config(), engine="piper")),
        (ENGLISH, replace(Config(), tone=replace(Config().tone, frequency=440))),
        (ENGLISH, replace(Config(), lead_in=0.0)),
        (ENGLISH, replace(Config(), tail=1.0)),
    ],
)
def test_clip_name_changes_with_anything_that_changes_the_sound(language, config):
    assert clip_name(HELLO, ENGLISH, Config()) != clip_name(
        HELLO, language, config
    ), "a new sound should get a new name"


def test_one_language_clip_keeps_the_name_earlier_builds_gave_it():
    assert (
        clip_name(HELLO, ENGLISH, Config()) == "deckaloud-3038242e372398fe3e72.m4a"
    ), "clips already cached or imported should not be rendered again under a new name"


def test_clip_name_is_stable_and_depends_on_text():
    assert clip_name(HELLO, ENGLISH, Config()) == clip_name(
        HELLO, ENGLISH, Config()
    ), "equal inputs should give equal names"
    assert clip_name(HELLO, ENGLISH, Config()) != clip_name(
        Speech("en", (Say("goodbye"),)), ENGLISH, Config()
    ), "different text should give a different name"


def test_newly_installed_better_voice_is_not_hidden_by_the_cache(studio, engine, mocker):
    before = render_clip(HELLO, studio)
    upgraded = (*engine.voices(), type(engine.voices()[0])("Samantha (Enhanced)", "en_US"))
    mocker.patch.object(engine, "voices", return_value=upgraded)

    after = render_clip(HELLO, studio)

    assert after != before, "a better variant of the configured voice should get its own clip"
    assert engine.spoken[-1][1] == "Samantha (Enhanced)", "the better variant should speak the new clip"


def test_unconfigured_language_is_a_speech_error(studio):
    with pytest.raises(SpeechError) as raised:
        render_clip(Speech("de", (Say("hallo"),)), studio)

    assert "'de'" in str(raised.value), "error should name the language without a voice"


def test_voice_that_is_not_installed_is_a_speech_error_and_leaves_no_clip(studio):
    config = replace(studio.config, languages={"en": Language("Missing", "en_US")})

    with pytest.raises(SpeechError) as raised:
        render_clip(HELLO, replace(studio, config=config))

    assert "'Missing' is not installed" in str(raised.value), "error should name the missing voice"
    assert not list(studio.cache_dir.glob("*")), "a failed render should not leave a file in the cache"


def test_voice_that_produces_only_silence_is_a_speech_error(studio, engine, mocker):
    mute = lambda text, voice, rate, target: write_wav(target, silence_frames(0.2))
    mocker.patch.object(engine, "synthesize", side_effect=mute)

    with pytest.raises(SpeechError) as raised:
        render_clip(HELLO, studio)

    assert "no sound" in str(raised.value), "a silent rendering should be reported, not baked"
    assert not list(studio.cache_dir.glob("*")), "a silent clip should not reach the cache"


MONTH = Speech("en", (Say("ua months:"), SayIn("Січень:", "uk"), Say("in english?")))
UKRAINIAN = Language("Lesya", "uk_UA", rate=165)


def test_stretch_in_another_language_is_spoken_by_that_language_voice(studio, engine):
    clip = render_clip(MONTH, studio)

    assert engine.spoken == [
        ("ua months:", "Samantha (English (US))", 175),
        ("Січень:", "Lesya", 165),
        ("in english?", "Samantha (English (US))", 175),
    ], "each stretch should go to the voice and rate of its own language"
    assert seconds(clip) == pytest.approx(
        28 * SECONDS_PER_CHARACTER + padding(studio.config), abs=0.001
    ), "the stretches should be joined into one clip"


@pytest.mark.parametrize(
    "guests",
    [(), (replace(UKRAINIAN, voice="Lesya (Enhanced)"),), (replace(UKRAINIAN, rate=120),)],
)
def test_clip_name_changes_with_the_voice_of_a_foreign_stretch(guests):
    assert clip_name(MONTH, ENGLISH, Config(), (UKRAINIAN,)) != clip_name(
        MONTH, ENGLISH, Config(), guests
    ), "a new sound for the foreign stretch should get a new name"


@pytest.mark.parametrize(
    "languages, fragment",
    [
        ({"en": ENGLISH}, "no voice configured for language 'uk'"),
        ({"en": ENGLISH, "uk": Language("Missing", "uk_UA")}, "'Missing' is not installed"),
    ],
)
def test_foreign_stretch_without_a_voice_is_a_speech_error(studio, languages, fragment):
    config = replace(studio.config, languages=languages)

    with pytest.raises(SpeechError) as raised:
        render_clip(MONTH, replace(studio, config=config))

    assert fragment in str(raised.value), f"error should say: {fragment}"
    assert not list(studio.cache_dir.glob("*")), "a failed render should not leave a file in the cache"
