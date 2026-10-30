"""Layout constants and small widget builders shared by the sections of the habit form."""

import tkinter as tk
from collections.abc import Callable
from functools import partial
from typing import Any

from ...domain.enums import Weekday
from ..calendar_es import WEEKDAYS_SHORT
from ..theme import palette
from ..theme.fonts import font
from ..widgets.chips import SelectionChip
from ..widgets.soft_button import SoftButton
from . import texts
from .choices import DayGroup, HintTone, TextField
from .form_state import FormState

FORM_WIDTH = 408  # the usable width of the form
PADDING = 20
PAGE_WIDTH = FORM_WIDTH + 2 * PADDING  # the content that scrolls

PROMPT_TOP_GAP = 14  # space above the title of a section
LABEL_SIZE = 10
PROMPT_SIZE = 11
HINT_SIZE = 9
COUNT_SIZE = 13
ENTRY_PAD_Y = 4  # inner vertical padding of the text entries

DAY_CHIP_WIDTH = 51
DAY_CHIP_HEIGHT = 30
DAY_CHIP_GAP = 6
STEP_BUTTON_WIDTH = 34
STEP_BUTTON_HEIGHT = 30
COUNT_LABEL_CHARS = 3
SMALL_BUTTON_HEIGHT = 30
SMALL_BUTTON_RADIUS = 10
DATE_ENTRY_CHARS = 14
NUMBER_ENTRY_CHARS = 9

TONE_COLORS = {
    HintTone.MUTED: palette.MUTED_LIGHT,
    HintTone.WARNING: palette.TRASH_ACTIVE,
    HintTone.SUCCESS: palette.ACCENT_TOTAL,
}


def clear(frame: tk.Misc) -> None:
    """Destroys everything inside ``frame``."""
    for widget in frame.winfo_children():
        widget.destroy()


def prompt(parent: tk.Misc, text: str, top: int = PROMPT_TOP_GAP) -> tk.Label:
    """The bold title of a section."""
    label = tk.Label(
        parent,
        text=text,
        bg=palette.PAPER,
        fg=palette.INK,
        font=font("sans", PROMPT_SIZE, "bold", master=parent),
    )
    label.pack(anchor="w", pady=(top, 5))
    return label


def hint(parent: tk.Misc, text: str, name: str | None = None) -> tk.Label:
    """A line of small muted text; its color changes with the hint it shows."""
    options: dict[str, Any] = {} if name is None else {"name": name}
    label = tk.Label(
        parent,
        text=text,
        bg=palette.PAPER,
        fg=palette.MUTED_LIGHT,
        font=font("sans", HINT_SIZE, master=parent),
        wraplength=FORM_WIDTH,
        justify="left",
        **options,
    )
    label.pack(anchor="w", pady=(4, 0))
    return label


def caption(parent: tk.Misc, text: str) -> tk.Label:
    """The label of a field. It is returned unpacked: each field places it its own way."""
    return tk.Label(
        parent,
        text=text,
        bg=palette.PAPER,
        fg=palette.MUTED_DARK,
        font=font("sans", LABEL_SIZE, master=parent),
    )


def subtitle(parent: tk.Misc, text: str) -> tk.Label:
    """A secondary title inside a zone."""
    label = caption(parent, text)
    label.pack(anchor="w", pady=(10, 4))
    return label


def text_variable(
    master: tk.Misc, state: FormState, field: TextField, after: Callable[[], object] | None = None
) -> tk.StringVar:
    """A variable for an entry, filled from the state and writing back to it as it is typed."""
    variable = tk.StringVar(master, value=state.text(field))

    def on_write(*_: object) -> None:
        state.set_text(field, variable.get())
        if after is not None:
            after()

    variable.trace_add("write", on_write)
    return variable


def _step_button(parent: tk.Misc, text: str, command: Callable[[], object]) -> SoftButton:
    return SoftButton(
        parent,
        text,
        command,
        palette.BUTTON_LILAC_BACKGROUND,
        palette.BUTTON_LILAC_TEXT,
        height=STEP_BUTTON_HEIGHT,
        width=STEP_BUTTON_WIDTH,
    )


def small_lilac_button(parent: tk.Misc, text: str, command: Callable[[], object]) -> SoftButton:
    """The 30 px lilac button with bold small text ("Elegir en el calendario")."""
    return SoftButton(
        parent,
        text,
        command,
        palette.BUTTON_LILAC_BACKGROUND,
        palette.BUTTON_LILAC_TEXT,
        button_font=font("sans", LABEL_SIZE, "bold", master=parent),
        height=SMALL_BUTTON_HEIGHT,
        radius=SMALL_BUTTON_RADIUS,
    )


def build_stepper(
    parent: tk.Misc, value: int, on_step: Callable[[int], object], gap_after: int = 0
) -> tk.Label:
    """A minus button, the count and a plus button, packed left; returns the count label."""
    _step_button(parent, texts.STEP_DOWN, partial(on_step, -1)).pack(side="left")
    count = tk.Label(
        parent,
        text=str(value),
        width=COUNT_LABEL_CHARS,
        bg=palette.PAPER,
        fg=palette.INK_TITLE,
        font=font("sans", COUNT_SIZE, "bold", master=parent),
    )
    count.pack(side="left")
    _step_button(parent, texts.STEP_UP, partial(on_step, 1)).pack(side="left", padx=(0, gap_after))
    return count


class WeekdayChipRow(tk.Frame):
    """Seven chips, Monday to Sunday, that put days into and out of one of the state's sets."""

    def __init__(
        self,
        master: tk.Misc,
        state: FormState,
        group: DayGroup,
        on_change: Callable[[], object],
    ) -> None:
        super().__init__(master, bg=palette.PAPER)
        self._state = state
        self._group = group
        self._on_change = on_change
        self.chips: dict[Weekday, SelectionChip] = {}
        for day in Weekday:
            chip = SelectionChip(
                self,
                WEEKDAYS_SHORT[day],
                partial(self._toggle, day),
                width=DAY_CHIP_WIDTH,
                height=DAY_CHIP_HEIGHT,
            )
            chip.pack(side="left", padx=(0, DAY_CHIP_GAP))
            chip.set_selected(day in state.days(group))
            self.chips[day] = chip

    def _toggle(self, day: Weekday) -> None:
        self._state.toggle_day(self._group, day)
        self.chips[day].set_selected(day in self._state.days(self._group))
        self._on_change()
