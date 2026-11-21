import shutil
from dataclasses import replace

import pytest
from conftest import copy_as_encoding

from deckaloud.building import Outcome, build_workspace, summary
from deckaloud.config import Config
from deckaloud.errors import PackageError
from deckaloud.ledger import digest
from deckaloud.render import Studio
from deckaloud.workspace import Workspace

GEO = "deck: Geo\n\nid: a1\nQ: Capital of Ukraine?\nA: Kyiv.\n"
NET = "deck: Net\n\nid: b1\nQ: Which protocol resolves names?\nA: DNS.\n"
UNSTAMPED = "deck: Geo\n\nQ: Capital of Ukraine?\nA: Kyiv.\n"
BROKEN = "deck: Geo\n\nQ: lonely question\n"


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "decks"
    root.mkdir()
    return Workspace(root)


@pytest.fixture
def booth(workspace, engine):
    return Studio(engine, copy_as_encoding, Config(), workspace.audio_cache)


@pytest.fixture
def voicing(mocker):
    def copy_package(source, output, studio, options):
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)

    return mocker.patch("deckaloud.building.voice_package", side_effect=copy_package)


def write(workspace, name, text):
    path = workspace.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def states(outcomes):
    return {outcome.name: outcome.state for outcome in outcomes}


@pytest.mark.parametrize("name", ["geo.txt", "notes/geo.txt"])
def test_new_source_is_built_and_recorded_as_waiting_for_import(workspace, booth, name):
    source = write(workspace, name, GEO)

    ledger, outcomes = build_workspace(workspace, booth, {})

    assert states(outcomes) == {name: "built"}, "a new source should be built"
    assert workspace.package_for(name).exists(), "its package should be written under toanki"
    assert ledger[name].digest == digest(source), "the source's content hash should be recorded"
    assert ledger[name].imported is False, "a fresh package should be waiting for import"
    assert ledger[name].guids == ("deckaloud-a1",), "the deck's note ids should be recorded"


def test_unchanged_source_is_left_alone(workspace, booth, engine):
    write(workspace, "geo.txt", GEO)
    ledger, _ = build_workspace(workspace, booth, {})
    spoken = len(engine.spoken)
    built_at = workspace.package_for("geo.txt").stat().st_mtime_ns

    again, outcomes = build_workspace(workspace, booth, ledger)

    assert states(outcomes) == {"geo.txt": "unchanged"}, "an unchanged source should not be rebuilt"
    assert workspace.package_for("geo.txt").stat().st_mtime_ns == built_at, "its package should not be rewritten"
    assert len(engine.spoken) == spoken, "no speech should be synthesized"
    assert again == ledger, "the ledger should stay as it was"


def test_edited_source_is_rebuilt_and_waits_for_import_again(workspace, booth):
    write(workspace, "geo.txt", GEO)
    ledger, _ = build_workspace(workspace, booth, {})
    imported = {"geo.txt": replace(ledger["geo.txt"], imported=True)}
    write(workspace, "geo.txt", GEO + "\nid: a2\nQ: Capital of Poland?\nA: Warsaw.\n")

    ledger, outcomes = build_workspace(workspace, booth, imported)

    assert states(outcomes) == {"geo.txt": "built"}, "an edited source should be rebuilt"
    assert ledger["geo.txt"].imported is False, "the rebuilt package should wait for import"
    assert ledger["geo.txt"].guids == ("deckaloud-a1", "deckaloud-a2"), "the new card should be recorded"


def test_missing_package_is_built_again(workspace, booth):
    write(workspace, "geo.txt", GEO)
    ledger, _ = build_workspace(workspace, booth, {})
    workspace.package_for("geo.txt").unlink()

    _, outcomes = build_workspace(workspace, booth, ledger)

    assert states(outcomes) == {"geo.txt": "built"}, "a deck whose package is gone should be built again"


def test_unstamped_cards_get_ids_before_the_hash_is_taken(workspace, booth):
    source = write(workspace, "geo.txt", UNSTAMPED)

    ledger, _ = build_workspace(workspace, booth, {})
    _, outcomes = build_workspace(workspace, booth, ledger)

    assert "\nid: " in source.read_text(encoding="utf-8"), "missing ids should be written into the source"
    assert states(outcomes) == {"geo.txt": "unchanged"}, "stamping should not make the deck look changed next time"


def test_broken_deck_is_skipped_and_the_rest_are_built(workspace, booth):
    write(workspace, "geo.txt", BROKEN)
    write(workspace, "net.txt", NET)

    ledger, outcomes = build_workspace(workspace, booth, {})

    assert states(outcomes) == {"geo.txt": "failed", "net.txt": "built"}, "one bad deck should not stop the others"
    assert "geo.txt" not in ledger, "a deck that never built should not be recorded"
    assert any("geo.txt:3" in message for message in outcomes[0].messages), "the failure should say where it is"


def test_deck_that_breaks_keeps_its_last_good_package(workspace, booth):
    write(workspace, "geo.txt", GEO)
    ledger, _ = build_workspace(workspace, booth, {})
    write(workspace, "geo.txt", BROKEN)

    after, outcomes = build_workspace(workspace, booth, ledger)

    assert states(outcomes) == {"geo.txt": "failed"}, "the broken edit should be reported"
    assert after == ledger, "the last good build should stay recorded"
    assert workspace.package_for("geo.txt").exists(), "the last good package should stay in place"


