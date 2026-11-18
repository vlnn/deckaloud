from dataclasses import dataclass


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class SayIn:
    text: str
    lang: str


@dataclass(frozen=True)
class Beep:
    pass


@dataclass(frozen=True)
class Pause:
    seconds: float


Segment = Say | SayIn | Beep | Pause


@dataclass(frozen=True)
class Speech:
    lang: str
    segments: tuple[Segment, ...]


def spoken_languages(speech: Speech) -> tuple[str, ...]:
    guests = (segment.lang for segment in speech.segments if isinstance(segment, SayIn))
    return tuple(dict.fromkeys((speech.lang, *guests)))


def plain_text(speech: Speech, gap_word: str) -> str:
    pieces = (spoken_piece(segment, gap_word) for segment in speech.segments)
    return " ".join(pieces).replace(" .", ".")


def spoken_piece(segment: Segment, gap_word: str) -> str:
    match segment:
        case Say(text) | SayIn(text):
            return text
        case Beep():
            return gap_word
        case Pause():
            return "."
