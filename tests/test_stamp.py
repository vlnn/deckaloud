from itertools import count

import pytest

from deckaloud.stamp import random_id, stamp_file, stamp_text


def numbered_ids():
    numbers = count(1)
    return lambda: f"new{next(numbers)}"


@pytest.mark.parametrize(
    "text, expected, stamped",
    [
        ("Q: a\nA: b\n", "id: new1\nQ: a\nA: b\n", 1),
        ("id: old\nQ: a\nA: b\n", "id: old\nQ: a\nA: b\n", 0),
        ("deck: D\nlang: uk\n\nC: {{c1::x}}\n", "deck: D\nlang: uk\n\nid: new1\nC: {{c1::x}}\n", 1),
        (
            "Q: a\nA: b\n\nid: old\nQ: c\nA: d\n\nlang: uk\nC: {{c1::x}}",
            "id: new1\nQ: a\nA: b\n\nid: old\nQ: c\nA: d\n\nid: new2\nlang: uk\nC: {{c1::x}}",
            2,
        ),
    ],
)
def test_stamp_text_adds_ids_only_where_missing(text, expected, stamped):
    result, added = stamp_text(text, numbered_ids())

    assert result == expected, "only card blocks without an id should gain one, in file order"
    assert added == stamped, f"{stamped} ids should be reported as added"


def test_stamp_file_rewrites_only_when_needed(tmp_path):
    stamped = tmp_path / "stamped.txt"
    stamped.write_text("id: old\nQ: a\nA: b\n", encoding="utf-8")
    before = stamped.stat().st_mtime_ns
    fresh = tmp_path / "fresh.txt"
    fresh.write_text("Q: a\nA: b\n", encoding="utf-8")

    assert stamp_file(stamped, numbered_ids()) == 0, "a fully stamped file should need no ids"
    assert stamped.stat().st_mtime_ns == before, "a fully stamped file should not be rewritten"
    assert stamp_file(fresh, numbered_ids()) == 1, "an unstamped card should be counted"
    assert fresh.read_text(encoding="utf-8").startswith("id: new1\n"), "the id should be written to disk"


def test_random_ids_are_short_and_distinct():
    ids = {random_id() for _ in range(50)}

    assert len(ids) == 50, "random ids should not repeat"
    assert all(len(value) == 8 for value in ids), "random ids should be 8 characters"


def test_stamping_leaves_no_temporary_files(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Q: a\nA: b\n", encoding="utf-8")

    stamp_file(path, numbered_ids())

    assert [item.name for item in tmp_path.iterdir()] == ["notes.txt"], "only the source should remain"


def test_failed_write_leaves_the_source_untouched(tmp_path, mocker):
    path = tmp_path / "notes.txt"
    path.write_text("Q: a\nA: b\n", encoding="utf-8")
    mocker.patch("deckaloud.stamp.os.replace", side_effect=OSError("disk full"))

    with pytest.raises(OSError):
        stamp_file(path, numbered_ids())

    assert path.read_text(encoding="utf-8") == "Q: a\nA: b\n", "a failed stamp should not damage the source"
    assert [item.name for item in tmp_path.iterdir()] == ["notes.txt"], "the draft should be cleaned up"


def test_byte_order_mark_does_not_hide_the_first_block(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xef\xbb\xbfQ: a\nA: b\n")

    assert stamp_file(path, numbered_ids()) == 1, "a card after a byte-order mark should still be stamped"
