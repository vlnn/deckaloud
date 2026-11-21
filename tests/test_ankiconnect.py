import io
import json
from urllib.error import URLError

import pytest

from deckaloud.ankiconnect import AnkiConnect, AnkiError, AnkiUnreachable, running_anki


def answering(mocker, answer):
    return mocker.patch("deckaloud.ankiconnect.urlopen", return_value=io.BytesIO(json.dumps(answer).encode()))


def test_action_is_posted_and_its_result_returned(mocker):
    urlopen = answering(mocker, {"result": [1, 2], "error": None})

    result = AnkiConnect().invoke("findNotes", query="tag:x")
    request = urlopen.call_args.args[0]

    assert result == [1, 2], "the result of the action should be returned"
    assert request.full_url == "http://127.0.0.1:8765", "the request should go to AnkiConnect's default address"
    assert json.loads(request.data) == {"action": "findNotes", "version": 6, "params": {"query": "tag:x"}}, (
        "the action and its parameters should be posted"
    )


def test_error_from_anki_is_raised_with_the_action_name(mocker):
    answering(mocker, {"result": None, "error": "deck was not found"})

    with pytest.raises(AnkiError) as failure:
        AnkiConnect().invoke("changeDeck", cards=[1], deck="Geo")

    assert str(failure.value) == "changeDeck: deck was not found", "the error should name the action and the reason"


def test_refused_connection_means_anki_is_unreachable(mocker):
    mocker.patch("deckaloud.ankiconnect.urlopen", side_effect=URLError("refused"))

    with pytest.raises(AnkiUnreachable):
        AnkiConnect().invoke("version")


class SlowAnki:
    def __init__(self, failures):
        self.failures = failures

    def invoke(self, action, **params):
        if self.failures:
            self.failures -= 1
            raise AnkiUnreachable("not yet")
        return 6


@pytest.mark.parametrize("failures, launches, naps", [(0, 0, 0), (1, 1, 0), (3, 1, 2)])
def test_anki_is_launched_once_and_waited_for(mocker, failures, launches, naps):
    launch, nap = mocker.Mock(), mocker.Mock()
    anki = SlowAnki(failures)

    found = running_anki(anki, launch, nap, attempts=5)

    assert found is anki, "the reachable Anki should be returned"
    assert launch.call_count == launches, f"Anki should be launched {launches} times"
    assert nap.call_count == naps, f"there should be {naps} pauses while waiting"


def test_anki_that_never_answers_is_an_error(mocker):
    with pytest.raises(AnkiUnreachable) as failure:
        running_anki(SlowAnki(99), mocker.Mock(), mocker.Mock(), attempts=3)

    assert "AnkiConnect" in str(failure.value), "the error should mention the add-on that has to answer"
