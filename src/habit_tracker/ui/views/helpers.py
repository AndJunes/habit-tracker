"""Small pieces several screens need: canvases, text fitting and the editing gesture."""

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from ...domain.models import Habit
from ..theme import palette
from ..theme.drawing import mix_colors
from ..theme.fonts import measure
from ..theme.tkutil import TkEvent

# Right click, Control-click and button 2 (the right button on some systems): edit the habit.
EDIT_SEQUENCES = ("<Button-2>", "<Button-3>", "<Control-Button-1>")

# How much white is mixed into the icon of a habit that is not due today, to dim it.
_MUTED_ICON_MIX = 0.45

_ELLIPSIS = "…"


def noop() -> None:
    """The command of a control that is drawn but cannot be used."""


def for_habit(action: Callable[[Habit], object], habit: Habit) -> Callable[[TkEvent], object]:
    """An event handler that applies ``action`` to ``habit``, whatever the event is.

    Each call has its own scope, so building handlers in a loop cannot end up with all of
    them pointing at the last habit.
    """
    return lambda _event: action(habit)


def new_canvas(master: tk.Misc, width: float, height: float, background: str) -> tk.Canvas:
    """A canvas that blends into its container (no border, the container's background)."""
    return tk.Canvas(master, width=width, height=height, bg=background, highlightthickness=0)


def clear_children(widget: tk.Misc) -> None:
    """Destroy everything inside ``widget`` so that it can be filled in again."""
    for child in widget.winfo_children():
        child.destroy()


def muted_icon_color(color: str) -> str:
    """The pale version of an area color, for habits that are not due today."""
    return mix_colors(color, palette.WHITE, _MUTED_ICON_MIX)


def truncate_text(text_font: tkfont.Font, text: str, available: float) -> str:
    """Cut ``text`` and end it with "…" when it is wider than ``available`` pixels."""
    if measure(text_font, text) <= available:
        return text
    while text and measure(text_font, text + _ELLIPSIS) > available:
        text = text[:-1]
    return text + _ELLIPSIS


@contextmanager
def tagged_items(canvas: tk.Canvas, tag: str) -> Iterator[None]:
    """Give ``tag`` to every canvas item drawn inside the block, so one binding covers a row."""
    before = len(canvas.find_all())
    yield
    for item in canvas.find_all()[before:]:
        canvas.addtag_withtag(tag, item)
