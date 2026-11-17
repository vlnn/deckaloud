import re
from dataclasses import dataclass

from deckaloud.cloze import (
    Part,
    deletion_numbers,
    full_sentence,
    hidden_deletions,
    is_hidden,
    parse_cloze,
    revealed,
)
from deckaloud.config import DEFAULT_GAP_WORD, Config
from deckaloud.language import detect_language
from deckaloud.source import ClozeEntry, Entry, QaEntry, SourceFile
from deckaloud.speech import Beep, Pause, Say, Segment, Speech

GUID_PREFIX = "deckaloud-"
DANGLING_PUNCTUATION = re.compile(r"^\s*(?:[,.;:!?)\]}»”…]+(?=\s|$))?\s*")
SPEAKABLE = re.compile(r"\w")


@dataclass(frozen=True)
class Side:
    text: str
    speech: Speech


@dataclass(frozen=True)
class Card:
    key: str
    deck: str
    origin: str
    front: Side
    back: Side

    @property
    def guid(self) -> str:
        return f"{GUID_PREFIX}{self.key}"


def cards_from_source(source: SourceFile, config: Config) -> tuple[Card, ...]:
    return tuple(card for entry in source.entries for card in entry_cards(entry, source, config))


def entry_cards(entry: Entry, source: SourceFile, config: Config) -> tuple[Card, ...]:
    match entry:
        case QaEntry():
            return (qa_card(entry, source),)
        case ClozeEntry():
            return cloze_cards(entry, source, config)


def entry_key(entry: Entry) -> str:
    return entry.id or f"line{entry.line}"


def origin(entry: Entry, source: SourceFile) -> str:
    return f"{source.path}:{entry.line}"


def qa_card(entry: QaEntry, source: SourceFile) -> Card:
    return Card(
        key=entry_key(entry),
        deck=source.deck,
        origin=origin(entry, source),
        front=spoken_side(entry.question, entry, source),
        back=spoken_side(entry.answer, entry, source),
    )


def spoken_side(text: str, entry: Entry, source: SourceFile) -> Side:
    return Side(text, Speech(side_language(text, entry, source), (Say(text),)))


def side_language(text: str, entry: Entry, source: SourceFile) -> str:
    return entry.lang or detect_language(text, source.lang)


def cloze_cards(entry: ClozeEntry, source: SourceFile, config: Config) -> tuple[Card, ...]:
    parts = parse_cloze(entry.text)
    lang = side_language(full_sentence(parts), entry, source)
    return tuple(
        Card(
            key=f"{entry_key(entry)}-c{number}",
            deck=source.deck,
            origin=origin(entry, source),
            front=cloze_front(parts, number, lang, config),
            back=cloze_back(parts, number, lang, config),
        )
        for number in deletion_numbers(parts)
    )


def cloze_front(parts: tuple[Part, ...], number: int, lang: str, config: Config) -> Side:
    gapped = blank_segments if config.gap_style == "blank" else tone_segments
    segments = gapped(parts, number, gap_word(config, lang))
    return Side(gapped_text(parts, number), Speech(lang, segments))


def cloze_back(parts: tuple[Part, ...], number: int, lang: str, config: Config) -> Side:
    sentence = full_sentence(parts)
    answers = ", ".join(deletion.answer for deletion in hidden_deletions(parts, number))
    return Side(sentence, Speech(lang, (Say(answers), Pause(config.cloze_pause), Say(sentence))))


def gap_word(config: Config, lang: str) -> str:
    language = config.languages.get(lang)
    return language.gap_word if language else DEFAULT_GAP_WORD


def gapped_text(parts: tuple[Part, ...], number: int) -> str:
    return "".join(f"[{part.hint or '...'}]" if is_hidden(part, number) else revealed(part) for part in parts)


def blank_segments(parts: tuple[Part, ...], number: int, word: str) -> tuple[Segment, ...]:
    return (Say("".join(blank_or_text(part, number, word) for part in parts).strip()),)


def blank_or_text(part: Part, number: int, word: str) -> str:
    if not is_hidden(part, number):
        return revealed(part)
    return f"{word}, {part.hint}" if part.hint else word


def tone_segments(parts: tuple[Part, ...], number: int, word: str) -> tuple[Segment, ...]:
    segments: list[Segment] = []
    spoken = ""
    for part in parts:
        if is_hidden(part, number):
            segments += [Say(spoken), Beep(), Say(part.hint or "")]
            spoken = ""
        else:
            spoken += revealed(part)
    return speakable((*segments, Say(spoken)))


def speakable(segments: tuple[Segment, ...]) -> tuple[Segment, ...]:
    tidied = (tidy(segment) for segment in segments)
    return tuple(segment for segment in tidied if not is_silent(segment))


def tidy(segment: Segment) -> Segment:
    if not isinstance(segment, Say):
        return segment
    return Say(DANGLING_PUNCTUATION.sub("", segment.text).strip())


def is_silent(segment: Segment) -> bool:
    return isinstance(segment, Say) and not SPEAKABLE.search(segment.text)
