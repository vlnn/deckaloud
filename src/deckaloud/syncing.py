import re
import sqlite3
import zipfile
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from deckaloud.ankiconnect import Anki, AnkiError, AnkiUnreachable
from deckaloud.building import Outcome, is_third_party
from deckaloud.cards import GUID_PREFIX
from deckaloud.ledger import Entry, Ledger
from deckaloud.workspace import Workspace

NOTE_SEARCH = f"tag:{GUID_PREFIX}*"
COLLECTION = "collection.anki2"
FIELD_SEPARATOR = "\x1f"
SOUND = re.compile(r"\[sound:([^\]]+)\]")
GUARD_SHARE = 0.2
GUARD_FLOOR = 5
OTHER_NOTE_TYPE = "the note type in Anki has different fields; rename or delete it in Anki, then sync again"

Notes = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class Synced:
    ledger: Ledger
    outcomes: tuple[Outcome, ...]
    deleted: int


def sync_workspace(
    workspace: Workspace,
    anki: Anki,
    ledger: Ledger,
    blocked: frozenset[str] = frozenset(),
    uncommitted: frozenset[str] = frozenset(),
    force: bool = False,
) -> Synced:
    held = (uncommitted - {workspace.name(workspace.quick_deck)}) | blocked
    waiting = tuple(name for name, entry in ledger.items() if awaits_import(entry) and name not in blocked)
    if not waiting and not any(needs_cleanup(name, entry, ledger) for name, entry in ledger.items() if name not in held):
        return Synced(ledger, (), 0)
    refused = import_failures(workspace, anki, waiting)
    notes = anki_notes(anki)
    arrived = {name: arrival(name, ledger[name], workspace, anki, notes, refused.get(name)) for name in waiting}
    after = {**ledger, **{name: entry for name, (entry, _) in arrived.items()}}
    cleaned = {
        name: cleanup(entry, leftovers(name, entry, after), anki, notes, force)
        for name, entry in after.items()
        if name not in held and is_settled(entry) and needs_cleanup(name, entry, after)
    }
    anki.invoke("sync")
    return Synced(
        ledger=settled_ledger(after, cleaned),
        outcomes=merged_outcomes({name: outcome for name, (_, outcome) in arrived.items()}, cleaned),
        deleted=sum(result.deleted for result in cleaned.values()),
    )


def awaits_import(entry: Entry) -> bool:
    return not entry.imported and not entry.removed


def is_settled(entry: Entry) -> bool:
    return entry.removed or entry.imported


def needs_cleanup(name: str, entry: Entry, ledger: Ledger) -> bool:
    return entry.removed or bool(leftovers(name, entry, ledger))


def import_failures(workspace: Workspace, anki: Anki, names: tuple[str, ...]) -> dict[str, str]:
    failures = {}
    for name in names:
        try:
            anki.invoke("importPackage", path=str(workspace.package_for(name).resolve()))
        except AnkiUnreachable:
            raise
        except AnkiError as error:
            failures[name] = str(error)
    return failures


def anki_notes(anki: Anki) -> Notes:
    found = anki.invoke("notesInfo", notes=anki.invoke("findNotes", query=NOTE_SEARCH))
    return {tag: note for note in found if note for tag in note["tags"] if tag.startswith(GUID_PREFIX)}


def arrival(
    name: str, entry: Entry, workspace: Workspace, anki: Anki, notes: Notes, refusal: str | None
) -> tuple[Entry, Outcome]:
    if is_third_party(name) and not refusal:
        return replace(entry, imported=True), Outcome(name, "imported")
    try:
        problems = (refusal,) if refusal else settle_notes(name, entry, workspace, anki, notes)
    except AnkiUnreachable:
        raise
    except AnkiError as error:
        problems = (str(error),)
    if problems:
        return entry, Outcome(name, "failed", problems)
    in_anki = tuple(sorted({*entry.anki_guids, *entry.guids}))
    return replace(entry, imported=True, anki_guids=in_anki), Outcome(name, "imported")


def settle_notes(name: str, entry: Entry, workspace: Workspace, anki: Anki, notes: Notes) -> tuple[str, ...]:
    expected = package_notes(workspace.package_for(name))
    missing = [guid for guid in expected if guid not in notes]
    if missing:
        return (f"{len(missing)} of {len(expected)} cards did not arrive in Anki",)
    if any(len(fields) != len(notes[guid]["fields"]) for guid, fields in expected.items()):
        return (OTHER_NOTE_TYPE,)
    for guid, fields in expected.items():
        correct_note(notes[guid], fields, workspace, anki)
    anki.invoke("changeDeck", cards=[card for guid in expected for card in notes[guid]["cards"]], deck=entry.deck)
    return ()


