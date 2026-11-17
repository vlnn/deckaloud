from dataclasses import dataclass


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Beep:
    pass


@dataclass(frozen=True)
class Pause:
    seconds: float


Segment = Say | Beep | Pause


@dataclass(frozen=True)
class Speech:
    lang: str
    segments: tuple[Segment, ...]


def plain_text(speech: Speech, gap_word: str) -> str:
    pieces = (spoken_piece(segment, gap_word) for segment in speech.segments)
    return " ".join(pieces).replace(" .", ".")


def spoken_piece(segment: Segment, gap_word: str) -> str:
    match segment:
        case Say(text):
            return text
        case Beep():
            return gap_word
        case Pause():
            return "."
