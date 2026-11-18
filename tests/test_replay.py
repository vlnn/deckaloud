import json
import re
import shutil
import subprocess

import pytest

from deckaloud.replay import replay_script

AWKWARD_KEYS = ["{", "}", "{{Front}}", "}}", "<", "</script>", '"', "\\", "є", "ArrowUp"]
PAGE = """
const page = JSON.parse(require("fs").readFileSync(0, "utf8"));
const listeners = [];
const clicked = [];
const claimed = [];
const button = (name) => ({ click: () => clicked.push(name) });
const matches = (name, selector) => selector.split(", ").some((part) => part === "." + name);
globalThis.window = globalThis;
globalThis.document = {
  addEventListener: (type, listener) => listeners.push(listener),
  removeEventListener: (type, listener) => {
    if (listeners.includes(listener)) listeners.splice(listeners.indexOf(listener), 1);
  },
  querySelector: (selector) => page.buttons.filter((name) => matches(name, selector)).map(button)[0] || null,
};
page.scripts.forEach((script) => (0, eval)(script));
const press = (key) => ({ key, preventDefault: () => claimed.push(key), stopPropagation: () => {} });
page.pressed.forEach((key) => listeners.forEach((listener) => listener(press(key))));
console.log(JSON.stringify({ clicked, claimed, listeners: listeners.length }));
"""

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="needs the node command")


def script_body(script):
    return script.removeprefix("<script>").removesuffix("</script>")


def listed_keys(script):
    return json.loads(re.search(r"const replayKeys = (.*);", script).group(1))


def press_keys(scripts, pressed, buttons=("replay-button",)):
    page = {"scripts": [script_body(script) for script in scripts], "pressed": pressed, "buttons": buttons}
    result = subprocess.run(
        ["node", "-e", PAGE], input=json.dumps(page), capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def test_no_keys_means_no_script():
    assert replay_script(()) == "", "a deck without replay keys should carry no script at all"


@pytest.mark.parametrize("keys", [("4",), ("2", "r"), *((key,) for key in AWKWARD_KEYS)])
def test_script_lists_exactly_the_configured_keys(keys):
    assert listed_keys(replay_script(keys)) == list(keys), f"the script should listen for {keys} and nothing else"


@pytest.mark.parametrize("key", AWKWARD_KEYS)
def test_script_never_looks_like_template_or_markup_syntax(key):
    script = replay_script((key,))

    assert "{{" not in script and "}}" not in script, f"key {key!r} should not read as an Anki field reference"
    assert "<" not in script_body(script), f"key {key!r} should not be able to close the script tag"


@needs_node
@pytest.mark.parametrize(
    "keys, pressed, replays, claimed",
    [
        (("4",), ["4"], 1, ["4"]),
        (("4",), ["4", "4"], 2, ["4", "4"]),
        (("4",), ["1", "2", " ", "r"], 0, []),
        (("2", "r"), ["2", "4", "r"], 2, ["2", "r"]),
        *(((key,), [key], 1, [key]) for key in AWKWARD_KEYS),
    ],
)
def test_configured_keys_replay_the_audio_and_other_keys_are_left_alone(keys, pressed, replays, claimed):
    outcome = press_keys([replay_script(keys)], pressed)

    assert len(outcome["clicked"]) == replays, f"pressing {pressed} with keys {keys} should replay {replays} times"
    assert outcome["claimed"] == claimed, f"only {claimed} should be kept from Anki's own shortcuts"


@needs_node
@pytest.mark.parametrize("button", ["replay-button", "soundLink", "replaybutton"])
def test_play_button_of_every_anki_client_is_found(button):
    outcome = press_keys([replay_script(("4",))], ["4"], buttons=(button,))

    assert outcome["clicked"] == [button], f"a play button with class {button} should be pressed"


@needs_node
def test_first_play_button_on_the_side_is_the_one_replayed():
    outcome = press_keys([replay_script(("4",))], ["4"], buttons=("soundLink", "replay-button"))

    assert outcome["clicked"] == ["soundLink"], "the first play button on the page should be pressed"


@needs_node
def test_side_without_audio_is_not_an_error():
    outcome = press_keys([replay_script(("4",))], ["4"], buttons=())

    assert outcome["clicked"] == [], "a side without a play button should replay nothing"


@needs_node
@pytest.mark.parametrize(
    "runs, pressed, replays",
    [
        ([("4",), ("4",)], ["4"], 1),
        ([("4",), ("2",)], ["4", "2"], 1),
        ([("4",), ("2",), ("4", "2")], ["4", "2"], 2),
    ],
)
def test_page_kept_between_cards_listens_once_with_the_latest_keys(runs, pressed, replays):
    outcome = press_keys([replay_script(keys) for keys in runs], pressed)

    assert outcome["listeners"] == 1, "showing another card should replace the listener, not add one"
    assert len(outcome["clicked"]) == replays, f"only the keys of the last card shown should replay: {runs[-1]}"