def test_id_used_in_two_decks_fails_the_later_one(workspace, booth):
    write(workspace, "geo.txt", GEO)
    write(workspace, "zoo.txt", GEO.replace("Geo", "Zoo"))

    _, outcomes = build_workspace(workspace, booth, {})

    assert states(outcomes) == {"geo.txt": "built", "zoo.txt": "failed"}, "a reused id should fail the later deck"


def test_deleted_source_loses_its_package_and_waits_for_removal(workspace, booth):
    source = write(workspace, "geo.txt", GEO)
    ledger, _ = build_workspace(workspace, booth, {})
    source.unlink()

    ledger, outcomes = build_workspace(workspace, booth, ledger)
    _, later = build_workspace(workspace, booth, ledger)

    assert states(outcomes) == {"geo.txt": "removed"}, "a deleted source should be reported as removed"
    assert not workspace.package_for("geo.txt").exists(), "its package should be deleted"
    assert ledger["geo.txt"].removed, "the deck should be marked for removal from Anki"
    assert ledger["geo.txt"].guids == ("deckaloud-a1",), "its note ids should be kept for that removal"
    assert states(later) == {}, "a removal should be reported once"


def test_fresh_build_redoes_every_deck_and_all_audio(workspace, booth, engine):
    write(workspace, "geo.txt", GEO)
    ledger, _ = build_workspace(workspace, booth, {})
    stale = workspace.audio_cache / "stale.m4a"
    stale.write_bytes(b"old")
    spoken = len(engine.spoken)

    _, outcomes = build_workspace(workspace, booth, ledger, fresh=True)

    assert states(outcomes) == {"geo.txt": "built"}, "a fresh build should rebuild unchanged decks"
    assert len(engine.spoken) == 2 * spoken, "every clip should be synthesized again"
    assert not stale.exists(), "old clips should be discarded"


def test_dropped_package_is_voiced_and_its_original_kept(workspace, booth, voicing):
    dropped = write(workspace, "inbox/shared.apkg", "original")

    ledger, outcomes = build_workspace(workspace, booth, {})

    assert states(outcomes) == {"originals/shared.apkg": "built"}, "a dropped package should be voiced"
    assert workspace.package_for("originals/shared.apkg").exists(), "the voiced copy should be under toanki"
    assert not dropped.exists(), "the package should leave the inbox"
    assert (workspace.originals / "shared.apkg").read_text() == "original", "the original should be kept unvoiced"
    assert ledger["originals/shared.apkg"].imported is False, "the voiced copy should wait for import"


def test_package_that_cannot_be_voiced_stays_in_the_inbox(workspace, booth, mocker):
    mocker.patch("deckaloud.building.voice_package", side_effect=PackageError("not an Anki package"))
    dropped = write(workspace, "inbox/shared.apkg", "junk")

    ledger, outcomes = build_workspace(workspace, booth, {})

    assert states(outcomes) == {"inbox/shared.apkg": "failed"}, "the failure should be reported against the inbox"
    assert outcomes[0].messages == ("not an Anki package",), "the reason should be reported"
    assert dropped.exists(), "the package should stay in the inbox"
    assert ledger == {}, "nothing should be recorded"


@pytest.mark.parametrize(
    "change, fresh, expected, last_read",
    [
        (None, False, "unchanged", "inbox/shared.apkg"),
        (None, True, "built", "originals/shared.apkg"),
        ("newer", False, "built", "originals/shared.apkg"),
    ],
)
def test_kept_original_is_voiced_again_only_when_needed(workspace, booth, voicing, change, fresh, expected, last_read):
    write(workspace, "inbox/shared.apkg", "original")
    ledger, _ = build_workspace(workspace, booth, {})
    if change:
        write(workspace, "originals/shared.apkg", change)

    _, outcomes = build_workspace(workspace, booth, ledger, fresh=fresh)

    assert states(outcomes) == {"originals/shared.apkg": expected}, f"the original should be {expected}"
    assert voicing.call_args.args[0] == workspace.root / last_read, f"the last voicing should have read {last_read}"


def test_deleted_original_loses_its_voiced_copy_and_is_forgotten(workspace, booth, voicing):
    write(workspace, "inbox/shared.apkg", "original")
    ledger, _ = build_workspace(workspace, booth, {})
    (workspace.originals / "shared.apkg").unlink()

    ledger, outcomes = build_workspace(workspace, booth, ledger)

    assert states(outcomes) == {"originals/shared.apkg": "removed"}, "the removal should be reported"
    assert not workspace.package_for("originals/shared.apkg").exists(), "the voiced copy should be deleted"
    assert ledger == {}, "a third-party deck should leave nothing to remove from Anki"


@pytest.mark.parametrize(
    "found, expected",
    [
        ([], "built 0, unchanged 0, removed 0, failed 0"),
        (["built", "built", "unchanged", "failed"], "built 2, unchanged 1, removed 0, failed 1"),
        (["removed"], "built 0, unchanged 0, removed 1, failed 0"),
    ],
)
def test_summary_counts_each_state(found, expected):
    outcomes = tuple(Outcome(f"deck{number}.txt", state) for number, state in enumerate(found))

    assert summary(outcomes) == expected, f"the summary should read '{expected}'"
