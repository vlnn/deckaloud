import sqlite3
import tempfile
import time
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from deckaloud.apkg import open_package, save_package
from deckaloud.errors import PackageError, SpeechError
from deckaloud.fieldtext import (
    field_checksum,
    has_formula,
    has_sound,
    sort_text,
    spoken_text,
)
from deckaloud.language import detect_language, has_unvoiced_script, voiced_by_script
from deckaloud.notetypes import NoteType, field_roles, read_note_types, replayed_fields
from deckaloud.render import Studio, render_clip
from deckaloud.speech import Say, Speech

FIELD_SEPARATOR = "\x1f"
EMPTY = "empty"
ALREADY_HAS_SOUND = "already has sound"
HAS_FORMULA = "contains a formula"
TOO_LONG = "too long to listen to"
UNVOICED_SCRIPT = "written in a script no configured voice reads"
UNKNOWN_NOTE_TYPE = "note type missing from the package"


@dataclass(frozen=True)
class VoiceOptions:
    default_lang: str = "en"
    max_chars: int = 600


@dataclass(frozen=True)
class VoicedField:
    content: str
    clip: Path | None = None
    skipped: str | None = None


@dataclass(frozen=True)
class VoicedNote:
    note_id: int
    modified: int
    sort_index: int
    fields: tuple[VoicedField, ...]

    @property
    def clips(self) -> tuple[Path, ...]:
        return tuple(field.clip for field in self.fields if field.clip)


@dataclass(frozen=True)
class VoiceReport:
    notes: int
    changed_notes: int
    voiced_fields: int
    skipped: tuple[tuple[str, int], ...]
    replayed: tuple[str, ...]


def voice_package(source: Path, output: Path, studio: Studio, options: VoiceOptions) -> VoiceReport:
    reject_same_file(source, output)
    with tempfile.TemporaryDirectory() as scratch:
        package = open_package(source, Path(scratch))
        with closing(sqlite3.connect(package.database)) as database:
            kinds = read_note_types(database)
            notes = [voice_note(row, kinds, studio, options) for row in note_rows(database)]
            store(database, [note for note in notes if note.clips])
        save_package(package, tuple(clip for note in notes for clip in note.clips), output)
    return report(notes, kinds)


def reject_same_file(source: Path, output: Path) -> None:
    if output.exists() and output.samefile(source):
        raise PackageError("the output must be a different file from the input package")


def note_rows(database: sqlite3.Connection) -> list[tuple[int, int, int, str]]:
    return database.execute("select id, mid, mod, flds from notes order by id").fetchall()


def voice_note(row: tuple[int, int, int, str], kinds: dict[int, NoteType], studio: Studio, options: VoiceOptions) -> VoicedNote:
    note_id, kind_id, modified, joined = row
    contents = joined.split(FIELD_SEPARATOR)
    kind = kinds.get(kind_id)
    roles = field_roles(kind) if kind else [UNKNOWN_NOTE_TYPE] * len(contents)
    fields = tuple(voice_field(content, role, studio, options) for content, role in zip(contents, padded(roles, contents)))
    return VoicedNote(note_id, modified, kind.sort_index if kind else 0, fields)


def padded(roles: tuple[str | None, ...] | list[str], contents: list[str]) -> list[str | None]:
    return [*roles, *[None] * len(contents)][: len(contents)]


def voice_field(content: str, role: str | None, studio: Studio, options: VoiceOptions) -> VoicedField:
    verdict = field_speech(content, options)
    if verdict == EMPTY or isinstance(role, str):
        return VoicedField(content, skipped=EMPTY if verdict == EMPTY else role)
    if isinstance(verdict, str):
        return VoicedField(content, skipped=verdict)
    try:
        clip = render_clip(verdict, studio)
    except SpeechError as error:
        return VoicedField(content, skipped=str(error))
    return VoicedField(f"{content}[sound:{clip.name}]", clip=clip)


def field_speech(content: str, options: VoiceOptions) -> Speech | str:
    text = spoken_text(content)
    if has_sound(content):
        return ALREADY_HAS_SOUND
    if not text:
        return EMPTY
    if has_formula(content):
        return HAS_FORMULA
    if len(text) > options.max_chars:
        return TOO_LONG
    if has_unvoiced_script(text):
        return UNVOICED_SCRIPT
    speech = Speech(detect_language(text, options.default_lang), (Say(text),))
    return voiced_by_script(speech, options.default_lang)


def store(database: sqlite3.Connection, notes: list[VoicedNote]) -> None:
    now = int(time.time())
    database.executemany(
        "update notes set flds = ?, sfld = ?, csum = ?, mod = ?, usn = -1 where id = ?",
        [stored_row(note, now) for note in notes],
    )
    database.commit()


def stored_row(note: VoicedNote, now: int) -> tuple[str, str, int, int, int]:
    contents = [field.content for field in note.fields]
    sort_field = contents[min(note.sort_index, len(contents) - 1)]
    return (
        FIELD_SEPARATOR.join(contents),
        sort_text(sort_field),
        field_checksum(contents[0]),
        max(now, note.modified + 1),
        note.note_id,
    )


def report(notes: list[VoicedNote], kinds: dict[int, NoteType]) -> VoiceReport:
    fields = [field for note in notes for field in note.fields]
    reasons = Counter(field.skipped for field in fields if field.skipped and field.skipped != EMPTY)
    return VoiceReport(
        notes=len(notes),
        changed_notes=sum(1 for note in notes if note.clips),
        voiced_fields=sum(1 for field in fields if field.clip),
        skipped=tuple(reasons.most_common()),
        replayed=tuple(kind.name for kind in kinds.values() if replayed_fields(kind)),
    )


def format_voice_report(report: VoiceReport, output: Path) -> str:
    headline = (
        f"Voiced {report.voiced_fields} fields in {report.changed_notes} of {report.notes} notes into {output}."
    )
    skipped = [f"  {count} × {reason}" for reason, count in report.skipped]
    replayed = [f"  {name}" for name in report.replayed]
    return "\n".join(
        [
            headline,
            *(["", "Fields left as they were:", *skipped] if skipped else []),
            *(["", "Question audio will play again on the answer side for these note types,", "because their answer template repeats the field instead of using {{FrontSide}}:", *replayed] if replayed else []),
        ]
    )
