"""The tabs of the main window with the keyboard: Tab order, the ring, Space, Enter and the arrows.

Whatever can be checked without real key events is: the state a focus event leaves, the size of the
tabs, what is reachable. The tests that press keys need the window system to give the window the
keyboard focus; they skip, saying so, when it does not.
"""

import contextlib
import tkinter as tk

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.service import HabitService
from habit_tracker.ui import main_window as module
from habit_tracker.ui.main_window import MainWindow, Tab
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.focus import RING_WIDTH
from habit_tracker.ui.views.helpers import is_inside

from .conftest import RecordingDialogs, Tree


@pytest.fixture
def app(
    private_root: tk.Tk, service: HabitService, clock: FixedClock, dialogs: RecordingDialogs
) -> MainWindow:
    return MainWindow(
        private_root, service, clock=clock, dialogs=dialogs, notifier=lambda _title, _text: True
    )


def show(root: tk.Tk) -> None:
    """Map the root, fully transparent, so that it receives events."""
    with contextlib.suppress(tk.TclError):
        root.attributes("-alpha", 0.0)  # unsupported on some systems: then it is just visible
    root.deiconify()
    root.geometry("+0+0")
    root.update()
    if not root.winfo_viewable():
        pytest.skip("windows cannot be mapped in this environment, so events are not delivered")


def focus_or_skip(root: tk.Tk, widget: tk.Misc) -> None:
    """Give ``widget`` the keyboard focus, or skip the test if the system will not."""
    widget.focus_force()
    root.update()
    if root.focus_get() is not widget:
        pytest.skip("the window did not get the keyboard focus")


def tab_labels(app: MainWindow) -> list[tk.Label]:
    tab_bar = app.window_frame.winfo_children()[0]
    return [child for child in tab_bar.winfo_children() if isinstance(child, tk.Label)]


def focus_order(start: tk.Misc) -> list[tk.Misc]:
    """What Tab visits after ``start``, in order, until it comes back to ``start``."""
    visited: list[tk.Misc] = []
    current = start.tk_focusNext()
    while current is not None and current is not start and len(visited) < 500:
        visited.append(current)
        current = current.tk_focusNext()
    return visited


def reachable_controls(widget: tk.Misc) -> list[tk.Canvas]:
    """The canvases under ``widget`` that Tab can stop at."""
    return [
        item
        for item in Tree.descendants(widget)
        if isinstance(item, tk.Canvas) and str(item.cget("takefocus")) == "1"
    ]


