import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from deckaloud.errors import DeckaloudError

DEFAULT_URL = "http://127.0.0.1:8765"
API_VERSION = 6
TIMEOUT_SECONDS = 600
LAUNCH_ATTEMPTS = 60
NOT_ANSWERING = "Anki did not answer; check that it starts and that the AnkiConnect add-on is installed"


class AnkiError(DeckaloudError):
    pass


class AnkiUnreachable(AnkiError):
    pass


class Anki(Protocol):
    def invoke(self, action: str, **params: Any) -> Any: ...


@dataclass(frozen=True)
class AnkiConnect:
    url: str = DEFAULT_URL

    def invoke(self, action: str, **params: Any) -> Any:
        body = json.dumps({"action": action, "version": API_VERSION, "params": params}).encode("utf-8")
        answer = self.posted(Request(self.url, data=body, headers={"Content-Type": "application/json"}))
        if answer["error"]:
            raise AnkiError(f"{action}: {answer['error']}")
        return answer["result"]

    def posted(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.load(response)
        except (URLError, OSError) as error:
            raise AnkiUnreachable(f"Anki is not reachable at {self.url}: {error}") from None


def running_anki(
    anki: Anki, launch: Callable[[], None], nap: Callable[[], None], attempts: int = LAUNCH_ATTEMPTS
) -> Anki:
    if answers(anki):
        return anki
    launch()
    for _ in range(attempts):
        if answers(anki):
            return anki
        nap()
    raise AnkiUnreachable(NOT_ANSWERING)


def answers(anki: Anki) -> bool:
    try:
        anki.invoke("version")
    except AnkiUnreachable:
        return False
    return True


def launch_anki() -> None:
    subprocess.run(["open", "-g", "-a", "Anki"], check=False, capture_output=True)


def short_nap() -> None:
    time.sleep(1)
