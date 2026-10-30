"""Notifications: how ``osascript`` is invoked, without ever running it."""

import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from habit_tracker import notifications
from habit_tracker.notifications import notify


class FakePopen:
    """Stands in for ``subprocess.Popen`` and records how it was called."""

    calls: list[tuple[list[str], dict[str, Any]]]
    error: OSError | None

    def __init__(self) -> None:
        self.calls = []
        self.error = None

    def __call__(self, command: list[str], **options: Any) -> None:
        self.calls.append((command, options))
        if self.error is not None:
            raise self.error


@pytest.fixture
def popen(monkeypatch: pytest.MonkeyPatch) -> FakePopen:
    """Replaces ``subprocess`` inside the module only, so nothing outside it is touched."""
    fake = FakePopen()
    monkeypatch.setattr(
        notifications,
        "subprocess",
        SimpleNamespace(Popen=fake, DEVNULL=subprocess.DEVNULL),
    )
    return fake


def test_it_launches_osascript_and_reports_success(popen: FakePopen) -> None:
    assert notify("Leer", "Es tu hora.", platform="darwin") is True

    ((command, options),) = popen.calls
    assert command[:2] == ["osascript", "-e"]
    assert command[-2:] == ["Leer", "Es tu hora."]
    assert options == {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


@pytest.mark.parametrize("platform", ["linux", "win32", "freebsd14"])
def test_it_does_nothing_and_says_so_outside_macos(popen: FakePopen, platform: str) -> None:
    assert notify("Leer", "Es tu hora.", platform=platform) is False
    assert popen.calls == []


def test_it_follows_the_running_platform_by_default(popen: FakePopen) -> None:
    assert notify("Leer", "Es tu hora.") is (sys.platform == "darwin")
    assert len(popen.calls) == (1 if sys.platform == "darwin" else 0)


def test_it_reports_failure_when_osascript_cannot_be_started(popen: FakePopen) -> None:
    popen.error = FileNotFoundError("osascript")

    assert notify("Leer", "Es tu hora.", platform="darwin") is False


@pytest.mark.parametrize(
    "title",
    [
        'Leer «con comillas» "dobles"',
        "It's \\ a \"tricky\" 'name'",
        'x" & (do shell script "echo hacked") & "',
        "línea 1\nlínea 2",
    ],
    ids=["quotes", "mixed-quotes-and-backslash", "applescript-injection", "newline"],
)
def test_the_text_travels_as_arguments_and_never_inside_the_script(
    popen: FakePopen, title: str
) -> None:
    notify(title, 'mensaje "con" comillas', platform="darwin")

    ((command, _),) = popen.calls
    script = command[command.index("-e") + 1]
    assert title not in script
    assert "mensaje" not in script
    assert command[-2:] == [title, 'mensaje "con" comillas']


@pytest.mark.parametrize("title", ["-Leer", "-e", "--help", "-"])
def test_a_title_that_starts_with_a_dash_is_never_read_as_an_option(
    popen: FakePopen, title: str
) -> None:
    # osascript would take "-Leer" for its "-L..." flags; "--" ends the options first.
    notify(title, "Es tu hora.", platform="darwin")

    ((command, _),) = popen.calls
    assert command[-3:] == ["--", title, "Es tu hora."]
    assert "--" not in command[: command.index("-e") + 2]


def test_a_message_that_starts_with_a_dash_is_data_too(popen: FakePopen) -> None:
    notify("Leer", "-1 página pendiente", platform="darwin")

    ((command, _),) = popen.calls
    assert command[-3:] == ["--", "Leer", "-1 página pendiente"]
