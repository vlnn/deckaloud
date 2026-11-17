import json
from collections.abc import Iterable
from pathlib import Path

from deckaloud.voicing import VoicedCard


def read_manifest(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    return frozenset(json.loads(path.read_text(encoding="utf-8")))


def write_manifest(path: Path, guids: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(guids), indent=2), encoding="utf-8")


def removed_guids(previous: Iterable[str], current: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(previous) - set(current)))


def fallbacks(voiced: tuple[VoicedCard, ...]) -> tuple[str, ...]:
    return tuple(
        f"{item.card.origin} ({item.card.key}) {name}: {side.problem}"
        for item in voiced
        for name, side in (("front", item.front), ("back", item.back))
        if side.clip is None
    )


def format_report(voiced: tuple[VoicedCard, ...], output: Path, removed: tuple[str, ...]) -> str:
    unbaked = fallbacks(voiced)
    return "\n".join(
        [
            headline(len(voiced), output, len(unbaked)),
            *section("Runtime speech used for:", unbaked),
            *section("No longer in the sources; delete in Anki, found by:", [f"tag:{guid}" for guid in removed]),
        ]
    )


def headline(card_count: int, output: Path, unbaked_count: int) -> str:
    cards = f"{card_count} card{'' if card_count == 1 else 's'}"
    if not unbaked_count:
        return f"Built {cards} into {output}, all sides baked."
    return f"Built {cards} into {output}; {unbaked_count} of {2 * card_count} sides will be read by the phone's own voice."


def section(title: str, lines: Iterable[str]) -> list[str]:
    lines = list(lines)
    return ["", title, *(f"  {line}" for line in lines)] if lines else []
