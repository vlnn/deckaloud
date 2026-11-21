# deckaloud

Sound-first Anki decks. Text files in, one `.apkg` out, every card spoken, so a
deck can be reviewed by ear with a keyboard or remote.

macOS only: speech comes from `say`, encoding from `afconvert`. The output is an
`.apkg` you import yourself, or `decks sync` imports it for you through the
AnkiConnect add-on.

## Install

Needs macOS, Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install .        # or: uv run deckaloud ...
```

This installs two names for the same command, `deckaloud` and the shorter `decks`.
After pulling changes, refresh the installed copy with
`uv tool install --force --reinstall .`

## Source files

One file is one deck. Blocks are separated by blank lines.

```
deck: Listening::Networking
lang: en

id: 3f9a1c20
Q: What does the TCP three-way handshake establish?
A: Initial sequence numbers for both directions of the connection.

id: c41d09ee
C: TCP guarantees {{c1::ordered}} and {{c2::reliable}} delivery,
   while UDP guarantees {{c3::neither::how many of the two}}.
```

- The first block is the header: `deck:` (default: file name) and `lang:` (default `en`).
- `Q:` with `A:` is a question card. Front speaks the question, back speaks only the answer.
- `C:` is a cloze sentence in Anki's own syntax. Each deletion number becomes its
  own card; deletions sharing a number are hidden together. Front speaks the
  sentence with the gap, back speaks the deleted part, a pause, then the full sentence.
- A hint (`{{c1::Kyiv::city}}`) is spoken in place of the gap.
- Lines that do not start with a key continue the previous one.
- `lang:` inside a card block forces the voice for that card. Otherwise a side is
  read in the file's language when its script fits that language. A side in the
  other script falls back to English (Latin letters) or Ukrainian (Cyrillic), so
  an English term answering a Ukrainian question gets the English voice.
- A side that mixes scripts is spoken in stretches, each by the voice of its
  script: in `Січень: in English?` the first word goes to the Ukrainian voice
  and the rest to the English one. Numbers and punctuation stay with the stretch
  before them. A card-level `lang:` turns this off and reads the whole card in
  one voice.
- `id:` is the card's identity. Wording can change freely; the id keeps the
  schedule. Letters, digits and underscores only.

## Commands

```sh
deckaloud stamp  notes/*.txt                  # write missing ids into the files
deckaloud check  notes/*.txt                  # validate, render nothing
deckaloud sample notes/*.txt -n 3             # 3 cards per language, both sides, in every natural voice
deckaloud build  notes/networking.txt         # stamps, then writes notes/networking.apkg
deckaloud build  notes/*.txt -o listening.apkg
deckaloud build  --no-stamp notes/*.txt       # fail on cards without ids instead of writing them
deckaloud voice  mydeck.apkg                  # add sound to an existing deck
```

## A decks directory

Without file arguments, the commands work on a whole directory of decks: `--dir`,
else `$DECKS_DIR`, else `~/decks`.

```sh
decks build      # build what changed, voice what was dropped into inbox/
decks rebuild    # build everything again and regenerate all audio
decks status     # show what is new, changed, waiting for import or deleted
decks sync       # build if needed, then bring Anki up to date
decks add 'booo is {{c1::doo}}'    # append a card to test.txt
```

| Path | What it holds |
|---|---|
| `*.txt`, also in subfolders | deck sources |
| `test.txt` | the deck `add` appends to |
| `inbox/` | third-party `.apkg` files waiting to be voiced |
| `originals/` | those packages, unvoiced, moved here once voiced |
| `toanki/` | built and voiced packages, `state.json`, `decks.log`, the audio cache |
| `deckaloud.toml` | settings for this directory |

- `build` stamps every source, then rebuilds a deck only when its content hash
  differs from the one in `toanki/state.json` or its package is missing.
- A deck that fails its checks is skipped and reported; the others are still
  built, and the failed deck keeps its last good package. The exit status is 1.
- An id used in two decks fails the later one.
- A package in `inbox/` is voiced into `toanki/originals/` and its original moves
  to `originals/`. If voicing fails it stays in `inbox/`.
- Deleting a source deletes its package. Its note ids stay in `state.json`,
  marked for removal from Anki.
- `rebuild` ignores `state.json` and empties the audio cache first.
- `add` takes a cloze sentence, or `Q:` and `A:` lines, or several cards
  separated by blank lines. Text that is not a valid card is rejected and
  nothing is written.
- The last line of `build` and `rebuild` is a summary such as
  `built 2, unchanged 5, removed 0, failed 0`. The full report of the last run
  is in `toanki/decks.log`.
- When the directory is a git repository, files whose new `id:` lines are not
  committed are named, as a reminder to commit them.
- Only one command works on a directory at a time; a second one stops with
  `already running`.

### sync

`decks sync` needs the [AnkiConnect](https://ankiweb.net/shared/info/2055492159)
add-on. It starts Anki if it is not running, and then:

1. Builds what `build` would build. Decks that are already built are not built
   again.
2. Imports every package that is waiting.
3. Reads the deck's notes back from Anki and corrects any whose text differs
   from the package, because Anki's import does not always update a note that
   already exists. Cards are moved to the deck named in their source.
4. Deletes notes that are no longer in any source. A card moved to another
   source file keeps its note and its schedule.
5. Removes the notes of a deleted source, and its deck if that is now empty.
6. Starts Anki's own sync.

The sources are the truth: an edit made inside Anki is overwritten the next time
that deck changes.

Deletion is limited in four ways:

- Only notes that sync itself imported are ever deleted, and only notes tagged
  `deckaloud-…`. Packages from `originals/` are imported and never cleaned.
- A deck that would lose more than a fifth of its cards, and more than five, is
  left alone and reported as failed until you run `decks sync --force`.
- A deck whose new `id:` lines are not committed to git keeps its deleted cards
  in Anki until they are. `test.txt` is exempt.
- A deck that failed to build is neither imported nor cleaned.

The summary reads `built 1, imported 1, removed 2, failed 0`, where `removed`
counts deleted notes. Try it first on a spare Anki profile.

## Adding sound to a deck you already have

```sh
deckaloud voice mydeck.apkg                  # writes mydeck-voiced.apkg
deckaloud voice mydeck.apkg -o spoken.apkg --lang uk --max-chars 400
```

`voice` reads an existing package, appends a baked clip to every field it can
speak, and writes a new package. Nothing else changes: note types, cards,
scheduling and existing media are carried over as they are. Import the result
over the deck you study and the notes update in place, keeping their schedule.

Export the deck from Anki with **Support older Anki versions** ticked. Anki's
newer package format is refused with a message saying so.

A field is left exactly as it was, and counted in the report, when it:

- already has a sound tag, or is already spoken by a `{{tts}}` tag in the template;
- holds the cloze text, because audio there would give the answer away (other
  fields of a cloze note, such as Back Extra, are voiced);
- is not shown on any card, or sits behind a hint;
- contains a formula, is longer than `--max-chars` (default 600), or is written
  in a script no configured voice reads;
- could not be rendered (voice not installed, engine failure).

The voice is chosen per field the same way as for source files; `--lang` plays
the part of the file language. Running `voice` on its own output changes nothing.

The audio sits in the fields, so it plays wherever the field is shown. With
Anki's stock note types the question clip plays on the front and only the
answer clip on the back. A note type whose answer template repeats the question
field, instead of using `{{FrontSide}}`, will play the question clip again
there; the report names those note types.

`build` writes an `id:` line into the source for every card that has none, and
never changes an id that is already there: the id is what ties a card to its
review history, so one that changed later would turn a reviewed card into a new
one. With `--no-stamp` it leaves your files alone and refuses cards without an id.

Without `-o`, a single source file is built into a package of the same name
beside it: `notes/networking.txt` becomes `notes/networking.apkg`. Several files
go into one `deckaloud.apkg` in the directory you run from.

Rendered clips are cached in `.deckaloud/audio`, so a rebuild only speaks what changed.

### The build report

- **Runtime speech**: a side that could not be baked (voice not installed, engine
  failure) is left for the phone's own voice through a `{{tts}}` tag, and listed
  with the reason.
- **No longer in the sources**: importing never deletes. Cards that were in the
  previous build and are gone now are listed as `tag:deckaloud-…` searches; paste
  one into Anki's browser and delete what it finds.

## Settings

`deckaloud.toml` in the directory you run from. Everything is optional.

```toml
engine = "say"

[gap]
style = "blank"            # or "tone"

[pauses]
cloze_answer = 0.6         # seconds between the deleted part and the full sentence
lead_in = 0.25             # silence before every clip
tail = 0.5                 # silence after every clip

[tone]
frequency = 880
duration = 0.25
padding = 0.15

[languages.en]
voice = "Samantha"
locale = "en_US"
rate = 175                 # words per minute
gap_word = "blank"

[languages.uk]
voice = "Lesya"
locale = "uk_UA"
rate = 165
gap_word = "пропуск"
```

`lead_in` and `tail` exist because mpv, which Anki's desktop app plays audio
with, can drop the start or end of short clips, and Bluetooth headphones do the
same while waking up. The silence gets cut instead of the speech. Raise them if
words still go missing; changing them re-renders every clip.

With `style = "tone"` the sentence is spoken in pieces around the tone, so the
intonation is choppier than with the spoken gap word.

## Voices

The voices macOS ships with are the compact ones. The Enhanced and Premium
versions are free downloads and sound much better: System Settings →
Accessibility → Spoken Content → System Voice → Manage Voices. Ukrainian has
`Lesya` and `Lesya (Enhanced)`. `say -v '?'` lists what is installed.

A bare name in the settings picks the best installed variant of that voice:
`voice = "Ava"` uses `Ava (Premium)` if it is there, then `Ava (Enhanced)`, then
the plain one. Write the full listed name to pin one variant. When a better
variant appears, the next build re-renders the affected clips.

`sample` leaves out the effect voices (Bells, Zarvox, …) and the robotic
screen-reader voices (Eddy, Fred, …); `--all-voices` brings them back. It tells
you when a language in your files has no installed voice at all.

## Updating a deck you already study

Rebuild and import the new `.apkg` over the old one. Notes are matched by id, so
edited cards keep their schedule and new cards are added. In Anki's import
dialog leave "Update notes" on "If newer".

Changing voices, pauses or the language list is safe between builds: the note
type keeps the same identity and fields whatever the settings are.

## Anki settings worth checking

These live in Anki, not in the deck file, and come from Anki's manual and forum
rather than from anything this project tests:

- Deck options → Audio: automatic playback on.
- Deck options → Audio: "Skip question when replaying answer" on.
- AnkiMobile is reported to follow the desktop review keys: Space shows the
  answer, 1–4 grade, R replays.
- AnkiMobile needs the screen on while reviewing.

## Known limitations

- macOS only. Other speech engines have a slot in the code (`engine = ...`) but
  none is implemented.
- At most six languages in the settings.
- Script detection knows two fallbacks, English and Ukrainian. For other
  languages set `lang:` in the file header or on the card.
- The voice changes only where the script changes, so an English word inside
  a German sentence stays with the German voice. Stretches are separate
  utterances joined into one clip, which can sound choppier than one sentence.
- Text is handed to `say` as written. `say` interprets embedded commands such as
  `[[rate 300]]`, so those characters are not spoken literally.
- A cloze answer cannot contain `::`, as in Anki itself: the part after it is
  read as the hint.
- Each cloze deletion is its own note, so Anki does not bury siblings.
- `voice` cannot give cloze cards a spoken question, and reads only packages
  exported for older Anki versions.
- Importing never deletes cards, and `.deckaloud/audio` is never pruned. Delete
  the folder to start the cache afresh.
- Card text is shown as plain text; HTML in a source file is escaped, not rendered.

## Development

```sh
uv run pytest
uv run --with anki python scripts/verify_import.py first.apkg second.apkg
```

The second command imports packages into a throwaway Anki collection and prints
the cards, which is how import and update behaviour was checked.

`PYTHONPATH=tests uv run --with anki python scripts/verify_sync.py` runs the
sync logic against a throwaway collection of the real `anki` library, through
an adapter that mirrors AnkiConnect's own code.
