import os
import shutil
import sqlite3
import zipfile
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from deckaloud.cards import cards_from_source
from deckaloud.check import problems, reused_ids
from deckaloud.config import Config
from deckaloud.errors import DeckaloudError, ParseError, SourceError
from deckaloud.ledger import Entry, Ledger, digest
from deckaloud.package import write_package
from deckaloud.render import Studio
from deckaloud.source import SourceFile, parse_source, read_source_text
from deckaloud.stamp import stamp_file
from deckaloud.voiceover import VoiceOptions, voice_package
from deckaloud.voicing import voice_cards
from deckaloud.workspace import Workspace

STATES = ("built", "unchanged", "removed", "failed")
VOICING_ERRORS = (DeckaloudError, sqlite3.Error, zipfile.BadZipFile, OSError)


@dataclass(frozen=True)
class Outcome:
    name: str
    state: str
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    entry: Entry | None = None


def build_workspace(
    workspace: Workspace, studio: Studio, ledger: Ledger, fresh: bool = False
) -> tuple[Ledger, tuple[Outcome, ...]]:
    known = {} if fresh else ledger
    if fresh:
        shutil.rmtree(workspace.audio_cache, ignore_errors=True)
    voiced = dropped_results(workspace, studio)
    texts = text_results(workspace, studio, known, ledger)
    results = (*texts, *voiced, *kept_results(workspace, studio, known, voiced))
    built = {**ledger, **{result.outcome.name: result.entry for result in results if result.entry}}
    present = {result.outcome.name for result in results}
    gone = tuple(name for name, entry in built.items() if name not in present and not entry.removed)
    return without(built, gone), (*(result.outcome for result in results), *removals(workspace, gone))


def text_results(workspace: Workspace, studio: Studio, known: Ledger, ledger: Ledger) -> tuple[Result, ...]:
    names = [workspace.name(path) for path in workspace.sources()]
    readings = {name: read_source(workspace, name) for name in names}
    shared = reused_ids(tuple(reading for reading in readings.values() if isinstance(reading, SourceFile)))
    return tuple(
        text_result(name, readings[name], shared, workspace, studio, known.get(name), in_anki(ledger.get(name)))
        for name in names
    )


def in_anki(entry: Entry | None) -> tuple[str, ...]:
    return entry.anki_guids if entry else ()


def read_source(workspace: Workspace, name: str) -> SourceFile | str:
    path = workspace.root / name
    try:
        stamp_file(path)
        return parse_source(read_source_text(path), Path(name))
    except SourceError:
        return f"{name} is not UTF-8 text, so it cannot be read as a source file"
    except ParseError as error:
        return str(error)


def text_result(
    name: str,
    reading: SourceFile | str,
    shared: tuple[str, ...],
    workspace: Workspace,
    studio: Studio,
    known: Entry | None,
    anki_guids: tuple[str, ...],
) -> Result:
    current = digest(workspace.root / name)
    package = workspace.package_for(name)
    if is_current(known, current, package):
        return Result(Outcome(name, "unchanged"))
    found = (reading,) if isinstance(reading, str) else deck_problems(reading, shared, studio.config)
    if found:
        return failed(name, found)
    cards = cards_from_source(reading, studio.config)
    if not cards:
        return failed(name, (f"{name}: no cards found",))
    package.parent.mkdir(parents=True, exist_ok=True)
    write_package(voice_cards(cards, studio), studio.config, package)
    guids = tuple(card.guid for card in cards)
    return Result(Outcome(name, "built"), Entry(current, False, guids, deck=reading.deck, anki_guids=anki_guids))


def is_current(entry: Entry | None, current: str, package: Path) -> bool:
    return entry is not None and not entry.removed and entry.digest == current and package.exists()


def deck_problems(source: SourceFile, shared: tuple[str, ...], config: Config) -> tuple[str, ...]:
    elsewhere = (message for message in shared if message.startswith(f"{source.path}:"))
    return tuple(dict.fromkeys((*problems((source,), config), *elsewhere)))


def failed(name: str, messages: tuple[str, ...]) -> Result:
    return Result(Outcome(name, "failed", tuple(messages)))


def dropped_results(workspace: Workspace, studio: Studio) -> tuple[Result, ...]:
    return tuple(dropped_result(path, workspace, studio) for path in workspace.dropped())


def dropped_result(path: Path, workspace: Workspace, studio: Studio) -> Result:
    original = workspace.originals / path.name
    name = workspace.name(original)
    try:
        voice_into(path, workspace.package_for(name), studio)
    except VOICING_ERRORS as error:
        return failed(workspace.name(path), (str(error),))
    workspace.originals.mkdir(exist_ok=True)
    os.replace(path, original)
    return Result(Outcome(name, "built"), Entry(digest(original), False))


def kept_results(workspace: Workspace, studio: Studio, known: Ledger, voiced: tuple[Result, ...]) -> tuple[Result, ...]:
    done = {result.outcome.name for result in voiced}
    waiting = (path for path in workspace.kept() if workspace.name(path) not in done)
    return tuple(kept_result(path, workspace, studio, known) for path in waiting)


def kept_result(path: Path, workspace: Workspace, studio: Studio, known: Ledger) -> Result:
    name = workspace.name(path)
    current = digest(path)
    package = workspace.package_for(name)
    if is_current(known.get(name), current, package):
        return Result(Outcome(name, "unchanged"))
    try:
        voice_into(path, package, studio)
    except VOICING_ERRORS as error:
        return failed(name, (str(error),))
    return Result(Outcome(name, "built"), Entry(current, False))


def voice_into(source: Path, package: Path, studio: Studio) -> None:
    package.parent.mkdir(parents=True, exist_ok=True)
    voice_package(source, package, studio, VoiceOptions())


def is_third_party(name: str) -> bool:
    return name.endswith(".apkg")


def without(ledger: Ledger, gone: tuple[str, ...]) -> Ledger:
    kept = {name: entry for name, entry in ledger.items() if not (name in gone and is_third_party(name))}
    return {name: awaiting_removal(entry) if name in gone else entry for name, entry in kept.items()}


def awaiting_removal(entry: Entry) -> Entry:
    return replace(entry, removed=True, imported=False)


def removals(workspace: Workspace, gone: tuple[str, ...]) -> tuple[Outcome, ...]:
    for name in gone:
        workspace.package_for(name).unlink(missing_ok=True)
    return tuple(Outcome(name, "removed") for name in gone)


def summary(outcomes: tuple[Outcome, ...]) -> str:
    counts = Counter(outcome.state for outcome in outcomes)
    return ", ".join(f"{state} {counts[state]}" for state in STATES)


def outcome_lines(outcomes: tuple[Outcome, ...]) -> list[str]:
    changed = (outcome for outcome in outcomes if outcome.state != "unchanged")
    return [line for outcome in changed for line in (f"{outcome.name}: {outcome.state}", *indented(outcome.messages))]


def indented(messages: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"  {message}" for message in messages)
