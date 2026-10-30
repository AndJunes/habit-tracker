"""The "duration of the habit" section: when it starts and, optionally, when it ends."""

import tkinter as tk
from collections.abc import Callable
from enum import Enum, auto
from functools import partial

from ..theme import palette
from ..widgets.chips import SelectionChip
from ..widgets.date_picker import DatePicker
from ..widgets.soft_button import SoftButton
from ..widgets.text_entry import themed_entry
from . import texts
from .choices import TextField
from .form_state import FormState
from .parts import (
    DATE_ENTRY_CHARS,
    ENTRY_PAD_Y,
    FORM_WIDTH,
    caption,
    clear,
    prompt,
    small_lilac_button,
    text_variable,
)

CALENDAR_BUTTON_GAP = 10
FIELD_TOP_GAP = 4
END_CHIP_TOP_GAP = 10
END_LABEL_TOP_GAP = 8
CALENDAR_TOP_GAP = 6
END_CHIP_WIDTH = 210
END_CHIP_HEIGHT = 30


class _Date(Enum):
    START = auto()
    END = auto()


class ValiditySection:
    """The start and end fields, each with a calendar that opens under it to pick the day.

    ``on_change`` is called whenever the start or the end changes, typed or picked, and when
    the end is switched on or off.
    """

    def __init__(
        self, body: tk.Frame, state: FormState, *, on_change: Callable[[], object]
    ) -> None:
        self._state = state
        self._on_change = on_change
        self._start = text_variable(body, state, TextField.START, on_change)
        self._end = text_variable(body, state, TextField.END, on_change)

        prompt(body, texts.VALIDITY_PROMPT)
        caption(body, texts.START_LABEL).pack(anchor="w")
        row = tk.Frame(body, bg=palette.PAPER)
        row.pack(anchor="w", fill="x", pady=(FIELD_TOP_GAP, 0))
        themed_entry(
            row, textvariable=self._start, width=DATE_ENTRY_CHARS, name=TextField.START.value
        ).pack(side="left", ipady=ENTRY_PAD_Y)
        small_lilac_button(
            row, texts.OPEN_CALENDAR, lambda: self._toggle_calendar(_Date.START)
        ).pack(side="left", padx=(CALENDAR_BUTTON_GAP, 0))
        self._start_calendar = tk.Frame(body, bg=palette.PAPER)
        self._start_calendar.pack(anchor="w", fill="x")

        end_toggle = tk.Frame(body, bg=palette.PAPER)
        end_toggle.pack(anchor="w", pady=(END_CHIP_TOP_GAP, 0))
        self._end_chip = SelectionChip(
            end_toggle,
            texts.WITH_END,
            self._toggle_end,
            width=END_CHIP_WIDTH,
            height=END_CHIP_HEIGHT,
        )
        self._end_chip.pack()
        self._end_chip.set_selected(state.has_end)
        self._end_zone = tk.Frame(body, bg=palette.PAPER)
        self._end_zone.pack(anchor="w", fill="x")
        self._end_calendar = tk.Frame(body, bg=palette.PAPER)
        self._end_calendar.pack(anchor="w", fill="x")
        self._rebuild_end()

    # ---------- The end ----------

    def _toggle_end(self) -> None:
        self._state.toggle_end()
        self._end_chip.set_selected(self._state.has_end)
        self._rebuild_end()
        self._on_change()

    def _rebuild_end(self) -> None:
        clear(self._end_zone)
        clear(self._end_calendar)
        if not self._state.has_end:
            return
        caption(self._end_zone, texts.END_LABEL).pack(anchor="w", pady=(END_LABEL_TOP_GAP, 0))
        row = tk.Frame(self._end_zone, bg=palette.PAPER)
        row.pack(anchor="w", fill="x", pady=(FIELD_TOP_GAP, 0))
        themed_entry(
            row, textvariable=self._end, width=DATE_ENTRY_CHARS, name=TextField.END.value
        ).pack(side="left", ipady=ENTRY_PAD_Y)
        small_lilac_button(
            row, texts.OPEN_CALENDAR, lambda: self._toggle_calendar(_Date.END)
        ).pack(side="left", padx=(CALENDAR_BUTTON_GAP, 0))

    # ---------- The calendars ----------

    def _calendar_button(self, row: tk.Frame, which: _Date) -> SoftButton:
        return small_lilac_button(row, texts.OPEN_CALENDAR, partial(self._toggle_calendar, which))

    def _toggle_calendar(self, which: _Date) -> None:
        """Opens, or closes, the single-date calendar under the start or the end field."""
        zone = self._start_calendar if which is _Date.START else self._end_calendar
        if zone.winfo_children():
            clear(zone)
            return
        variable = self._start if which is _Date.START else self._end
        field = TextField.START if which is _Date.START else TextField.END
        current = self._state.typed_date(field)
        start, end = self._state.validity_limits()
        picker = DatePicker(
            zone,
            today=self._state.today,
            mode="single",
            selection=[current] if current is not None else [],
            minimum=None if which is _Date.START else start,
            maximum=end if which is _Date.START else None,
            width=FORM_WIDTH,
        )

        def on_picked() -> None:
            days = picker.dates()
            variable.set(days[0].isoformat() if days else "")
            if days:
                clear(zone)  # a date was chosen: the calendar folds away

        picker.on_change = on_picked
        picker.pack(anchor="w", pady=(CALENDAR_TOP_GAP, 0))
