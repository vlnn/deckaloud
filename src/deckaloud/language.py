import re
from dataclasses import replace

from deckaloud.speech import Say, SayIn, Segment, Speech

CYRILLIC_LETTERS = r"\u0400-\u04FF"
LATIN_LETTERS = r"A-Za-z\u00C0-\u024F"
LETTERS = {
    "cyrillic": re.compile(f"[{CYRILLIC_LETTERS}]"),
    "latin": re.compile(f"[{LATIN_LETTERS}]"),
}
SCRIPT_RUN = re.compile(
    f"[^{LATIN_LETTERS}]*[{CYRILLIC_LETTERS}][^{LATIN_LETTERS}]*"
    f"|[^{CYRILLIC_LETTERS}]*[{LATIN_LETTERS}][^{CYRILLIC_LETTERS}]*"
    "|.+",
    re.DOTALL,
)
CYRILLIC_LANGUAGES = frozenset({"uk", "ru", "be", "bg", "sr", "mk", "kk", "ky", "mn", "tg"})
FALLBACK_BY_SCRIPT = {"cyrillic": "uk", "latin": "en"}


def detect_language(text: str, default: str) -> str:
    home = script_written_by(default)
    script = dominant_script(text, home)
    if script is None or script == home:
        return default
    return FALLBACK_BY_SCRIPT[script]


def dominant_script(text: str, tie_winner: str) -> str | None:
    counts = {script: len(letters.findall(text)) for script, letters in LETTERS.items()}
    if not any(counts.values()):
        return None
    return max(counts, key=lambda script: (counts[script], script == tie_winner))


def script_written_by(language: str) -> str:
    return "cyrillic" if language in CYRILLIC_LANGUAGES else "latin"


def has_voiced_letters(text: str) -> bool:
    return any(letters.search(text) for letters in LETTERS.values())


def has_unvoiced_script(text: str) -> bool:
    return any(character.isalpha() for character in text) and not has_voiced_letters(text)


def language_runs(text: str, default: str) -> tuple[tuple[str, str | None], ...]:
    runs = (match.group().strip() for match in SCRIPT_RUN.finditer(text))
    return tuple((run, run_language(run, default)) for run in runs if run)


def run_language(run: str, default: str) -> str | None:
    return detect_language(run, default) if has_voiced_letters(run) else None


def voiced_by_script(speech: Speech, default: str) -> Speech:
    stretches = (stretch for segment in speech.segments for stretch in stretches_of(segment, speech.lang, default))
    return replace(speech, segments=tuple(stretches))


def stretches_of(segment: Segment, lang: str, default: str) -> tuple[Segment, ...]:
    if not isinstance(segment, Say):
        return (segment,)
    return tuple(stretch(text, run_lang, lang) for text, run_lang in language_runs(segment.text, default))


def stretch(text: str, run_lang: str | None, lang: str) -> Say | SayIn:
    return Say(text) if run_lang in (None, lang) else SayIn(text, run_lang)
