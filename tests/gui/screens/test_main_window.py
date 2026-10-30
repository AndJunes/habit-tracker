"""The main window: tabs, the switch to the dashboard, the reminder clock and closing.

Every test builds the window on a root of its own (``private_root``): the window installs
a callback-error hook and a close handler on its root, which must not leak into the shared one.
"""

import contextlib
import logging
import time
import tkinter as tk
from collections.abc import Callable
from datetime import date
from datetime import time as day_time

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.enums import MeasurementKind
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import Habit, Measurement, Reminder
from habit_tracker.service import HabitService
from habit_tracker.ui import main_window as module
from habit_tracker.ui.main_window import MainWindow, Mode, Tab, fills_screen, reminder_message
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.tkutil import widget_exists
from habit_tracker.ui.views import texts

from .conftest import RecordingDialogs, Tree

LOGGER = "habit_tracker.ui.main_window"


class Notifier:
    """Stands in for the system notification: records each reminder, fails for chosen titles."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failing: set[str] = set()

    def __call__(self, title: str, message: str) -> bool:
        self.calls.append((title, message))
        if title in self.failing:
            raise OSError("the notification center is not available")
        return True


@pytest.fixture
def notifier() -> Notifier:
    return Notifier()


@pytest.fixture
def make_app(
    private_root: tk.Tk, clock: FixedClock, dialogs: RecordingDialogs, notifier: Notifier
) -> Callable[..., MainWindow]:
    def make(service: HabitService, *, demo: bool = False) -> MainWindow:
        return MainWindow(
            private_root, service, demo=demo, clock=clock, dialogs=dialogs, notifier=notifier
        )

    return make


@pytest.fixture
def app(make_app: Callable[..., MainWindow], service: HabitService) -> MainWindow:
    return make_app(service)


def pending_jobs(root: tk.Tk) -> set[str]:
    """The ids of everything scheduled with ``after`` on this root."""
    return set(root.tk.splitlist(root.tk.call("after", "info")))


def pump(root: tk.Tk, seconds: float = 0.15) -> None:
    """Let Tk process events and fire the timers that fall due."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


def show(root: tk.Tk) -> None:
    """Map the root, fully transparent, so that it receives events."""
    with contextlib.suppress(tk.TclError):
        root.attributes("-alpha", 0.0)  # unsupported on some systems: then it is just visible
    root.deiconify()
    root.geometry("+0+0")
    root.update()
    if not root.winfo_viewable():
        pytest.skip("windows cannot be mapped in this environment, so events are not delivered")


def resize_event(root: tk.Tk) -> None:
    """What the window system sends when the size changes (here, with the current size)."""
    root.event_generate("<Configure>", width=root.winfo_width(), height=root.winfo_height())


def tab_bar_children(app: MainWindow) -> list[tk.Misc]:
    tab_bar = app.window_frame.winfo_children()[0]
    return tab_bar.winfo_children()


def tab_labels(app: MainWindow) -> list[tk.Label]:
    return [child for child in tab_bar_children(app) if isinstance(child, tk.Label)]


def tab_underlines(app: MainWindow) -> list[tk.Frame]:
    return [child for child in tab_bar_children(app) if isinstance(child, tk.Frame)]


def add_reminder_habit(service: HabitService, name: str, *, goal: float | None = None) -> Habit:
    """A daily habit whose reminder is due right now (the fixed clock says 9:30)."""
    measurement = (
        Measurement(MeasurementKind.QUANTITY, goal, "páginas") if goal is not None else None
    )
    return service.add_habit(
        name=name,
        area_id="carrera",
        frequency=Daily(),
        start=date(2026, 9, 29),
        measurement=measurement,
        reminder=Reminder(day_time(9, 30)),
    )


class TestPureFunctions:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            ((1440, 900), True),
            ((1430, 740), True),  # the edge: 10 px short in width, 160 px in height
            ((1429, 900), False),
            ((1440, 739), False),
            ((620, 800), False),
        ],
    )
    def test_a_window_fills_the_screen_when_it_nearly_reaches_both_sides(
        self, size: tuple[int, int], expected: bool
    ) -> None:
        assert fills_screen(*size, 1440, 900) is expected

    def test_the_reminder_of_a_plain_habit_is_a_nudge(self) -> None:
        habit = Habit(
            id=1, name="Leer", area_id="carrera", frequency=Daily(), start=date(2026, 1, 1)
        )

        assert reminder_message(habit) == "Es tu hora. Márcalo cuando lo hagas."

    @pytest.mark.parametrize(
        ("goal", "text"),
        [(10, "10"), (10.0, "10"), (2.5, "2.5")],
    )
    def test_the_reminder_of_a_measured_habit_names_the_goal(self, goal: float, text: str) -> None:
        habit = Habit(
            id=1,
            name="Leer",
            area_id="carrera",
            frequency=Daily(),
            start=date(2026, 1, 1),
            measurement=Measurement(MeasurementKind.QUANTITY, goal, "páginas"),
        )

        assert reminder_message(habit) == f"Es tu hora. Meta: {text} páginas."

    def test_the_timing_constants_are_the_ones_the_design_calls_for(self) -> None:
        assert module.REMINDER_INTERVAL_MS == 30_000
        assert module.MODE_DEBOUNCE_MS == 200
        assert (module.MIN_WIDTH, module.MIN_HEIGHT) == (620, 720)


