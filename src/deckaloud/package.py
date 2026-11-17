import hashlib
import html
from collections.abc import Mapping
from pathlib import Path

import genanki

from deckaloud.config import MAX_LANGUAGES, Config, Language
from deckaloud.speech import plain_text
from deckaloud.voicing import VoicedCard, VoicedSide

MODEL_VERSION = "2"
SPEECH_SLOTS = range(1, MAX_LANGUAGES + 1)
FIELD_NAMES = (
    "Front",
    "Back",
    "FrontAudio",
    "BackAudio",
    *(f"{side}Speech{slot}" for slot in SPEECH_SLOTS for side in ("Front", "Back")),
)
STYLE = ".card { font-family: -apple-system, sans-serif; font-size: 22px; text-align: center; }"


def write_package(voiced: tuple[VoicedCard, ...], config: Config, output: Path) -> None:
    package = genanki.Package(decks(voiced, config))
    package.media_files = media_files(voiced)
    package.write_to_file(str(output))


def decks(voiced: tuple[VoicedCard, ...], config: Config) -> list[genanki.Deck]:
    model = listening_model(config.languages)
    by_name = {name: genanki.Deck(stable_id("deck", name), name) for name in deck_names(voiced)}
    for item in voiced:
        by_name[item.card.deck].add_note(note(item, model, config))
    return list(by_name.values())


def deck_names(voiced: tuple[VoicedCard, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.card.deck for item in voiced))


def media_files(voiced: tuple[VoicedCard, ...]) -> list[str]:
    clips = (side.clip for item in voiced for side in (item.front, item.back) if side.clip)
    return [str(clip) for clip in dict.fromkeys(clips)]


def stable_id(*parts: str) -> int:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return (1 << 30) + int(digest[:8], 16) % (1 << 30)


def listening_model(languages: Mapping[str, Language]) -> genanki.Model:
    return genanki.Model(
        stable_id("model", MODEL_VERSION),
        "deckaloud listening",
        fields=[{"name": name} for name in FIELD_NAMES],
        templates=[
            {"name": "Listen", "qfmt": front_template(languages), "afmt": back_template(languages)}
        ],
        css=STYLE,
    )


def front_template(languages: Mapping[str, Language]) -> str:
    return "<div>{{Front}}</div>{{FrontAudio}}" + runtime_speech("Front", languages)


def back_template(languages: Mapping[str, Language]) -> str:
    shown = "<div>{{Front}}</div><hr id=answer><div>{{Back}}</div>"
    return shown + "{{BackAudio}}" + runtime_speech("Back", languages)


def runtime_speech(side: str, languages: Mapping[str, Language]) -> str:
    return "".join(
        f"{{{{#{side}Speech{slot}}}}}{{{{tts {language.locale}:{side}Speech{slot}}}}}{{{{/{side}Speech{slot}}}}}"
        for slot, language in zip(SPEECH_SLOTS, languages.values())
    )


def note(item: VoicedCard, model: genanki.Model, config: Config) -> genanki.Note:
    return genanki.Note(model=model, fields=note_fields(item, config), guid=item.card.guid, tags=[item.card.guid])


def note_fields(item: VoicedCard, config: Config) -> list[str]:
    sides = (item.front, item.back)
    return [
        *(html.escape(side.side.text, quote=False) for side in sides),
        *(sound_tag(side) for side in sides),
        *(runtime_text(side, code, config) for code in slot_languages(config) for side in sides),
    ]


def slot_languages(config: Config) -> list[str | None]:
    codes = list(config.languages)
    return [*codes, *[None] * (MAX_LANGUAGES - len(codes))]


def sound_tag(side: VoicedSide) -> str:
    return f"[sound:{side.clip.name}]" if side.clip else ""


def runtime_text(side: VoicedSide, code: str | None, config: Config) -> str:
    speech = side.side.speech
    if side.clip or code is None or speech.lang != code:
        return ""
    return html.escape(plain_text(speech, config.languages[code].gap_word), quote=False)
