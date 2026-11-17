from pathlib import Path

import pytest

from deckaloud.cards import cards_from_source
from deckaloud.engines import Voice
from deckaloud.errors import SpeechError
from deckaloud.sample import (
    audition_voices,
    render_samples,
    sample_jobs,
    sampled_sides,
    silent_languages,
)
from deckaloud.source import parse_source

ENGLISH_THEN_UKRAINIAN = """\
id: e1
Q: First question?
A: First answer.

id: e2
Q: Second question?
A: Second answer.

id: u1
Q: Що таке TCP?
A: Протокол.
"""


def cards(config):
    return cards_from_source(parse_source(ENGLISH_THEN_UKRAINIAN, Path("mixed.txt")), config)


def labels(sides):
    return [side.label for side in sides]


@pytest.mark.parametrize(
    "count, expected",
    [
        (1, ["e1-front", "e1-back", "u1-front", "u1-back"]),
        (2, ["e1-front", "e1-back", "e2-front", "e2-back", "u1-front", "u1-back"]),
    ],
)
def test_every_language_gets_its_own_share_of_whole_cards(studio, count, expected):
    sides = sampled_sides(cards(studio.config), count)

    assert labels(sides) == expected, f"count {count} should pick both sides of {expected}, however late a language appears"


@pytest.mark.parametrize(
    "everything, expected",
    [
        (False, ["Daniel", "Samantha (English (US))", "Ava (Premium)", "Lesya"]),
        (
            True,
            [
                "Bells",
                "Daniel",
                "Eddy (English (US))",
                "Fred",
                "Samantha (English (US))",
                "Ava (Premium)",
                "Lesya",
            ],
        ),
    ],
)
def test_effect_and_synthetic_voices_are_auditioned_only_on_request(everything, expected):
    installed = (
        Voice("Bells", "en_US"),
        Voice("Daniel", "en_GB"),
        Voice("Eddy (English (US))", "en_US"),
        Voice("Fred", "en_US"),
        Voice("Samantha (English (US))", "en_US"),
        Voice("Ava (Premium)", "en_US"),
        Voice("Lesya", "uk_UA"),
    )

    names = [voice.name for voice in audition_voices(installed, everything)]

    assert names == expected, f"all_voices={everything} should audition {expected}"


def test_jobs_pair_each_side_with_the_voices_of_its_language(studio, engine):
    sides = sampled_sides(cards(studio.config), 1)

    jobs = sample_jobs(sides, audition_voices(engine.voices(), False), studio.config)

    assert [str(job.target) for job in jobs] == [
        "en/Daniel/e1-front.m4a",
        "en/Samantha (English (US))/e1-front.m4a",
        "en/Daniel/e1-back.m4a",
        "en/Samantha (English (US))/e1-back.m4a",
        "uk/Lesya/u1-front.m4a",
        "uk/Lesya/u1-back.m4a",
    ], "samples should be laid out as language/voice/card-side"


def test_languages_without_a_voice_are_named(studio):
    sides = sampled_sides(cards(studio.config), 1)

    silent = silent_languages(sides, (Voice("Daniel", "en_GB"),), studio.config)

    assert silent == ("uk",), "a language with sides but no installed voice should be reported"


def test_samples_are_spoken_by_the_sampled_voice(studio, engine, tmp_path):
    jobs = sample_jobs(sampled_sides(cards(studio.config), 1), engine.voices(), studio.config)

    written, failed = render_samples(jobs, studio, tmp_path / "samples")

    assert len(written) == len(jobs) == 10, "one file per side and voice should be written"
    assert all(path.exists() for path in written), "every sample should exist on disk"
    assert failed == (), "nothing should fail with working voices"
    assert {voice for _, voice, _ in engine.spoken} == {
        "Bells",
        "Daniel",
        "Eddy (English (US))",
        "Samantha (English (US))",
        "Lesya",
    }, "each sample should be spoken by its own voice, not the configured one"


def test_one_broken_voice_does_not_stop_the_audition(studio, engine, tmp_path, mocker):
    working = engine.synthesize

    def synthesize(text, voice, rate, target):
        if voice == "Daniel":
            raise SpeechError("'say' failed: no audio")
        working(text, voice, rate, target)

    mocker.patch.object(engine, "synthesize", side_effect=synthesize)
    jobs = sample_jobs(sampled_sides(cards(studio.config), 1), engine.voices(), studio.config)

    written, failed = render_samples(jobs, studio, tmp_path / "samples")

    assert len(written) == 8, "the other voices should still be sampled"
    assert failed == (
        "en/Daniel/e1-front.m4a: 'say' failed: no audio",
        "en/Daniel/e1-back.m4a: 'say' failed: no audio",
    ), "the broken voice should be reported for each side it could not speak"
