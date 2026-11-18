from collections.abc import Iterator

from deckaloud.cards import Card, cards_from_source
from deckaloud.config import Config
from deckaloud.source import Entry, SourceFile
from deckaloud.speech import spoken_languages


def problems(sources: tuple[SourceFile, ...], config: Config) -> tuple[str, ...]:
    return (
        *missing_ids(sources),
        *reused_ids(sources),
        *unvoiced_languages(sources, config),
    )


def located_entries(sources: tuple[SourceFile, ...]) -> Iterator[tuple[str, Entry]]:
    return ((f"{source.path}:{entry.line}", entry) for source in sources for entry in source.entries)


def missing_ids(sources: tuple[SourceFile, ...]) -> tuple[str, ...]:
    return tuple(
        f"{place}: card has no id; run 'deckaloud stamp' or build with --stamp"
        for place, entry in located_entries(sources)
        if entry.id is None
    )


def reused_ids(sources: tuple[SourceFile, ...]) -> tuple[str, ...]:
    first_seen: dict[str, str] = {}
    stamped = ((place, entry.id) for place, entry in located_entries(sources) if entry.id)
    return tuple(
        f"{place}: id '{card_id}' is already used at {first_seen[card_id]}"
        for place, card_id in stamped
        if first_seen.setdefault(card_id, place) != place
    )


def unvoiced_languages(sources: tuple[SourceFile, ...], config: Config) -> tuple[str, ...]:
    cards = (card for source in sources for card in cards_from_source(source, config))
    return tuple(dict.fromkeys(message for card in cards for message in unvoiced(card, config)))


def unvoiced(card: Card, config: Config) -> Iterator[str]:
    langs = dict.fromkeys(lang for side in (card.front, card.back) for lang in spoken_languages(side.speech))
    return (
        f"{card.origin}: no voice configured for language '{lang}'"
        for lang in langs
        if lang not in config.languages
    )
