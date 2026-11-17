import re
from dataclasses import dataclass

DELETION = re.compile(r"\{\{c(\d+)::(.+?)(?:::(.+?))?\}\}")


@dataclass(frozen=True)
class Deletion:
    number: int
    answer: str
    hint: str | None


Part = str | Deletion


def parse_cloze(text: str) -> tuple[Part, ...]:
    pieces = DELETION.split(text)
    literals = pieces[0::4]
    deletions = [as_deletion(*pieces[index : index + 3]) for index in range(1, len(pieces), 4)]
    interleaved = [part for pair in zip(literals, [*deletions, ""]) for part in pair]
    return tuple(part for part in interleaved if part != "")


def as_deletion(number: str, answer: str, hint: str | None) -> Deletion:
    return Deletion(int(number), answer, hint)


def deletion_numbers(parts: tuple[Part, ...]) -> tuple[int, ...]:
    return tuple(sorted({part.number for part in parts if isinstance(part, Deletion)}))


def hidden_deletions(parts: tuple[Part, ...], number: int) -> tuple[Deletion, ...]:
    return tuple(part for part in parts if is_hidden(part, number))


def is_hidden(part: Part, number: int) -> bool:
    return isinstance(part, Deletion) and part.number == number


def revealed(part: Part) -> str:
    return part.answer if isinstance(part, Deletion) else part


def full_sentence(parts: tuple[Part, ...]) -> str:
    return "".join(revealed(part) for part in parts)
