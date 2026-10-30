"""Fixtures for the interface tests.

Tk needs a display even for hidden windows. Without one, every test that asks for
``tk_root`` is skipped with the reason visible in the report.
"""

import contextlib
import tkinter as tk
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marks as ``gui`` every test under this folder that needs a Tk root."""
    for item in items:
        if HERE in item.path.parents and "tk_root" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.gui)


@pytest.fixture(scope="session")
def tk_root() -> Iterator[tk.Tk]:
    """The application root, hidden. It is the implicit root of the whole test session."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"no display available: {error}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture(autouse=True)
def _destroy_leftover_widgets(request: pytest.FixtureRequest) -> Iterator[None]:
    """Gives every test an empty root: widgets and windows a test created are destroyed."""
    yield
    if "tk_root" in request.fixturenames:
        root: tk.Tk = request.getfixturevalue("tk_root")
        for child in root.winfo_children():
            child.destroy()


def _show_invisibly(window: tk.Toplevel) -> None:
    """Maps a window so it receives events, fully transparent so nothing flashes on screen."""
    # Where transparency is unsupported the window is simply visible for a moment.
    with contextlib.suppress(tk.TclError):
        window.attributes("-alpha", 0.0)
    window.geometry("+0+0")
    window.update()
    if not window.winfo_viewable():
        window.destroy()
        pytest.skip("windows cannot be mapped in this environment, so events are not delivered")


@pytest.fixture
def window(tk_root: tk.Tk) -> Iterator[tk.Toplevel]:
    """A mapped, transparent window of the shared root, for tests that need real events."""
    top = tk.Toplevel(tk_root)
    _show_invisibly(top)
    yield top
    if top.winfo_exists():
        top.destroy()


@pytest.fixture
def private_window(tk_root: tk.Tk) -> Iterator[tk.Toplevel]:
    """A mapped, transparent window on its own root (its own Tcl interpreter).

    Global bindings (``bind_all``) are per interpreter, so tests that inspect or change
    them use this one and cannot disturb the shared root.
    """
    root = tk.Tk()
    root.withdraw()
    try:
        top = tk.Toplevel(root)
        _show_invisibly(top)
        yield top
    finally:
        root.destroy()


class FakeEvent:
    """The minimum of a mouse event: where it landed."""

    def __init__(self, widget: object = None, x: int = 0, y: int = 0) -> None:
        self.widget, self.x, self.y = widget, x, y


@pytest.fixture
def fake_event() -> Callable[..., FakeEvent]:
    """Builds minimal mouse events to call handlers directly."""
    return FakeEvent
