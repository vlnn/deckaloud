import pytest

from deckaloud.ledger import Entry, digest
from deckaloud.overview import overview_lines
from deckaloud.workspace import Workspace

GEO = "deck: Geo\n\nid: a1\nQ: Capital of Ukraine?\nA: Kyiv.\n"
UNSTAMPED = "deck: Geo\n\nQ: Capital of Ukraine?\nA: Kyiv.\n"


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path)


def write(workspace, name, text="package"):
    path = workspace.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def recorded(workspace, name, **changes):
    return {name: Entry(**{"digest": digest(workspace.root / name), "imported": True, **changes})}


def test_empty_directory_has_nothing_to_do(workspace):
    assert overview_lines(workspace, {}) == ["nothing to do"], "an empty directory should need no work"


def test_new_source_is_to_be_built(workspace):
    write(workspace, "geo.txt", GEO)

    assert overview_lines(workspace, {}) == ["geo.txt: new", "1 to build, 0 to import, 0 to remove"], (
        "a source that was never built should be listed as new"
    )


@pytest.mark.parametrize(
    "text, changes, with_package, expected",
    [
        (GEO, {}, True, []),
        (GEO, {"imported": False}, True, ["geo.txt: built, waiting for import", "0 to build, 1 to import, 0 to remove"]),
        (GEO, {"digest": "older"}, True, ["geo.txt: changed", "1 to build, 0 to import, 0 to remove"]),
        (GEO, {}, False, ["geo.txt: changed", "1 to build, 0 to import, 0 to remove"]),
        (UNSTAMPED, {}, True, ["geo.txt: changed", "1 to build, 0 to import, 0 to remove"]),
        (GEO, {"removed": True}, False, ["geo.txt: new", "1 to build, 0 to import, 0 to remove"]),
    ],
)
def test_known_source_is_reported_by_what_it_still_needs(workspace, text, changes, with_package, expected):
    write(workspace, "geo.txt", text)
    if with_package:
        write(workspace, "toanki/geo.apkg")

    lines = overview_lines(workspace, recorded(workspace, "geo.txt", **changes))

    assert lines == (expected or ["nothing to do"]), f"the overview should read {expected}"


def test_source_that_is_not_text_is_listed_for_building(workspace):
    (workspace.root / "binary.txt").write_bytes(b"\xff\xfe\x00 not text")

    lines = overview_lines(workspace, {"binary.txt": Entry(digest(workspace.root / "binary.txt"), True)})

    assert lines[0] == "binary.txt: changed", "an unreadable source should be left for build to report"


def test_overview_changes_nothing(workspace):
    source = write(workspace, "geo.txt", UNSTAMPED)

    overview_lines(workspace, {})

    assert source.read_text(encoding="utf-8") == UNSTAMPED, "looking should not stamp the source"
    assert not workspace.toanki.exists(), "looking should not create the output folder"


@pytest.mark.parametrize(
    "ledger, expected",
    [
        ({"geo.txt": Entry("gone", True, ("deckaloud-a1",))}, "geo.txt: deleted, to be removed from Anki"),
        ({"geo.txt": Entry("gone", False, ("deckaloud-a1",), removed=True)}, "geo.txt: deleted, to be removed from Anki"),
        ({"originals/shared.apkg": Entry("gone", True)}, "originals/shared.apkg: deleted"),
    ],
)
def test_deleted_decks_are_listed(workspace, ledger, expected):
    lines = overview_lines(workspace, ledger)

    assert lines[0] == expected, f"the deleted deck should be listed as '{expected}'"


def test_text_deck_waiting_for_removal_is_counted(workspace):
    lines = overview_lines(workspace, {"geo.txt": Entry("gone", True, ("deckaloud-a1",))})

    assert lines[-1] == "0 to build, 0 to import, 1 to remove", "a deleted text deck should count as one removal"


def test_third_party_packages_are_listed(workspace):
    write(workspace, "inbox/fresh.apkg")
    write(workspace, "originals/shared.apkg")

    lines = overview_lines(workspace, {})

    assert lines == [
        "inbox/fresh.apkg: waiting to be voiced",
        "originals/shared.apkg: new",
        "2 to build, 0 to import, 0 to remove",
    ], "dropped and kept packages should both be listed for building"