class TestReachability:
    def test_every_tab_is_in_the_tab_order(self, app: MainWindow) -> None:
        assert [str(label.cget("takefocus")) for label in tab_labels(app)] == ["1", "1", "1"]

    def test_a_tab_has_the_size_it_had_before_the_ring_existed(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        tab_bar = tab_labels(app)[0].master
        for label in tab_labels(app):
            reference = tk.Label(
                tab_bar,
                text=label.cget("text"),
                font=label.cget("font"),
                padx=module._TAB_PADDING_X,
                pady=module._TAB_PADDING_Y,
            )
            assert (label.winfo_reqwidth(), label.winfo_reqheight()) == (
                reference.winfo_reqwidth(),
                reference.winfo_reqheight(),
            )

    def test_the_ring_takes_no_room_when_it_appears(self, app: MainWindow) -> None:
        label = tab_labels(app)[1]
        size = (label.winfo_reqwidth(), label.winfo_reqheight())

        label.event_generate("<FocusIn>")
        assert (label.winfo_reqwidth(), label.winfo_reqheight()) == size

        label.event_generate("<FocusOut>")
        assert (label.winfo_reqwidth(), label.winfo_reqheight()) == size

    def test_the_border_that_carries_the_ring_is_as_thick_as_every_other_ring(
        self, app: MainWindow
    ) -> None:
        for label in tab_labels(app):
            assert int(str(label.cget("highlightthickness"))) == RING_WIDTH
            assert label.cget("highlightcolor") == palette.FOCUS_RING


class TestRing:
    def test_nothing_shows_until_a_tab_gets_the_keyboard_focus(self, app: MainWindow) -> None:
        for label in tab_labels(app):
            assert label.cget("highlightbackground") == label.cget("bg")

    def test_the_ring_shows_only_while_the_tab_has_the_focus(self, app: MainWindow) -> None:
        show(app.root)  # a window that is not on screen gets no focus events
        label = tab_labels(app)[2]

        label.event_generate("<FocusIn>")
        assert label.cget("highlightbackground") == palette.FOCUS_RING

        label.event_generate("<FocusOut>")
        assert label.cget("highlightbackground") == label.cget("bg")

    def test_the_ring_survives_the_tab_bar_being_repainted(self, app: MainWindow) -> None:
        show(app.root)
        label = tab_labels(app)[0]
        label.event_generate("<FocusIn>")

        app.show_tab(Tab.CALENDAR)

        assert label.cget("highlightbackground") == palette.FOCUS_RING
        assert label.cget("bg") == palette.TAB_INACTIVE_BACKGROUND

    def test_the_border_follows_the_colors_of_the_tab_when_it_changes_state(
        self, app: MainWindow
    ) -> None:
        app.show_tab(Tab.MONTH)

        for label in tab_labels(app):
            assert label.cget("highlightbackground") == label.cget("bg")

    def test_clicking_a_tab_gives_it_no_focus_and_no_ring(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        show(private_root)
        label = tab_labels(app)[1]

        label.event_generate("<Button-1>", x=5, y=5)

        assert app.active_tab is Tab.CALENDAR
        assert private_root.focus_lastfor() is not label
        for tab in tab_labels(app):
            assert tab.cget("highlightbackground") == tab.cget("bg")


class TestArrows:
    def test_the_arrows_activate_the_neighbor_tab_and_hand_it_the_focus(
        self, app: MainWindow
    ) -> None:
        show(app.root)  # Tk only gives the focus to widgets that are on screen
        labels = tab_labels(app)

        app.select_neighbor_tab(Tab.TODAY, 1)
        assert app.active_tab is Tab.CALENDAR
        assert app.root.focus_lastfor() is labels[1]

        app.select_neighbor_tab(Tab.CALENDAR, 1)
        assert app.active_tab is Tab.MONTH
        assert app.root.focus_lastfor() is labels[2]

        app.select_neighbor_tab(Tab.MONTH, -1)
        assert app.active_tab is Tab.CALENDAR
        assert app.root.focus_lastfor() is labels[1]

    def test_the_arrows_stop_at_the_ends(self, app: MainWindow) -> None:
        app.select_neighbor_tab(Tab.TODAY, -1)
        assert app.active_tab is Tab.TODAY
        assert app.root.focus_lastfor() is not tab_labels(app)[0]

        app.show_tab(Tab.MONTH)
        app.select_neighbor_tab(Tab.MONTH, 1)
        assert app.active_tab is Tab.MONTH

    def test_the_left_and_right_keys_are_bound_on_every_tab(self, app: MainWindow) -> None:
        for label in tab_labels(app):
            assert label.bind("<Left>")
            assert label.bind("<Right>")

    def test_space_and_enter_are_bound_on_every_tab(self, app: MainWindow) -> None:
        for label in tab_labels(app):
            for key in ("<space>", "<Return>", "<KP_Enter>"):
                assert label.bind(key), key


class TestRealKeys:
    def test_space_and_enter_activate_the_tab_with_the_focus(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        show(private_root)
        _today, calendar, month = tab_labels(app)

        focus_or_skip(private_root, calendar)
        calendar.event_generate("<space>")
        assert app.active_tab is Tab.CALENDAR

        focus_or_skip(private_root, month)
        month.event_generate("<Return>")
        assert app.active_tab is Tab.MONTH

    def test_the_arrow_keys_move_between_the_tabs(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        show(private_root)
        today, calendar, _month = tab_labels(app)

        focus_or_skip(private_root, today)
        today.event_generate("<Right>")
        private_root.update()
        assert app.active_tab is Tab.CALENDAR
        assert private_root.focus_get() is calendar

        calendar.event_generate("<Left>")
        private_root.update()
        assert app.active_tab is Tab.TODAY
        assert private_root.focus_get() is today


class TestOnlyTheVisibleViewIsReachable:
    def test_the_views_that_are_not_showing_are_off_the_screen(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        show(private_root)

        app.show_tab(Tab.CALENDAR)
        private_root.update()

        assert app.calendar_view.winfo_viewable()
        assert not app.today_view.winfo_viewable()
        assert not app.month_view.winfo_viewable()

    def test_tab_never_stops_at_a_control_of_a_view_that_is_not_showing(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        show(private_root)
        first_tab = tab_labels(app)[0]

        app.show_tab(Tab.CALENDAR)
        private_root.update()
        stops = focus_order(first_tab)
        assert not [w for w in stops if is_inside(w, app.today_view)]
        assert not [w for w in stops if is_inside(w, app.month_view)]

        app.show_tab(Tab.TODAY)
        private_root.update()
        stops = focus_order(first_tab)
        assert [w for w in stops if is_inside(w, app.today_view)]
        assert not [w for w in stops if is_inside(w, app.calendar_view)]

    def test_a_view_that_comes_back_is_laid_out_as_before(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        show(private_root)
        before = (app.today_view.winfo_width(), app.today_view.winfo_height())

        app.show_tab(Tab.MONTH)
        private_root.update()
        app.show_tab(Tab.TODAY)
        private_root.update()

        assert (app.today_view.winfo_width(), app.today_view.winfo_height()) == before

    def test_the_focus_leaves_a_view_that_is_hidden(self, app: MainWindow) -> None:
        show(app.root)
        row = app.today_view.list_frame.winfo_children()[0]
        row.focus_set()
        assert app.root.focus_lastfor() is row

        app.show_tab(Tab.CALENDAR)

        assert app.root.focus_lastfor() is app.root

    def test_the_focus_of_a_tab_is_not_taken_away_when_the_views_change(
        self, app: MainWindow
    ) -> None:
        show(app.root)
        label = tab_labels(app)[0]
        label.focus_set()

        app.show_tab(Tab.CALENDAR)

        assert app.root.focus_lastfor() is label

    def test_the_focus_leaves_the_window_when_the_dashboard_takes_over(
        self, app: MainWindow
    ) -> None:
        app.today_view.list_frame.winfo_children()[0].focus_set()

        app.show_dashboard()

        assert app.root.focus_lastfor() is app.root

    def test_the_focus_leaves_the_dashboard_when_the_window_comes_back(
        self, app: MainWindow
    ) -> None:
        app.show_dashboard()
        assert app.dashboard is not None
        reachable_controls(app.dashboard.page)[0].focus_set()

        app.show_window()

        assert app.root.focus_lastfor() is app.root


class TestIsInside:
    def test_a_widget_is_inside_itself_and_what_hangs_from_it(self, tk_root: tk.Tk) -> None:
        outer = tk.Frame(tk_root)
        inner = tk.Frame(outer)
        deeper = tk.Label(inner)

        assert is_inside(outer, outer)
        assert is_inside(inner, outer)
        assert is_inside(deeper, outer)

    def test_a_sibling_whose_name_starts_the_same_is_not_inside(self, tk_root: tk.Tk) -> None:
        first = tk.Frame(tk_root, name="box")
        second = tk.Frame(tk_root, name="box2")  # its path begins with the first one's

        assert not is_inside(second, first)
        assert not is_inside(first, second)
