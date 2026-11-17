import shutil

import pytest

from deckaloud.audio import tone_frames, write_wav
from deckaloud.config import Config
from deckaloud.engines import Voice
from deckaloud.render import Studio

SECONDS_PER_CHARACTER = 0.01


class FakeEngine:
    def __init__(self):
        self.spoken = []

    def synthesize(self, text, voice, rate, target):
        self.spoken.append((text, voice, rate))
        write_wav(target, tone_frames(440, SECONDS_PER_CHARACTER * len(text)))

    def voices(self):
        return (
            Voice("Bells", "en_US"),
            Voice("Daniel", "en_GB"),
            Voice("Eddy (English (US))", "en_US"),
            Voice("Samantha (English (US))", "en_US"),
            Voice("Lesya", "uk_UA"),
        )


def copy_as_encoding(wav, target):
    shutil.copyfile(wav, target)


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def studio(engine, tmp_path):
    return Studio(engine=engine, encode=copy_as_encoding, config=Config(), cache_dir=tmp_path / "audio")
