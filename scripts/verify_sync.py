"""Run the sync logic against a throwaway Anki collection, through an adapter that mirrors AnkiConnect's own code.

usage: PYTHONPATH=tests uv run --with anki python scripts/verify_sync.py
"""
import sys
import tempfile
from pathlib import Path

from anki.collection import Collection
from anki.importing import AnkiPackageImporter
from conftest import FakeEngine, copy_as_encoding

from deckaloud.building import build_workspace
from deckaloud.config import Config
from deckaloud.render import Studio
from deckaloud.syncing import sync_workspace
from deckaloud.workspace import Workspace


class CollectionAnki:
    def __init__(self, collection):
        self.col = collection
        self.calls = []

    def invoke(self, action, **params):
        self.calls.append(action)
        return getattr(self, action)(**params)

    def importPackage(self, path):
        AnkiPackageImporter(self.col, path).run()
        return True

    def findNotes(self, query):
        return list(map(int, self.col.find_notes(query)))

    def findCards(self, query):
        return list(map(int, self.col.find_cards(query)))

    def notesInfo(self, notes):
        result = []
        for nid in notes:
            note = self.col.get_note(nid)
            model = note.note_type()
            fields = {info["name"]: {"value": note.fields[info["ord"]], "order": info["ord"]} for info in model["flds"]}
            cards = self.col.db.list("select id from cards where nid = ? order by ord", note.id)
            result.append({"noteId": note.id, "tags": note.tags, "fields": fields, "modelName": model["name"], "cards": cards})
        return result

    def updateNoteFields(self, note):
        anki_note = self.col.get_note(note["id"])
        for name, value in note["fields"].items():
            if name in anki_note:
                anki_note[name] = value
        self.col.update_note(anki_note)

    def changeDeck(self, cards, deck):
        did = self.col.decks.id(deck)
        self.col.set_deck(cards, did)

    def deleteNotes(self, notes):
        self.col.remove_notes(notes)

    def deleteDecks(self, decks, cardsToo):
        names = [d.name for d in self.col.decks.all_names_and_ids()]
        self.col.decks.remove([self.col.decks.id(deck) for deck in decks if deck in names])

    def storeMediaFile(self, filename, path):
        self.col.media.write_data(filename, Path(path).read_bytes())

    def sync(self):
        return None


def card(number, answer="Answer"):
    return f"\nid: g{number}\nQ: Question {number}?\nA: {answer} {number}.\n"


def deck(numbers, name="Geo", answer="Answer"):
    return f"deck: {name}\n" + "".join(card(number, answer) for number in numbers)


def snapshot(col):
    rows = col.db.all("select n.guid, n.flds, c.did, c.ivl from notes n join cards c on c.nid = n.id order by n.guid")
    return {guid: (flds.split("\x1f")[1], col.decks.name(did), ivl) for guid, flds, did, ivl in rows}


def expect(condition, message):
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        sys.exit(1)


with tempfile.TemporaryDirectory() as scratch:
    root = Path(scratch) / "decks"
    root.mkdir()
    workspace = Workspace(root)
    booth = Studio(FakeEngine(), copy_as_encoding, Config(), workspace.audio_cache)
    col = Collection(str(Path(scratch) / "collection.anki2"))
    anki = CollectionAnki(col)

    def sync(ledger, **options):
        built, outcomes = build_workspace(workspace, booth, ledger)
        failed = frozenset(o.name for o in outcomes if o.state == "failed")
        synced = sync_workspace(workspace, anki, built, blocked=failed, **options)
        print("     ", [(o.name, o.state, o.messages) for o in synced.outcomes], "deleted", synced.deleted)
        return synced.ledger

    (root / "geo.txt").write_text(deck(range(8)), encoding="utf-8")
    ledger = sync({})
    expect(len(snapshot(col)) == 8, "first sync imports 8 notes")
    expect(all(name == "Geo" for _, name, _ in snapshot(col).values()), "they land in deck Geo")

    col.db.execute("update cards set ivl = 42, type = 2, queue = 2")
    (root / "geo.txt").write_text(deck(range(8)).replace("Answer 3.", "A better answer."), encoding="utf-8")
    ledger = sync(ledger)
    expect(snapshot(col)["deckaloud-g3"][0] == "A better answer.", "a reworded card is updated in Anki")
    expect(snapshot(col)["deckaloud-g3"][2] == 42, "and keeps its schedule")
    print("      updateNoteFields calls so far:", anki.calls.count("updateNoteFields"))

    (root / "geo.txt").write_text(deck([0, 1, 2, 4, 5, 6]).replace("Answer 3.", "A better answer."), encoding="utf-8")
    (root / "net.txt").write_text(deck([7], name="Listening::Net stuff"), encoding="utf-8")
    ledger = sync(ledger)
    after = snapshot(col)
    expect("deckaloud-g3" not in after, "a card removed from its source is deleted")
    expect(after["deckaloud-g7"][1:] == ("Listening::Net stuff", 42), "a moved card changes deck and keeps its schedule")
    expect(len(after) == 7, "seven notes remain")

    (root / "net.txt").unlink()
    ledger = sync(ledger)
    names = [d.name for d in col.decks.all_names_and_ids()]
    expect("deckaloud-g7" not in snapshot(col), "deleting a source deletes its note")
    expect("Listening::Net stuff" not in names, "and its emptied deck")
    expect("net.txt" not in ledger, "and forgets the deck")

    (root / "geo.txt").write_text(deck(range(100)), encoding="utf-8")
    ledger = sync(ledger)
    (root / "geo.txt").write_text(deck(range(50)), encoding="utf-8")
    ledger = sync(ledger)
    expect(len(snapshot(col)) == 100, "a large deletion is held back by the guard")
    ledger = sync(ledger, force=True)
    expect(len(snapshot(col)) == 50, "and carried out with force")
    print("ALL CHECKS PASSED against anki", __import__("anki.buildinfo").buildinfo.version)
