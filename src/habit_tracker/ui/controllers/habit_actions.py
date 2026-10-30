"""What the person can do to a habit from the screens, written once for all of them."""

import tkinter as tk
from collections.abc import Callable, Collection
from datetime import date
from functools import partial

from ...domain.models import RECOMMENDED_MAX_HABITS, Habit
from ...service import HabitService
from ..calendar_es import short_date_text
from ..forms.habit_form import HabitFormDialog
from ..forms.value_dialog import ask_value
from ..views import texts
from .dialogs import Dialogs, TkDialogs, attempt


def format_number(value: float | None) -> str:
    """``10`` and ``10.0`` become ``"10"``, ``2.5`` stays ``"2.5"`` and ``None`` becomes ``""``."""
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else str(value)


class HabitActions:
    """Mark, add, edit and delete habits on behalf of a screen.

    The screen passes the widget the dialogs open over (``master``) and ``on_change``,
    which it calls whenever the data may have changed so that the screen redraws itself.
    Deleting is the exception: the caller redraws, because leaving delete mode and removing
    the habits must show up as one change.
    """

    def __init__(
        self,
        service: HabitService,
        master: tk.Misc,
        *,
        on_change: Callable[[], None],
        dialogs: Dialogs | None = None,
    ) -> None:
        self._service = service
        self._master = master
        self._on_change = on_change
        self._dialogs = dialogs or TkDialogs()

    def toggle(self, habit: Habit, day: date | None = None) -> None:
        """Mark the habit as done on ``day`` (today), or unmark it if it already was.

        A measured habit asks how much was done when it is marked, and warns that the
        recorded value is lost when it is unmarked. Cancelling either leaves everything as it was.
        """
        day = day or self._service.today()
        if habit.is_done(day):
            if not self._confirm_unmark(habit, day):
                return
            attempt(self._dialogs, lambda: self._service.mark(habit.id, False, day=day))
        else:
            value = None
            if habit.measurement is not None:
                value = ask_value(self._master, habit, day)
                if value is None:
                    return
            attempt(
                self._dialogs, lambda: self._service.mark(habit.id, True, day=day, value=value)
            )
        self._on_change()

    def add_habit(self) -> None:
        """Open the form for a new habit, after warning when there are already many."""
        active = len(self._service.active_habits())
        if active >= RECOMMENDED_MAX_HABITS and not self._dialogs.ask_yes_no(
            texts.TOO_MANY_HABITS_TITLE, texts.too_many_habits_message(active)
        ):
            return
        self._open_form(None)

    def edit_habit(self, habit: Habit) -> None:
        """Open the form filled in with the habit's data."""
        self._open_form(habit)

    def delete_habits(self, habit_ids: Collection[int]) -> bool:
        """Delete the habits and their history, after listing them and asking to confirm.

        Returns ``True`` when every one of them was deleted. If a deletion fails the person is
        told, the ones after it are left alone and ``False`` is returned; the ones before it
        stay deleted, so the caller should read the service again instead of assuming.
        """
        chosen = [habit for habit in self._service.habits() if habit.id in habit_ids]
        if not chosen:
            return False
        names = [habit.name for habit in chosen]
        if not self._dialogs.ask_yes_no(
            texts.CONFIRM_TITLE, texts.delete_confirmation(len(chosen), names)
        ):
            return False
        return all(
            attempt(self._dialogs, partial(self._service.delete_habit, habit.id))
            for habit in chosen
        )

    def _open_form(self, habit: Habit | None) -> None:
        HabitFormDialog(
            self._master,
            self._service,
            habit=habit,
            on_saved=lambda _saved: self._on_change(),
        )

    def _confirm_unmark(self, habit: Habit, day: date) -> bool:
        """Unmarking a habit that has a recorded value throws that value away, so ask first."""
        value = habit.completions.get(day)
        if value is None:
            return True
        unit = habit.measurement.unit if habit.measurement is not None else ""
        amount = f"{format_number(value)} {unit}".strip()
        when = "de hoy" if day == self._service.today() else f"del {short_date_text(day)}"
        return self._dialogs.ask_yes_no(texts.UNMARK_TITLE, texts.unmark_message(when, amount))
