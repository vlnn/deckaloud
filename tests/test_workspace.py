from pathlib import Path

import pytest

from deckaloud.workspace import Workspace, workspace_root


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path)


def touch(workspace, name):
    path = workspace.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "explicit, environ, expected",
    [
        (Path("/given"), {"DECKS_DIR": "/from-env"}, Path("/given")),
        (None, {"DECKS_DIR": "/from-env"}, Path("/from-env")),
        (None, {"DECKS_DIR": "~/cards"}, Path("/home/me/cards")),
        (None, {"DECKS_DIR": ""}, Path("/home/me/decks")),
        (None, {}, Path("/home/me/decks")),
    ],
)
def test_directory_comes_from_option_then_environment_then_home(explicit, environ, expected):
    found = workspace_root(explicit, {"HOME": "/home/me", **environ})

    assert found == expected, f"the decks directory should be {expected}"


def test_sources_are_found_in_subfolders_in_a_stable_order(workspace):
    for name in ("b.txt", "a.txt", "notes/c.txt", "readme.md"):
        touch(workspace, name)

    names = [workspace.name(path) for path in workspace.sources()]

    assert names == ["a.txt", "b.txt", "notes/c.txt"], "every txt should be found, sorted, and nothing else"


@pytest.mark.parametrize("name", ["toanki/x.txt", "inbox/x.txt", "originals/x.txt", ".git/x.txt", "notes/.hidden/x.txt"])
def test_reserved_and_hidden_folders_hold_no_sources(workspace, name):
    touch(workspace, name)

    assert workspace.sources() == (), f"{name} should not be treated as a deck source"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("geo.txt", "toanki/geo.apkg"),
        ("notes/geo.txt", "toanki/notes/geo.apkg"),
        ("originals/shared.apkg", "toanki/originals/shared.apkg"),
    ],
)
def test_package_mirrors_the_source_path_under_toanki(workspace, name, expected):
    assert workspace.package_for(name) == workspace.root / expected, f"{name} should be built into {expected}"


def test_dropped_and_kept_packages_are_listed(workspace):
    touch(workspace, "inbox/new.apkg")
    touch(workspace, "inbox/.gitkeep")
    touch(workspace, "originals/old.apkg")

    assert [path.name for path in workspace.dropped()] == ["new.apkg"], "only packages in inbox should be listed"
    assert [path.name for path in workspace.kept()] == ["old.apkg"], "only packages in originals should be listed"
