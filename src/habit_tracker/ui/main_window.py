"""The main window: the tab bar, the switch to the dashboard and the reminder clock.

Why not ``ttk.Notebook``? It brings the system's look and cannot be painted with the pastel
palette. A row of labels can: every "tab" is a clickable label with a lilac bar under it when
active. The three views share the same cell and only the one that is due is on the grid.

The tabs work with the keyboard too: Tab reaches them, Space or Enter activate the one with the
focus and Left / Right move to the neighbor tab and activate it.

The window has two layouts that follow the real state of the window (there are no buttons to
choose, the person only uses the green button of macOS):

* a normal window: the compact app, tabs plus views;
* full screen or maximized: the dashboard.

The detection listens to the root's ``<Configure>`` events: when the window reaches the size of
the screen the dashboard comes in, and when it gets small again the compact mode returns.
Everything of the window mode lives in a single frame, so switching is hiding one pack and
showing the other.
"""

import logging
import tkinter as tk
from collections.abc import Callable, Sequence
from enum import StrEnum
from functools import partial
from types import TracebackType

from ..clock import Clock, SystemClock
from ..domain.models import Habit
from ..notifications import notify
from ..service import HabitService
from .controllers.dialogs import Dialogs, TkDialogs
from .controllers.habit_actions import format_number
from .controllers.priority import PriorityEditor
from .theme import palette
from .theme.cursors import pointer_cursor
from .theme.focus import RING_WIDTH, activate_with_keys
from .theme.fonts import font
from .theme.tkutil import TkEvent, widget_exists
from .views import texts
from .views.calendar import CalendarView
from .views.dashboard import DashboardView
from .views.helpers import focused_widget, is_inside
from .views.month import MonthView
from .views.today import TodayView

log = logging.getLogger(__name__)

WINDOW_SIZE = "620x800"
MIN_WIDTH = 620
MIN_HEIGHT = 720

# The window counts as filling the screen when its width reaches the screen's (give or take
# this margin) and its height almost does: the menu bar and the Dock take part of it.
FULLSCREEN_WIDTH_MARGIN = 10
FULLSCREEN_HEIGHT_MARGIN = 160

# Entering full screen fires a burst of <Configure> events; the mode is decided once the size
# has settled for this long.
MODE_DEBOUNCE_MS = 200

# A reminder is written in minutes, so checking twice a minute never lets one slip by.
FIRST_REMINDER_CHECK_MS = 2000
REMINDER_INTERVAL_MS = 30_000

# How long to wait, once the loop runs, before the first startup notice (the window is up by then).
STARTUP_NOTICE_DELAY_MS = 300

_TAB_PADDING_X = 22
_TAB_PADDING_Y = 8
_TAB_UNDERLINE_HEIGHT = 3

# The focus ring is the border of the tab label. The border is always there, in the tab's own
# color, and is taken out of the padding, so the tab has the same size with or without the ring.
_TAB_RING_WIDTH = RING_WIDTH


class Tab(StrEnum):
    TODAY = "today"
    CALENDAR = "calendar"
    MONTH = "month"


class Mode(StrEnum):
    WINDOW = "window"
    FULLSCREEN = "fullscreen"


_TAB_LABELS = {
    Tab.TODAY: texts.TAB_TODAY,
    Tab.CALENDAR: texts.TAB_CALENDAR,
    Tab.MONTH: texts.TAB_MONTH,
}

type TabView = TodayView | CalendarView | MonthView


def fills_screen(width: int, height: int, screen_width: int, screen_height: int) -> bool:
    """Whether a window of this size counts as full screen (or maximized)."""
    return (
        width >= screen_width - FULLSCREEN_WIDTH_MARGIN
        and height >= screen_height - FULLSCREEN_HEIGHT_MARGIN
    )


def reminder_message(habit: Habit) -> str:
    """The body of a habit's reminder: a nudge, plus the goal for a measured habit."""
    measurement = habit.measurement
    if measurement is None:
        return texts.REMINDER_MESSAGE
    return texts.reminder_with_goal(format_number(measurement.goal), measurement.unit)


