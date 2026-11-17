from pathlib import Path

import pytest

from deckaloud.check import problems
from deckaloud.config import Config
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
