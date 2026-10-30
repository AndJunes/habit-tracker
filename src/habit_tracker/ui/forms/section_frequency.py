"""The "how often" section: a menu and, under it, the zone of the chosen frequency."""

import tkinter as tk
from collections.abc import Callable

from ...domain.enums import Period
from ..theme import palette
from ..widgets.date_picker import DatePicker
from ..widgets.soft_menu import SoftMenu
from . import texts
from .choices import DayGroup, FrequencyChoice, IntervalChoice
from .form_state import FormState
from .parts import (
    FORM_WIDTH,
    TONE_COLORS,
    WeekdayChipRow,
    build_stepper,
    caption,
    clear,
    hint,
    prompt,
    subtitle,
)

INTERVAL_MENU_WIDTH = 236
COUNTER_TOP_GAP = 8
PICKER_TOP_GAP = 2
INTERVAL_COUNTER_GAP = 8  # between the counter and the unit menu
LABEL_GAP = 8
CAPTION_GAP = 10


class FrequencySection:
    """The frequency menu and the zone that changes with the chosen option.

    ``on_change`` is called when something that the preview shows has changed;
    ``on_choice_changed`` when another frequency was chosen, which also changes what the
    advanced options offer.
    """

    def __init__(
        self,
        body: tk.Frame,
        state: FormState,
        *,
        on_change: Callable[[], object],
        on_choice_changed: Callable[[], object],
    ) -> None:
        self._state = state
        self._on_change = on_change
        self._on_choice_changed = on_choice_changed
        self._picker: DatePicker | None = None
        self._hint: tk.Label | None = None
        self._count: tk.Label | None = None
        self._interval_menu: SoftMenu | None = None

        prompt(body, texts.FREQUENCY_PROMPT)
        self._menu = SoftMenu(
            body, texts.FREQUENCY_OPTIONS, width=FORM_WIDTH, command=self._on_menu
        )
        self._menu.current(state.frequency_choice)
        self._menu.pack(anchor="w")
        self._zone = tk.Frame(body, bg=palette.PAPER)
        self._zone.pack(anchor="w", fill="x")
        self.rebuild()

    @property
    def picker(self) -> DatePicker | None:
        """The calendar of the zone, when the chosen frequency has one."""
        return self._picker

    # ---------- The zone ----------

    def rebuild(self) -> None:
        """Draws the zone of the chosen frequency from the state."""
        zone = self._zone
        clear(zone)
        self._picker = self._hint = self._count = self._interval_menu = None
        state = self._state
        choice = state.frequency_choice

        if choice is FrequencyChoice.WEEKDAYS:
            subtitle(zone, texts.PICK_WEEKDAYS)
            self._day_row(DayGroup.WEEKDAYS, self._on_change)
        elif choice is FrequencyChoice.TIMES_PER_WEEK:
            self._build_counter(Period.WEEK)
            subtitle(zone, texts.PICK_PREFERRED_DAYS)
            self._day_row(DayGroup.PREFERRED, self._on_preferred_changed)
            self._hint = hint(zone, "", name="frequency_hint")
        elif choice is FrequencyChoice.TIMES_PER_MONTH:
            self._build_counter(Period.MONTH)
            subtitle(zone, texts.PICK_MONTH_DATES)
            self._build_picker()
            self._hint = hint(zone, "", name="frequency_hint")
        elif choice is FrequencyChoice.FIXED_DATES:
            subtitle(zone, texts.PICK_DATES)
            self._build_picker()
            self._hint = hint(zone, "", name="frequency_hint")
        elif choice is FrequencyChoice.CUSTOM:
            self._build_custom()
        self.refresh_hint()

    def refresh_hint(self) -> None:
        """Repaints the line under the zone from the state (it never touches the picked dates)."""
        current = self._state.frequency_hint()
        if self._hint is not None and current is not None:
            self._hint.configure(text=current.text, fg=TONE_COLORS[current.tone])

    def update_limits(self) -> None:
        """The period of the habit changed: tells the calendar and checks the dates again."""
        if self._picker is not None:
            start, end = self._state.validity_limits()
            self._picker.set_limits(start, end)
            self.refresh_hint()

    def _day_row(self, group: DayGroup, on_change: Callable[[], object]) -> None:
        WeekdayChipRow(self._zone, self._state, group, on_change).pack(anchor="w")

    def _build_counter(self, period: Period) -> None:
        """The counter with its "times per week/month" caption."""
        row = tk.Frame(self._zone, bg=palette.PAPER)
        row.pack(anchor="w", pady=(COUNTER_TOP_GAP, 0))
        self._count = build_stepper(
            row, self._state.times(period), lambda step: self._step_times(period, step)
        )
        caption(row, texts.times_per(period)).pack(side="left", padx=(CAPTION_GAP, 0))

    def _build_picker(self) -> None:
        """The calendar of the zone; what was picked is kept when the frequency changes."""
        start, end = self._state.validity_limits()
        picker = DatePicker(
            self._zone,
            today=self._state.today,
            selection=self._state.chosen_dates,
            minimum=start,
            maximum=end,
            on_change=self._on_dates_changed,
            width=FORM_WIDTH,
        )
        picker.pack(anchor="w", pady=(PICKER_TOP_GAP, 0))
        self._picker = picker

    def _build_custom(self) -> None:
        state = self._state
        zone = self._zone
        row = tk.Frame(zone, bg=palette.PAPER)
        row.pack(anchor="w", pady=(COUNTER_TOP_GAP, 0), fill="x")
        caption(row, texts.EVERY).pack(side="left", padx=(0, LABEL_GAP))
        menu = SoftMenu(
            row, texts.INTERVAL_OPTIONS, width=INTERVAL_MENU_WIDTH, command=self._on_interval_menu
        )
        if state.interval_choice is IntervalChoice.PICKED_DATES:
            menu.current(IntervalChoice.PICKED_DATES)
        else:
            self._count = build_stepper(
                row, state.interval_every, self._step_interval, gap_after=INTERVAL_COUNTER_GAP
            )
            menu.current(state.interval_choice)
        menu.pack(side="left")
        self._interval_menu = menu
        if state.interval_choice is IntervalChoice.PICKED_DATES:
            self._build_picker()
            self._hint = hint(zone, "", name="frequency_hint")
        else:
            hint(zone, texts.INTERVAL_FROM_START)

    # ---------- What the person does ----------

    def _on_menu(self) -> None:
        self._state.choose_frequency(FrequencyChoice(self._menu.current()))
        self.rebuild()
        self._on_change()
        self._on_choice_changed()

    def _on_interval_menu(self) -> None:
        if self._interval_menu is not None:
            self._state.interval_choice = IntervalChoice(self._interval_menu.current())
            self.rebuild()
            self._on_change()

    def _step_times(self, period: Period, step: int) -> None:
        value = self._state.adjust_times(period, step)
        if self._count is not None:
            self._count.configure(text=str(value))
        self.refresh_hint()
        self._on_change()

    def _step_interval(self, step: int) -> None:
        value = self._state.adjust_interval(step)
        if self._count is not None:
            self._count.configure(text=str(value))
        self._on_change()

    def _on_preferred_changed(self) -> None:
        self.refresh_hint()
        self._on_change()

    def _on_dates_changed(self) -> None:
        if self._picker is not None:
            self._state.set_dates(self._picker.dates())
        self.refresh_hint()
        self._on_change()
