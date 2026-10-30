"""Importing a tool must do nothing: no window, no subprocess, no files, no output.

That is what lets the tests (and anyone else) load the scripts and call their functions.
"""

import subprocess
import tkinter
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools"
TOOL_NAMES = ["capture_screens", "build_macos_app"]


class ForbiddenWindow:
    """Stands in for ``tkinter.Tk``: opening a window is a failure."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("importing the tool opened a window")


def forbidden(*args: object, **kwargs: object) -> None:
    raise AssertionError("importing the tool ran a program")


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_importing_a_tool_does_nothing(
    name: str,
    load_tool: Callable[[str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tkinter, "Tk", ForbiddenWindow)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)

    module = load_tool(name)

    assert callable(module.main)
    assert list(tmp_path.iterdir()) == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_a_tool_runs_its_main_only_when_executed_as_a_script(name: str) -> None:
    source = (TOOLS / f"{name}.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":\n    raise SystemExit(main())\n' in source
