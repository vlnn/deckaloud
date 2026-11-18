import argparse
import sqlite3
import sys
from pathlib import Path

from deckaloud.cards import Card, cards_from_source
from deckaloud.check import problems
from deckaloud.config import Config, load_config
from deckaloud.engines import encode_m4a, engine_named
from deckaloud.errors import DeckaloudError
from deckaloud.package import write_package
from deckaloud.render import Studio
from deckaloud.report import format_report, read_manifest, removed_guids, write_manifest
from deckaloud.sample import (
    audition_voices,
    render_samples,
    sample_jobs,
    sampled_sides,
    silent_languages,
)
from deckaloud.source import SourceFile, parse_source
from deckaloud.stamp import stamp_file
from deckaloud.voiceover import VoiceOptions, format_voice_report, voice_package
from deckaloud.voicing import voice_cards

STATE_DIR = Path(".deckaloud")
DEFAULT_CONFIG = Path("deckaloud.toml")
COMBINED_OUTPUT = Path("deckaloud.apkg")
DEFAULT_SAMPLES = Path("samples")
VOICE_SETTINGS = "System Settings → Accessibility → Spoken Content → System Voice → Manage Voices"


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.run(args)
    except (DeckaloudError, OSError, sqlite3.Error) as error:
        return failure([str(error)])


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="deckaloud", description="Sound-first Anki deck generator")
    commands = root.add_subparsers(required=True)
    add_build(commands)
    add_sample(commands)
    add_voice(commands)
    add_command(commands, "stamp", run_stamp, "write missing card ids into the source files")
    add_command(commands, "check", run_check, "validate source files without rendering audio")
    return root


def add_command(commands, name: str, run, summary: str) -> argparse.ArgumentParser:
    command = commands.add_parser(name, help=summary)
    command.add_argument("files", nargs="+", type=Path)
    command.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    command.set_defaults(run=run)
    return command


def add_build(commands) -> None:
    command = add_command(commands, "build", run_build, "render audio and write the .apkg")
    command.add_argument(
        "-o", "--output", type=Path, help=f"default: <file>.apkg for one file, {COMBINED_OUTPUT} for several"
    )
    command.add_argument("--stamp", action="store_true", help="write missing ids into the sources first")


def add_sample(commands) -> None:
    command = add_command(commands, "sample", run_sample, "render a few cards in every installed voice")
    command.add_argument("-o", "--output", type=Path, default=DEFAULT_SAMPLES)
    command.add_argument("-n", "--count", type=int, default=3, help="cards to sample per language, both sides of each")
    command.add_argument("--all-voices", action="store_true", help="include effect and synthetic voices")


def add_voice(commands) -> None:
    command = commands.add_parser("voice", help="add spoken audio to an existing .apkg")
    command.add_argument("package", type=Path)
    command.add_argument("-o", "--output", type=Path, help="default: <package>-voiced.apkg")
    command.add_argument("--lang", default="en", help="language of text whose script does not decide it")
    command.add_argument("--max-chars", type=int, default=600, help="skip fields longer than this")
    command.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    command.set_defaults(run=run_voice)


def run_voice(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output = args.output or args.package.with_name(f"{args.package.stem}-voiced.apkg")
    options = VoiceOptions(default_lang=args.lang, max_chars=args.max_chars)
    print(format_voice_report(voice_package(args.package, output, studio(config), options), output))
    return 0


def run_build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.stamp:
        stamp_files(args.files)
    sources = read_sources(args.files)
    found = problems(sources, config)
    if found:
        return failure(found)
    cards = all_cards(sources, config)
    if not cards:
        return failure(["no cards found in the given files"])
    output = args.output or default_output(args.files)
    voiced = voice_cards(cards, studio(config))
    write_package(voiced, config, output)
    print(format_report(voiced, output, forgotten_guids(output, voiced)))
    return 0


def default_output(files: list[Path]) -> Path:
    return files[0].with_suffix(".apkg") if len(files) == 1 else COMBINED_OUTPUT


def run_sample(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    booth = studio(config)
    sides = sampled_sides(all_cards(read_sources(args.files), config), args.count)
    voices = audition_voices(booth.engine.voices(), args.all_voices)
    written, failed = render_samples(sample_jobs(sides, voices, config), booth, args.output)
    print(f"{len(written)} samples written under {args.output}")
    for lang in silent_languages(sides, voices, config):
        print(f"no installed voice speaks '{lang}'; download one in {VOICE_SETTINGS}")
    return failure(failed) if failed else 0


def run_stamp(args: argparse.Namespace) -> int:
    stamp_files(args.files)
    return 0


def run_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = read_sources(args.files)
    found = problems(sources, config)
    if found:
        return failure(found)
    print(f"{len(all_cards(sources, config))} cards in {len(sources)} files, no problems")
    return 0


def stamp_files(paths: list[Path]) -> None:
    for path in paths:
        added = stamp_file(path)
        print(f"{path}: {added} id{'' if added == 1 else 's'} added")


def read_sources(paths: list[Path]) -> tuple[SourceFile, ...]:
    return tuple(parse_source(path.read_text(encoding="utf-8-sig"), path) for path in paths)


def all_cards(sources: tuple[SourceFile, ...], config: Config) -> tuple[Card, ...]:
    return tuple(card for source in sources for card in cards_from_source(source, config))


def studio(config: Config) -> Studio:
    return Studio(engine_named(config.engine), encode_m4a, config, STATE_DIR / "audio")


def forgotten_guids(output: Path, voiced) -> tuple[str, ...]:
    manifest = STATE_DIR / f"{output.name}.manifest.json"
    current = [item.card.guid for item in voiced]
    removed = removed_guids(read_manifest(manifest), current)
    write_manifest(manifest, current)
    return removed


def failure(messages) -> int:
    for message in messages:
        print(f"error: {message}", file=sys.stderr)
    return 1
