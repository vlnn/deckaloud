import json
import sqlite3
import zipfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from deckaloud.cards import cards_from_source
from deckaloud.config import Language
from deckaloud.package import (
    FIELD_NAMES,
    back_template,
    front_template,
    listening_model,
    stable_id,
    write_package,
)
from deckaloud.replay import replay_script
from deckaloud.source import parse_source
from deckaloud.voicing import voice_cards

SOURCE = """\
deck: Geo::Ukraine

id: a1
Q: What is the capital of <Ukraine>?
A: Kyiv.

id: p7
C: Столиця України це {{c1::Київ}} на {{c2::Дніпрі}}.
"""
FIELD_SEPARATOR = "\x1f"


def build(tmp_path, studio, text=SOURCE):
    cards = cards_from_source(parse_source(text, Path("geo.txt")), studio.config)
    output = tmp_path / "out.apkg"
    write_package(voice_cards(cards, studio), studio.config, output)
    return output


def query(apkg, tmp_path, sql):
    with zipfile.ZipFile(apkg) as archive:
        archive.extract("collection.anki2", tmp_path)
    with closing(sqlite3.connect(tmp_path / "collection.anki2")) as database:
        return database.execute(sql).fetchall()


def notes(apkg, tmp_path):
    rows = query(apkg, tmp_path, "select guid, flds, tags from notes order by id")
    return {guid: (fields.split(FIELD_SEPARATOR), tags.strip()) for guid, fields, tags in rows}


def card_templates(apkg, tmp_path):
    ((stored,),) = query(apkg, tmp_path, "select models from col")
    (model,) = json.loads(stored).values()
    return [model["tmpls"][0][side] for side in ("qfmt", "afmt")]


def media_names(apkg):
    with zipfile.ZipFile(apkg) as archive:
        return set(json.loads(archive.read("media")).values())


def test_every_card_becomes_a_note_with_a_stable_guid(tmp_path, studio):
    built = notes(build(tmp_path, studio), tmp_path)

    assert set(built) == {
        "deckaloud-a1",
        "deckaloud-p7-c1",
        "deckaloud-p7-c2",
    }, "each card should be one note keyed by its guid"


def test_note_shows_escaped_text_and_plays_its_clips(tmp_path, studio):
    apkg = build(tmp_path, studio)
    fields, tags = notes(apkg, tmp_path)["deckaloud-a1"]
    front, back, front_audio, back_audio, *runtime = fields

    assert front == "What is the capital of &lt;Ukraine&gt;?", "front text should be HTML-escaped"
    assert back == "Kyiv.", "back text should be the answer"
    assert front_audio.startswith("[sound:deckaloud-") and front_audio.endswith(
        ".m4a]"
    ), "front should reference its baked clip with a sound tag"
    assert front_audio != back_audio, "front and back should have their own clips"
    assert runtime == [""] * 12, "baked sides should leave every runtime speech slot empty"
    assert tags == "deckaloud-a1", "note should be tagged with its guid so it can be found in Anki"


def test_clips_are_packed_as_media(tmp_path, studio):
    apkg = build(tmp_path, studio)
    referenced = {
        field[len("[sound:") : -1]
        for fields, _ in notes(apkg, tmp_path).values()
        for field in fields[2:4]
    }

    assert referenced == media_names(apkg), "every referenced clip should be packed, and nothing else"
    assert len(referenced) == 6, "three cards should carry six distinct clips"


def test_side_that_cannot_be_baked_falls_back_to_runtime_speech(tmp_path, studio):
    silent_uk = replace(
        studio.config, languages={**studio.config.languages, "uk": Language("Missing", "uk_UA", gap_word="пропуск")}
    )
    apkg = build(tmp_path, replace(studio, config=silent_uk))
    fields, _ = notes(apkg, tmp_path)["deckaloud-p7-c1"]
    _, _, front_audio, back_audio, front_en, back_en, front_uk, back_uk, *unused = fields

    assert (front_audio, back_audio) == ("", ""), "unbaked sides should have no sound tag"
    assert (front_en, back_en) == ("", ""), "runtime speech should not land in another language's field"
    assert front_uk == "Столиця України це пропуск на Дніпрі.", "front should carry text for the phone's voice"
    assert back_uk == "Київ. Столиця України це Київ на Дніпрі.", "back should carry deletion then sentence"
    assert unused == [""] * 8, "slots without a language should stay empty"


def test_cards_land_in_their_decks(tmp_path, studio):
    ((stored,),) = query(build(tmp_path, studio), tmp_path, "select decks from col")
    decks = json.loads(stored)

    assert "Geo::Ukraine" in {deck["name"] for deck in decks.values()}, "deck should be named by the header"


def test_templates_speak_runtime_fields_per_language(studio):
    front, back = front_template(studio.config), back_template(studio.config)

    assert "{{tts uk_UA:FrontSpeech2}}" in front, "front should offer Ukrainian runtime speech"
    assert "{{tts en_US:BackSpeech1}}" in back, "back should offer English runtime speech"
    assert "{{FrontAudio}}" not in back, "back should not replay the question clip"
    assert "FrontSpeech" not in back, "back should not speak the question at runtime"


@pytest.mark.parametrize("template", [front_template, back_template])
@pytest.mark.parametrize("keys", [("4",), ("2", "r")])
def test_both_sides_replay_their_audio_on_the_configured_keys(studio, template, keys):
    side = template(replace(studio.config, replay_keys=keys))

    assert side.endswith(replay_script(keys)), f"{template.__name__} should end with the replay script for {keys}"


@pytest.mark.parametrize("template", [front_template, back_template])
def test_sides_carry_no_script_when_replay_keys_are_turned_off(studio, template):
    side = template(replace(studio.config, replay_keys=()))

    assert "<script>" not in side, f"{template.__name__} should carry no script without replay keys"


def test_built_package_replays_on_the_4_key_by_default(tmp_path, studio):
    sides = card_templates(build(tmp_path, studio), tmp_path)

    assert all(
        'const replayKeys = ["4"];' in side for side in sides
    ), "both sides of a built card should replay on the 4 key"


@pytest.mark.parametrize("parts", [("deck", "Geo"), ("model", "en", "uk")])
def test_stable_ids_repeat_and_fit_anki(parts):
    assert stable_id(*parts) == stable_id(*parts), "the same name should always give the same id"
    assert 1 << 30 <= stable_id(*parts) < 1 << 31, "ids should sit in the range genanki recommends"


@pytest.mark.parametrize(
    "settings",
    [
        {"languages": {"en": Language("Samantha", "en_US")}},
        {"languages": {"en": Language("Moira", "en_IE"), "uk": Language("Lesya", "uk_UA")}},
        {
            "languages": {
                "uk": Language("Lesya", "uk_UA"),
                "de": Language("Anna", "de_DE"),
                "en": Language("Ava", "en_US"),
            }
        },
        {"replay_keys": ()},
        {"replay_keys": ("2", "r")},
    ],
)
def test_note_type_identity_and_fields_do_not_depend_on_settings(studio, settings):
    reference = listening_model(studio.config)
    model = listening_model(replace(studio.config, **settings))

    assert model.model_id == reference.model_id, f"note type id should be the same with {settings}"
    assert [field["name"] for field in model.fields] == list(
        FIELD_NAMES
    ), f"note type fields should be the same with {settings}"
