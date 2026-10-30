"""The entry and save button of the "tomorrow's priority" card (Today and the dashboard)."""

import tkinter as tk
from dataclasses import dataclass

from ..controllers.priority import PriorityEditor
from ..theme import palette
from ..theme.fonts import INPUT_FONT_SIZE, font
from ..widgets.soft_button import SoftButton
from . import texts


@dataclass(frozen=True, slots=True)
class PriorityControlsLayout:
    """Where the controls sit on the card's canvas."""

    entry_x: int
    entry_y: int
    entry_width: int
    entry_height: int
    button_right: int
    button_y: int
    button_height: int


def add_priority_controls(
    canvas: tk.Canvas, editor: PriorityEditor, layout: PriorityControlsLayout
) -> tk.Entry:
    """Place the entry (bound to the editor's text) and the save button on the card.

    Both are windows embedded in the canvas. Enter in the entry saves as well.
    """
    entry = tk.Entry(
        canvas,
        textvariable=editor.variable,
        bg=palette.WHITE,
        fg=palette.PEACH_INK,
        font=font("sans", INPUT_FONT_SIZE, master=canvas),
        bd=0,
        relief="flat",
        highlightthickness=1,
        highlightbackground=palette.PEACH_BORDER,
        highlightcolor=palette.PEACH_BUTTON,
        insertbackground=palette.PEACH_INK,
    )
    canvas.create_window(
        layout.entry_x,
        layout.entry_y,
        anchor="nw",
        window=entry,
        width=layout.entry_width,
        height=layout.entry_height,
    )
    entry.bind("<Return>", lambda _event: editor.save())

    button = SoftButton(
        canvas,
        texts.PRIORITY_SAVE,
        editor.save,
        palette.PEACH_BUTTON,
        palette.WHITE,
        parent_background=palette.PEACH_BACKGROUND,
        height=layout.button_height,
    )
    canvas.create_window(layout.button_right, layout.button_y, anchor="ne", window=button)
    return entry
