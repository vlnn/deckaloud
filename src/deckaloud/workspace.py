from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DIRECTORY_VARIABLE = "DECKS_DIR"
DEFAULT_DIRECTORY = "decks"
RESERVED_FOLDERS = frozenset({"toanki", "inbox", "originals"})
PACKAGE_PATTERN = "*.apkg"


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def toanki(self) -> Path:
        return self.root / "toanki"

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def originals(self) -> Path:
        return self.root / "originals"

    @property
    def audio_cache(self) -> Path:
        return self.toanki / "audio"

    @property
    def ledger_file(self) -> Path:
        return self.toanki / "state.json"

    @property
    def log_file(self) -> Path:
        return self.toanki / "decks.log"

    @property
    def lock_file(self) -> Path:
        return self.toanki / "decks.lock"

    @property
    def config_file(self) -> Path:
        return self.root / "deckaloud.toml"

    @property
    def quick_deck(self) -> Path:
        return self.root / "test.txt"

    def name(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def sources(self) -> tuple[Path, ...]:
        return tuple(sorted(path for path in self.root.rglob("*.txt") if self.holds_source(path)))

    def holds_source(self, path: Path) -> bool:
        folders = path.relative_to(self.root).parts[:-1]
        return folders[:1] not in ((name,) for name in RESERVED_FOLDERS) and not any(
            folder.startswith(".") for folder in folders
        )

    def dropped(self) -> tuple[Path, ...]:
        return tuple(sorted(self.inbox.glob(PACKAGE_PATTERN)))

    def kept(self) -> tuple[Path, ...]:
        return tuple(sorted(self.originals.glob(PACKAGE_PATTERN)))

    def package_for(self, name: str) -> Path:
        return (self.toanki / name).with_suffix(".apkg")


def workspace_root(explicit: Path | None, environ: Mapping[str, str]) -> Path:
    home = Path(environ.get("HOME", "~"))
    if explicit is not None:
        return explicit
    configured = environ.get(DIRECTORY_VARIABLE)
    return within_home(configured, home) if configured else home / DEFAULT_DIRECTORY


def within_home(directory: str, home: Path) -> Path:
    return home / directory[2:] if directory.startswith("~/") else Path(directory)
