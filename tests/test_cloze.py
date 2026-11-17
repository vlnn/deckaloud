import pytest

from deckaloud.cloze import (
    Deletion,
    deletion_numbers,
    full_sentence,
    hidden_deletions,
    parse_cloze,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("plain text", ("plain text",)),
        ("{{c1::Kyiv}} is big", (Deletion(1, "Kyiv", None), " is big")),
        ("in {{c2::Kyiv::city}}.", ("in ", Deletion(2, "Kyiv", "city"), ".")),
        (
            "{{c1::A}} and {{c2::B}}",
            (Deletion(1, "A", None), " and ", Deletion(2, "B", None)),
        ),
    ],
)
def test_parse_cloze_splits_text_and_deletions(text, expected):
    assert parse_cloze(text) == expected, f"'{text}' should parse into {expected}"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("no gaps", ()),
        ("{{c2::b}} {{c1::a}}", (1, 2)),
        ("{{c1::a}} {{c1::b}} {{c3::c}}", (1, 3)),
    ],
)
def test_deletion_numbers_are_distinct_and_sorted(text, expected):
    assert deletion_numbers(parse_cloze(text)) == expected, f"'{text}' should number as {expected}"


def test_full_sentence_restores_every_answer():
    parts = parse_cloze("The capital of {{c1::Ukraine}} is {{c2::Kyiv::city}}.")

    assert (
        full_sentence(parts) == "The capital of Ukraine is Kyiv."
    ), "full sentence should contain answers without markup or hints"


def test_hidden_deletions_selects_one_number():
    parts = parse_cloze("{{c1::a}} {{c2::b}} {{c1::c}}")

    assert hidden_deletions(parts, 1) == (
        Deletion(1, "a", None),
        Deletion(1, "c", None),
    ), "same-numbered deletions should be hidden together"