class MainWindow:
    """The application window. It owns the root: closing the window ends the program.

    ``clock`` supplies the hour for the greetings and ``notifier`` shows a reminder; both
    exist to be replaced in tests.
    """

    def __init__(
        self,
        root: tk.Tk,
        service: HabitService,
        *,
        demo: bool = False,
        clock: Clock | None = None,
        dialogs: Dialogs | None = None,
        notifier: Callable[[str, str], object] = notify,
    ) -> None:
        self.root = root
        self.service = service
        self._clock = clock or SystemClock()
        self._dialogs = dialogs or TkDialogs()
        self._notifier = notifier
        self._mode = Mode.WINDOW
        self._active_tab = Tab.TODAY
        self._focused_tab: Tab | None = None  # the tab with the keyboard focus, if any
        self._mode_job: str | None = None  # the debounce of the size detection
        self._reminder_job: str | None = None
        self._startup_job: str | None = None
        self._reporting_error = False
        self.dashboard: DashboardView | None = None  # built the first time it is needed

        self._configure_root(demo)

        # What is typed for tomorrow's priority follows the person between all the screens.
        self.priority = PriorityEditor(service, root, dialogs=self._dialogs)

        # The window mode's frame wraps the tab bar and the views, so switching modes is
        # hiding or showing a single frame.
        self.window_frame = tk.Frame(root, bg=palette.PAPER)
        self.window_frame.pack(fill="both", expand=True)

        self._tab_widgets: dict[Tab, tuple[tk.Label, tk.Frame]] = {}
        self._build_tab_bar()

        container = self._build_view_container()
        self.today_view = TodayView(
            container, service, priority=self.priority, dialogs=self._dialogs
        )
        self.calendar_view = CalendarView(container, service)
        self.month_view = MonthView(container, service, clock=self._clock)
        self._views: dict[Tab, TabView] = {
            Tab.TODAY: self.today_view,
            Tab.CALENDAR: self.calendar_view,
            Tab.MONTH: self.month_view,
        }
        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

        # The layout follows the real state of the window.
        root.bind("<Configure>", self._on_root_configure)

        self.show_tab(Tab.TODAY)

        # Reminders only sound while the app is open: this clock is all that fires them.
        self._schedule_reminder_check(FIRST_REMINDER_CHECK_MS)

    def _configure_root(self, demo: bool) -> None:
        root = self.root
        root.title(texts.WINDOW_TITLE_DEMO if demo else texts.WINDOW_TITLE)
        root.geometry(WINDOW_SIZE)
        root.minsize(MIN_WIDTH, MIN_HEIGHT)
        root.configure(bg=palette.PAPER)
        root.protocol("WM_DELETE_WINDOW", self.close)
        # Tkinter documents replacing this method as the way to handle errors in callbacks.
        root.report_callback_exception = self.report_callback_exception

    def _build_view_container(self) -> tk.Frame:
        """The frame where the three views share one grid cell; only the due one is on the grid."""
        container = tk.Frame(self.window_frame, bg=palette.PAPER)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        return container

    # ---------- Tabs (window mode) ----------

    def _build_tab_bar(self) -> None:
        """A row of labels with a bar under each: the labels on row 0, the bars on row 1."""
        tab_bar = tk.Frame(self.window_frame, bg=palette.PAPER)
        tab_bar.pack(anchor="w", padx=(22, 0), pady=(10, 0))
        tab_font = font("sans", 12, "bold", master=tab_bar)
        for column, tab in enumerate(Tab):
            label = tk.Label(
                tab_bar,
                text=_TAB_LABELS[tab],
                font=tab_font,
                padx=_TAB_PADDING_X - _TAB_RING_WIDTH,
                pady=_TAB_PADDING_Y - _TAB_RING_WIDTH,
                highlightthickness=_TAB_RING_WIDTH,
                highlightcolor=palette.FOCUS_RING,
                takefocus=True,
                cursor=pointer_cursor(tab_bar),
            )
            label.grid(row=0, column=column, sticky="ew")
            # sticky="ew" makes the bar exactly as wide as its label.
            underline = tk.Frame(tab_bar, height=_TAB_UNDERLINE_HEIGHT, bg=palette.PAPER)
            underline.grid(row=1, column=column, sticky="ew")
            label.bind("<Button-1>", partial(self._on_tab_click, tab))
            label.bind("<FocusIn>", partial(self._on_tab_focus, tab, True), add="+")
            label.bind("<FocusOut>", partial(self._on_tab_focus, tab, False), add="+")
            activate_with_keys(label, partial(self.show_tab, tab))
            label.bind("<Left>", partial(self._on_tab_arrow, tab, -1))
            label.bind("<Right>", partial(self._on_tab_arrow, tab, 1))
            self._tab_widgets[tab] = (label, underline)

    def _on_tab_click(self, tab: Tab, _event: TkEvent) -> None:
        self.show_tab(tab)

    def _on_tab_focus(self, tab: Tab, focused: bool, _event: TkEvent) -> None:
        self._focused_tab = tab if focused else None
        self._paint_tab(tab)

    def _on_tab_arrow(self, tab: Tab, step: int, _event: TkEvent) -> str:
        self.select_neighbor_tab(tab, step)
        return "break"  # the arrows do nothing else while a tab has the focus

    def select_neighbor_tab(self, tab: Tab, step: int) -> None:
        """Activate the tab ``step`` places from ``tab`` and give it the keyboard focus.

        Nothing happens past the first and the last tab.
        """
        tabs = list(Tab)
        index = tabs.index(tab) + step
        if 0 <= index < len(tabs):
            neighbor = tabs[index]
            self.show_tab(neighbor)
            self._tab_widgets[neighbor][0].focus_set()

    def _paint_tab(self, tab: Tab) -> None:
        """Color a tab for its state: active or not, and with the keyboard focus or not."""
        label, underline = self._tab_widgets[tab]
        active = tab is self._active_tab
        background = palette.TAB_ACTIVE_BACKGROUND if active else palette.TAB_INACTIVE_BACKGROUND
        label.configure(
            bg=background,
            fg=palette.TAB_ACTIVE_TEXT if active else palette.TAB_INACTIVE_TEXT,
            # The border is the focus ring: in the tab's color it is not seen.
            highlightbackground=palette.FOCUS_RING if tab is self._focused_tab else background,
        )
        underline.configure(bg=palette.LILAC if active else palette.PAPER)

    def show_tab(self, tab: Tab) -> None:
        """Activate a tab: repaint the bar, show its view and refresh it with fresh data.

        The other views leave the grid instead of just being covered, so Tab never reaches a
        control that cannot be seen; the keyboard focus leaves them too.
        """
        self._active_tab = tab
        for key in self._tab_widgets:
            self._paint_tab(key)
        for key, view in self._views.items():
            if key is tab:
                view.grid(row=0, column=0, sticky="nsew")
            else:
                self._release_focus_from(view)
                view.grid_remove()
        self._views[tab].refresh()

    def _release_focus_from(self, widget: tk.Misc) -> None:
        """Take the keyboard focus to the window if it is inside ``widget``, about to be hidden."""
        focused = focused_widget(self.root)
        if focused is not None and is_inside(focused, widget):
            self.root.focus_set()

    @property
    def active_tab(self) -> Tab:
        return self._active_tab

    @property
    def mode(self) -> Mode:
        return self._mode

    # ---------- Mode: window or dashboard, from the real size ----------
    # The window is never moved from here: macOS decides, the person enters and leaves full
    # screen with the green button and the app only reacts.

    def _on_root_configure(self, event: TkEvent) -> None:
        # A bind on the root also receives the <Configure> of all its children.
        if str(event.widget) != str(self.root):
            return
        if self._mode_job is not None:
            self.root.after_cancel(self._mode_job)
        self._mode_job = self.root.after(MODE_DEBOUNCE_MS, self._adjust_mode_to_size)

    def _adjust_mode_to_size(self) -> None:
        """If the window fills the screen it is the dashboard's turn; if not, the compact mode."""
        self._mode_job = None
        full = fills_screen(
            self.root.winfo_width(),
            self.root.winfo_height(),
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
        )
        if full and self._mode is not Mode.FULLSCREEN:
            self.show_dashboard()
        elif not full and self._mode is not Mode.WINDOW:
            self.show_window()

    def show_dashboard(self) -> None:
        """Show the big dashboard (the window is already filling the screen)."""
        # Built once and reused: its constructor already draws, so reusing it only refreshes.
        if self.dashboard is None:
            self.dashboard = DashboardView(
                self.root,
                self.service,
                priority=self.priority,
                dialogs=self._dialogs,
                clock=self._clock,
            )
        else:
            self.dashboard.reset_modes()  # a half-done delete does not survive the switch
            self.dashboard.refresh()
        self._release_focus_from(self.window_frame)
        self.window_frame.pack_forget()
        self.root.configure(bg=palette.BACKGROUND)
        self.dashboard.pack(fill="both", expand=True)
        self._mode = Mode.FULLSCREEN

    def show_window(self) -> None:
        """Go back to the compact app (the window has returned to its size)."""
        if self.dashboard is not None:
            self._release_focus_from(self.dashboard)
            self.dashboard.pack_forget()
        self.root.configure(bg=palette.PAPER)
        self.window_frame.pack(fill="both", expand=True)
        self._mode = Mode.WINDOW
        # The data may have changed on the dashboard (a habit was marked, say).
        self.show_tab(self._active_tab)

    # ---------- Reminders ----------

    def check_reminders(self) -> None:
        """Show the reminders that are due now and schedule the next check.

        This is a periodic task, so a failure is logged and never stops the clock: the next
        check runs regardless. Each reminder is isolated from the others, because the service
        reports a reminder only once and one that fails to show would otherwise be lost
        together with the ones after it.
        """
        try:
            due = self.service.pending_reminders()
        except Exception:
            log.exception("could not read the pending reminders")
            due = []
        for habit in due:
            try:
                self._notifier(habit.name, reminder_message(habit))
            except Exception:
                log.exception("could not show the reminder of habit %d", habit.id)
        self._schedule_reminder_check(REMINDER_INTERVAL_MS)

    def _schedule_reminder_check(self, delay_ms: int) -> None:
        # Cancelling the previous one keeps a single clock running even if a check is
        # requested by hand while the timer is still pending.
        if self._reminder_job is not None:
            self.root.after_cancel(self._reminder_job)
        self._reminder_job = self.root.after(delay_ms, self.check_reminders)

    # ---------- Startup notices ----------

    def show_startup_messages(self, messages: Sequence[str]) -> None:
        """Show each message in a warning dialog once the window is on screen."""
        if messages:
            self._startup_job = self.root.after(
                STARTUP_NOTICE_DELAY_MS, self._show_messages, tuple(messages)
            )

    def _show_messages(self, messages: tuple[str, ...]) -> None:
        self._startup_job = None
        for message in messages:
            self._dialogs.show_warning(texts.NOTICE_TITLE, message)

    # ---------- Errors and closing ----------

    def report_callback_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        """Log an error raised inside a Tk callback and tell the person, briefly.

        Without this Tkinter prints the traceback to stderr, which nobody sees when the
        app is launched from the Dock.
        """
        log.error(
            "unhandled error in a Tk callback", exc_info=(exc_type, exc_value, exc_traceback)
        )
        if self._reporting_error:  # an error while the dialog is open must not stack dialogs
            return
        self._reporting_error = True
        try:
            self._dialogs.show_error(texts.UNEXPECTED_ERROR_TITLE, texts.UNEXPECTED_ERROR_MESSAGE)
        except tk.TclError:
            log.exception("the error dialog could not be shown")
        finally:
            self._reporting_error = False

    def close(self) -> None:
        """Cancel everything scheduled and destroy the window, which ends the program."""
        if not widget_exists(self.root):
            return
        for job in (self._mode_job, self._reminder_job, self._startup_job):
            if job is not None:
                self.root.after_cancel(job)
        self._mode_job = self._reminder_job = self._startup_job = None
        self.root.destroy()


def run(
    service: HabitService, *, demo: bool = False, startup_messages: Sequence[str] = ()
) -> None:
    """Open the application window and keep it running until it is closed.

    ``startup_messages`` (what happened while the data was being prepared) are each shown in
    a warning dialog as soon as the window is on screen. Logging is configured by the caller.
    """
    root = tk.Tk()
    window = MainWindow(root, service, demo=demo)
    window.show_startup_messages(startup_messages)
    root.mainloop()
