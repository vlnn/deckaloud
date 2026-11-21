import shutil
from dataclasses import replace

import pytest
from conftest import copy_as_encoding
from fake_anki import FakeAnki

from deckaloud.building import build_workspace
from deckaloud.config import Config
from deckaloud.render import Studio
from deckaloud.syncing import sync_workspace
from deckaloud.workspace import Workspace

HEADER = "deck: Geo\n"


def card(number):
    return f"\nid: g{number}\nQ: Question {number}?\nA: Answer {number}.\n"


def deck(numbers, header=HEADER):
    return header + "".join(card(number) for number in numbers)


def guids(numbers):
    return {f"deckaloud-g{number}" for number in numbers}


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "decks"
    root.mkdir()
    return Workspace(root)


@pytest.fixture
def booth(workspace, engine):
    return Studio(engine, copy_as_encoding, Config(), workspace.audio_cache)


@pytest.fixture
def anki():
    return FakeAnki()


@pytest.fixture
def sync(workspace, booth, anki):
    def build_then_sync(ledger=None, target=anki, **options):
        built, outcomes = build_workspace(workspace, booth, ledger or {})
        failed = frozenset(outcome.name for outcome in outcomes if outcome.state == "failed")
        return sync_workspace(workspace, target, built, blocked=failed, **options)

    return build_then_sync


def write(workspace, name, text):
    path = workspace.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def states(synced):
    return {outcome.name: outcome.state for outcome in synced.outcomes}


def test_new_deck_is_imported_and_recorded(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1, 2]))

    synced = sync()

    assert anki.guids() == guids([1, 2]), "both cards should arrive in Anki"
    assert states(synced) == {"geo.txt": "imported"}, "the deck should be reported as imported"
    assert synced.ledger["geo.txt"].imported, "the deck should be recorded as imported"
    assert set(synced.ledger["geo.txt"].anki_guids) == guids([1, 2]), "the notes now in Anki should be recorded"
    assert anki.called("sync") == 1, "AnkiWeb should be synced after a change"


def test_deck_already_in_anki_is_left_alone(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1]))
    first = sync()

    second = sync(first.ledger)

    assert states(second) == {}, "nothing should be reported for an up to date deck"
    assert anki.called("importPackage") == 1, "the package should not be imported twice"
    assert anki.called("sync") == 1, "AnkiWeb should not be synced when nothing changed"


def test_text_that_the_import_did_not_update_is_corrected(workspace, booth, sync):
    stubborn = FakeAnki(updates_existing=False)
    write(workspace, "geo.txt", deck([1]))
    first = sync(target=stubborn)
    write(workspace, "geo.txt", deck([1]).replace("Answer 1.", "A better answer."))

    second = sync(first.ledger, target=stubborn)

    assert stubborn.note("deckaloud-g1")["fields"][1] == "A better answer.", "the reworded answer should reach Anki"
    assert stubborn.called("storeMediaFile") == 2, "the clips of the corrected note should be stored"
    assert second.ledger["geo.txt"].imported, "the corrected deck should count as imported"


def test_card_moved_to_another_source_changes_deck_and_keeps_its_note(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1, 2]))
    first = sync()
    write(workspace, "geo.txt", deck([1]))
    write(workspace, "net.txt", deck([2], header="deck: Net\n"))

    second = sync(first.ledger)

    assert anki.guids() == guids([1, 2]), "a moved card should not be deleted"
    assert anki.note("deckaloud-g2")["deck"] == "Net", "the moved card should be in its new deck"
    assert second.deleted == 0, "no deletion should be reported"
    assert set(second.ledger["geo.txt"].anki_guids) == guids([1]), "the old deck should no longer claim the moved card"


def test_card_removed_from_its_source_is_deleted_from_anki(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1, 2, 3]))
    first = sync()
    write(workspace, "geo.txt", deck([1, 2]))

    second = sync(first.ledger)

    assert anki.guids() == guids([1, 2]), "the removed card should be deleted from Anki"
    assert second.deleted == 1, "one deletion should be reported"
    assert set(second.ledger["geo.txt"].anki_guids) == guids([1, 2]), "the record of Anki's notes should shrink"


@pytest.mark.parametrize(
    "before, after, force, survivors, state",
    [
        (range(10), range(5), False, range(5), "imported"),
        (range(10), range(4), False, range(10), "failed"),
        (range(10), range(4), True, range(4), "imported"),
        (range(100), range(79), False, range(100), "failed"),
        (range(100), range(80), False, range(80), "imported"),
    ],
)
def test_large_deletions_need_force(workspace, anki, sync, before, after, force, survivors, state):
    write(workspace, "geo.txt", deck(before))
    first = sync()
    write(workspace, "geo.txt", deck(after))

    second = sync(first.ledger, force=force)

    assert anki.guids() == guids(survivors), f"{len(list(survivors))} cards should be left in Anki"
    assert states(second) == {"geo.txt": state}, f"the deck should be reported as {state}"


def test_guarded_deletion_is_offered_again_next_time(workspace, anki, sync):
    write(workspace, "geo.txt", deck(range(10)))
    first = sync()
    write(workspace, "geo.txt", deck(range(4)))
    guarded = sync(first.ledger)

    forced = sync(guarded.ledger, force=True)

    assert "--force" in " ".join(guarded.outcomes[0].messages), "the guard should say how to go ahead"
    assert anki.guids() == guids(range(4)), "a later forced sync should carry out the deletion"
    assert forced.deleted == 6, "the forced sync should report the deletions"


