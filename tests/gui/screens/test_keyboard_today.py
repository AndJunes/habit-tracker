"""The rows of the "Hoy" tab with the keyboard: Tab order, the ring, the keys and the focus.

Whatever can be checked without real key events is: what is reachable, the ring that a focus event
draws, and where the focus is after the list is drawn again. The tests that press keys need the
window system to give the window the keyboard focus; they skip, saying so, when it does not.
"""

import tkinter as tk
from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.domain.models import Habit
from habit_tracker.service import HabitService
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.focus import ACTIVATION_KEYS, RING_WIDTH
from habit_tracker.ui.views.helpers import EDIT_KEYS, FOCUS_RING_TAG
from habit_tracker.ui.views.today import CONTENT_WIDTH, ROW_HEIGHT, TodayView

from .conftest import FormRecorder, RecordingDialogs, Tree, ValuePrompt

TRAIN = "Entrenar 3 veces por semana"  # a quota that is not marked today
STUDY = "Bloque de estudio"  # measured, marked today
FINANCES = "Viernes de finanzas (1 h)"  # only on Fridays, and today is a Thursday


@pytest.fixture
def make_view(
    window: tk.Toplevel,
    dialogs: RecordingDialogs,
    forms: FormRecorder,
    value_prompt: ValuePrompt,
) -> Callable[[HabitService], TodayView]:
    def make(service: HabitService) -> TodayView:
        view = TodayView(window, service, dialogs=dialogs)
        view.pack()
        window.update()
        return view

    return make


@pytest.fixture
def view(make_view: Callable[[HabitService], TodayView], service: HabitService) -> TodayView:
    return make_view(service)


def rows(view: TodayView) -> list[tk.Canvas]:
    return [child for child in view.list_frame.winfo_children() if isinstance(child, tk.Canvas)]


def row_of(view: TodayView, name: str) -> tk.Canvas:
    return next(row for row in rows(view) if name in Tree.texts(row))


def habit_named(service: HabitService, name: str) -> Habit:
    return next(habit for habit in service.habits() if habit.name == name)


def is_tab_stop(widget: tk.Misc) -> bool:
    return str(widget.cget("takefocus")) == "1"


def rings(canvas: tk.Canvas) -> tuple[int, ...]:
    return canvas.find_withtag(FOCUS_RING_TAG)


def snapshot(canvas: tk.Canvas) -> list[tuple[str, tuple[float, ...], str]]:
    """Everything that is drawn on the canvas: kind, coordinates and fill of each item."""
    return [
        (canvas.type(item) or "", tuple(canvas.coords(item)), str(canvas.itemcget(item, "fill")))
        for item in canvas.find_all()
    ]


def trash_buttons(view: TodayView) -> list[tk.Canvas]:
    return list(Tree.trash_buttons(view.list_frame))


def focus_or_skip(widget: tk.Misc) -> None:
    """Give ``widget`` the keyboard focus, or skip the test if the system will not."""
    widget.focus_force()
    widget.update()
    if widget.focus_get() is not widget:
        pytest.skip("the window did not get the keyboard focus")


