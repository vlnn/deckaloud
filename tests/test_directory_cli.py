import fcntl

import pytest
from conftest import copy_as_encoding
from fake_anki import FakeAnki

from deckaloud.ankiconnect import AnkiUnreachable
from deckaloud.cli import main
from deckaloud.ledger import read_ledger
from deckaloud.workspace import Workspace

GEO = "deck: Geo\n\nid: a1\nQ: Capital of Ukraine?\nA: Kyiv.\n"
UNSTAMPED = "deck: Geo\n\nQ: Capital of Ukraine?\nA: Kyiv.\n"
BROKEN = "deck: Geo\n\nQ: lonely question\n"


@pytest.fixture
def decks(tmp_path, monkeypatch, mocker, engine):
    root = tmp_path / "decks"
    root.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DECKS_DIR", raising=False)
    mocker.patch("deckaloud.cli.engine_named", return_value=engine)
    mocker.patch("deckaloud.cli.encode_m4a", side_effect=copy_as_encoding)
    return Workspace(root)


@pytest.fixture
def anki(mocker):
    fake = FakeAnki()
    mocker.patch("deckaloud.cli.connected_anki", return_value=fake)
    return fake


def numbered_deck(count):
    cards = "".join(f"\nid: g{number}\nQ: Question {number}?\nA: Answer {number}.\n" for number in range(count))
    return f"deck: Geo\n{cards}"


def write(workspace, name, text):
    path = workspace.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def last_line(text):
    return text.strip().splitlines()[-1]


@pytest.mark.parametrize("command", ["build", "rebuild"])
def test_directory_build_ends_with_a_summary_and_keeps_a_log(decks, capsys, command):
    write(decks, "geo.txt", GEO)

    code = main([command, "--dir", str(decks.root)])
    printed = capsys.readouterr().out

    assert code == 0, f"a clean {command} should exit with 0"
    assert last_line(printed) == "built 1, unchanged 0, removed 0, failed 0", "the last line should be the summary"
    assert decks.package_for("geo.txt").exists(), "the deck should be built under toanki"
    assert read_ledger(decks.ledger_file)["geo.txt"].imported is False, "the build should be recorded for sync"
    assert printed.strip() in decks.log_file.read_text(encoding="utf-8"), "the log should hold the same report"


def test_directory_is_found_without_the_option(decks, capsys):
    write(decks, "geo.txt", GEO)

    code = main(["build"])

    assert code == 0, "build without files should use the default decks directory"
    assert decks.package_for("geo.txt").exists(), "the default directory should be built"


def test_second_build_does_nothing_but_rebuild_redoes_it(decks, capsys):
    write(decks, "geo.txt", GEO)
    main(["build", "--dir", str(decks.root)])
    capsys.readouterr()

    main(["build", "--dir", str(decks.root)])
    built = last_line(capsys.readouterr().out)
    main(["rebuild", "--dir", str(decks.root)])
    rebuilt = last_line(capsys.readouterr().out)

    assert built == "built 0, unchanged 1, removed 0, failed 0", "an unchanged deck should not be built again"
    assert rebuilt == "built 1, unchanged 0, removed 0, failed 0", "rebuild should build it regardless"


def test_failed_deck_is_reported_and_fails_the_run(decks, capsys):
    write(decks, "geo.txt", BROKEN)
    write(decks, "net.txt", GEO)

    code = main(["build", "--dir", str(decks.root)])
    printed = capsys.readouterr().out

    assert code == 1, "a failed deck should make the run exit with 1"
    assert "geo.txt: failed" in printed and "geo.txt:3" in printed, "the failure and its place should be printed"
    assert last_line(printed) == "built 1, unchanged 0, removed 0, failed 1", "the summary should count the failure"


def test_missing_directory_is_an_error(decks, capsys):
    code = main(["build", "--dir", str(decks.root / "absent")])

    assert code == 1, "a missing decks directory should fail"
    assert "decks directory not found" in capsys.readouterr().err, "the error should say what is missing"


@pytest.mark.parametrize("command", [["build"], ["rebuild"], ["sync"], ["add", "x {{c1::y}}"]])
def test_second_run_is_refused_while_one_is_working(decks, capsys, command):
    decks.toanki.mkdir()
    with open(decks.lock_file, "w") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)

        code = main([*command, "--dir", str(decks.root)])

    assert code == 1, "a concurrent run should fail"
    assert "already running" in capsys.readouterr().err, "the error should say another run is working"


def test_status_reports_without_touching_anything(decks, capsys):
    source = write(decks, "geo.txt", UNSTAMPED)

    code = main(["status", "--dir", str(decks.root)])

    assert code == 0, "status should exit with 0"
    assert capsys.readouterr().out.splitlines() == ["geo.txt: new", "1 to build, 0 to import, 0 to remove"], (
        "status should list what a sync would do"
    )
    assert source.read_text(encoding="utf-8") == UNSTAMPED, "status should not stamp sources"
    assert not decks.toanki.exists(), "status should not create the output folder"


