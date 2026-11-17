import struct
import wave

import pytest

from deckaloud.audio import (
    SAMPLE_RATE,
    read_frames,
    silence_frames,
    tone_frames,
    write_wav,
)
from deckaloud.errors import SpeechError

BYTES_PER_SAMPLE = 2


@pytest.mark.parametrize("seconds", [0.0, 0.1, 0.25, 1.0])
def test_silence_lasts_the_requested_time(seconds):
    frames = silence_frames(seconds)

    assert len(frames) == round(seconds * SAMPLE_RATE) * BYTES_PER_SAMPLE, f"silence should last {seconds}s"
    assert not any(frames), "silence should contain only zero samples"


@pytest.mark.parametrize("frequency, seconds", [(440, 0.1), (880, 0.25)])
def test_tone_lasts_the_requested_time_and_fades_at_the_edges(frequency, seconds):
    frames = tone_frames(frequency, seconds)
    samples = struct.unpack(f"<{len(frames) // BYTES_PER_SAMPLE}h", frames)

    assert len(samples) == round(seconds * SAMPLE_RATE), f"tone should last {seconds}s"
    assert samples[0] == 0 and samples[-1] == 0, "tone should start and end at zero to avoid clicks"
    assert max(samples) > 5000, "tone should be audible"


def test_written_wav_reads_back_unchanged(tmp_path):
    frames = tone_frames(440, 0.05)
    path = tmp_path / "clip.wav"

    write_wav(path, frames)

    assert read_frames(path) == frames, "read_frames should return what write_wav stored"


@pytest.mark.parametrize("channels, rate", [(2, SAMPLE_RATE), (1, 44100)])
def test_unexpected_wav_format_is_rejected(tmp_path, channels, rate):
    path = tmp_path / "odd.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(BYTES_PER_SAMPLE)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * channels * 10)

    with pytest.raises(SpeechError) as raised:
        read_frames(path)

    assert "format" in str(raised.value), "error should say the audio format is unexpected"