class TestReachability:
    def test_a_row_is_in_the_tab_order_only_when_it_can_be_marked_today(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        for habit in service.habits():
            assert is_tab_stop(row_of(view, habit.name)) == habit.applies_on(today), habit.name

    def test_there_is_at_least_one_row_to_reach_in_the_demo(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        assert any(habit.applies_on(today) for habit in service.habits())

    def test_tab_goes_through_the_rows_in_the_order_they_are_drawn(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        reachable = [
            row_of(view, habit.name) for habit in service.habits() if habit.applies_on(today)
        ]
        assert len(reachable) > 1
        visited = [reachable[0]]
        for _ in reachable[1:]:
            visited.append(visited[-1].tk_focusNext())

        assert visited == reachable

    def test_the_dimmed_row_is_skipped_by_tab_and_still_edits_with_the_mouse(
        self, view: TodayView
    ) -> None:
        row = row_of(view, FINANCES)

        assert str(row.cget("takefocus")) == "0"
        assert not row.bind("<space>")
        assert not row.bind("<e>")
        assert row.bind("<Button-3>")

    def test_a_row_that_can_be_marked_answers_to_the_activation_and_edit_keys(
        self, view: TodayView
    ) -> None:
        row = row_of(view, TRAIN)

        for key in (*ACTIVATION_KEYS, *EDIT_KEYS):
            assert row.bind(key), key


class TestRing:
    def test_the_row_shows_nothing_extra_until_the_keyboard_has_the_focus(
        self, view: TodayView
    ) -> None:
        assert all(rings(row) == () for row in rows(view))

    def test_the_ring_is_drawn_while_the_row_has_the_focus_and_taken_away_after(
        self, view: TodayView
    ) -> None:
        row = row_of(view, TRAIN)

        row.event_generate("<FocusIn>")
        assert len(rings(row)) == 1
        (ring,) = rings(row)
        assert row.itemcget(ring, "outline") == palette.FOCUS_RING
        assert row.itemcget(ring, "fill") == ""

        row.event_generate("<FocusOut>")
        assert rings(row) == ()

    def test_getting_the_focus_twice_does_not_stack_rings(self, view: TodayView) -> None:
        row = row_of(view, TRAIN)

        row.event_generate("<FocusIn>")
        row.event_generate("<FocusIn>")

        assert len(rings(row)) == 1

    def test_the_whole_stroke_stays_inside_the_row(self, view: TodayView) -> None:
        row = row_of(view, TRAIN)

        row.event_generate("<FocusIn>")

        (ring,) = rings(row)
        coords = row.coords(ring)
        xs, ys = coords[0::2], coords[1::2]
        half = RING_WIDTH / 2
        assert min(xs) - half >= 0
        assert max(xs) + half <= CONTENT_WIDTH
        assert min(ys) - half >= 0
        assert max(ys) + half <= ROW_HEIGHT

    def test_the_ring_is_above_everything_else_in_the_row(self, view: TodayView) -> None:
        row = row_of(view, TRAIN)

        row.event_generate("<FocusIn>")

        assert row.find_all()[-1] == rings(row)[0]

    def test_the_row_keeps_its_size_with_the_ring(self, view: TodayView) -> None:
        row = row_of(view, TRAIN)

        row.event_generate("<FocusIn>")

        assert (int(row["width"]), int(row["height"])) == (CONTENT_WIDTH, ROW_HEIGHT)

    def test_after_the_focus_comes_and_goes_the_row_is_exactly_as_it_was(
        self, view: TodayView
    ) -> None:
        row = row_of(view, TRAIN)
        before = snapshot(row)

        row.event_generate("<FocusIn>")
        row.event_generate("<FocusOut>")

        assert snapshot(row) == before

    def test_the_ring_also_shows_on_a_row_of_delete_mode(self, view: TodayView) -> None:
        view.delete_mode.enter()
        view.update()  # the new rows get events and the focus only once they are mapped
        row = row_of(view, FINANCES)

        row.event_generate("<FocusIn>")

        assert len(rings(row)) == 1


class TestFocusAfterTheListIsDrawnAgain:
    def test_marking_a_habit_keeps_the_focus_on_its_row(
        self, view: TodayView, service: HabitService
    ) -> None:
        row = row_of(view, TRAIN)
        row.focus_set()

        view.actions.toggle(habit_named(service, TRAIN))

        new_row = row_of(view, TRAIN)
        assert new_row is not row  # the list was built again
        assert view.focus_lastfor() is new_row

    def test_the_focus_stays_with_its_habit_when_another_one_changes(
        self, view: TodayView, service: HabitService
    ) -> None:
        row_of(view, STUDY).focus_set()

        view.actions.toggle(habit_named(service, TRAIN))

        assert view.focus_lastfor() is row_of(view, STUDY)

    def test_a_focus_that_was_somewhere_else_is_left_alone(
        self, view: TodayView, service: HabitService
    ) -> None:
        view.priority_entry.focus_set()

        view.actions.toggle(habit_named(service, TRAIN))

        assert view.focus_lastfor() is view.priority_entry

    def test_nothing_is_focused_after_a_redraw_if_nothing_was(
        self, view: TodayView, service: HabitService
    ) -> None:
        view.actions.toggle(habit_named(service, TRAIN))

        assert view.focus_lastfor() is view.winfo_toplevel()

    def test_the_focus_of_a_habit_that_was_deleted_goes_nowhere(
        self, view: TodayView, service: HabitService
    ) -> None:
        row_of(view, TRAIN).focus_set()
        service.delete_habit(habit_named(service, TRAIN).id)

        view.refresh()

        assert view.focus_lastfor() is view.winfo_toplevel()

    def test_a_ring_is_not_carried_over_to_the_rows_that_never_had_the_focus(
        self, view: TodayView
    ) -> None:
        row = row_of(view, TRAIN)
        row.focus_set()
        row.event_generate("<FocusIn>")

        view.refresh()

        # (The row that gets the focus back may show its own ring, as soon as the system says so.)
        assert all(rings(other) == () for other in rows(view) if other is not view.focus_lastfor())


class TestDeleteMode:
    def test_every_row_can_be_reached_also_those_not_due_today(self, view: TodayView) -> None:
        view.delete_mode.enter()

        assert all(is_tab_stop(row) for row in rows(view))

    def test_the_rows_select_with_the_same_keys_and_do_not_edit(self, view: TodayView) -> None:
        view.delete_mode.enter()

        for row in rows(view):
            for key in ACTIVATION_KEYS:
                assert row.bind(key), key
            for key in EDIT_KEYS:
                assert not row.bind(key), key

    def test_tab_goes_from_a_row_to_its_trash_can_and_on_to_the_next_row(
        self, view: TodayView
    ) -> None:
        view.delete_mode.enter()
        view.update()  # Tab skips the trash cans (windows of the rows) until they are mapped
        first, second = rows(view)[:2]
        first_trash, second_trash = trash_buttons(view)[:2]

        assert first.tk_focusNext() is first_trash
        assert first_trash.tk_focusNext() is second
        assert second.tk_focusNext() is second_trash

    def test_selecting_a_row_keeps_the_focus_on_it(
        self, view: TodayView, service: HabitService
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()
        view.update()  # the new rows get the focus only once they are mapped
        rows(view)[1].focus_set()

        view.delete_mode.toggle(habits[1])

        assert view.delete_mode.selected == {habits[1].id}
        assert view.focus_lastfor() is rows(view)[1]

    def test_selecting_with_a_trash_can_keeps_the_focus_on_that_trash_can(
        self, view: TodayView, service: HabitService
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()
        view.update()  # the new rows get the focus only once they are mapped
        trash_buttons(view)[2].focus_set()

        view.delete_mode.toggle(habits[2])

        assert view.focus_lastfor() is trash_buttons(view)[2]

    def test_a_row_and_its_trash_can_keep_their_own_focus(
        self, view: TodayView, service: HabitService
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()
        view.update()  # the new rows get the focus only once they are mapped
        rows(view)[0].focus_set()

        view.delete_mode.toggle(habits[3])

        assert view.focus_lastfor() is rows(view)[0]
        assert view.focus_lastfor() not in trash_buttons(view)


class TestRealKeys:
    def test_space_marks_the_habit_and_the_focus_stays_on_the_row(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        train = habit_named(service, TRAIN)
        row = row_of(view, TRAIN)
        focus_or_skip(row)

        row.event_generate("<space>")
        view.update()

        assert service.get_habit(train.id).is_done(today)
        assert view.focus_get() is row_of(view, TRAIN)

    def test_enter_unmarks_it_again(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        train = habit_named(service, TRAIN)
        row = row_of(view, TRAIN)
        focus_or_skip(row)
        row.event_generate("<space>")
        view.update()

        row_of(view, TRAIN).event_generate("<Return>")
        view.update()

        assert not service.get_habit(train.id).is_done(today)
        assert view.focus_get() is row_of(view, TRAIN)

    def test_unmarking_a_measured_habit_asks_first_like_a_click_does(
        self, view: TodayView, service: HabitService, dialogs: RecordingDialogs, today: date
    ) -> None:
        study = habit_named(service, STUDY)
        assert study.is_done(today)
        row = row_of(view, STUDY)
        focus_or_skip(row)

        row.event_generate("<space>")

        assert len(dialogs.asked) == 1
        assert not service.get_habit(study.id).is_done(today)

    def test_the_e_key_opens_the_editor_of_the_habit(
        self, view: TodayView, service: HabitService, forms: FormRecorder
    ) -> None:
        row = row_of(view, STUDY)
        focus_or_skip(row)

        row.event_generate("<e>")

        (call,) = forms.calls
        assert call.habit is habit_named(service, STUDY)
        assert call.master is view

    def test_in_delete_mode_space_selects_the_row_and_e_does_nothing(
        self, view: TodayView, service: HabitService, forms: FormRecorder
    ) -> None:
        view.delete_mode.enter()
        row = rows(view)[0]
        focus_or_skip(row)

        row.event_generate("<e>")
        assert forms.calls == []
        row.event_generate("<space>")
        view.update()

        assert view.delete_mode.selected == {service.habits()[0].id}
        assert view.focus_get() is rows(view)[0]
