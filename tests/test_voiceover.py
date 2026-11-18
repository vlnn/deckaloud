import json
import sqlite3
import zipfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from deckaloud.config import Language
from deckaloud.errors import PackageError
from deckaloud.fieldtext import field_checksum, sort_text
from deckaloud.speech import Say, SayIn, Speech
from deckaloud.voiceover import (
    ALREADY_HAS_SOUND,
    EMPTY,
    HAS_FORMULA,
    TOO_LONG,
    UNVOICED_SCRIPT,
    VoiceOptions,
    field_speech,
    format_voice_report,
    voice_package,
)

LEGACY = Path(__file__).parent / "data" / "anki_legacy_export.apkg"
OPTIONS = VoiceOptions()


def rows(apkg, sql):
    with zipfile.ZipFile(apkg) as archive, closing(sqlite3.connect(":memory:")) as database:
        database.deserialize(archive.read("collection.anki21"))
        return database.execute(sql).fetchall()


def fields_by_first_word(apkg):
    notes = rows(apkg, "select flds from notes")
    return {flds.split("[sound:")[0].split("\x1f")[0].split()[0]: flds.split("\x1f") for (flds,) in notes}


@pytest.fixture
def voiced(studio, tmp_path):
    output = tmp_path / "voiced.apkg"
    report = voice_package(LEGACY, output, studio, OPTIONS)
    return output, report


@pytest.mark.parametrize(
    "html, expected",
    [
        ("What is <b>TCP</b>?", Speech("en", (Say("What is TCP?"),))),
        ("Столиця України?", Speech("uk", (Say("Столиця України?"),))),
        ("1991", Speech("en", (Say("1991"),))),
        (
            "Month <b>Січень</b> in English?",
            Speech("en", (Say("Month"), SayIn("Січень", "uk"), Say("in English?"))),
        ),
        ("", EMPTY),
        ('<img src="map.png">', EMPTY),
        ("word [sound:word.mp3]", ALREADY_HAS_SOUND),
        ("[sound:only.mp3]", ALREADY_HAS_SOUND),
        (r"Solve \(x^2 = 4\)", HAS_FORMULA),
        ("日本の首都は？", UNVOICED_SCRIPT),
        ("Ελληνικά", UNVOICED_SCRIPT),
        ("x" * 601, TOO_LONG),
    ],
)
def test_field_speech_speaks_what_it_can_and_names_why_not(html, expected):
    assert field_speech(html, OPTIONS) == expected, f"{html[:30]!r} should give {expected}"


@pytest.mark.parametrize(
    "options, html, lang",
    [
        (VoiceOptions(default_lang="uk"), "1991", "uk"),
        (VoiceOptions(default_lang="uk"), "TCP", "en"),
        (VoiceOptions(default_lang="de"), "Was ist das?", "de"),
    ],
)
def test_default_language_applies_when_the_script_allows(options, html, lang):
    assert field_speech(html, options).lang == lang, f"{html!r} should be read in {lang}"


def test_every_speakable_field_gains_a_sound_tag(voiced):
    notes = fields_by_first_word(voiced[0])

    for word in ("What", "Столиця", "Year?"):
        front, back = notes[word]
        assert front.endswith(".m4a]") and "[sound:deckaloud-" in front, f"front of '{word}' should gain a clip"
        assert back.endswith(".m4a]") and "[sound:deckaloud-" in back, f"back of '{word}' should gain a clip"
    assert notes["What"][0].startswith("What is <b>TCP</b>?"), "the original markup should be kept"


def test_fields_that_cannot_be_voiced_are_left_exactly_as_they_were(voiced):
    notes = fields_by_first_word(voiced[0])

    assert notes["Has"][0] == "Has sound already [sound:old.mp3]", "a field with sound should be untouched"
    assert "[sound:deckaloud-" in notes["Has"][1], "its sibling field should still be voiced"
    assert notes["日本の首都は？"] == ["日本の首都は？", "東京"], "a script without a voice should be untouched"
    assert notes["Kyiv"][0] == "Kyiv lies on the {{c1::Dnipro}}.", "cloze text should be untouched"
    assert "[sound:deckaloud-" in notes["Kyiv"][1], "the cloze note's extra field should be voiced"


