import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.fixture(scope="module")
def scripts():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["scripts"]


@pytest.mark.parametrize("command", ["deckaloud", "decks"])
def test_command_is_installed_and_runs_the_cli(scripts, command):
    assert scripts.get(command) == "deckaloud.cli:main", f"{command} should be installed as the deckaloud command line"
