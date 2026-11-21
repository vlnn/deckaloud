import subprocess

import pytest

from deckaloud.gitstate import files_with_uncommitted_ids

COMMITTED = "deck: Geo\n\nid: a1\nQ: Capital of Ukraine?\nA: Kyiv.\n"
NEW_CARD = "\nid: a2\nQ: Capital of Poland?\nA: Warsaw.\n"
REWORDED = COMMITTED.replace("Capital", "Main city")


def git(root, *args):
    identity = ["-c", "user.name=tester", "-c", "user.email=tester@example.com"]
    subprocess.run(["git", "-C", str(root), *identity, *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "geo.txt").write_text(COMMITTED, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "decks")
    return tmp_path


@pytest.mark.parametrize(
    "name, text, expected",
    [
        ("geo.txt", COMMITTED, ()),
        ("geo.txt", COMMITTED + NEW_CARD, ("geo.txt",)),
        ("geo.txt", REWORDED, ()),
        ("new.txt", COMMITTED, ("new.txt",)),
        ("notes/new.txt", COMMITTED, ("notes/new.txt",)),
        ("new.txt", "deck: Geo\n\nQ: Capital of Ukraine?\nA: Kyiv.\n", ()),
    ],
)
def test_only_files_with_ids_missing_from_the_last_commit_are_listed(repo, name, text, expected):
    path = repo / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")

    assert files_with_uncommitted_ids(repo) == expected, f"uncommitted ids should be found in {expected}"


def test_directory_outside_git_has_nothing_to_commit(tmp_path):
    (tmp_path / "geo.txt").write_text(COMMITTED, encoding="utf-8")

    assert files_with_uncommitted_ids(tmp_path) == (), "a directory that is not a repository should list nothing"
