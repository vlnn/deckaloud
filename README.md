# deckaloud

Sound-first Anki decks. Text files in, one `.apkg` out, every card spoken, so a
deck can be reviewed by ear with a keyboard or remote.

macOS only: speech comes from `say`, encoding from `afconvert`. Nothing talks to
Anki; the only output is the `.apkg` you import yourself.

## Install

Needs macOS, Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install .        # or: uv run deckaloud ...
```

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
- `id:` is the card's identity. Wording can change freely; the id keeps the
  schedule. Letters, digits and underscores only.

## Commands

```sh
deckaloud stamp  notes/*.txt                  # write missing ids into the files
deckaloud check  notes/*.txt                  # validate, render nothing
deckaloud sample notes/*.txt -n 3             # 3 cards per language, both sides, in every natural voice
deckaloud build  notes/*.txt -o listening.apkg
deckaloud build  --stamp notes/*.txt          # stamp, then build
```

`build` refuses cards without an id instead of inventing one, because an id that
changes later would turn a reviewed card into a new one. It only edits your files
when you pass `--stamp`.

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
- Text is handed to `say` as written. `say` interprets embedded commands such as
  `[[rate 300]]`, so those characters are not spoken literally.
- A cloze answer cannot contain `::`, as in Anki itself: the part after it is
  read as the hint.
- Each cloze deletion is its own note, so Anki does not bury siblings.
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
