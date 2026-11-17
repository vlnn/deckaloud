from pathlib import Path

import pytest

from deckaloud.cards import cards_from_source
from deckaloud.config import Config
from deckaloud.report import (
    fallbacks,
    format_report,
    read_manifest,
    removed_guids,
    write_manifest,
)
from deckaloud.source import parse_source
from deckaloud.voicing import VoicedCard, VoicedSide


def voiced(problem=None):
    (card,) = cards_from_source(parse_source("id: a1\nQ: q\nA: a\n", Path("geo.txt")), Config())
    clip = None if problem else Path("clip.m4a")
    return VoicedCard(card, VoicedSide(card.front, clip, problem), VoicedSide(card.back, Path("b.m4a"), None))


@pytest.mark.parametrize(
    "previous, current, expected",
    [
        (set(), {"a"}, ()),
        ({"a", "b"}, {"a", "b"}, ()),
        ({"b", "a", "c"}, {"a"}, ("b", "c")),
    ],
)
def test_removed_guids_are_what_the_last_build_had_and_this_one_lacks(previous, current, expected):
    assert removed_guids(previous, current) == expected, f"{previous} minus {current} should be {expected}"


def test_manifest_round_trips_and_starts_empty(tmp_path):
    path = tmp_path / "state" / "deck.manifest.json"

    assert read_manifest(path) == frozenset(), "a missing manifest should mean no previous build"

    write_manifest(path, {"deckaloud-a", "deckaloud-b"})

    assert read_manifest(path) == {"deckaloud-a", "deckaloud-b"}, "manifest should return the stored guids"


def test_fallbacks_list_each_unbaked_side_with_its_reason():
    assert fallbacks((voiced(),)) == (), "fully baked cards should report no fallback"
    assert fallbacks((voiced("voice 'Lesya' is not installed"),)) == (
        "geo.txt:1 (a1) front: voice 'Lesya' is not installed",
    ), "an unbaked side should be listed with place, side and reason"


def test_report_for_a_clean_build_is_one_line():
    report = format_report((voiced(),), Path("out.apkg"), ())

    assert report == "Built 1 card into out.apkg, all sides baked.", "a clean build should be a single line"


def test_report_lists_fallbacks_and_removed_cards():
    report = format_report((voiced("no voice"),), Path("out.apkg"), ("deckaloud-old-c2",))

    assert "1 of 2 sides will be read by the phone's own voice" in report, "report should count fallbacks"
    assert "geo.txt:1 (a1) front: no voice" in report, "report should say which side fell back and why"
    assert "tag:deckaloud-old-c2" in report, "report should give a search that finds each removed card"
