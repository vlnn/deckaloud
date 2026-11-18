import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass

NOT_SHOWN = "not shown on any card"
CLOZE_TEXT = "cloze text, where audio would give the answer away"
ALREADY_SPOKEN = "already spoken by the card template"
BEHIND_HINT = "hidden behind a hint"
REFERENCE = re.compile(r"\{\{([^{}#^/][^{}]*)\}\}")
CLOZE_TYPE = 1


@dataclass(frozen=True)
class Template:
    front: str
    back: str


@dataclass(frozen=True)
class NoteType:
    name: str
    fields: tuple[str, ...]
    templates: tuple[Template, ...]
    sort_index: int


Uses = frozenset[str]


def read_note_types(database: sqlite3.Connection) -> dict[int, NoteType]:
    (models,) = database.execute("select models from col").fetchone()
    return {int(key): note_type(model) for key, model in json.loads(models or "{}").items()}


def note_type(model: dict) -> NoteType:
    fields = sorted(model["flds"], key=lambda field: field["ord"])
    return NoteType(
        name=model["name"],
        fields=tuple(field["name"] for field in fields),
        templates=tuple(Template(template["qfmt"], template["afmt"]) for template in model["tmpls"]),
        sort_index=model.get("sortf", 0),
    )


def references(template_text: str) -> Iterator[tuple[str, Uses]]:
    for match in REFERENCE.finditer(template_text):
        *filters, name = match.group(1).split(":")
        yield name.strip(), frozenset(used.strip().split(" ")[0] for used in filters)


def field_uses(sides: list[str]) -> dict[str, list[Uses]]:
    uses: dict[str, list[Uses]] = {}
    for side in sides:
        for name, filters in references(side):
            uses.setdefault(name, []).append(filters)
    return uses


def field_roles(kind: NoteType) -> tuple[str | None, ...]:
    sides = [side for template in kind.templates for side in (template.front, template.back)]
    uses = field_uses(sides)
    return tuple(role(uses.get(name, [])) for name in kind.fields)


def role(uses: list[Uses]) -> str | None:
    shown = [filters for filters in uses if "type" not in filters or "cloze" in filters]
    if any("cloze" in filters for filters in shown):
        return CLOZE_TEXT
    if any("tts" in filters for filters in shown):
        return ALREADY_SPOKEN
    if not shown:
        return NOT_SHOWN
    if all("hint" in filters for filters in shown):
        return BEHIND_HINT
    return None


def replayed_fields(kind: NoteType) -> tuple[str, ...]:
    return tuple(name for name in kind.fields if any(is_repeated(name, template) for template in kind.templates))


def is_repeated(name: str, template: Template) -> bool:
    return is_displayed(name, template.front) and is_displayed(name, template.back)


def is_displayed(name: str, side: str) -> bool:
    return role(field_uses([side]).get(name, [])) is None
