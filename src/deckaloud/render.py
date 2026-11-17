import hashlib
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from deckaloud.audio import read_frames, silence_frames, tone_frames, write_wav
from deckaloud.config import Config, Language, ToneShape
from deckaloud.engines import Engine, resolve_voice
from deckaloud.errors import SpeechError
from deckaloud.speech import Beep, Pause, Say, Segment, Speech

CLIP_PREFIX = "deckaloud-"
CLIP_SUFFIX = ".m4a"


@dataclass(frozen=True)
class Studio:
    engine: Engine
    encode: Callable[[Path, Path], None]
    config: Config
    cache_dir: Path


def render_clip(speech: Speech, studio: Studio) -> Path:
    language = installed_language(speech, studio)
    clip = studio.cache_dir / clip_name(speech, language, studio.config)
    if not clip.exists():
        record(speech, language, studio, clip)
    return clip


def installed_language(speech: Speech, studio: Studio) -> Language:
    language = configured_language(speech, studio.config)
    voice = resolve_voice(language.voice, language.locale, studio.engine.voices())
    return replace(language, voice=voice)


def configured_language(speech: Speech, config: Config) -> Language:
    if speech.lang not in config.languages:
        raise SpeechError(f"no voice configured for language '{speech.lang}'")
    return config.languages[speech.lang]


def clip_name(speech: Speech, language: Language, config: Config) -> str:
    sound = repr((config.engine, language, config.tone, config.lead_in, config.tail, speech.segments))
    return f"{CLIP_PREFIX}{hashlib.sha256(sound.encode('utf-8')).hexdigest()[:20]}{CLIP_SUFFIX}"


def record(speech: Speech, language: Language, studio: Studio, clip: Path) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        workdir = Path(scratch)
        takes = (segment_frames(segment, language, studio, workdir) for segment in speech.segments)
        write_wav(workdir / "joined.wav", padded(b"".join(takes), studio.config))
        studio.encode(workdir / "joined.wav", workdir / clip.name)
        studio.cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(workdir / clip.name, clip)


def padded(frames: bytes, config: Config) -> bytes:
    return silence_frames(config.lead_in) + frames + silence_frames(config.tail)


def segment_frames(segment: Segment, language: Language, studio: Studio, workdir: Path) -> bytes:
    match segment:
        case Say(text):
            return spoken_frames(text, language, studio.engine, workdir)
        case Beep():
            return beep_frames(studio.config.tone)
        case Pause(seconds):
            return silence_frames(seconds)


def spoken_frames(text: str, language: Language, engine: Engine, workdir: Path) -> bytes:
    take = workdir / "take.wav"
    engine.synthesize(text, language.voice, language.rate, take)
    return audible(read_frames(take), language)


def audible(frames: bytes, language: Language) -> bytes:
    if not any(frames):
        raise SpeechError(f"voice '{language.voice}' produced no sound")
    return frames


def beep_frames(tone: ToneShape) -> bytes:
    padding = silence_frames(tone.padding)
    return padding + tone_frames(tone.frequency, tone.duration) + padding
