import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from deckaloud.fieldtext import field_checksum, has_formula, sort_text, spoken_text

LEGACY = Path(__file__).parent / "data" / "anki_legacy_export.apkg"


@pytest.mark.parametrize(
    "html, expected",
    [
        ("plain words", "plain words"),
        ("What is <b>TCP</b>?", "What is TCP?"),
        ("  spaced \n out  ", "spaced out"),
        ("first line<br>second line", "first line. second line"),
        ("<div>Is it?</div><div>Yes</div>", "Is it? Yes"),
        ("<ul><li>one</li><li>two</li></ul>", "one. two"),
        ("Tom &amp; Jerry &lt;3", "Tom & Jerry <3"),
        ("<style>.x{color:red}</style>shown<script>alert(1)</script>", "shown"),
        ('<img src="map.png">', ""),
        ("word [sound:word.mp3]", "word"),
        ("", ""),
    ],
)
def test_spoken_text_keeps_only_what_a_reader_would_say(html, expected):
    assert spoken_text(html) == expected, f"{html!r} should be spoken as {expected!r}"


@pytest.mark.parametrize(
    "html, expected",
    [
        ("E = mc<sup>2</sup>", False),
        (r"Solve \(x^2 = 4\)", True),
        (r"\[ \int_0^1 x \, dx \]", True),
        ("[latex]x^2[/latex]", True),
        ("[$]x^2[/$]", True),
        ("It costs $5 (five dollars) [roughly]", False),
    ],
)
def test_formulas_are_recognised(html, expected):
    assert has_formula(html) is expected, f"{html!r} formula detection should be {expected}"


def stored_notes():
    with zipfile.ZipFile(LEGACY) as archive, closing(sqlite3.connect(":memory:")) as database:
        database.deserialize(archive.read("collection.anki21"))
        return database.execute("select flds, sfld, csum from notes").fetchall()


@pytest.mark.parametrize("fields, sort_field, checksum", stored_notes())
def test_sort_text_and_checksum_match_what_anki_itself_stored(fields, sort_field, checksum):
    first = fields.split("\x1f")[0]

    assert sort_text(first) == str(sort_field), f"sort text of {first!r} should match Anki's"
    assert field_checksum(first) == checksum, f"checksum of {first!r} should match Anki's"


@pytest.mark.parametrize(
    "field, sort_field, checksum",
    [
        ('<i>Front</i> <img src="map.png">[sound:a.m4a]', "Front  map.png [sound:a.m4a]", 500005531),
        ("A &amp; B<br>line two", "A & Bline two", 1323640027),
        ("<div>x</div> <audio src='s.mp3'></audio>", "x  s.mp3 ", 918646449),
    ],
)
def test_sort_text_and_checksum_match_values_recorded_from_anki(field, sort_field, checksum):
    assert sort_text(field) == sort_field, f"sort text of {field!r} should be {sort_field!r}"
    assert field_checksum(field) == checksum, f"checksum of {field!r} should be {checksum}"
