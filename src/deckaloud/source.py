import re
import zipfile
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from deckaloud.cloze import deletion_numbers, parse_cloze
from deckaloud.errors import ParseError, SourceError

FIELD = re.compile(r"^(deck|lang|id|Q|A|C):\s*(.*)$")
CARD_KEYS = frozenset({"Q", "A", "C"})
CARD_ID = re.compile(r"^[A-Za-z0-9_]+$")
DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class Block:
    line: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class QaEntry:
    id: str | None
    lang: str | None
    line: int
    question: str
    answer: str


@dataclass(frozen=True)
class ClozeEntry:
    id: str | None
    lang: str | None
    line: int
    text: str


Entry = QaEntry | ClozeEntry


@dataclass(frozen=True)
class SourceFile:
    path: Path
    deck: str
    lang: str
    entries: tuple[Entry, ...]


def read_source_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise SourceError(unreadable(path)) from None


def unreadable(path: Path) -> str:
    if zipfile.is_zipfile(path):
        return f"{path} is an Anki package, not a source file; add sound to it with 'deckaloud voice {path}'"
    return f"{path} is not UTF-8 text, so it cannot be read as a source file"


def parse_source(text: str, path: Path) -> SourceFile:
    parsed = [(block, block_fields(block, path)) for block in split_blocks(text)]
    header, cards = split_header(parsed)
    return SourceFile(
        path=path,
        deck=header.get("deck", path.stem),
        lang=header.get("lang", DEFAULT_LANGUAGE),
        entries=tuple(entry(block, fields, path) for block, fields in cards),
    )


def split_blocks(text: str) -> tuple[Block, ...]:
    numbered = enumerate(text.splitlines(), start=1)
    groups = groupby(numbered, key=lambda pair: bool(pair[1].strip()))
    return tuple(as_block(tuple(lines)) for has_text, lines in groups if has_text)


def as_block(numbered_lines: tuple[tuple[int, str], ...]) -> Block:
    return Block(numbered_lines[0][0], tuple(line for _, line in numbered_lines))


def block_keys(block: Block) -> frozenset[str]:
    return frozenset(match.group(1) for line in block.lines if (match := FIELD.match(line)))


def block_fields(block: Block, path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    key = None
    for line_number, line in enumerate(block.lines, start=block.line):
        match = FIELD.match(line)
        if match and match.group(1) in fields:
            raise ParseError(path, line_number, f"'{match.group(1)}:' appears twice in one block")
        if not match and key is None:
            raise ParseError(path, line_number, "expected a line starting with Q:, A:, C:, id:, lang: or deck:")
        key = match.group(1) if match else key
        fields[key] = continued(fields.get(key), match.group(2) if match else line)
    return fields


def continued(so_far: str | None, more: str) -> str:
    return f"{so_far or ''} {more.strip()}".strip()


def split_header(parsed: list[tuple[Block, dict[str, str]]]) -> tuple[dict[str, str], list]:
    if parsed and not CARD_KEYS & parsed[0][1].keys():
        return parsed[0][1], parsed[1:]
    return {}, parsed


def entry(block: Block, fields: dict[str, str], path: Path) -> Entry:
    reject_misplaced_deck(block, fields, path)
    reject_empty_fields(block, fields, path)
    reject_unsafe_id(block, fields, path)
    kind = fields.keys() & CARD_KEYS
    if kind == {"Q", "A"}:
        return QaEntry(fields.get("id"), fields.get("lang"), block.line, fields["Q"], fields["A"])
    if kind == {"C"}:
        return cloze_entry(block, fields, path)
    raise ParseError(path, block.line, "a card needs 'Q:' with 'A:', or a single 'C:'")


def reject_misplaced_deck(block: Block, fields: dict[str, str], path: Path) -> None:
    if "deck" in fields:
        raise ParseError(path, block.line, "'deck:' belongs in the header block at the top of the file")


def reject_empty_fields(block: Block, fields: dict[str, str], path: Path) -> None:
    empty = sorted(key for key, value in fields.items() if not value)
    if empty:
        raise ParseError(path, block.line, f"'{empty[0]}:' is empty")


def reject_unsafe_id(block: Block, fields: dict[str, str], path: Path) -> None:
    card_id = fields.get("id")
    if card_id is not None and not CARD_ID.match(card_id):
        raise ParseError(path, block.line, f"id '{card_id}' may only contain letters, digits and underscores")


def cloze_entry(block: Block, fields: dict[str, str], path: Path) -> ClozeEntry:
    if not deletion_numbers(parse_cloze(fields["C"])):
        raise ParseError(path, block.line, "'C:' has no {{c1::...}} deletion")
    return ClozeEntry(fields.get("id"), fields.get("lang"), block.line, fields["C"])