def package_notes(package: Path) -> dict[str, tuple[str, ...]]:
    with zipfile.ZipFile(package) as archive, closing(sqlite3.connect(":memory:")) as database:
        database.deserialize(archive.read(COLLECTION))
        rows = database.execute("select guid, flds from notes").fetchall()
    return {guid: tuple(fields.split(FIELD_SEPARATOR)) for guid, fields in rows}


def correct_note(note: dict[str, Any], fields: tuple[str, ...], workspace: Workspace, anki: Anki) -> None:
    names = sorted(note["fields"], key=lambda name: note["fields"][name]["order"])
    if tuple(note["fields"][name]["value"] for name in names) == fields:
        return
    for clip in SOUND.findall(" ".join(fields)):
        store_clip(workspace.audio_cache / clip, anki)
    anki.invoke("updateNoteFields", note={"id": note["noteId"], "fields": dict(zip(names, fields))})


def store_clip(clip: Path, anki: Anki) -> None:
    if clip.exists():
        anki.invoke("storeMediaFile", filename=clip.name, path=str(clip.resolve()))


def leftovers(name: str, entry: Entry, ledger: Ledger) -> tuple[str, ...]:
    if is_third_party(name):
        return ()
    current = {guid for other in ledger.values() if not other.removed for guid in other.guids}
    return tuple(sorted(set(entry.anki_guids) - current))


@dataclass(frozen=True)
class Cleanup:
    entry: Entry | None
    outcome: Outcome | None
    deleted: int = 0


def cleanup(entry: Entry, orphans: tuple[str, ...], anki: Anki, notes: Notes, force: bool) -> Cleanup:
    if is_guarded(len(orphans), len(entry.anki_guids)) and not force:
        return Cleanup(entry, Outcome("", "failed", (guard_message(len(orphans), len(entry.anki_guids)),)))
    found = [notes[guid]["noteId"] for guid in orphans if guid in notes]
    if found:
        anki.invoke("deleteNotes", notes=found)
    deleted = (f"deleted {counted(len(found))} from Anki",) if found else ()
    if not entry.removed:
        return Cleanup(replace(entry, anki_guids=entry.guids), Outcome("", "cleaned", deleted), len(found))
    delete_deck_if_empty(entry.deck, anki)
    return Cleanup(None, Outcome("", "removed", deleted), len(found))


def counted(cards: int) -> str:
    return f"{cards} card{'' if cards == 1 else 's'}"


def is_guarded(leaving: int, present: int) -> bool:
    return leaving > max(GUARD_FLOOR, GUARD_SHARE * present)


def guard_message(leaving: int, present: int) -> str:
    return f"would delete {leaving} of {present} cards from Anki; run 'decks sync --force' to allow it"


def delete_deck_if_empty(deck: str, anki: Anki) -> None:
    if deck and not anki.invoke("findCards", query=f'"deck:{deck}"'):
        anki.invoke("deleteDecks", decks=[deck], cardsToo=True)


def settled_ledger(ledger: Ledger, cleaned: dict[str, Cleanup]) -> Ledger:
    kept = {name: entry for name, entry in ledger.items() if name not in cleaned}
    settled = {**kept, **{name: result.entry for name, result in cleaned.items() if result.entry}}
    return {name: without_moved_notes(name, entry, settled) for name, entry in settled.items()}


def without_moved_notes(name: str, entry: Entry, ledger: Ledger) -> Entry:
    if entry.removed or not entry.imported or is_third_party(name):
        return entry
    still_here = {*entry.guids, *leftovers(name, entry, ledger)}
    return replace(entry, anki_guids=tuple(guid for guid in entry.anki_guids if guid in still_here))


def merged_outcomes(arrived: dict[str, Outcome], cleaned: dict[str, Cleanup]) -> tuple[Outcome, ...]:
    names = sorted({*arrived, *cleaned})
    return tuple(merged(name, arrived.get(name), cleaned[name].outcome if name in cleaned else None) for name in names)


def merged(name: str, arrived: Outcome | None, cleaned: Outcome | None) -> Outcome:
    if cleaned is None:
        return arrived
    if arrived is None or cleaned.state == "failed" or arrived.state == "failed":
        worst = arrived if arrived and arrived.state == "failed" else cleaned
        return Outcome(name, worst.state, worst.messages)
    return Outcome(name, arrived.state, cleaned.messages)
