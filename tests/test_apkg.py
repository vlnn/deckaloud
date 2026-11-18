import json
import zipfile
from pathlib import Path

import pytest

from deckaloud.apkg import open_package, save_package
from deckaloud.errors import PackageError

DATA = Path(__file__).parent / "data"
LEGACY = DATA / "anki_legacy_export.apkg"
MODERN = DATA / "anki_modern_export.apkg"


def test_legacy_export_opens_the_real_collection_not_the_decoy(tmp_path):
    package = open_package(LEGACY, tmp_path)

    assert package.collection_name == "collection.anki21", "the real data lives in collection.anki21"
    assert package.database.exists(), "the collection should be extracted for editing"
    assert package.media == {"0": "old.mp3"}, "the media map should be read"


def test_modern_export_is_refused_with_a_way_forward(tmp_path):
    with pytest.raises(PackageError) as raised:
        open_package(MODERN, tmp_path)

    assert "Support older Anki versions" in str(raised.value), "the error should say how to export a usable file"


@pytest.mark.parametrize(
    "make",
    [
        lambda path: path.write_text("not a zip", encoding="utf-8"),
        lambda path: zipfile.ZipFile(path, "w").writestr("readme.txt", "no collection here"),
    ],
)
def test_files_that_are_not_packages_are_refused(tmp_path, make):
    bogus = tmp_path / "bogus.apkg"
    make(bogus)

    with pytest.raises(PackageError) as raised:
        open_package(bogus, tmp_path / "work")

    assert "not an Anki package" in str(raised.value), "the error should say the file is not a package"


def test_saved_package_keeps_everything_and_adds_the_clips(tmp_path):
    package = open_package(LEGACY, tmp_path / "work")
    first, second = tmp_path / "deckaloud-aaa.m4a", tmp_path / "deckaloud-bbb.m4a"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    output = tmp_path / "out.apkg"

    save_package(package, (first, second, first), output)

    with zipfile.ZipFile(LEGACY) as before, zipfile.ZipFile(output) as after:
        media = json.loads(after.read("media"))
        assert media == {
            "0": "old.mp3",
            "1": "deckaloud-aaa.m4a",
            "2": "deckaloud-bbb.m4a",
        }, "new clips should be numbered after the existing media, once each"
        assert after.read("1") == b"one" and after.read("2") == b"two", "clip bytes should be stored by number"
        for kept in ("0", "meta", "collection.anki2"):
            assert after.read(kept) == before.read(kept), f"{kept} should be carried over unchanged"
        assert sorted(after.namelist()) == sorted(
            [*before.namelist(), "1", "2"]
        ), "nothing but the clips should be added"


def test_clip_already_in_the_package_is_not_stored_twice(tmp_path):
    package = open_package(LEGACY, tmp_path / "work")
    clip = tmp_path / "old.mp3"
    clip.write_bytes(b"again")
    output = tmp_path / "out.apkg"

    save_package(package, (clip,), output)

    with zipfile.ZipFile(output) as after:
        assert json.loads(after.read("media")) == {"0": "old.mp3"}, "a known media name should not be added again"
