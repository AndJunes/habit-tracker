"""Fixtures for the GUI tests of tools/capture_screens.py.

``tk_root`` (from ``tests/gui/conftest.py``) is requested only for the skip logic and the
``gui`` marker: the script builds the app on a root of its own, which is destroyed with it.
"""

import importlib.util
import sys
import tkinter as tk
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.ui.theme.tkutil import widget_exists

TOOLS = Path(__file__).resolve().parents[3] / "tools"
NOW = datetime(2026, 10, 29, 10, 0)  # a Thursday: the demo has a habit that can be marked


class SilentDialogs:
    """Answers "no" to every question and shows nothing, so no message box can block a test."""

    def ask_yes_no(self, title: str, message: str) -> bool:
        return False

    def show_info(self, title: str, message: str) -> None:
        pass

    def show_warning(self, title: str, message: str) -> None:
        pass

    def show_error(self, title: str, message: str) -> None:
        pass


@pytest.fixture
def now() -> datetime:
    """The moment the clock of the script is stopped at."""
    return NOW


@pytest.fixture
def capture_screens() -> Iterator[ModuleType]:
    """``tools/capture_screens.py`` loaded as a module (``tools`` is not a package)."""
    module_name = "tools_capture_screens"
    spec = importlib.util.spec_from_file_location(module_name, TOOLS / "capture_screens.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # dataclasses look their own module up here
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(module_name, None)


@pytest.fixture
def private_root(tk_root: tk.Tk) -> Iterator[tk.Tk]:
    """A hidden root of its own: the script installs hooks on the root it builds the app on."""
    root = tk.Tk()
    root.withdraw()
    try:
        yield root
    finally:
        if widget_exists(root):
            root.destroy()


@pytest.fixture
def make_script(
    capture_screens: ModuleType, private_root: tk.Tk, tmp_path: Path
) -> Callable[..., Any]:
    """Builds a hidden ``CaptureScript`` on the demo data of a fixed day.

    The images go to ``tmp_path / "img"`` and the screenshots are looked for in
    ``tmp_path / "captures"``: nothing touches the real ``docs/img`` or the Desktop.
    """

    def make(**options: Any) -> Any:
        output = tmp_path / "img"
        captures = tmp_path / "captures"
        output.mkdir()
        captures.mkdir()
        return capture_screens.CaptureScript(
            output,
            captures,
            hidden=True,
            root=private_root,
            clock=FixedClock(NOW),
            dialogs=SilentDialogs(),
            **options,
        )

    return make
