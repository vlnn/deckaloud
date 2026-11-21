import argparse
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from deckaloud.ankiconnect import (
    Anki,
    AnkiConnect,
    launch_anki,
    running_anki,
    short_nap,
)
from deckaloud.building import Outcome, build_workspace, outcome_lines, summary
from deckaloud.cards import Card, cards_from_source
from deckaloud.check import problems
from deckaloud.config import Config, load_config
from deckaloud.engines import encode_m4a, engine_named
from deckaloud.errors import DeckaloudError
from deckaloud.gitstate import files_with_uncommitted_ids
from deckaloud.ledger import Ledger, read_ledger, write_ledger
from deckaloud.lockfile import exclusive
from deckaloud.overview import overview_lines
from deckaloud.package import write_package
from deckaloud.quickadd import add_cards, new_card_count
from deckaloud.render import Studio
from deckaloud.report import format_report, read_manifest, removed_guids, write_manifest
from deckaloud.sample import (
    audition_voices,
    render_samples,
    sample_jobs,
    sampled_sides,
    silent_languages,
)
from deckaloud.source import SourceFile, parse_source, read_source_text
from deckaloud.stamp import stamp_file
from deckaloud.syncing import Synced, sync_workspace
from deckaloud.voiceover import VoiceOptions, format_voice_report, voice_package
from deckaloud.voicing import voice_cards
from deckaloud.workspace import Workspace, workspace_root

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
    add_directory_command(commands, "rebuild", run_rebuild, "rebuild every deck in the decks directory, audio included")
    add_directory_command(commands, "status", run_status, "show what the decks directory still needs")
    add_sync(commands)
    add_quick_add(commands)
    add_command(commands, "stamp", run_stamp, "write missing card ids into the source files")
    add_command(commands, "check", run_check, "validate source files without rendering audio")
    return root


def add_command(commands, name: str, run, summary: str) -> argparse.ArgumentParser:
    command = commands.add_parser(name, help=summary)
    command.add_argument("files", nargs="+", type=Path)
    command.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    command.set_defaults(run=run)
    return command


def add_directory_command(commands, name: str, run, summary: str) -> argparse.ArgumentParser:
    command = commands.add_parser(name, help=summary)
    command.add_argument("--dir", type=Path, help="decks directory; default: $DECKS_DIR, then ~/decks")
    command.set_defaults(run=run)
    return command


def add_build(commands) -> None:
    summary = "render audio and write the .apkg; without files, build what changed in the decks directory"
    command = add_directory_command(commands, "build", run_build, summary)
    command.add_argument("files", nargs="*", type=Path)
    command.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    command.add_argument(
        "-o", "--output", type=Path, help=f"default: <file>.apkg for one file, {COMBINED_OUTPUT} for several"
    )
    command.add_argument("--stamp", action="store_true", help="accepted for compatibility; ids are written by default")
    command.add_argument("--no-stamp", action="store_true", help="fail on cards without ids instead of writing them")


def add_sync(commands) -> None:
    command = add_directory_command(commands, "sync", run_sync, "build what changed, then bring Anki up to date")
    command.add_argument("--force", action="store_true", help="let a deck lose more than a fifth of its cards")


def add_quick_add(commands) -> None:
    command = add_directory_command(commands, "add", run_add, "append cards to test.txt in the decks directory")
    command.add_argument("text", nargs="+", help="a cloze sentence, or Q: and A: lines")


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
    return build_files(args) if args.files else build_directory(args, fresh=False)


def run_rebuild(args: argparse.Namespace) -> int:
    return build_directory(args, fresh=True)


def build_directory(args: argparse.Namespace, fresh: bool) -> int:
    workspace = chosen_workspace(args)
    with exclusive(workspace.lock_file):
        _, outcomes = built_ledger(workspace, fresh)
    return reported(workspace, outcomes, summary(outcomes))