@pytest.mark.parametrize("name, survivors", [("geo.txt", [1, 2]), ("test.txt", [1])])
def test_uncommitted_ids_hold_back_deletion_except_in_the_test_deck(workspace, anki, sync, name, survivors):
    write(workspace, name, deck([1, 2]))
    first = sync()
    write(workspace, name, deck([1]))

    second = sync(first.ledger, uncommitted=frozenset({name}))
    third = sync(second.ledger)

    assert anki.guids() == guids([1]), "the deletion should happen once the ids are committed"
    assert second.deleted == 2 - len(survivors), f"{survivors} should have survived the first sync"
    assert third.deleted == len(survivors) - 1, "the held back deletion should be carried out later"


def test_deleted_source_takes_its_notes_and_empty_deck_with_it(workspace, anki, sync):
    source = write(workspace, "geo.txt", deck([1, 2]))
    first = sync()
    source.unlink()

    second = sync(first.ledger)

    assert anki.guids() == set(), "the deck's notes should be deleted"
    assert "Geo" not in anki.decks, "the emptied deck should be deleted"
    assert second.ledger == {}, "the deck should be forgotten"
    assert states(second) == {"geo.txt": "removed"}, "the removal should be reported"


def test_source_deleted_before_it_ever_reached_anki_is_forgotten(workspace, booth, anki):
    source = write(workspace, "geo.txt", deck([1]))
    built, _ = build_workspace(workspace, booth, {})
    source.unlink()
    removed, _ = build_workspace(workspace, booth, built)

    synced = sync_workspace(workspace, anki, removed)

    assert synced.ledger == {}, "a deck that never reached Anki should simply be forgotten"
    assert anki.called("deleteNotes") == 0, "there should be nothing to delete"


def test_deck_shared_with_another_source_survives(workspace, anki, sync):
    source = write(workspace, "geo.txt", deck([1]))
    write(workspace, "more.txt", deck([2]))
    first = sync()
    source.unlink()

    sync(first.ledger)

    assert anki.guids() == guids([2]), "only the deleted source's note should go"
    assert "Geo" in anki.decks, "a deck that still has cards should stay"


def test_renamed_source_keeps_its_notes(workspace, anki, sync):
    source = write(workspace, "geo.txt", deck([1, 2]))
    first = sync()
    shutil.move(source, workspace.root / "geography.txt")

    second = sync(first.ledger)

    assert anki.guids() == guids([1, 2]), "renaming a source should delete nothing"
    assert set(second.ledger) == {"geography.txt"}, "only the new name should be recorded"


def test_deck_that_failed_to_build_is_neither_imported_nor_cleaned(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1, 2]))
    first = sync()
    write(workspace, "geo.txt", "deck: Geo\n\nQ: lonely question\n")

    second = sync(first.ledger)

    assert anki.guids() == guids([1, 2]), "a broken deck should lose nothing in Anki"
    assert anki.called("importPackage") == 1, "a broken deck should not be imported"
    assert states(second) == {}, "sync should have nothing to add to the build's failure report"


def test_note_missing_after_import_fails_the_deck(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1, 2]))
    anki.importPackage = lambda path: True

    synced = sync()

    assert states(synced) == {"geo.txt": "failed"}, "a deck whose cards did not arrive should fail"
    assert not synced.ledger["geo.txt"].imported, "it should be tried again next time"


def test_changed_note_type_fails_the_deck(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1]))
    first = sync()
    anki.note("deckaloud-g1")["fields"].append("extra field")
    anki.updates_existing = False
    write(workspace, "geo.txt", deck([1]).replace("Answer 1.", "Another."))

    second = sync(first.ledger)

    assert states(second) == {"geo.txt": "failed"}, "a note type with other fields should fail the deck"
    assert "note type" in " ".join(second.outcomes[0].messages), "the failure should name the cause"


def test_package_anki_cannot_import_fails_only_its_deck(workspace, anki, sync):
    write(workspace, "geo.txt", deck([1]))
    write(workspace, "net.txt", deck([2], header="deck: Net\n"))
    anki.broken_packages.add("geo.apkg")

    synced = sync()

    assert states(synced) == {"geo.txt": "failed", "net.txt": "imported"}, "the other deck should still be imported"
    assert anki.guids() == guids([2]), "only the readable package should arrive"


def test_third_party_package_is_imported_and_never_cleaned(workspace, booth, anki, mocker):
    write(workspace, "geo.txt", deck([1]))
    built, _ = build_workspace(workspace, booth, {})
    shared = workspace.package_for("originals/shared.apkg")
    shared.parent.mkdir(parents=True)
    shutil.copyfile(workspace.package_for("geo.txt"), shared)
    ledger = {"originals/shared.apkg": replace(built["geo.txt"], guids=(), deck="")}

    synced = sync_workspace(workspace, anki, ledger)

    assert states(synced) == {"originals/shared.apkg": "imported"}, "the voiced package should be imported"
    assert anki.guids() == guids([1]), "its notes should arrive"
    assert anki.called("deleteNotes") == 0, "nothing should be deleted for a third-party deck"
