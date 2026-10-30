"""What a click on a habit does: mark, unmark, add, edit and delete."""

import tkinter as tk
from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.domain.enums import MeasurementKind
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import RECOMMENDED_MAX_HABITS, Habit, Measurement
from habit_tracker.service import HabitService
from habit_tracker.ui.controllers.habit_actions import HabitActions, format_number

from .conftest import FlakyRepository, FormRecorder, RecordingDialogs, ValuePrompt


class Changes:
    """Counts how many times the screen was asked to redraw."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> None:
        self.count += 1


@pytest.fixture
def changes() -> Changes:
    return Changes()


@pytest.fixture
def actions(
    tk_root: tk.Tk, service: HabitService, changes: Changes, dialogs: RecordingDialogs
) -> HabitActions:
    return HabitActions(service, tk_root, on_change=changes, dialogs=dialogs)


@pytest.fixture
def empty_actions(
    tk_root: tk.Tk, empty_service: HabitService, changes: Changes, dialogs: RecordingDialogs
) -> HabitActions:
    """Actions over a service with no habits, so the add warning does not come into play."""
    return HabitActions(empty_service, tk_root, on_change=changes, dialogs=dialogs)


def by_name(service: HabitService, name: str) -> Habit:
    return next(habit for habit in service.habits() if habit.name == name)


@pytest.fixture
def measured(service: HabitService) -> Habit:
    """A habit measured in pages, not done on any day yet."""
    return service.add_habit(
        name="Leer",
        area_id="carrera",
        frequency=Daily(),
        start=date(2026, 9, 29),
        measurement=Measurement(MeasurementKind.QUANTITY, 10, "páginas"),
    )


@pytest.mark.parametrize(
    ("value", "text"),
    [(None, ""), (10, "10"), (10.0, "10"), (2.5, "2.5"), (0, "0"), (1234567.0, "1234567")],
)
def test_format_number_drops_the_decimal_point_of_whole_numbers(
    value: float | None, text: str
) -> None:
    assert format_number(value) == text


class TestToggle:
    def test_a_plain_habit_is_marked_directly(
        self,
        actions: HabitActions,
        service: HabitService,
        today: date,
        value_prompt: ValuePrompt,
        dialogs: RecordingDialogs,
        changes: Changes,
    ) -> None:
        train = by_name(service, "Entrenar 3 veces por semana")
        assert not train.is_done(today)

        actions.toggle(train)

        assert service.get_habit(train.id).is_done(today)
        assert value_prompt.calls == []
        assert dialogs.asked == []
        assert dialogs.shown == []
        assert changes.count == 1

    def test_a_measured_habit_asks_for_the_value_and_stores_it(
        self, actions: HabitActions, service: HabitService, measured: Habit, today: date,
        value_prompt: ValuePrompt,
    ) -> None:  # fmt: skip
        value_prompt.answer = 12

        actions.toggle(measured)

        assert value_prompt.calls == [(measured, today)]
        assert measured.completions == {today: 12}

    def test_cancelling_the_value_prompt_marks_nothing_and_does_not_redraw(
        self, actions: HabitActions, measured: Habit, today: date, value_prompt: ValuePrompt,
        changes: Changes,
    ) -> None:  # fmt: skip
        value_prompt.answer = None

        actions.toggle(measured)

        assert not measured.is_done(today)
        assert changes.count == 0

    def test_unmarking_a_habit_with_a_value_asks_before_losing_it(
        self, actions: HabitActions, measured: Habit, today: date, value_prompt: ValuePrompt,
        dialogs: RecordingDialogs, changes: Changes,
    ) -> None:  # fmt: skip
        value_prompt.answer = 12
        actions.toggle(measured)
        changes.count = 0

        dialogs.answers = [False]  # "I don't want to lose the value"
        actions.toggle(measured)
        assert measured.completions == {today: 12}
        assert changes.count == 0

        dialogs.answers = [True]
        actions.toggle(measured)
        assert measured.completions == {}
        assert changes.count == 1

    def test_the_unmark_warning_says_today_and_shows_the_amount(
        self, actions: HabitActions, measured: Habit, today: date, value_prompt: ValuePrompt,
        dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        value_prompt.answer = 12
        actions.toggle(measured)

        actions.toggle(measured)

        ((title, message),) = dialogs.asked
        assert title == "Quitar el registro"
        assert "la marca de hoy" in message
        assert "(12 páginas)" in message

    def test_the_unmark_warning_names_the_real_date_of_another_day(
        self, actions: HabitActions, measured: Habit, value_prompt: ValuePrompt,
        dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        other_day = date(2026, 11, 3)
        value_prompt.answer = 12.5
        actions.toggle(measured, other_day)
        assert measured.completions == {other_day: 12.5}

        actions.toggle(measured, other_day)

        ((_, message),) = dialogs.asked
        assert "la marca del 3 nov" in message
        assert "(12.5 páginas)" in message
        assert "hoy" not in message

    def test_unmarking_a_habit_without_a_value_does_not_ask(
        self, actions: HabitActions, service: HabitService, today: date,
        dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        train = by_name(service, "Entrenar 3 veces por semana")
        actions.toggle(train)

        actions.toggle(train)

        assert not train.is_done(today)
        assert dialogs.asked == []

    def test_a_rejected_change_is_explained_and_the_screen_is_redrawn(
        self, actions: HabitActions, service: HabitService, dialogs: RecordingDialogs,
        changes: Changes,
    ) -> None:  # fmt: skip
        gone = by_name(service, "Entrenar 3 veces por semana")
        service.delete_habit(gone.id)  # the screen still holds the old habit

        actions.toggle(gone)

        assert dialogs.shown == [("warning", "Aviso", "Ese hábito ya no existe.")]
        assert changes.count == 1  # redrawn, so the row that no longer exists goes away

    def test_a_failed_write_shows_an_error_and_the_next_click_still_works(
        self, actions: HabitActions, service: HabitService, repository: FlakyRepository,
        today: date, dialogs: RecordingDialogs, changes: Changes,
    ) -> None:  # fmt: skip
        train = by_name(service, "Entrenar 3 veces por semana")
        repository.failing = True

        actions.toggle(train)

        assert dialogs.kinds() == ["error"]
        assert dialogs.shown[0][1] == "No se pudo guardar"
        assert not train.is_done(today)

        repository.failing = False
        actions.toggle(train)

        assert train.is_done(today)
        assert dialogs.kinds() == ["error"]  # nothing new was reported
        assert changes.count == 2


class TestAddAndEdit:
    def test_it_opens_an_empty_form_that_redraws_the_screen_once_saved(
        self, empty_actions: HabitActions, forms: FormRecorder, tk_root: tk.Tk,
        empty_service: HabitService, dialogs: RecordingDialogs, changes: Changes,
    ) -> None:  # fmt: skip
        empty_actions.add_habit()

        (call,) = forms.calls
        assert call.habit is None
        assert call.master is tk_root
        assert call.service is empty_service
        assert dialogs.asked == []
        assert changes.count == 0  # nothing yet: the person has not saved

        forms.save(empty_service.add_habit(name="Nuevo", area_id="salud", frequency=Daily()))
        assert changes.count == 1

    def test_it_warns_before_going_past_the_recommended_number(
        self, actions: HabitActions, forms: FormRecorder, service: HabitService,
        add_daily_habit: Callable[[HabitService, str], Habit], dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        for number in range(RECOMMENDED_MAX_HABITS - len(service.habits())):
            add_daily_habit(service, f"Extra {number}")
        assert len(service.active_habits()) == RECOMMENDED_MAX_HABITS

        dialogs.answers = [False]  # "no, better not"
        actions.add_habit()
        assert len(dialogs.asked) == 1
        assert forms.calls == []

        dialogs.answers = [True]  # "yes, I want another"
        actions.add_habit()
        assert len(forms.calls) == 1

    def test_the_warning_is_neutral_and_gives_the_count(
        self, actions: HabitActions, service: HabitService, forms: FormRecorder,
        add_daily_habit: Callable[[HabitService, str], Habit], dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        add_daily_habit(service, "Extra")
        actions.add_habit()

        ((title, message),) = dialogs.asked
        assert title == "Un momento"
        assert "Ya tienes 7 hábitos activos." in message
        assert "regla" not in message.lower()

    def test_habits_that_already_ended_do_not_count_toward_the_warning(
        self, empty_actions: HabitActions, forms: FormRecorder, empty_service: HabitService,
        dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        ended_start, ended_end = date(2026, 8, 1), date(2026, 9, 1)
        for number in range(RECOMMENDED_MAX_HABITS):
            empty_service.add_habit(
                name=f"Pasado {number}", area_id="salud", frequency=Daily(),
                start=ended_start, end=ended_end,
            )  # fmt: skip
        empty_actions.add_habit()

        assert dialogs.asked == []
        assert len(forms.calls) == 1

    def test_editing_opens_the_form_with_that_habit(
        self, actions: HabitActions, forms: FormRecorder, service: HabitService, changes: Changes,
    ) -> None:  # fmt: skip
        finances = by_name(service, "Viernes de finanzas (1 h)")

        actions.edit_habit(finances)

        (call,) = forms.calls
        assert call.habit is finances
        forms.save(finances)
        assert changes.count == 1


class TestDelete:
    def test_it_lists_the_habits_and_deletes_them_with_their_history_once_confirmed(
        self, actions: HabitActions, service: HabitService, dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        first, second, third = service.habits()[:3]
        remaining_ids = [
            habit.id for habit in service.habits() if habit.id not in {first.id, third.id}
        ]

        deleted = actions.delete_habits({first.id, third.id})

        assert deleted is True
        ((title, message),) = dialogs.asked
        assert title == "Confirmar"
        assert message.startswith("¿Eliminar 2 hábitos y todo su historial?")
        assert f"• {first.name}" in message
        assert f"• {third.name}" in message
        assert second.name not in message
        assert [habit.id for habit in service.habits()] == remaining_ids
        assert second.id in remaining_ids

    def test_a_single_habit_is_named_in_the_singular(
        self, actions: HabitActions, service: HabitService, dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        actions.delete_habits({service.habits()[0].id})

        assert dialogs.asked[0][1].startswith("¿Eliminar 1 hábito y todo su historial?")

    def test_declining_the_confirmation_deletes_nothing(
        self, actions: HabitActions, service: HabitService, dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        total = len(service.habits())
        dialogs.answers = [False]

        assert actions.delete_habits({h.id for h in service.habits()[:2]}) is False

        assert len(service.habits()) == total

    def test_nothing_to_delete_asks_nothing(
        self, actions: HabitActions, dialogs: RecordingDialogs
    ) -> None:
        assert actions.delete_habits(set()) is False
        assert actions.delete_habits({9999}) is False
        assert dialogs.asked == []

    def test_a_failure_stops_the_rest_and_is_reported(
        self, actions: HabitActions, service: HabitService, repository: FlakyRepository,
        dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        first, second, third = service.habits()[:3]
        repository.writes_allowed = 1  # the second deletion fails

        deleted = actions.delete_habits({first.id, second.id, third.id})

        assert deleted is False
        assert dialogs.kinds() == ["error"]
        assert service.find_habit(first.id) is None
        assert service.find_habit(second.id) is not None
        assert service.find_habit(third.id) is not None