def test_add_appends_to_the_test_deck_and_counts_new_cards(decks, capsys):
    main(["add", "--dir", str(decks.root), "--", "booo is {{c1::doo}}"])
    code = main(["add", "--dir", str(decks.root), "--", "Q: Test: what is booo?\nA: Doo."])

    assert code == 0, "a valid card should be added"
    assert last_line(capsys.readouterr().out) == "added 1 card; test.txt has 2 new cards", "add should report the counts"
    assert "C: booo is {{c1::doo}}" in decks.quick_deck.read_text(encoding="utf-8"), "the card should be in test.txt"


def test_add_rejects_invalid_text(decks, capsys):
    code = main(["add", "--dir", str(decks.root), "--", "just some words"])

    assert code == 1, "invalid text should fail"
    assert "expected a line starting with" in capsys.readouterr().err, "the reason should be printed"
    assert not decks.quick_deck.exists(), "nothing should be written"


def test_added_cards_are_built_with_the_rest(decks, capsys):
    main(["add", "--dir", str(decks.root), "--", "booo is {{c1::doo}}"])

    code = main(["build", "--dir", str(decks.root)])

    assert code == 0, "the test deck should build like any other"
    assert decks.package_for("test.txt").exists(), "the test deck should have its package"


def test_sync_builds_imports_and_ends_with_a_summary(decks, anki, capsys):
    write(decks, "geo.txt", GEO)

    code = main(["sync", "--dir", str(decks.root)])
    printed = capsys.readouterr().out

    assert code == 0, "a clean sync should exit with 0"
    assert anki.guids() == {"deckaloud-a1"}, "the card should arrive in Anki"
    assert last_line(printed) == "built 1, imported 1, removed 0, failed 0", "the last line should be the summary"
    assert read_ledger(decks.ledger_file)["geo.txt"].imported, "the import should be recorded"
    assert printed.strip() in decks.log_file.read_text(encoding="utf-8"), "the log should hold the same report"


def test_sync_after_a_build_only_imports(decks, anki, capsys, engine):
    write(decks, "geo.txt", GEO)
    main(["build", "--dir", str(decks.root)])
    spoken = len(engine.spoken)
    capsys.readouterr()

    code = main(["sync", "--dir", str(decks.root)])

    assert code == 0, "sync after a build should succeed"
    assert last_line(capsys.readouterr().out) == "built 0, imported 1, removed 0, failed 0", "nothing should be built again"
    assert len(engine.spoken) == spoken, "no speech should be synthesized again"


def test_second_sync_has_nothing_to_do(decks, anki, capsys):
    write(decks, "geo.txt", GEO)
    main(["sync", "--dir", str(decks.root)])
    capsys.readouterr()

    code = main(["sync", "--dir", str(decks.root)])

    assert code == 0, "a sync with nothing to do should succeed"
    assert capsys.readouterr().out.strip() == "built 0, imported 0, removed 0, failed 0", "only the summary should print"
    assert anki.called("importPackage") == 1, "nothing should be imported twice"


@pytest.mark.parametrize(
    "options, code, left, summary",
    [
        ([], 1, 10, "built 1, imported 0, removed 0, failed 1"),
        (["--force"], 0, 3, "built 1, imported 1, removed 7, failed 0"),
    ],
)
def test_large_deletion_waits_for_force(decks, anki, capsys, options, code, left, summary):
    write(decks, "geo.txt", numbered_deck(10))
    main(["sync", "--dir", str(decks.root)])
    write(decks, "geo.txt", numbered_deck(3))
    capsys.readouterr()

    result = main(["sync", *options, "--dir", str(decks.root)])
    printed = capsys.readouterr().out

    assert result == code, f"the sync should exit with {code}"
    assert len(anki.guids()) == left, f"{left} cards should be left in Anki"
    assert last_line(printed) == summary, f"the summary should read '{summary}'"


def test_failed_build_is_reported_once_and_fails_the_sync(decks, anki, capsys):
    write(decks, "geo.txt", BROKEN)

    code = main(["sync", "--dir", str(decks.root)])
    printed = capsys.readouterr().out

    assert code == 1, "a deck that does not build should fail the sync"
    assert printed.count("geo.txt: failed") == 1, "the failure should be listed once"
    assert last_line(printed) == "built 0, imported 0, removed 0, failed 1", "the summary should count it once"


def test_unreachable_anki_fails_but_keeps_what_was_built(decks, mocker, capsys):
    mocker.patch("deckaloud.cli.connected_anki", side_effect=AnkiUnreachable("Anki did not answer"))
    write(decks, "geo.txt", GEO)

    code = main(["sync", "--dir", str(decks.root)])

    assert code == 1, "sync should fail when Anki cannot be reached"
    assert "Anki did not answer" in capsys.readouterr().err, "the error should say why"
    assert read_ledger(decks.ledger_file)["geo.txt"].imported is False, "the built deck should wait for the next sync"
