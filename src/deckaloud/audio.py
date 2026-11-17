import math
import struct
import wave
from pathlib import Path

from deckaloud.errors import SpeechError

SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2
CHANNELS = 1
PEAK = 0.4 * 32767
FADE_SECONDS = 0.01


def silence_frames(seconds: float) -> bytes:
    return b"\x00" * SAMPLE_WIDTH * sample_count(seconds)


def tone_frames(frequency: float, seconds: float) -> bytes:
    count = sample_count(seconds)
    samples = (round(tone_sample(index, count, frequency)) for index in range(count))
    return struct.pack(f"<{count}h", *samples)


def sample_count(seconds: float) -> int:
    return round(seconds * SAMPLE_RATE)


def tone_sample(index: int, count: int, frequency: float) -> float:
    return PEAK * fade(index, count) * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)


def fade(index: int, count: int) -> float:
    ramp = max(1, sample_count(FADE_SECONDS))
    return min(1.0, index / ramp, (count - 1 - index) / ramp)


def write_wav(path: Path, frames: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)


def read_frames(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        shape = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
        if shape != (CHANNELS, SAMPLE_WIDTH, SAMPLE_RATE):
            raise SpeechError(f"{path.name} has an unexpected audio format {shape}")
        return wav.readframes(wav.getnframes())
