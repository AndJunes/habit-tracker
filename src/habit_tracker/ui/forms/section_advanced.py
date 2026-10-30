"""The folded "advanced options": reference goals, rest days and the reminder."""

import tkinter as tk
from collections.abc import Callable

from ..theme import palette
from ..theme.fonts import font
from ..widgets.chips import SelectionChip
from ..widgets.soft_button import SoftButton
from ..widgets.text_entry import themed_entry
from . import texts
from .choices import DayGroup, FrequencyChoice, MeasurementChoice, TextField
from .form_state import FormState
from .parts import (
    ENTRY_PAD_Y,
    LABEL_SIZE,
    NUMBER_ENTRY_CHARS,
    WeekdayChipRow,
    caption,
    clear,
    hint,
    subtitle,
    text_variable,
)

TOGGLE_TOP_GAP = 16
TOGGLE_HEIGHT = 32
TOGGLE_RADIUS = 10
REMINDER_CHIP_WIDTH = 190
REMINDER_CHIP_HEIGHT = 30
REFERENCE_FIELD_GAP = 16
CAPTION_FIELD_GAP = 4
TIME_LABEL_GAP = (8, 4)
TIME_ENTRY_CHARS = 8


class AdvancedSection:
    """A toggle that shows or hides the options most habits do not need.

    What is offered depends on the rest of the form: the reference goals only exist when
    something is measured and the rest days only with "every day".
    """

    def __init__(
        self, body: tk.Frame, state: FormState, *, on_change: Callable[[], object]
    ) -> None:
        self._state = state
        self._on_change = on_change
        self._minimum = text_variable(body, state, TextField.MINIMUM)
        self._ideal = text_variable(body, state, TextField.IDEAL)
        self._reminder_time = text_variable(body, state, TextField.REMINDER_TIME, on_change)
        self._reminder_chip: SelectionChip | None = None
        self._reminder_zone: tk.Frame | None = None

        self._toggle_frame = tk.Frame(body, bg=palette.PAPER)
        self._toggle_frame.pack(anchor="w", pady=(TOGGLE_TOP_GAP, 0))
        self._zone = tk.Frame(body, bg=palette.PAPER)
        self._zone.pack(anchor="w", fill="x")
        self.rebuild()

    def rebuild(self) -> None:
        """Draws the toggle and, when it is open, the options that apply right now."""
        state = self._state
        clear(self._toggle_frame)
        clear(self._zone)
        self._reminder_chip = self._reminder_zone = None
        SoftButton(
            self._toggle_frame,
            texts.HIDE_ADVANCED if state.advanced_visible else texts.SHOW_ADVANCED,
            self._toggle,
            palette.BUTTON_LILAC_BACKGROUND,
            palette.BUTTON_LILAC_TEXT,
            button_font=font("sans", LABEL_SIZE, "bold", master=self._toggle_frame),
            height=TOGGLE_HEIGHT,
            radius=TOGGLE_RADIUS,
        ).pack()
        if not state.advanced_visible:
            return
        zone = self._zone

        if state.measurement_choice is not MeasurementChoice.YES_NO:
            subtitle(zone, texts.REFERENCE_GOALS)
            row = tk.Frame(zone, bg=palette.PAPER)
            row.pack(anchor="w", fill="x")
            for label, variable, field in (
                (texts.MINIMUM_LABEL, self._minimum, TextField.MINIMUM),
                (texts.IDEAL_LABEL, self._ideal, TextField.IDEAL),
            ):
                column = tk.Frame(row, bg=palette.PAPER)
                column.pack(side="left", padx=(0, REFERENCE_FIELD_GAP))
                caption(column, label).pack(anchor="w")
                themed_entry(
                    column, textvariable=variable, width=NUMBER_ENTRY_CHARS, name=field.value
                ).pack(anchor="w", pady=(CAPTION_FIELD_GAP, 0), ipady=ENTRY_PAD_Y)
            hint(zone, texts.REFERENCE_GOALS_NOTE)

        if state.frequency_choice is FrequencyChoice.DAILY:
            subtitle(zone, texts.REST_DAYS)
            WeekdayChipRow(zone, state, DayGroup.REST, self._on_change).pack(anchor="w")
            hint(zone, texts.REST_DAYS_NOTE)

        subtitle(zone, texts.REMINDER_HEADING)
        self._reminder_chip = SelectionChip(
            zone,
            texts.WANT_REMINDER,
            self._toggle_reminder,
            width=REMINDER_CHIP_WIDTH,
            height=REMINDER_CHIP_HEIGHT,
        )
        self._reminder_chip.pack(anchor="w")
        self._reminder_chip.set_selected(state.has_reminder)
        self._reminder_zone = tk.Frame(zone, bg=palette.PAPER)
        self._reminder_zone.pack(anchor="w", fill="x")
        self._rebuild_reminder()

    def _toggle(self) -> None:
        self._state.toggle_advanced()
        self.rebuild()

    def _toggle_reminder(self) -> None:
        self._state.toggle_reminder()
        if self._reminder_chip is not None:
            self._reminder_chip.set_selected(self._state.has_reminder)
        self._rebuild_reminder()
        self._on_change()

    def _rebuild_reminder(self) -> None:
        zone = self._reminder_zone
        if zone is None:
            return
        clear(zone)
        if not self._state.has_reminder:
            return
        caption(zone, texts.REMINDER_TIME_LABEL).pack(anchor="w", pady=TIME_LABEL_GAP)
        themed_entry(
            zone,
            textvariable=self._reminder_time,
            width=TIME_ENTRY_CHARS,
            name=TextField.REMINDER_TIME.value,
        ).pack(anchor="w", ipady=ENTRY_PAD_Y)
        subtitle(zone, texts.REMINDER_DAYS)
        WeekdayChipRow(zone, self._state, DayGroup.REMINDER, self._on_change).pack(anchor="w")
        hint(zone, texts.REMINDER_NOTE)