def built_ledger(workspace: Workspace, fresh: bool) -> tuple[Ledger, tuple[Outcome, ...]]:
    booth = studio(load_config(workspace.config_file), workspace.audio_cache)
    ledger, outcomes = build_workspace(workspace, booth, read_ledger(workspace.ledger_file), fresh)
    write_ledger(workspace.ledger_file, ledger)
    return ledger, outcomes


def reported(workspace: Workspace, outcomes: tuple[Outcome, ...], last_line: str) -> int:
    lines = [*outcome_lines(outcomes), *uncommitted_ids_note(workspace), last_line]
    keep_log(workspace, lines)
    print("\n".join(lines))
    return 1 if failures(outcomes) else 0


def failures(outcomes: tuple[Outcome, ...]) -> frozenset[str]:
    return frozenset(outcome.name for outcome in outcomes if outcome.state == "failed")


def run_sync(args: argparse.Namespace) -> int:
    workspace = chosen_workspace(args)
    with exclusive(workspace.lock_file):
        ledger, built = built_ledger(workspace, fresh=False)
        uncommitted = frozenset(files_with_uncommitted_ids(workspace.root))
        synced = sync_workspace(workspace, connected_anki(), ledger, failures(built), uncommitted, args.force)
        write_ledger(workspace.ledger_file, synced.ledger)
    return reported(workspace, (*built, *synced.outcomes), sync_summary(built, synced))


def sync_summary(built: tuple[Outcome, ...], synced: Synced) -> str:
    counts = Counter(outcome.state for outcome in (*built, *synced.outcomes))
    return f"built {counts['built']}, imported {counts['imported']}, removed {synced.deleted}, failed {counts['failed']}"


def connected_anki() -> Anki:
    return running_anki(AnkiConnect(), launch_anki, short_nap)


def run_status(args: argparse.Namespace) -> int:
    workspace = chosen_workspace(args)
    lines = overview_lines(workspace, read_ledger(workspace.ledger_file))
    print("\n".join([*lines[:-1], *uncommitted_ids_note(workspace), lines[-1]]))
    return 0


def run_add(args: argparse.Namespace) -> int:
    workspace = chosen_workspace(args)
    with exclusive(workspace.lock_file):
        added = add_cards(workspace.quick_deck, " ".join(args.text), load_config(workspace.config_file))
    waiting = new_card_count(workspace.quick_deck)
    print(f"added {counted(added, 'card')}; {workspace.quick_deck.name} has {counted(waiting, 'new card')}")
    return 0


def chosen_workspace(args: argparse.Namespace) -> Workspace:
    root = workspace_root(args.dir, os.environ)
    if not root.is_dir():
        raise DeckaloudError(f"decks directory not found: {root}")
    return Workspace(root)


def uncommitted_ids_note(workspace: Workspace) -> list[str]:
    files = files_with_uncommitted_ids(workspace.root)
    return [f"ids not committed yet in: {', '.join(files)}"] if files else []


def keep_log(workspace: Workspace, lines: list[str]) -> None:
    started = datetime.now().isoformat(sep=" ", timespec="seconds")
    workspace.log_file.write_text("\n".join([started, *lines, ""]), encoding="utf-8")


def counted(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def build_files(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if not args.no_stamp:
        stamp_files(args.files, quiet=True)
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


def stamp_files(paths: list[Path], quiet: bool = False) -> None:
    for path in paths:
        added = stamp_file(path)
        if added or not quiet:
            print(f"{path}: {counted(added, 'id')} added")


def read_sources(paths: list[Path]) -> tuple[SourceFile, ...]:
    return tuple(parse_source(read_source_text(path), path) for path in paths)


def all_cards(sources: tuple[SourceFile, ...], config: Config) -> tuple[Card, ...]:
    return tuple(card for source in sources for card in cards_from_source(source, config))


def studio(config: Config, cache: Path = STATE_DIR / "audio") -> Studio:
    return Studio(engine_named(config.engine), encode_m4a, config, cache)


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
