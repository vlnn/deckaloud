import pytest

from deckaloud.notetypes import (
    ALREADY_SPOKEN,
    BEHIND_HINT,
    CLOZE_TEXT,
    NOT_SHOWN,
    NoteType,
    Template,
    field_roles,
    replayed_fields,
)


def note_type(fields, *templates):
    return NoteType("Test", tuple(fields), tuple(Template(front, back) for front, back in templates), 0)


@pytest.mark.parametrize(
    "fields, templates, expected",
    [
        (["Front", "Back"], [("{{Front}}", "{{FrontSide}}<hr id=answer>{{Back}}")], (None, None)),
        (["Text", "Back Extra"], [("{{cloze:Text}}", "{{cloze:Text}}<br>{{Back Extra}}")], (CLOZE_TEXT, None)),
        (["Text"], [("{{type:cloze:Text}}", "{{cloze:Text}}")], (CLOZE_TEXT,)),
        (["Front", "Back", "Notes"], [("{{Front}}", "{{Back}}")], (None, None, NOT_SHOWN)),
        (["Front", "Back"], [("{{tts en_US voices=Apple_Ava:Front}}{{Front}}", "{{Back}}")], (ALREADY_SPOKEN, None)),
        (["Front", "Back"], [("{{Front}}{{type:Back}}", "{{FrontSide}}")], (None, NOT_SHOWN)),
        (["Front", "Back"], [("{{Front}}{{type:Back}}", "{{Back}}")], (None, None)),
        (["Front", "Tip", "Back"], [("{{Front}}{{hint:Tip}}", "{{Back}}")], (None, BEHIND_HINT, None)),
        (["Front", "Back"], [("{{text:Front}}", "{{ Back }}")], (None, None)),
        (["Front", "Back"], [("{{#Front}}x{{/Front}}{{^Back}}y{{/Back}}", "z")], (NOT_SHOWN, NOT_SHOWN)),
        (["A", "B"], [("{{A}}", "{{B}}"), ("{{B}}", "{{A}}")], (None, None)),
    ],
)
def test_field_roles_follow_how_templates_use_each_field(fields, templates, expected):
    assert field_roles(note_type(fields, *templates)) == expected, f"{templates} should give roles {expected}"


@pytest.mark.parametrize(
    "templates, expected",
    [
        ([("{{Front}}", "{{FrontSide}}<hr>{{Back}}")], ()),
        ([("{{Front}}", "{{Front}}<hr>{{Back}}")], ("Front",)),
        ([("{{Front}}", "{{text:Front}}<hr>{{Back}}")], ("Front",)),
        ([("{{Front}}", "{{Back}}"), ("{{Back}}", "{{Front}}")], ()),
    ],
)
def test_fields_repeated_on_the_answer_side_are_found(templates, expected):
    assert (
        replayed_fields(note_type(["Front", "Back"], *templates)) == expected
    ), f"{templates} should replay {expected} on the answer side"
