"""Delete mode: the state shared by every screen that offers it."""

import tkinter as tk

import pytest

from habit_tracker.service import HabitService
from habit_tracker.ui.controllers.delete_mode import DeleteMode
from habit_tracker.ui.controllers.habit_actions import HabitActions

from .conftest import FlakyRepository, RecordingDialogs


class Redraws:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> None:
        self.count += 1


@pytest.fixture
def redraws() -> Redraws:
    return Redraws()


@pytest.fixture
def mode(
    tk_root: tk.Tk, service: HabitService, redraws: Redraws, dialogs: RecordingDialogs
) -> DeleteMode:
    actions = HabitActions(service, tk_root, on_change=redraws, dialogs=dialogs)
    return DeleteMode(service, actions, on_change=redraws, dialogs=dialogs)


def test_it_starts_off_with_nothing_selected(mode: DeleteMode) -> None:
    assert not mode.active
    assert mode.selected == frozenset()
    assert mode.count == 0


def test_entering_starts_selecting_and_redraws_the_screen(
    mode: DeleteMode, redraws: Redraws
) -> None:
    mode.enter()

    assert mode.active
    assert redraws.count == 1


def test_with_nothing_to_delete_it_says_so_instead_of_entering(
    tk_root: tk.Tk, empty_service: HabitService, redraws: Redraws, dialogs: RecordingDialogs
) -> None:
    actions = HabitActions(empty_service, tk_root, on_change=redraws, dialogs=dialogs)
    empty = DeleteMode(empty_service, actions, on_change=redraws, dialogs=dialogs)

    empty.enter()

    assert not empty.active
    assert dialogs.shown == [("info", "Aviso", "No hay hábitos para eliminar.")]
    assert redraws.count == 0


def test_toggling_marks_and_unmarks_habits_and_counts_them(
    mode: DeleteMode, service: HabitService, redraws: Redraws
) -> None:
    first, second, third = service.habits()[:3]
    mode.enter()

    mode.toggle(first)
    mode.toggle(third)
    assert mode.selected == {first.id, third.id}
    assert mode.count == 2
    assert mode.is_selected(first)
    assert not mode.is_selected(second)

    mode.toggle(third)
    assert mode.selected == {first.id}
    assert redraws.count == 4  # entering plus three toggles


def test_entering_again_forgets_a_previous_selection(
    mode: DeleteMode, service: HabitService
) -> None:
    mode.enter()
    mode.toggle(service.habits()[0])
    mode.cancel()

    mode.enter()

    assert mode.count == 0


def test_cancelling_leaves_the_mode_and_deletes_nothing(
    mode: DeleteMode, service: HabitService, redraws: Redraws
) -> None:
    total = len(service.habits())
    mode.enter()
    mode.toggle(service.habits()[0])
    redraws.count = 0

    mode.cancel()

    assert not mode.active
    assert mode.count == 0
    assert len(service.habits()) == total
    assert redraws.count == 1


def test_confirming_deletes_the_selection_and_leaves_the_mode(
    mode: DeleteMode, service: HabitService, redraws: Redraws, dialogs: RecordingDialogs
) -> None:
    first, second, *rest = service.habits()
    mode.enter()
    mode.toggle(first)
    mode.toggle(second)
    redraws.count = 0

    mode.confirm()

    assert [habit.id for habit in service.habits()] == [habit.id for habit in rest]
    assert not mode.active
    assert mode.count == 0
    assert redraws.count == 1  # a single redraw for deleting and leaving the mode


def test_declining_the_confirmation_keeps_the_mode_and_the_selection(
    mode: DeleteMode, service: HabitService, redraws: Redraws, dialogs: RecordingDialogs
) -> None:
    total = len(service.habits())
    first, second = service.habits()[:2]
    mode.enter()
    mode.toggle(first)
    mode.toggle(second)
    redraws.count = 0
    dialogs.answers = [False]  # the person changes their mind at the confirmation

    mode.confirm()

    assert len(service.habits()) == total
    assert mode.active
    assert mode.selected == {first.id, second.id}
    assert redraws.count == 0  # nothing changed, so there is nothing to redraw


def test_a_failure_halfway_keeps_the_mode_with_only_what_is_left_marked(
    mode: DeleteMode,
    service: HabitService,
    repository: FlakyRepository,
    redraws: Redraws,
    dialogs: RecordingDialogs,
) -> None:
    first, second, third = service.habits()[:3]
    mode.enter()
    for habit in (first, second, third):
        mode.toggle(habit)
    redraws.count = 0
    repository.writes_allowed = 1  # the first deletion goes through, the second fails

    mode.confirm()

    assert service.find_habit(first.id) is None
    assert mode.active
    assert mode.selected == {second.id, third.id}
    assert dialogs.kinds() == ["error"]
    assert redraws.count == 1  # the list lost a habit, so it is drawn again

    repository.writes_allowed = None  # the problem is fixed: the same button works again
    mode.confirm()

    assert [habit.id for habit in service.habits() if habit.id in {second.id, third.id}] == []
    assert not mode.active


def test_a_failure_before_anything_was_deleted_changes_nothing_on_screen(
    mode: DeleteMode,
    service: HabitService,
    repository: FlakyRepository,
    redraws: Redraws,
    dialogs: RecordingDialogs,
) -> None:
    first = service.habits()[0]
    mode.enter()
    mode.toggle(first)
    redraws.count = 0
    repository.failing = True

    mode.confirm()

    assert mode.active
    assert mode.selected == {first.id}
    assert dialogs.kinds() == ["error"]
    assert redraws.count == 0


def test_reset_leaves_the_mode_without_redrawing(
    mode: DeleteMode, service: HabitService, redraws: Redraws
) -> None:
    mode.enter()
    mode.toggle(service.habits()[0])
    redraws.count = 0

    mode.reset()

    assert not mode.active
    assert mode.count == 0
    assert redraws.count == 0
