import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from deckaloud.errors import ConfigError

GAP_STYLES = ("blank", "tone")
DEFAULT_GAP_WORD = "blank"
MAX_LANGUAGES = 6
DEFAULT_REPLAY_KEYS = ("4",)
LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}$")
LOCALE = re.compile(r"^[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)*$")


@dataclass(frozen=True)
class Language:
    voice: str
    locale: str
    rate: int = 175
    gap_word: str = DEFAULT_GAP_WORD


@dataclass(frozen=True)
class ToneShape:
    frequency: float = 880.0
    duration: float = 0.25
    padding: float = 0.15


def default_languages() -> dict[str, Language]:
    return {
        "en": Language(voice="Samantha", locale="en_US"),
        "uk": Language(voice="Lesya", locale="uk_UA", rate=165, gap_word="пропуск"),
    }


@dataclass(frozen=True)
class Config:
    gap_style: str = "blank"
    cloze_pause: float = 0.6
    lead_in: float = 0.25
    tail: float = 0.5
    engine: str = "say"
    tone: ToneShape = ToneShape()
    languages: Mapping[str, Language] = field(default_factory=default_languages)
    replay_keys: tuple[str, ...] = DEFAULT_REPLAY_KEYS


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    return config_from_mapping(tomllib.loads(path.read_text(encoding="utf-8")))


def config_from_mapping(data: Mapping[str, Any]) -> Config:
    defaults = Config()
    pauses = data.get("pauses", {})
    return Config(
        gap_style=gap_style(data.get("gap", {}).get("style", defaults.gap_style)),
        cloze_pause=pauses.get("cloze_answer", defaults.cloze_pause),
        lead_in=pauses.get("lead_in", defaults.lead_in),
        tail=pauses.get("tail", defaults.tail),
        engine=data.get("engine", defaults.engine),
        tone=replace(defaults.tone, **known(ToneShape, data.get("tone", {}))),
        languages=merged_languages(defaults.languages, data.get("languages", {})),
        replay_keys=replay_keys(data.get("keys", {}).get("replay", defaults.replay_keys)),
    )


def gap_style(style: str) -> str:
    if style not in GAP_STYLES:
        raise ConfigError(f"gap.style must be one of {', '.join(GAP_STYLES)}, got '{style}'")
    return style


def replay_keys(value: Any) -> tuple[str, ...]:
    keys = [value] if isinstance(value, str) else value
    if not is_key_list(keys):
        raise ConfigError(f'keys.replay must be a quoted key or a list of them, like "4" or ["4", "r"], got {value!r}')
    return tuple(keys)


def is_key_list(keys: Any) -> bool:
    return isinstance(keys, (list, tuple)) and all(isinstance(key, str) and key for key in keys)


def merged_languages(
    defaults: Mapping[str, Language], overrides: Mapping[str, Mapping[str, Any]]
) -> dict[str, Language]:
    merged = {code: language(code, defaults.get(code), values) for code, values in overrides.items()}
    return within_limit({**defaults, **merged})


def within_limit(languages: dict[str, Language]) -> dict[str, Language]:
    if len(languages) > MAX_LANGUAGES:
        raise ConfigError(f"at most {MAX_LANGUAGES} languages can be configured, got {len(languages)}")
    return languages


def language(code: str, base: Language | None, values: Mapping[str, Any]) -> Language:
    if not LANGUAGE_CODE.match(code):
        raise ConfigError(f"language code '{code}' must be two or three lowercase letters")
    return with_valid_locale(code, described_language(code, base, values))


def described_language(code: str, base: Language | None, values: Mapping[str, Any]) -> Language:
    if base is not None:
        return replace(base, **known(Language, values))
    try:
        return Language(**known(Language, values))
    except TypeError:
        raise ConfigError(f"languages.{code} needs both 'voice' and 'locale'") from None


def with_valid_locale(code: str, described: Language) -> Language:
    if not LOCALE.match(str(described.locale)):
        raise ConfigError(f"languages.{code}: locale '{described.locale}' should look like en_US")
    return described


def known(shape: type, values: Mapping[str, Any]) -> dict[str, Any]:
    names = {item.name for item in fields(shape)}
    return {key: value for key, value in values.items() if key in names}
