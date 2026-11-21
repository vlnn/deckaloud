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


Ledger = dict[str, Entry]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_ledger(path: Path) -> Ledger:
    if not path.exists():
        return {}
    decks = json.loads(path.read_text(encoding="utf-8"))["decks"]
    return {name: Entry(**{**fields, "guids": tuple(fields["guids"])}) for name, fields in decks.items()}


def write_ledger(path: Path, ledger: Ledger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    decks = {name: asdict(entry) for name, entry in sorted(ledger.items())}
    path.write_text(json.dumps({"decks": decks}, indent=2), encoding="utf-8")
