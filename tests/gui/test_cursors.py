import tkinter as tk
from types import SimpleNamespace
from typing import cast

import pytest

from habit_tracker.ui.theme.cursors import DEFAULT_CURSOR, pointer_cursor


def fake_widget(windowing_system: str) -> tk.Misc:
    """A stand-in that only answers ``tk.call("tk", "windowingsystem")``."""
    calls = {("tk", "windowingsystem"): windowing_system}
    return cast("tk.Misc", SimpleNamespace(tk=SimpleNamespace(call=lambda *args: calls[args])))


@pytest.mark.parametrize(
    ("windowing_system", "expected"),
    [("aqua", "pointinghand"), ("x11", "hand2"), ("win32", "hand2")],
)
def test_pointer_cursor_depends_on_the_windowing_system(
    windowing_system: str, expected: str
) -> None:
    assert pointer_cursor(fake_widget(windowing_system)) == expected


def test_pointer_cursor_of_a_real_widget_is_accepted_by_tk(tk_root: tk.Tk) -> None:
    cursor = pointer_cursor(tk_root)
    assert cursor in {"pointinghand", "hand2"}
    button = tk.Canvas(tk_root, cursor=cursor)
    assert str(button.cget("cursor")) == cursor
    assert str(tk.Canvas(tk_root, cursor=DEFAULT_CURSOR).cget("cursor")) == "arrow"
