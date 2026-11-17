import re

CYRILLIC = re.compile(r"[\u0400-\u04FF]")
LATIN = re.compile(r"[A-Za-z]")
CYRILLIC_LANGUAGES = frozenset({"uk", "ru", "be", "bg", "sr", "mk", "kk", "ky", "mn", "tg"})
FALLBACK_BY_SCRIPT = {"cyrillic": "uk", "latin": "en"}


def detect_language(text: str, default: str) -> str:
    script = script_of(text)
    if script is None or script == script_written_by(default):
        return default
    return FALLBACK_BY_SCRIPT[script]


def script_of(text: str) -> str | None:
    if CYRILLIC.search(text):
        return "cyrillic"
    if LATIN.search(text):
        return "latin"
    return None


def script_written_by(language: str) -> str:
    return "cyrillic" if language in CYRILLIC_LANGUAGES else "latin"
