from dataclasses import dataclass
from pathlib import Path

from deckaloud.cards import Card, Side
from deckaloud.errors import SpeechError
from deckaloud.render import Studio, render_clip


@dataclass(frozen=True)
class VoicedSide:
    side: Side
    clip: Path | None
    problem: str | None


@dataclass(frozen=True)
class VoicedCard:
    card: Card
    front: VoicedSide
    back: VoicedSide


def voice_cards(cards: tuple[Card, ...], studio: Studio) -> tuple[VoicedCard, ...]:
    return tuple(
        VoicedCard(card, voice_side(card.front, studio), voice_side(card.back, studio)) for card in cards
    )


def voice_side(side: Side, studio: Studio) -> VoicedSide:
    try:
        return VoicedSide(side, render_clip(side.speech, studio), None)
    except SpeechError as error:
        return VoicedSide(side, None, str(error))