def test_each_language_is_spoken_by_its_voice(voiced, engine):
    voices = {text: voice for text, voice, _ in engine.spoken}

    assert voices["Столиця України?"] == "Lesya", "Cyrillic fields should use the Ukrainian voice"
    assert voices["What is TCP?"] == "Samantha (English (US))", "Latin fields should use the English voice"


def test_report_counts_what_was_voiced_and_why_the_rest_was_not(voiced):
    report = voiced[1]

    assert (report.notes, report.changed_notes, report.voiced_fields) == (6, 5, 8), "counts should match the deck"
    assert dict(report.skipped) == {
        "cloze text, where audio would give the answer away": 1,
        ALREADY_HAS_SOUND: 1,
        UNVOICED_SCRIPT: 2,
    }, "every skipped field should be counted under its reason"


def test_clips_are_packed_and_old_media_is_kept(voiced):
    with zipfile.ZipFile(voiced[0]) as archive:
        media = json.loads(archive.read("media"))
        names = set(archive.namelist())

    assert media["0"] == "old.mp3", "existing media should keep its number"
    assert len(media) == 9, "eight clips should join the one existing file"
    assert all(index in names for index in media), "every listed media file should be in the archive"
    referenced = {
        tag.split("]")[0]
        for (flds,) in rows(voiced[0], "select flds from notes")
        for tag in flds.split("[sound:")[1:]
    }
    assert referenced == set(media.values()), "every sound tag should point at a packed file"


def test_changed_notes_are_newer_and_consistent_so_anki_will_update_them(voiced):
    before = dict(rows(LEGACY, "select id, mod from notes"))
    after = rows(voiced[0], "select id, mod, usn, flds, sfld, csum from notes")

    for note_id, mod, usn, flds, sfld, csum in after:
        first = flds.split("\x1f")[0]
        changed = "[sound:deckaloud-" in flds
        assert (mod > before[note_id]) is changed, "only changed notes should get a newer modification time"
        assert not changed or usn == -1, "changed notes should be marked as needing sync"
        assert str(sfld) == sort_text(first), "the sort field should match the new first field"
        assert csum == field_checksum(first), "the checksum should match the new first field"


def test_scheduling_and_everything_else_in_the_collection_is_untouched(voiced):
    for table in ("cards", "revlog", "col"):
        assert rows(voiced[0], f"select * from {table}") == rows(
            LEGACY, f"select * from {table}"
        ), f"table {table} should be identical"


def test_voicing_a_voiced_package_changes_nothing(voiced, studio, tmp_path):
    again = tmp_path / "again.apkg"

    report = voice_package(voiced[0], again, studio, OPTIONS)

    assert report.voiced_fields == 0, "nothing should be left to voice"
    assert rows(again, "select flds, mod from notes") == rows(
        voiced[0], "select flds, mod from notes"
    ), "notes should be unchanged by a second pass"


def test_engine_failures_are_counted_as_skips_not_crashes(studio, tmp_path):
    languages = {**studio.config.languages, "uk": Language("Missing", "uk_UA")}
    broken = replace(studio, config=replace(studio.config, languages=languages))

    report = voice_package(LEGACY, tmp_path / "out.apkg", broken, OPTIONS)

    reasons = dict(report.skipped)
    assert report.voiced_fields == 6, "English fields should still be voiced"
    assert any("'Missing' is not installed" in reason and count == 2 for reason, count in reasons.items()), (
        "both Ukrainian fields should be counted under the engine's explanation"
    )


def test_long_fields_respect_the_limit(studio, tmp_path):
    report = voice_package(LEGACY, tmp_path / "out.apkg", studio, VoiceOptions(max_chars=10))

    assert dict(report.skipped)[TOO_LONG] >= 3, "fields over the limit should be skipped as too long"


def test_writing_over_the_input_is_refused(studio):
    with pytest.raises(PackageError) as raised:
        voice_package(LEGACY, LEGACY, studio, OPTIONS)

    assert "different" in str(raised.value), "the error should ask for a different output file"


def test_report_text_names_counts_reasons_and_output(voiced):
    text = format_voice_report(voiced[1], Path("voiced.apkg"))

    assert "Voiced 8 fields in 5 of 6 notes into voiced.apkg." in text, "the headline should give the counts"
    assert f"2 × {UNVOICED_SCRIPT}" in text, "each reason should be listed with its count"
