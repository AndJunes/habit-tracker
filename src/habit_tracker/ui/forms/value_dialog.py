"""The small dialog that asks how much was done when a measured habit is marked.

It works with the keyboard alone: the field has the focus when it opens, Enter accepts the number,
Escape cancels, and Tab goes on to the two buttons.
"""

import tkinter as tk
from datetime import date

from ...domain.models import Habit, Measurement
from ..theme import palette
from ..theme.fonts import font
from ..theme.tkutil import TkEvent
from ..widgets.soft_button import SoftButton
from ..widgets.text_entry import themed_entry
from . import texts
from .modal import make_modal
from .numbers import format_number, parse_number
from .parts import ENTRY_PAD_Y, HINT_SIZE, LABEL_SIZE, NUMBER_ENTRY_CHARS, PADDING

VALUE_ENTRY_NAME = "value"

_BODY_PADDING = (18, 16)  # top and bottom
_HEADING_SIZE = 18
_UNIT_SIZE = 12
_NAME_GAP = (2, 10)
_UNIT_GAP = 8
_REFERENCES_GAP = (6, 0)
_ERROR_GAP = (4, 0)
_BUTTONS_GAP = (10, 0)


def ask_value(master: tk.Misc, habit: Habit, day: date) -> float | None:
    """Ask for the measured value and return it, or ``None`` if the person cancels.

    ``habit`` must be a measured one. The dialog is modal: this call returns once it closes.
    """
    if habit.measurement is None:
        raise ValueError("ask_value needs a habit that is measured")
    dialog = ValueDialog(master, habit, day)
    master.wait_window(dialog)
    return dialog.result


class ValueDialog(tk.Toplevel):
    """Asks how much was done. It arrives with the goal already typed: if the goal was met,
    it is a single click. ``result`` is the number recorded, or ``None`` if cancelled.
    """

    def __init__(self, master: tk.Misc, habit: Habit, day: date) -> None:
        if habit.measurement is None:
            raise ValueError("a value dialog needs a habit that is measured")
        super().__init__(master)
        measurement = habit.measurement
        self.habit = habit
        self.day = day
        self.result: float | None = None

        self.title(habit.name)
        self.configure(bg=palette.PAPER)
        self.resizable(False, False)

        body = tk.Frame(self, bg=palette.PAPER)
        body.pack(padx=PADDING, pady=_BODY_PADDING)
        tk.Label(
            body,
            text=texts.VALUE_QUESTION,
            bg=palette.PAPER,
            fg=palette.INK_TITLE,
            font=font("serif", _HEADING_SIZE, master=body),
        ).pack(anchor="w")
        tk.Label(
            body,
            text=habit.name,
            bg=palette.PAPER,
            fg=palette.MUTED,
            font=font("sans", LABEL_SIZE, master=body),
        ).pack(anchor="w", pady=_NAME_GAP)

        row = tk.Frame(body, bg=palette.PAPER)
        row.pack(anchor="w")
        self._value = tk.StringVar(self, value=format_number(measurement.goal))
        self._entry = themed_entry(
            row, textvariable=self._value, width=NUMBER_ENTRY_CHARS, name=VALUE_ENTRY_NAME
        )
        self._entry.pack(side="left", ipady=ENTRY_PAD_Y)
        tk.Label(
            row,
            text=measurement.unit,
            bg=palette.PAPER,
            fg=palette.INK,
            font=font("sans", _UNIT_SIZE, master=body),
        ).pack(side="left", padx=(_UNIT_GAP, 0))

        tk.Label(
            body,
            text=_references(measurement),
            bg=palette.PAPER,
            fg=palette.MUTED_LIGHT,
            font=font("sans", HINT_SIZE, master=body),
        ).pack(anchor="w", pady=_REFERENCES_GAP)

        self._error_label = tk.Label(
            body,
            text="",
            bg=palette.PAPER,
            fg=palette.TRASH_ACTIVE,
            font=font("sans", LABEL_SIZE, "bold", master=body),
        )
        self._error_label.pack(anchor="w", pady=_ERROR_GAP)

        buttons = tk.Frame(body, bg=palette.PAPER)
        buttons.pack(fill="x", pady=_BUTTONS_GAP)
        SoftButton(
            buttons,
            texts.CANCEL,
            self.destroy,
            palette.BUTTON_PINK_BACKGROUND,
            palette.BUTTON_PINK_TEXT,
        ).pack(side="left")
        SoftButton(buttons, texts.VALUE_SUBMIT, self.submit, palette.LILAC, palette.WHITE).pack(
            side="right"
        )

        self._entry.bind("<Return>", lambda _event: self.submit())
        # On the dialog, not the field: the Toplevel is in the bindtags of all its widgets, so
        # Escape cancels wherever the focus is (also on the buttons).
        self.bind("<Escape>", self._on_escape)
        self._entry.focus()
        self._entry.selection_range(0, "end")
        self.after(0, lambda: make_modal(self))

    @property
    def error_text(self) -> str:
        """What the dialog says about the last attempt: empty unless the number was rejected."""
        return str(self._error_label.cget("text"))

    def cancel(self) -> None:
        """Close without a result, as the Cancel button does."""
        self.destroy()

    def _on_escape(self, _event: TkEvent) -> str:
        self.cancel()
        return "break"

    def submit(self) -> None:
        """Accepts the number and closes; an invalid one is reported without closing."""
        value = parse_number(self._value.get())
        if value is None or value <= 0:
            self._error_label.configure(text=texts.VALUE_INVALID)
            return
        self.result = float(value)
        self.destroy()


def _references(measurement: Measurement) -> str:
    """``"meta 10 · mínimo 5 · ideal 15. Cualquier cantidad cuenta."``"""
    return texts.value_references(
        format_number(measurement.goal),
        format_number(measurement.minimum) if measurement.minimum is not None else None,
        format_number(measurement.ideal) if measurement.ideal is not None else None,
    )
