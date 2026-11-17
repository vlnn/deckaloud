"""Import a package into a throwaway Anki collection twice and print what Anki made of it.

usage: uv run --with anki python scripts/verify_import.py [--merge] FIRST.apkg [SECOND.apkg]

--merge ticks Anki's "Merge note types" import option.
"""

import sys
import tempfile
from pathlib import Path

from anki.collection import (
    Collection,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)

MERGE = "--merge" in sys.argv


def import_package(collection: Collection, package: Path) -> None:
    options = ImportAnkiPackageOptions(merge_notetypes=MERGE)
    request = ImportAnkiPackageRequest(package_path=str(package), options=options)
    collection.import_anki_package(request)


def describe(collection: Collection) -> None:
    for card_id in collection.find_cards(""):
        card = collection.get_card(card_id)
        note = card.note()
        deck = collection.decks.name(card.did)
        print(f"card {card_id} due={card.due} ivl={card.ivl} deck={deck} guid={note.guid}")
        print(f"   question html: {card.question()!r}")
        print(f"   answer html:   {card.answer()!r}")
        print(f"   question audio: {card.question_av_tags()}")
        print(f"   answer audio:   {card.answer_av_tags()}")


def age_every_card(collection: Collection) -> None:
    collection.db.execute("update cards set ivl = 42, type = 2, queue = 2")


def main(packages: list[Path]) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        collection = Collection(str(Path(scratch) / "collection.anki2"))
        import_package(collection, packages[0])
        print(f"== after importing {packages[0].name}: {collection.card_count()} cards")
        describe(collection)
        for package in packages[1:]:
            age_every_card(collection)
            import_package(collection, package)
            print(f"== after re-importing {package.name}: {collection.card_count()} cards")
            describe(collection)
        collection.close()


main([Path(argument) for argument in sys.argv[1:] if argument != "--merge"])
