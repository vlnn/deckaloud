import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    digest: str
    imported: bool
    guids: tuple[str, ...] = ()
    removed: bool = False
    deck: str = ""
    anki_guids: tuple[str, ...] = ()


Ledger = dict[str, Entry]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_ledger(path: Path) -> Ledger:
    if not path.exists():
        return {}
    decks = json.loads(path.read_text(encoding="utf-8"))["decks"]
    return {name: entry(fields) for name, fields in decks.items()}


def entry(fields: dict) -> Entry:
    listed = {key: tuple(fields.get(key, ())) for key in ("guids", "anki_guids")}
    return Entry(**{**fields, **listed})


def write_ledger(path: Path, ledger: Ledger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    decks = {name: asdict(entry) for name, entry in sorted(ledger.items())}
    path.write_text(json.dumps({"decks": decks}, indent=2), encoding="utf-8")
