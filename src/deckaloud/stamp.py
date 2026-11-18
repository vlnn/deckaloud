import os
import secrets
import shutil
from collections.abc import Callable
from pathlib import Path

from deckaloud.source import CARD_KEYS, Block, block_keys, read_source_text, split_blocks


def random_id() -> str:
    return secrets.token_hex(4)


def stamp_text(text: str, new_id: Callable[[], str] = random_id) -> tuple[str, int]:
    lines = text.splitlines()
    targets = [block.line for block in split_blocks(text) if needs_id(block)]
    ids = [new_id() for _ in targets]
    for line, card_id in reversed(list(zip(targets, ids))):
        lines.insert(line - 1, f"id: {card_id}")
    return "\n".join(lines) + trailing_newline(text), len(targets)


def needs_id(block: Block) -> bool:
    keys = block_keys(block)
    return bool(keys & CARD_KEYS) and "id" not in keys


def trailing_newline(text: str) -> str:
    return "\n" if text.endswith("\n") else ""


def stamp_file(path: Path, new_id: Callable[[], str] = random_id) -> int:
    stamped, added = stamp_text(read_source_text(path), new_id)
    if added:
        write_atomically(path, stamped)
    return added


def write_atomically(path: Path, text: str) -> None:
    draft = path.with_name(f".{path.name}.stamping")
    try:
        draft.write_text(text, encoding="utf-8")
        shutil.copymode(path, draft)
        os.replace(draft, path)
    finally:
        draft.unlink(missing_ok=True)
