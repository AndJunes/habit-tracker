"""The "how to measure" section: yes/no, or a goal in some unit."""

import tkinter as tk
from collections.abc import Callable

from ..theme import palette
from ..widgets.soft_menu import SoftMenu
from ..widgets.text_entry import themed_entry
from . import texts
from .choices import MeasurementChoice, TextField
from .form_state import FormState
from .parts import (
    ENTRY_PAD_Y,
    FORM_WIDTH,
    NUMBER_ENTRY_CHARS,
    caption,
    clear,
    prompt,
    subtitle,
    text_variable,
)
from .units import CUSTOM_UNIT

UNIT_MENU_WIDTH = 236
ROW_TOP_GAP = 10
FIELD_GAP = 16  # between the goal and the unit menu
CAPTION_FIELD_GAP = 4


class MeasurementSection:
    """The measurement menu and the goal and unit fields that appear when something is measured.

    ``on_change`` is called when something that the preview shows has changed;
    ``on_choice_changed`` when the way of measuring changed, which also changes what the
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
        self._unit_menu: SoftMenu | None = None
        # The variables outlive the entries: the zone is rebuilt without losing what was typed.
        self._goal = text_variable(body, state, TextField.GOAL, on_change)
        self._custom_unit = text_variable(body, state, TextField.CUSTOM_UNIT, on_change)

        prompt(body, texts.MEASUREMENT_PROMPT)
        self._menu = SoftMenu(
            body, texts.MEASUREMENT_OPTIONS, width=FORM_WIDTH, command=self._on_menu
        )
        self._menu.current(state.measurement_choice)
        self._menu.pack(anchor="w")
        self._zone = tk.Frame(body, bg=palette.PAPER)
        self._zone.pack(anchor="w", fill="x")
        self.rebuild()

    def rebuild(self) -> None:
        """Draws the fields for the chosen way of measuring, with the units of the area."""
        zone = self._zone
        clear(zone)
        self._unit_menu = None
        state = self._state
        if state.measurement_choice is MeasurementChoice.YES_NO:
            return

        options = state.unit_options()
        row = tk.Frame(zone, bg=palette.PAPER)
        row.pack(anchor="w", fill="x", pady=(ROW_TOP_GAP, 0))
        left = tk.Frame(row, bg=palette.PAPER)
        left.pack(side="left", anchor="n")
        caption(left, texts.GOAL_LABEL).pack(anchor="w")
        themed_entry(
            left, textvariable=self._goal, width=NUMBER_ENTRY_CHARS, name=TextField.GOAL.value
        ).pack(anchor="w", pady=(CAPTION_FIELD_GAP, 0), ipady=ENTRY_PAD_Y)
        right = tk.Frame(row, bg=palette.PAPER)
        right.pack(side="left", padx=(FIELD_GAP, 0), anchor="n")
        caption(right, texts.UNIT_LABEL).pack(anchor="w")
        menu = SoftMenu(right, options, width=UNIT_MENU_WIDTH, command=self._on_unit)
        menu.current(options.index(state.unit_choice))
        menu.pack(anchor="w", pady=(CAPTION_FIELD_GAP, 0))
        self._unit_menu = menu

        if state.unit_choice == CUSTOM_UNIT:
            subtitle(zone, texts.CUSTOM_UNIT_LABEL)
            themed_entry(
                zone, textvariable=self._custom_unit, name=TextField.CUSTOM_UNIT.value
            ).pack(fill="x", ipady=ENTRY_PAD_Y)

    def _on_menu(self) -> None:
        self._state.select_measurement(MeasurementChoice(self._menu.current()))
        self.rebuild()
        self._on_change()
        self._on_choice_changed()

    def _on_unit(self) -> None:
        if self._unit_menu is not None:
            self._state.choose_unit(self._unit_menu.current())
            self.rebuild()
            self._on_change()
