import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

from deckaloud.ankiconnect import AnkiError

FIELD_SEPARATOR = "\x1f"
TAG_PREFIX = "deckaloud-"


def package_rows(package):
    with zipfile.ZipFile(package) as archive, closing(sqlite3.connect(":memory:")) as database:
        database.deserialize(archive.read("collection.anki2"))
        decks = {int(deck_id): deck["name"] for deck_id, deck in json.loads(database.execute("select decks from col").fetchone()[0]).items()}
        rows = database.execute("select n.guid, n.flds, min(c.did) from notes n join cards c on c.nid = n.id group by n.id")
        return [(guid, fields.split(FIELD_SEPARATOR), decks[deck_id]) for guid, fields, deck_id in rows]


class FakeAnki:
    def __init__(self, updates_existing=True):
        self.updates_existing = updates_existing
        self.notes = {}
        self.decks = set()
        self.calls = []
        self.media = {}
        self.next_id = 1
        self.broken_packages = set()

    def invoke(self, action, **params):
        self.calls.append(action)
        return getattr(self, action)(**params)

    def called(self, action):
        return self.calls.count(action)

    def guids(self):
        return {note["guid"] for note in self.notes.values()}

    def note(self, guid):
        return next(note for note in self.notes.values() if note["guid"] == guid)

    def add(self, guid, fields, deck):
        self.notes[self.next_id] = {"guid": guid, "fields": list(fields), "deck": deck}
        self.decks.add(deck)
        self.next_id += 1

    def version(self):
        return 6

    def importPackage(self, path):
        if Path(path).name in self.broken_packages:
            raise AnkiError("importPackage: could not read the package")
        for guid, fields, deck in package_rows(path):
            if guid not in self.guids():
                self.add(guid, fields, deck)
            elif self.updates_existing:
                self.note(guid)["fields"] = list(fields)
        return True

    def findNotes(self, query):
        assert query == f"tag:{TAG_PREFIX}*", f"unexpected note search: {query}"
        return list(self.notes)

    def notesInfo(self, notes):
        return [self.info(note_id) for note_id in notes]

    def info(self, note_id):
        note = self.notes[note_id]
        fields = {f"Field{order}": {"value": value, "order": order} for order, value in enumerate(note["fields"])}
        return {"noteId": note_id, "tags": [note["guid"]], "fields": fields, "modelName": "Listening", "cards": [note_id]}

    def updateNoteFields(self, note):
        stored = self.notes[note["id"]]["fields"]
        for name, value in note["fields"].items():
            stored[int(name.removeprefix("Field"))] = value

    def changeDeck(self, cards, deck):
        self.decks.add(deck)
        for card in cards:
            self.notes[card]["deck"] = deck

    def deleteNotes(self, notes):
        for note_id in notes:
            del self.notes[note_id]

    def findCards(self, query):
        deck = query.removeprefix('"deck:').removesuffix('"')
        return [note_id for note_id, note in self.notes.items() if note["deck"] == deck or note["deck"].startswith(f"{deck}::")]

    def deleteDecks(self, decks, cardsToo):
        assert cardsToo, "Anki refuses to delete a deck without its cards"
        self.decks -= set(decks)

    def storeMediaFile(self, filename, path):
        self.media[filename] = path

    def sync(self):
        return None
