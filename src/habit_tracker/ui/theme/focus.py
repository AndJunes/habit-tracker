"""Keyboard focus: the ring that shows it, and what makes a canvas reachable with Tab.

The widgets are drawn on a canvas, which Tk does not put in the Tab order by itself, so each
one asks for it here. The ring is drawn only while the keyboard has the focus: a click does not
give a canvas the focus, so the mouse never shows it.
"""

import tkinter as tk
from collections.abc import Callable, Iterable

from . import palette
from .drawing import rounded_rect
from .tkutil import TkEvent

RING_WIDTH = 2
ACTIVATION_KEYS = ("<space>", "<Return>", "<KP_Enter>")


def focus_ring(
    canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float
) -> int:
    """Draw the focus ring as an outline with no fill inside the box ``(x1, y1, x2, y2)``."""
    return rounded_rect(
        canvas, x1, y1, x2, y2, radius, fill="", outline=palette.FOCUS_RING, width=RING_WIDTH
    )


def track_focus(widget: tk.Canvas, redraw: Callable[[], object]) -> Callable[[], bool]:
    """Make ``widget`` reachable with Tab and call ``redraw`` when it gains or loses the focus.

    Returns a function that says whether the widget has the keyboard focus right now.
    """
    state = {"focused": False}

    def gained(_event: TkEvent) -> None:
        state["focused"] = True
        redraw()

    def lost(_event: TkEvent) -> None:
        state["focused"] = False
        redraw()

    widget.configure(takefocus=True)
    widget.bind("<FocusIn>", gained, add="+")
    widget.bind("<FocusOut>", lost, add="+")
    return lambda: state["focused"]


def activate_with_keys(
    widget: tk.Misc, command: Callable[[], object], keys: Iterable[str] = ACTIVATION_KEYS
) -> None:
    """Call ``command`` when one of ``keys`` is pressed while ``widget`` has the focus."""

    def pressed(_event: TkEvent) -> str:
        command()
        return "break"  # nothing else should also react to this key

    for key in keys:
        widget.bind(key, pressed, add="+")
