import json

KEYS = "REPLAY_KEYS"
SCRIPT = """\
<script>
(() => {
  const replayKeys = REPLAY_KEYS;
  const playButton = () => document.querySelector(".replay-button, .soundLink, .replaybutton");
  const replayAudio = () => {
    const button = playButton();
    if (button) button.click();
  };
  const onKeydown = (event) => {
    if (!replayKeys.includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    replayAudio();
  };
  document.removeEventListener("keydown", window.deckaloudReplay, true);
  window.deckaloudReplay = onKeydown;
  document.addEventListener("keydown", onKeydown, true);
})();
</script>"""
TEMPLATE_SYNTAX = str.maketrans({"{": "\\u007b", "}": "\\u007d", "<": "\\u003c"})


def replay_script(keys: tuple[str, ...]) -> str:
    return SCRIPT.replace(KEYS, key_literal(keys)) if keys else ""


def key_literal(keys: tuple[str, ...]) -> str:
    return json.dumps(list(keys)).translate(TEMPLATE_SYNTAX)
