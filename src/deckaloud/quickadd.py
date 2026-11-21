import re
from pathlib import Path

from deckaloud.check import unvoiced_languages
from deckaloud.config import Config
from deckaloud.errors import DeckaloudError
from deckaloud.source import Block, block_keys, parse_source, split_blocks
from deckaloud.stamp import stamp_text

HEADER = "deck: Test\n"
CLOZE_DELETION = re.compile(r"\{\{c\d+::")


def add_cards(deck: Path, typed: str, config: Config) -> int:
    cards = as_cards(typed)
    if not cards:
        raise DeckaloudError("nothing to add")
    source = parse_source(f"{HEADER}\n{cards}\n", Path(deck.name))
    unvoiced = unvoiced_languages((source,), config)
    if unvoiced:
        raise DeckaloudError("\n".join(unvoiced))
    deck.write_text(f"{existing_text(deck).rstrip()}\n\n{cards}\n", encoding="utf-8")
    return len(source.entries)


def existing_text(deck: Path) -> str:
    return deck.read_text(encoding="utf-8-sig") if deck.exists() else HEADER


def as_cards(typed: str) -> str:
    return "\n\n".join(card_block(block) for block in split_blocks(typed))


def card_block(block: Block) -> str:
    tidy = Block(block.line, tuple(line.strip() for line in block.lines))
    text = "\n".join(tidy.lines)
    return f"C: {text}" if is_bare_cloze(tidy, text) else text


def is_bare_cloze(block: Block, text: str) -> bool:
    return not block_keys(block) and bool(CLOZE_DELETION.search(text))


def new_card_count(deck: Path) -> int:
    return stamp_text(existing_text(deck))[1]
