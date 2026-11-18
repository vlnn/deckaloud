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
deckaloud build  notes/networking.txt         # writes notes/networking.apkg
deckaloud build  notes/*.txt -o listening.apkg
deckaloud build  --stamp notes/*.txt          # stamp, then build
deckaloud voice  mydeck.apkg                  # add sound to an existing deck
```

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

`build` refuses cards without an id instead of inventing one, because an id that
changes later would turn a reviewed card into a new one. It only edits your files
when you pass `--stamp`.

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

[keys]
replay = ["4"]             # keys that replay the side being shown; [] for none

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

## Replay key

Rings and remotes made for Anki send the review keys (Space, 1, 2, 4), and none
of those replays the audio. AnkiMobile cannot rebind keys, so the cards do it
themselves: a small script in the card template listens for the keys listed in
`[keys] replay` and presses the play button of the side being shown. The default
is `4`.

```toml
[keys]
replay = ["4", "r"]        # several keys
# replay = "2"             # one key
# replay = []              # none: the cards carry no script
```

Keys are named the way browsers name them: `"4"`, `"r"`, `"ArrowUp"`.

The script is tested in a browser-like page and through a real Anki import, not
inside the Anki apps, so try it with your remote before relying on it:

- It only hears a key the app passes on to the card. On the answer side Anki
  may grade the card instead of replaying it, or as well: `4` is Easy there.
- Anki's desktop app is expected to keep 1–4 for itself. R replays there anyway.
- It presses the play button Anki draws next to the audio, so that button has to
  be shown (desktop: Preferences → Review → Show play buttons on cards with audio).
- `voice` leaves note types as they are, so decks voiced that way do not get it.

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
dialog leave "Update notes" and "Update note types" on "If newer".

Changing voices, pauses, replay keys or the language list is safe between
builds: the note type keeps the same identity and fields whatever the settings
are. The replay keys live in the note type, so a deck you already study gets
them, or a new choice of keys, with the next import.

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

The replay script's tests run it under `node` and are skipped when it is missing.