class TestWindow:
    def test_it_is_titled_after_the_app(self, private_root: tk.Tk, app: MainWindow) -> None:
        assert private_root.title() == "Registro de hábitos"

    def test_the_demo_says_so_in_the_title(
        self, private_root: tk.Tk, make_app: Callable[..., MainWindow], service: HabitService
    ) -> None:
        make_app(service, demo=True)

        assert private_root.title() == "Registro de hábitos · modo demo"

    def test_it_cannot_be_made_smaller_than_the_design(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        assert private_root.minsize() == (620, 720)

    def test_it_starts_in_window_mode_on_the_today_tab(self, app: MainWindow) -> None:
        assert app.mode is Mode.WINDOW
        assert app.active_tab is Tab.TODAY
        assert app.dashboard is None

    def test_the_screens_share_one_priority_editor(self, app: MainWindow) -> None:
        assert app.today_view.priority is app.priority

    def test_what_is_typed_in_the_window_is_still_there_in_full_screen(
        self, app: MainWindow
    ) -> None:
        app.today_view.priority_entry.delete(0, "end")
        app.today_view.priority_entry.insert(0, "Escrito en la ventana")

        app.show_dashboard()

        assert app.dashboard is not None
        assert app.dashboard.priority is app.priority
        assert app.dashboard.priority_entry is not None
        assert app.dashboard.priority_entry.get() == "Escrito en la ventana"


class TestTabs:
    def test_there_is_a_label_per_tab_in_order(self, app: MainWindow) -> None:
        assert [label.cget("text") for label in tab_labels(app)] == ["Hoy", "Calendario", "Mi mes"]

    def test_the_active_tab_is_painted_and_underlined_in_lilac(self, app: MainWindow) -> None:
        app.show_tab(Tab.CALENDAR)

        assert [label.cget("bg") for label in tab_labels(app)] == [
            palette.TAB_INACTIVE_BACKGROUND,
            palette.TAB_ACTIVE_BACKGROUND,
            palette.TAB_INACTIVE_BACKGROUND,
        ]
        assert [bar.cget("bg") for bar in tab_underlines(app)] == [
            palette.PAPER,
            palette.LILAC,
            palette.PAPER,
        ]
        assert app.active_tab is Tab.CALENDAR

    def test_showing_a_tab_refreshes_its_view_with_fresh_data(
        self, app: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        refreshed: list[str] = []
        monkeypatch.setattr(app.month_view, "refresh", lambda: refreshed.append("month"))

        app.show_tab(Tab.MONTH)

        assert refreshed == ["month"]

    def test_clicking_a_tab_label_shows_that_tab(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        show(private_root)

        tab_labels(app)[2].event_generate("<Button-1>", x=5, y=5)

        assert app.active_tab is Tab.MONTH


class TestMode:
    def test_the_dashboard_is_built_on_first_use_and_reused_afterwards(
        self, app: MainWindow
    ) -> None:
        app.show_dashboard()
        first = app.dashboard
        assert first is not None

        app.show_window()
        app.show_dashboard()

        assert app.dashboard is first

    def test_the_dashboard_takes_the_place_of_the_window_and_changes_the_background(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        app.show_dashboard()

        assert app.mode is Mode.FULLSCREEN
        assert app.window_frame.winfo_manager() == ""
        assert app.dashboard is not None
        assert app.dashboard.winfo_manager() == "pack"
        assert private_root.cget("bg") == palette.BACKGROUND

    def test_going_back_restores_the_window_and_its_background(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        app.show_dashboard()

        app.show_window()

        assert app.mode is Mode.WINDOW
        assert app.window_frame.winfo_manager() == "pack"
        assert app.dashboard is not None
        assert app.dashboard.winfo_manager() == ""
        assert private_root.cget("bg") == palette.PAPER

    def test_going_back_refreshes_the_tab_that_was_active(
        self, app: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app.show_tab(Tab.MONTH)
        refreshed: list[str] = []
        monkeypatch.setattr(app.month_view, "refresh", lambda: refreshed.append("month"))
        app.show_dashboard()

        app.show_window()

        assert refreshed == ["month"]
        assert app.active_tab is Tab.MONTH

    def test_a_half_done_delete_does_not_survive_leaving_and_entering_full_screen(
        self, app: MainWindow, service: HabitService
    ) -> None:
        app.show_dashboard()
        dashboard = app.dashboard
        assert dashboard is not None
        dashboard.delete_mode.enter()
        dashboard.delete_mode.toggle(service.habits()[0])
        assert dashboard.delete_mode.active

        app.show_window()  # leaves full screen...
        app.show_dashboard()  # ...and comes back

        assert not dashboard.delete_mode.active
        assert dashboard.delete_mode.selected == frozenset()
        assert Tree.trash_buttons(dashboard.page) == []

    def test_a_burst_of_resize_events_is_decided_only_once(
        self, private_root: tk.Tk, app: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[tuple[int, ...]] = []

        def never_full(*sizes: int) -> bool:
            asked.append(sizes)
            return False

        monkeypatch.setattr(module, "fills_screen", never_full)
        monkeypatch.setattr(module, "MODE_DEBOUNCE_MS", 20)
        show(private_root)
        pump(private_root, 0.2)  # let the events of mapping the window settle
        asked.clear()

        for _ in range(5):
            resize_event(private_root)
        pump(private_root, 0.2)

        assert len(asked) == 1

    def test_filling_the_screen_brings_the_dashboard_and_shrinking_brings_the_window_back(
        self, private_root: tk.Tk, app: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        full = [False]
        monkeypatch.setattr(module, "fills_screen", lambda *_sizes: full[0])
        monkeypatch.setattr(module, "MODE_DEBOUNCE_MS", 20)
        show(private_root)
        pump(private_root, 0.2)
        assert app.mode is Mode.WINDOW

        full[0] = True
        resize_event(private_root)
        pump(private_root, 0.3)
        assert app.mode is Mode.FULLSCREEN
        assert app.dashboard is not None

        full[0] = False
        resize_event(private_root)
        pump(private_root, 0.3)
        assert app.mode is Mode.WINDOW


class TestReminders:
    def test_a_reminder_is_shown_once_per_day_with_its_goal(
        self, app: MainWindow, service: HabitService, notifier: Notifier
    ) -> None:
        add_reminder_habit(service, 'Leer «con comillas» "dobles"', goal=10.0)
        service.add_habit(
            name="Sin recordatorio", area_id="salud", frequency=Daily(), start=date(2026, 9, 29)
        )

        app.check_reminders()
        assert notifier.calls == [
            ('Leer «con comillas» "dobles"', "Es tu hora. Meta: 10 páginas.")
        ]

        app.check_reminders()  # the same day does not repeat it
        assert len(notifier.calls) == 1

    def test_a_habit_without_a_goal_gets_the_plain_nudge(
        self, app: MainWindow, service: HabitService, notifier: Notifier
    ) -> None:
        add_reminder_habit(service, "Estirar")

        app.check_reminders()

        assert notifier.calls == [("Estirar", "Es tu hora. Márcalo cuando lo hagas.")]

    def test_each_check_schedules_the_next_one_and_only_one(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        before = pending_jobs(private_root)

        app.check_reminders()
        app.check_reminders()

        after = pending_jobs(private_root)
        assert len(before - after) == 1  # the pending check was replaced...
        assert len(after - before) == 1  # ...by a single new one

    def test_an_error_of_the_service_is_logged_and_the_clock_keeps_going(
        self,
        private_root: tk.Tk,
        app: MainWindow,
        service: HabitService,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def broken() -> list[Habit]:
            raise ZeroDivisionError("damaged data")

        monkeypatch.setattr(service, "pending_reminders", broken)
        before = pending_jobs(private_root)

        with caplog.at_level(logging.ERROR, logger=LOGGER):
            app.check_reminders()

        (record,) = [r for r in caplog.records if r.name == LOGGER]
        assert record.getMessage() == "could not read the pending reminders"
        assert record.exc_info is not None
        assert record.exc_info[0] is ZeroDivisionError
        assert pending_jobs(private_root) != before  # a new check was scheduled

    def test_an_error_of_the_notification_is_logged_and_the_other_reminders_still_go_out(
        self,
        private_root: tk.Tk,
        app: MainWindow,
        service: HabitService,
        notifier: Notifier,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        first = add_reminder_habit(service, "Primero")
        add_reminder_habit(service, "Segundo")
        notifier.failing = {"Primero"}
        before = pending_jobs(private_root)

        with caplog.at_level(logging.ERROR, logger=LOGGER):
            app.check_reminders()

        assert [title for title, _ in notifier.calls] == ["Primero", "Segundo"]
        (record,) = [r for r in caplog.records if r.name == LOGGER]
        assert record.getMessage() == f"could not show the reminder of habit {first.id}"
        assert pending_jobs(private_root) != before


class TestStartupMessages:
    def test_each_message_is_shown_in_a_warning_once_the_loop_runs(
        self,
        private_root: tk.Tk,
        app: MainWindow,
        dialogs: RecordingDialogs,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(module, "STARTUP_NOTICE_DELAY_MS", 1)

        app.show_startup_messages(["uno", "dos"])
        assert dialogs.shown == []  # not before the window is up

        pump(private_root, 0.1)
        assert dialogs.shown == [("warning", "Aviso", "uno"), ("warning", "Aviso", "dos")]

    def test_without_messages_nothing_is_scheduled(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        before = pending_jobs(private_root)

        app.show_startup_messages([])

        assert pending_jobs(private_root) == before


class TestClosing:
    def test_closing_cancels_every_scheduled_job_and_destroys_the_window(
        self, private_root: tk.Tk, app: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        show(private_root)
        resize_event(private_root)  # leaves the size detection waiting
        app.show_startup_messages(["pendiente"])
        pending = pending_jobs(private_root)
        assert len(pending) >= 3  # the reminder clock, the size detection and the notice

        cancelled: list[str] = []
        original = private_root.after_cancel

        def spy(job: str) -> None:
            cancelled.append(job)
            original(job)

        monkeypatch.setattr(private_root, "after_cancel", spy)

        app.close()

        assert pending <= set(cancelled)
        assert not widget_exists(private_root)

    def test_the_close_button_of_the_window_runs_the_orderly_close(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        command = private_root.protocol("WM_DELETE_WINDOW")
        assert command

        private_root.tk.call(command)

        assert not widget_exists(private_root)

    def test_closing_twice_is_harmless(self, app: MainWindow) -> None:
        app.close()

        app.close()


class TestErrorReport:
    def test_the_window_takes_over_the_error_report_of_tk(
        self, private_root: tk.Tk, app: MainWindow
    ) -> None:
        assert private_root.report_callback_exception == app.report_callback_exception

    def test_an_error_inside_a_callback_is_logged_and_shown_briefly(
        self,
        private_root: tk.Tk,
        app: MainWindow,
        dialogs: RecordingDialogs,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def broken() -> None:
            raise RuntimeError("callback failed")

        private_root.after(1, broken)

        with caplog.at_level(logging.ERROR, logger=LOGGER):
            pump(private_root, 0.1)

        assert dialogs.shown == [
            ("error", texts.UNEXPECTED_ERROR_TITLE, texts.UNEXPECTED_ERROR_MESSAGE)
        ]
        (record,) = [r for r in caplog.records if r.name == LOGGER]
        assert record.getMessage() == "unhandled error in a Tk callback"
        assert record.exc_info is not None
        assert record.exc_info[0] is RuntimeError

    def test_later_errors_are_shown_again_once_the_dialog_is_closed(
        self, app: MainWindow, dialogs: RecordingDialogs
    ) -> None:
        app.report_callback_exception(RuntimeError, RuntimeError("first"), None)
        app.report_callback_exception(RuntimeError, RuntimeError("second"), None)

        assert dialogs.kinds() == ["error", "error"]

    def test_an_error_while_the_dialog_is_open_does_not_stack_another_dialog(
        self,
        app: MainWindow,
        dialogs: RecordingDialogs,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original = dialogs.show_error

        def error_during_the_dialog(title: str, message: str) -> None:
            original(title, message)
            app.report_callback_exception(ValueError, ValueError("again"), None)

        monkeypatch.setattr(dialogs, "show_error", error_during_the_dialog)

        with caplog.at_level(logging.ERROR, logger=LOGGER):
            app.report_callback_exception(RuntimeError, RuntimeError("first"), None)

        assert dialogs.kinds() == ["error"]
        assert len([r for r in caplog.records if r.name == LOGGER]) == 2  # both are logged

    def test_a_dialog_that_cannot_be_shown_is_logged_and_does_not_raise(
        self,
        app: MainWindow,
        dialogs: RecordingDialogs,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def no_display(title: str, message: str) -> None:
            raise tk.TclError("no display")

        monkeypatch.setattr(dialogs, "show_error", no_display)

        with caplog.at_level(logging.ERROR, logger=LOGGER):
            app.report_callback_exception(RuntimeError, RuntimeError("first"), None)

        messages = [r.getMessage() for r in caplog.records if r.name == LOGGER]
        assert "the error dialog could not be shown" in messages
