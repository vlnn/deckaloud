import sys

import pytest

from deckaloud.config import Config
from deckaloud.engines import SayEngine, encode_m4a
from deckaloud.render import Studio, render_clip
from deckaloud.sample import voices_speaking
from deckaloud.speech import Beep, Pause, Say, Speech

pytestmark = [
    pytest.mark.macos,
    pytest.mark.skipif(sys.platform != "darwin", reason="needs the macOS say and afconvert commands"),
]


@pytest.mark.parametrize(
    "speech",
    [
        Speech("en", (Say("The capital of Ukraine is"), Beep(), Say("on the Dnipro river."))),
        Speech("uk", (Say("Київ"), Pause(0.6), Say("Столиця України це Київ."))),
    ],
)
def test_real_voice_and_encoder_produce_a_clip(tmp_path, speech):
    studio = Studio(SayEngine(), encode_m4a, Config(), tmp_path / "audio")
    if not voices_speaking(studio.engine.voices(), speech.lang, studio.config):
        pytest.skip(f"no voice installed for '{speech.lang}'")

    clip = render_clip(speech, studio)

    assert clip.stat().st_size > 2000, "say and afconvert should produce a non-trivial m4a file"
