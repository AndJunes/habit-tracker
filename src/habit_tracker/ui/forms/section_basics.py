"""The first and last sections of the form: header, name, motivation, area and notes."""

import tkinter as tk
from collections.abc import Callable
from functools import partial

from ..theme import palette
from ..theme.fonts import font
from ..widgets.chips import SelectionChip
from ..widgets.text_entry import themed_entry
from . import texts
from .choices import TextField
from .form_state import FormState
from .parts import ENTRY_PAD_Y, hint, prompt, text_variable

AREA_CHIP_WIDTH = 96
AREA_CHIPS_PER_ROW = 4
AREA_CHIP_GAP = 8
MOTIVATION_TOP_GAP = 10

_EYEBROW_SIZE = 9
_TITLE_SIZE = 20
_TAGLINE_SIZE = 14


class HeaderSection:
    """The title block: what the window is for, and its tagline."""

    def __init__(self, body: tk.Frame, state: FormState) -> None:
        tk.Label(
            body,
            text=texts.EYEBROW,
            bg=palette.PAPER,
            fg=palette.MUTED,
            font=font("sans", _EYEBROW_SIZE, "bold", master=body),
        ).pack(anchor="w")
        tk.Label(
            body,
            text=texts.TITLE_EDIT if state.is_editing else texts.TITLE_NEW,
            bg=palette.PAPER,
            fg=palette.INK_TITLE,
            font=font("serif", _TITLE_SIZE, master=body),
        ).pack(anchor="w")
        tk.Label(
            body,
            text=texts.TAGLINE,
            bg=palette.PAPER,
            fg=palette.MUTED_LIGHT,
            font=font("script", _TAGLINE_SIZE, master=body),
        ).pack(anchor="w")


class NameSection:
    """The name of the habit and, optionally, why the person wants it."""

    def __init__(
        self,
        body: tk.Frame,
        state: FormState,
        *,
        on_change: Callable[[], object],
        on_submit: Callable[[], object],
    ) -> None:
        prompt(body, texts.NAME_PROMPT)
        self._name = text_variable(body, state, TextField.NAME, on_change)
        self._entry = themed_entry(body, textvariable=self._name, name=TextField.NAME.value)
        self._entry.pack(fill="x", ipady=ENTRY_PAD_Y)
        self._entry.bind("<Return>", lambda _event: on_submit())
        hint(body, texts.NAME_EXAMPLE)
        prompt(body, texts.MOTIVATION_PROMPT, top=MOTIVATION_TOP_GAP)
        self._description = text_variable(body, state, TextField.DESCRIPTION, on_change)
        themed_entry(body, textvariable=self._description, name=TextField.DESCRIPTION.value).pack(
            fill="x", ipady=ENTRY_PAD_Y
        )

    def focus(self) -> None:
        self._entry.focus()


class AreaSection:
    """One chip per area, in the color of the area; the choice defines the habit's color."""

    def __init__(
        self, body: tk.Frame, state: FormState, *, on_change: Callable[[], object]
    ) -> None:
        self._state = state
        self._on_change = on_change
        prompt(body, texts.AREA_PROMPT)
        row = tk.Frame(body, bg=palette.PAPER)
        row.pack(anchor="w")
        self.chips: list[SelectionChip] = []
        for index, area in enumerate(state.areas):
            chip = SelectionChip(
                row, area.name, partial(self._pick, index), color=area.color, width=AREA_CHIP_WIDTH
            )
            column = index % AREA_CHIPS_PER_ROW
            last_in_row = column == AREA_CHIPS_PER_ROW - 1
            chip.grid(
                row=index // AREA_CHIPS_PER_ROW,
                column=column,
                padx=(0, 0 if last_in_row else AREA_CHIP_GAP),
                pady=(0, AREA_CHIP_GAP),
            )
            chip.set_selected(index == state.area_index)
            self.chips.append(chip)

    def _pick(self, index: int) -> None:
        self._state.select_area(index)
        for position, chip in enumerate(self.chips):
            chip.set_selected(position == index)
        self._on_change()


class NotesSection:
    """Free notes about the habit."""

    def __init__(self, body: tk.Frame, state: FormState) -> None:
        prompt(body, texts.NOTES_PROMPT)
        self._notes = text_variable(body, state, TextField.NOTES)
        themed_entry(body, textvariable=self._notes, name=TextField.NOTES.value).pack(
            fill="x", ipady=ENTRY_PAD_Y
        )
