from collections import Counter
from pathlib import Path

from deckaloud.building import is_current, is_third_party
from deckaloud.errors import SourceError
from deckaloud.ledger import Ledger, digest
from deckaloud.source import read_source_text
from deckaloud.stamp import stamp_text
from deckaloud.workspace import Workspace

NEW = "new"
CHANGED = "changed"
UNVOICED = "waiting to be voiced"
WAITING = "built, waiting for import"
CURRENT = "up to date"
DELETED = "deleted"
TO_REMOVE = "deleted, to be removed from Anki"
TO_BUILD = frozenset({NEW, CHANGED, UNVOICED})
NOTHING = "nothing to do"


def overview_lines(workspace: Workspace, ledger: Ledger) -> list[str]:
    states = deck_states(workspace, ledger)
    listed = [f"{name}: {state}" for name, state in states if state != CURRENT]
    return [*listed, totals(state for _, state in states)] if listed else [NOTHING]


def deck_states(workspace: Workspace, ledger: Ledger) -> tuple[tuple[str, str], ...]:
    present = (*workspace.sources(), *workspace.kept())
    names = {workspace.name(path) for path in present}
    return (
        *((workspace.name(path), UNVOICED) for path in workspace.dropped()),
        *((workspace.name(path), deck_state(path, workspace, ledger)) for path in present),
        *((name, deleted_state(name)) for name in sorted(ledger) if name not in names),
    )


def deck_state(path: Path, workspace: Workspace, ledger: Ledger) -> str:
    name = workspace.name(path)
    entry = ledger.get(name)
    if entry is None or entry.removed:
        return NEW
    if has_unstamped_cards(path) or not is_current(entry, digest(path), workspace.package_for(name)):
        return CHANGED
    return CURRENT if entry.imported else WAITING


def has_unstamped_cards(path: Path) -> bool:
    return path.suffix == ".txt" and unstamped_count(path) > 0


def unstamped_count(path: Path) -> int:
    try:
        return stamp_text(read_source_text(path))[1]
    except SourceError:
        return 1


def deleted_state(name: str) -> str:
    return DELETED if is_third_party(name) else TO_REMOVE


def totals(states) -> str:
    counts = Counter(states)
    to_build = sum(counts[state] for state in TO_BUILD)
    return f"{to_build} to build, {counts[WAITING]} to import, {counts[TO_REMOVE]} to remove"
