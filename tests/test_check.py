from pathlib import Path

import pytest

from deckaloud.check import problems
from deckaloud.config import Config, Language
from deckaloud.source import parse_source


def sources(*texts):
    return tuple(parse_source(text, Path(f"file{index}.txt")) for index, text in enumerate(texts))


def test_clean_sources_have_no_problems():
    found = problems(sources("id: a\nQ: q\nA: a\n", "id: b\nC: {{c1::x}} y\n"), Config())

    assert found == (), "stamped, voiced, unique cards should pass"


@pytest.mark.parametrize(
    "texts, fragments",
    [
        (("Q: q\nA: a\n",), ["file0.txt:1", "no id"]),
        (("id: a\nQ: q\nA: a\n\nid: a\nQ: r\nA: b\n",), ["file0.txt:5", "'a'", "already used"]),
        (("id: a\nQ: q\nA: a\n", "id: a\nQ: r\nA: b\n"), ["file1.txt:1", "already used"]),
        (("id: a\nlang: de\nQ: q\nA: a\n",), ["file0.txt:1", "'de'", "no voice"]),
    ],
)
def test_each_problem_names_its_place(texts, fragments):
    (problem,) = problems(sources(*texts), Config())

    assert all(fragment in problem for fragment in fragments), f"'{problem}' should mention {fragments}"


def test_language_of_a_foreign_stretch_needs_a_voice_too():
    english_only = Config(languages={"en": Language("Samantha", "en_US")})

    (problem,) = problems(sources("id: a\nQ: Січень in english?\nA: January.\n"), english_only)

    assert all(
        fragment in problem for fragment in ["file0.txt:1", "'uk'", "no voice"]
    ), f"'{problem}' should name the voiceless language of the Ukrainian word"
