"""The habit rows of the dashboard with the keyboard.

Its rows are items of one canvas, which cannot take the focus, so each row has a one-pixel anchor
hung from the card that stands in for it. These tests check the anchors, the ring they make appear,
and where the focus is after the page is built again. The tests that press keys need the window
system to give the window the keyboard focus; they skip, saying so, when it does not.
"""

import tkinter as tk
from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.models import Habit
from habit_tracker.service import HabitService
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.focus import ACTIVATION_KEYS, RING_WIDTH
from habit_tracker.ui.views.dashboard import DashboardView
from habit_tracker.ui.views.helpers import EDIT_KEYS, FOCUS_RING_TAG

from .conftest import FormRecorder, RecordingDialogs, Tree, ValuePrompt

TRAIN = "Entrenar 3 veces por semana"  # a quota that is not marked today
STUDY = "Bloque de estudio"  # measured, marked today
FINANCES = "Viernes de finanzas (1 h)"  # only on Fridays, and today is a Thursday


@pytest.fixture
def make_view(
    window: tk.Toplevel,
    clock: FixedClock,
    dialogs: RecordingDialogs,
    forms: FormRecorder,
    value_prompt: ValuePrompt,
) -> Callable[[HabitService], DashboardView]:
    def make(service: HabitService) -> DashboardView:
        view = DashboardView(window, service, dialogs=dialogs, clock=clock)
        view.pack(fill="both", expand=True)
        window.update()
        return view

    return make


@pytest.fixture
def view(
    make_view: Callable[[HabitService], DashboardView], service: HabitService
) -> DashboardView:
    return make_view(service)


def today_card(view: DashboardView) -> tk.Canvas:
    return next(
        item
        for item in Tree.descendants(view.page)
        if isinstance(item, tk.Canvas) and Tree.texts(item)[:1] == ["Hoy"]
    )


def anchors(card: tk.Canvas) -> list[tk.Canvas]:
    """The one-pixel canvases hung from the card, in the order they were made."""
    return [
        child
        for child in card.winfo_children()
        if isinstance(child, tk.Canvas) and int(child["width"]) == 1 and int(child["height"]) == 1
    ]


def trash_buttons(view: DashboardView) -> list[tk.Canvas]:
    return list(Tree.trash_buttons(today_card(view)))


def habit_named(service: HabitService, name: str) -> Habit:
    return next(habit for habit in service.habits() if habit.name == name)


def due_today(service: HabitService, today: date) -> list[Habit]:
    return [habit for habit in service.habits() if habit.applies_on(today)]


def is_tab_stop(widget: tk.Misc) -> bool:
    return str(widget.cget("takefocus")) == "1"


def rings(card: tk.Canvas) -> tuple[int, ...]:
    return card.find_withtag(FOCUS_RING_TAG)


def row_background(card: tk.Canvas, habit: Habit) -> int:
    """The first item of the habit's row: its rounded background."""
    return card.find_withtag(f"h{habit.id}")[0]


def window_item_of(card: tk.Canvas, widget: tk.Misc) -> int:
    return next(
        item
        for item in card.find_all()
        if card.type(item) == "window" and card.itemcget(item, "window") == str(widget)
    )


def snapshot(card: tk.Canvas) -> list[tuple[str, tuple[float, ...]]]:
    """Kind and coordinates of every item of the card."""
    return [(card.type(item) or "", tuple(card.coords(item))) for item in card.find_all()]


def focus_or_skip(widget: tk.Misc) -> None:
    """Give ``widget`` the keyboard focus, or skip the test if the system will not."""
    widget.focus_force()
    widget.update()
    if widget.focus_get() is not widget:
        pytest.skip("the window did not get the keyboard focus")


