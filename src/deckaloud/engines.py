import re
import subprocess
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Protocol

from deckaloud.audio import SAMPLE_RATE
from deckaloud.errors import ConfigError, SpeechError

VOICE_LINE = re.compile(r"^(.+?)\s+([a-z]{2,3}_[A-Za-z0-9]+)\s+#")
BEST_FIRST = ("(Premium)", "(Enhanced)")
TOOL_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class Voice:
    name: str
    locale: str


class Engine(Protocol):
    def synthesize(self, text: str, voice: str, rate: int, target: Path) -> None: ...

    def voices(self) -> tuple[Voice, ...]: ...


class SayEngine:
    def synthesize(self, text: str, voice: str, rate: int, target: Path) -> None:
        command = [
            "say",
            "-v",
            voice,
            "-r",
            str(rate),
            "-o",
            str(target),
            "--file-format=WAVE",
            f"--data-format=LEI16@{SAMPLE_RATE}",
        ]
        run_tool(command, stdin=text)

    def voices(self) -> tuple[Voice, ...]:
        return self.installed

    @cached_property
    def installed(self) -> tuple[Voice, ...]:
        return parse_voices(run_tool(["say", "-v", "?"]))


ENGINES = {"say": SayEngine}


def engine_named(name: str) -> Engine:
    if name not in ENGINES:
        raise ConfigError(f"engine '{name}' is not supported yet; available: {', '.join(ENGINES)}")
    return ENGINES[name]()


def encode_m4a(wav: Path, target: Path) -> None:
    run_tool(["afconvert", "-f", "m4af", "-d", "aac", str(wav), str(target)])


def run_tool(command: list[str], stdin: str | None = None) -> str:
    try:
        completed = subprocess.run(
            command, input=stdin, capture_output=True, text=True, check=True, timeout=TOOL_TIMEOUT_SECONDS
        )
    except FileNotFoundError:
        raise SpeechError(f"'{command[0]}' is not available on this machine") from None
    except subprocess.TimeoutExpired:
        raise SpeechError(f"'{command[0]}' did not finish within {TOOL_TIMEOUT_SECONDS} seconds") from None
    except subprocess.CalledProcessError as error:
        raise SpeechError(f"'{command[0]}' failed: {(error.stderr or '').strip()}") from None
    return completed.stdout


def parse_voices(listing: str) -> tuple[Voice, ...]:
    matches = (VOICE_LINE.match(line) for line in listing.splitlines())
    return tuple(Voice(match.group(1).strip(), match.group(2)) for match in matches if match)


def resolve_voice(wanted: str, locale: str, installed: tuple[Voice, ...]) -> str:
    variants = [voice for voice in installed if is_variant(voice.name, wanted)]
    if not variants:
        raise SpeechError(f"voice '{wanted}' is not installed; \"say -v '?'\" lists the installed voices")
    return min(variants, key=lambda voice: preference(voice, wanted, locale)).name


def is_variant(name: str, wanted: str) -> bool:
    return name == wanted or name.startswith(f"{wanted} (")


def preference(voice: Voice, wanted: str, locale: str) -> tuple[int, bool, bool]:
    return (quality_rank(voice.name), voice.locale != locale, voice.name != wanted)


def quality_rank(name: str) -> int:
    return next((rank for rank, mark in enumerate(BEST_FIRST) if name.endswith(mark)), len(BEST_FIRST))
