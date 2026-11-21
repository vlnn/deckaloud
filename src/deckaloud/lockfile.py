import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from deckaloud.errors import DeckaloudError


@contextmanager
def exclusive(lock: Path) -> Iterator[None]:
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeckaloudError("already running") from None
        yield