class TestAnchors:
    def test_a_row_that_can_be_marked_has_an_anchor_in_the_tab_order(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        found = anchors(today_card(view))

        assert len(found) == len(due_today(service, today))
        assert found
        assert all(is_tab_stop(anchor) for anchor in found)

    def test_a_dimmed_row_has_no_anchor(self, view: DashboardView, service: HabitService) -> None:
        card = today_card(view)
        finances = habit_named(service, FINANCES)

        assert FINANCES in Tree.texts(card)
        assert card.find_withtag(f"h{finances.id}") == ()
        assert len(anchors(card)) < len(service.habits())

    def test_the_anchor_is_painted_like_its_row_and_lies_inside_it(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        card = today_card(view)

        for habit, anchor in zip(due_today(service, today), anchors(card), strict=True):
            background = row_background(card, habit)
            assert anchor.cget("bg") == card.itemcget(background, "fill"), habit.name
            row = card.coords(background)
            x, y = card.coords(window_item_of(card, anchor))
            assert min(row[0::2]) < x < max(row[0::2]), habit.name
            assert min(row[1::2]) < y < max(row[1::2]), habit.name

    def test_tab_goes_through_the_anchors_in_the_order_of_the_rows(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        found = anchors(today_card(view))
        assert len(found) > 1

        visited = [found[0]]
        for _ in found[1:]:
            visited.append(visited[-1].tk_focusNext())

        assert visited == found

    def test_a_click_on_the_anchor_does_what_a_click_on_the_row_does(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        train = habit_named(service, TRAIN)
        anchor = anchors(today_card(view))[0]
        anchor.update()

        anchor.event_generate("<Button-1>", x=0, y=0)
        anchor.update()

        assert service.get_habit(train.id).is_done(today)

    def test_a_right_click_on_the_anchor_opens_the_editor(
        self, view: DashboardView, service: HabitService, forms: FormRecorder
    ) -> None:
        anchor = anchors(today_card(view))[0]
        anchor.update()

        anchor.event_generate("<Button-3>", x=0, y=0)

        (call,) = forms.calls
        assert call.habit is habit_named(service, TRAIN)

    def test_the_anchors_answer_to_the_activation_and_edit_keys(self, view: DashboardView) -> None:
        for anchor in anchors(today_card(view)):
            for key in (*ACTIVATION_KEYS, *EDIT_KEYS):
                assert anchor.bind(key), key


class TestRing:
    def test_nothing_extra_is_drawn_until_the_keyboard_has_the_focus(
        self, view: DashboardView
    ) -> None:
        assert rings(today_card(view)) == ()

    def test_the_ring_is_drawn_around_the_row_with_the_focus_and_taken_away_after(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        card = today_card(view)
        habits = due_today(service, today)
        anchor = anchors(card)[1]

        anchor.event_generate("<FocusIn>")
        assert len(rings(card)) == 1
        (ring,) = rings(card)
        assert card.itemcget(ring, "outline") == palette.FOCUS_RING
        assert card.itemcget(ring, "fill") == ""

        # It surrounds the second row that can be marked, and stays within that row.
        row = card.coords(row_background(card, habits[1]))
        points = card.coords(ring)
        half = RING_WIDTH / 2
        assert min(points[0::2]) - half >= min(row[0::2])
        assert max(points[0::2]) + half <= max(row[0::2])
        assert min(points[1::2]) - half >= min(row[1::2])
        assert max(points[1::2]) + half <= max(row[1::2])

        anchor.event_generate("<FocusOut>")
        assert rings(card) == ()

    def test_moving_the_focus_from_one_row_to_another_leaves_a_single_ring(
        self, view: DashboardView
    ) -> None:
        card = today_card(view)
        first, second = anchors(card)[:2]

        first.event_generate("<FocusIn>")
        first.event_generate("<FocusOut>")
        second.event_generate("<FocusIn>")

        assert len(rings(card)) == 1

    def test_after_the_focus_comes_and_goes_the_card_is_exactly_as_it_was(
        self, view: DashboardView
    ) -> None:
        card = today_card(view)
        before = snapshot(card)

        anchors(card)[0].event_generate("<FocusIn>")
        anchors(card)[0].event_generate("<FocusOut>")

        assert snapshot(card) == before

    def test_the_card_keeps_its_size_with_the_ring(self, view: DashboardView) -> None:
        card = today_card(view)
        size = (int(card["width"]), int(card["height"]))

        anchors(card)[0].event_generate("<FocusIn>")

        assert (int(card["width"]), int(card["height"])) == size


class TestFocusAfterThePageIsBuiltAgain:
    def test_marking_a_habit_keeps_the_focus_on_its_row(
        self, view: DashboardView, service: HabitService
    ) -> None:
        old = anchors(today_card(view))
        old[0].focus_set()

        view.actions.toggle(habit_named(service, TRAIN))

        new = anchors(today_card(view))
        assert new[0] is not old[0]  # the page was built again
        assert view.focus_lastfor() is new[0]

    def test_the_focus_stays_with_its_habit_when_another_one_changes(
        self, view: DashboardView, service: HabitService
    ) -> None:
        anchors(today_card(view))[1].focus_set()  # the study block

        view.actions.toggle(habit_named(service, TRAIN))

        assert view.focus_lastfor() is anchors(today_card(view))[1]

    def test_a_focus_that_was_somewhere_else_is_left_alone(
        self, view: DashboardView, service: HabitService
    ) -> None:
        view.winfo_toplevel().focus_set()

        view.actions.toggle(habit_named(service, TRAIN))

        assert view.focus_lastfor() is view.winfo_toplevel()

    def test_a_focus_on_the_buttons_is_not_moved_to_a_row(
        self, view: DashboardView, service: HabitService
    ) -> None:
        button = next(iter(Tree.buttons(today_card(view)).values()))
        button.focus_set()
        view.refresh()

        assert view.focus_lastfor() not in anchors(today_card(view))


class TestDeleteMode:
    def test_every_habit_gets_an_anchor_also_those_not_due_today(
        self, view: DashboardView, service: HabitService
    ) -> None:
        view.delete_mode.enter()

        found = anchors(today_card(view))

        assert len(found) == len(service.habits())
        assert all(is_tab_stop(anchor) for anchor in found)

    def test_the_anchors_select_with_the_same_keys_and_do_not_edit(
        self, view: DashboardView
    ) -> None:
        view.delete_mode.enter()

        for anchor in anchors(today_card(view)):
            for key in ACTIVATION_KEYS:
                assert anchor.bind(key), key
            for key in EDIT_KEYS:
                assert not anchor.bind(key), key

    def test_the_ring_surrounds_the_row_in_delete_mode_too(
        self, view: DashboardView, service: HabitService
    ) -> None:
        view.delete_mode.enter()
        view.update()  # the new rows get events only once they are mapped
        card = today_card(view)

        anchors(card)[-1].event_generate("<FocusIn>")

        assert len(rings(card)) == 1

    def test_tab_goes_from_an_anchor_to_its_trash_can_and_on_to_the_next_row(
        self, view: DashboardView
    ) -> None:
        view.delete_mode.enter()
        view.update()  # Tab skips widgets that are not mapped yet
        card = today_card(view)
        first, second = anchors(card)[:2]
        first_trash, second_trash = trash_buttons(view)[:2]

        assert first.tk_focusNext() is first_trash
        assert first_trash.tk_focusNext() is second
        assert second.tk_focusNext() is second_trash

    def test_selecting_a_row_keeps_the_focus_on_its_anchor(
        self, view: DashboardView, service: HabitService
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()
        view.update()  # the new rows get the focus only once they are mapped
        anchors(today_card(view))[2].focus_set()

        view.delete_mode.toggle(habits[2])

        assert view.delete_mode.selected == {habits[2].id}
        assert view.focus_lastfor() is anchors(today_card(view))[2]

    def test_selecting_with_a_trash_can_keeps_the_focus_on_that_trash_can(
        self, view: DashboardView, service: HabitService
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()
        view.update()  # the new rows get the focus only once they are mapped
        trash_buttons(view)[1].focus_set()

        view.delete_mode.toggle(habits[1])

        assert view.focus_lastfor() is trash_buttons(view)[1]


class TestRealKeys:
    def test_space_marks_the_habit_and_the_focus_stays_on_the_row(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        train = habit_named(service, TRAIN)
        anchor = anchors(today_card(view))[0]
        focus_or_skip(anchor)

        anchor.event_generate("<space>")
        view.update()

        assert service.get_habit(train.id).is_done(today)
        assert view.focus_get() is anchors(today_card(view))[0]

    def test_enter_unmarks_it_again(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        train = habit_named(service, TRAIN)
        anchor = anchors(today_card(view))[0]
        focus_or_skip(anchor)
        anchor.event_generate("<space>")
        view.update()

        anchors(today_card(view))[0].event_generate("<Return>")
        view.update()

        assert not service.get_habit(train.id).is_done(today)

    def test_the_e_key_opens_the_editor_of_the_habit(
        self, view: DashboardView, service: HabitService, forms: FormRecorder
    ) -> None:
        anchor = anchors(today_card(view))[1]  # the study block
        focus_or_skip(anchor)

        anchor.event_generate("<e>")

        (call,) = forms.calls
        assert call.habit is habit_named(service, STUDY)

    def test_in_delete_mode_space_selects_the_row_and_e_does_nothing(
        self, view: DashboardView, service: HabitService, forms: FormRecorder
    ) -> None:
        view.delete_mode.enter()
        anchor = anchors(today_card(view))[0]
        focus_or_skip(anchor)

        anchor.event_generate("<e>")
        assert forms.calls == []
        anchor.event_generate("<space>")
        view.update()

        assert view.delete_mode.selected == {service.habits()[0].id}
        assert view.focus_get() is anchors(today_card(view))[0]
