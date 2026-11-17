import shutil
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from deckaloud.cards import Card
from deckaloud.config import Config
from deckaloud.engines import Voice
from deckaloud.errors import SpeechError
from deckaloud.render import Studio, render_clip
from deckaloud.speech import Speech

EFFECT_VOICES = frozenset(
    {
        "Albert", "Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos", "Good News",
        "Jester", "Organ", "Superstar", "Trinoids", "Whisper", "Wobble", "Zarvox",
    }
)
SYNTHETIC_VOICES = frozenset(
    {
        "Eddy", "Flo", "Grandma", "Grandpa", "Reed", "Rocko", "Sandy", "Shelley",
        "Fred", "Junior", "Kathy", "Ralph",
    }
)
NOT_AUDITIONED = EFFECT_VOICES | SYNTHETIC_VOICES


@dataclass(frozen=True)
class SampledSide:
    label: str
    speech: Speech


@dataclass(frozen=True)
class SampleJob:
    speech: Speech
    voice: str
    target: Path


def sampled_sides(cards: tuple[Card, ...], per_language: int) -> tuple[SampledSide, ...]:
    taken: Counter[str] = Counter()
    return all_sides(tuple(card for card in cards if is_within_share(card, taken, per_language)))


def all_sides(cards: tuple[Card, ...]) -> tuple[SampledSide, ...]:
    return tuple(
        SampledSide(f"{card.key}-{name}", side.speech)
        for card in cards
        for name, side in (("front", card.front), ("back", card.back))
    )


def is_within_share(card: Card, taken: Counter, per_language: int) -> bool:
    lang = card.front.speech.lang
    taken[lang] += 1
    return taken[lang] <= per_language


def audition_voices(installed: tuple[Voice, ...], everything: bool) -> tuple[Voice, ...]:
    return tuple(voice for voice in installed if everything or base_name(voice) not in NOT_AUDITIONED)


def base_name(voice: Voice) -> str:
    return voice.name.split(" (")[0]


def voices_speaking(voices: tuple[Voice, ...], lang: str, config: Config) -> tuple[Voice, ...]:
    if lang not in config.languages:
        return ()
    return tuple(voice for voice in voices if voice.locale.startswith(f"{lang}_"))


def sample_jobs(sides: tuple[SampledSide, ...], voices: tuple[Voice, ...], config: Config) -> tuple[SampleJob, ...]:
    return tuple(
        SampleJob(side.speech, voice.name, Path(side.speech.lang, voice.name, f"{side.label}.m4a"))
        for side in sides
        for voice in voices_speaking(voices, side.speech.lang, config)
    )


def silent_languages(sides: tuple[SampledSide, ...], voices: tuple[Voice, ...], config: Config) -> tuple[str, ...]:
    langs = dict.fromkeys(side.speech.lang for side in sides)
    return tuple(lang for lang in langs if not voices_speaking(voices, lang, config))


def render_samples(
    jobs: tuple[SampleJob, ...], studio: Studio, out_dir: Path
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    outcomes = [render_sample(job, studio, out_dir) for job in jobs]
    written = tuple(outcome for outcome in outcomes if isinstance(outcome, Path))
    failed = tuple(outcome for outcome in outcomes if isinstance(outcome, str))
    return written, failed


def render_sample(job: SampleJob, studio: Studio, out_dir: Path) -> Path | str:
    try:
        clip = render_clip(job.speech, with_voice(studio, job.speech.lang, job.voice))
    except SpeechError as error:
        return f"{job.target}: {error}"
    target = out_dir / job.target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip, target)
    return target


def with_voice(studio: Studio, lang: str, voice: str) -> Studio:
    config = studio.config
    languages = {**config.languages, lang: replace(config.languages[lang], voice=voice)}
    return replace(studio, config=replace(config, languages=languages))
