"""Guided capture of the README screenshots, and the animated GIF built from them.

    python tools/capture_screens.py                  # capture every scene
    python tools/capture_screens.py --rebuild-gif    # rebuild demo.gif from the saved PNGs

The app opens in demo mode on a fixed clock with its data in memory: nothing is read from or
written to disk. The script puts the window in each scene and asks for a screenshot of it
(Command-Shift-4, Space, click on the window). It picks up the new file from the screenshots
folder once it is completely written, refuses full-screen captures and captures of another
window, and saves the accepted ones under the name of the scene. When every scene is saved it
builds the GIF.

Taking screenshots needs macOS. Pillow (the ``tools`` dependency group) reads and combines the
images; the GIF can be rebuilt on any system.
"""

import argparse
import importlib
import sys
import time
import tkinter as tk
import traceback
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import ModuleType, TracebackType

from habit_tracker.clock import Clock, FixedClock
from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.enums import Weekday
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository
from habit_tracker.ui.controllers.dialogs import Dialogs
from habit_tracker.ui.forms import texts as form_texts
from habit_tracker.ui.forms.choices import FrequencyChoice, MeasurementChoice, TextField
from habit_tracker.ui.forms.habit_form import HabitFormDialog
from habit_tracker.ui.forms.parts import WeekdayChipRow
from habit_tracker.ui.main_window import WINDOW_SIZE, MainWindow, Mode, Tab
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.tkutil import widget_exists
from habit_tracker.ui.views import texts as view_texts
from habit_tracker.ui.widgets.chips import SelectionChip
from habit_tracker.ui.widgets.date_picker import DatePicker
from habit_tracker.ui.widgets.soft_button import SoftButton
from habit_tracker.ui.widgets.soft_menu import SoftMenu

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "img"
GIF_NAME = "demo.gif"

# The scenes in the order they are shown; each one is saved as ``<name>.png``.
SCENES: tuple[str, ...] = (
    "hoy",
    "marcado",
    "formulario",
    "formulario-fechas",
    "formulario-final",
    "calendario",
    "mi-mes",
    "eliminar",
    "dashboard",
    "dashboard-constancia",
)

# The frames of the GIF, in order; the other scenes only illustrate the README.
GIF_FRAMES: tuple[str, ...] = (
    "hoy",
    "marcado",
    "formulario",
    "formulario-fechas",
    "formulario-final",
    "calendario",
    "mi-mes",
    "eliminar",
)

TITLE_BAR_HEIGHT = 32  # points the macOS title bar adds above the window content
SCREEN_SCALE = 2  # screenshots come out at twice the size in points (retina)
FULLSCREEN_MARGIN = 6  # pixels of difference still counted as "the whole screen"
ASPECT_TOLERANCE = 0.12
SCREENSHOT_PREFIXES = ("captura", "screenshot")  # macOS names them in the system language

GIF_CANVAS = (760, 940)
GIF_MARGIN = 40
GIF_FRAME_SECONDS = 1.8
GIF_COLORS = 128
GIF_BACKGROUND = palette.BACKGROUND

CAPTURE_HOUR = 10  # the fixed clock stops at this hour of the current day
MAIN_WINDOW_POSITION = "+40+70"
FORM_POSITION = "+700+70"  # beside the main window, so neither one covers the other
DASHBOARD_TOP = 28  # below the menu bar
DASHBOARD_BOTTOM_MARGIN = 110  # screen height left free for the Dock
FORM_SCROLL_MARGIN = 30

START_DELAY_MS = 1200
POLL_START_MS = 1500
POLL_INTERVAL_MS = 600
SETTLE_DELAY_MS = 900  # time given to a scene to lay itself out before asking for the capture
SETTLE_POLL_MS = 200
MAX_SETTLE_ATTEMPTS = 25

# Sample content typed into the form (what the screenshots show).
SAMPLE_NAME = "Leer 20 minutos"
SAMPLE_MOTIVATION = "Un poquito cada día, sin presión."
SAMPLE_AREA_ID = "crecimiento"
SAMPLE_DAYS = (Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY)
SAMPLE_DATE_OFFSETS = (3, 10, 17)  # days from today
SAMPLE_GOAL = "20"
SAMPLE_END_OFFSET = 60  # days from today
SAMPLE_REMINDER_TIME = "20:00"
DELETE_SELECTION = (3, 4)  # positions in the habit list

PILLOW_MISSING = (
    "Pillow is required to read and combine the screenshots. "
    "Install it with: python -m pip install pillow  (or: python -m pip install --group tools)"
)

# What the person reads while taking the captures is in Spanish, like the app.
MAIN_WINDOW = f"la ventana «{view_texts.WINDOW_TITLE}»"
FORM_WINDOW = f"la ventana «{form_texts.TITLE_NEW}»"
LARGE_WINDOW = f"{MAIN_WINDOW} (grande)"

# For each scene: what it shows and which window has to be captured.
SCENE_TEXTS: dict[str, tuple[str, str]] = {
    "hoy": ("La vista Hoy", MAIN_WINDOW),
    "marcado": ("Con un hábito marcado", MAIN_WINDOW),
    "formulario": ("El formulario de hábito", FORM_WINDOW),
    "formulario-fechas": ("Fechas concretas con el calendario", FORM_WINDOW),
    "formulario-final": ("Medición, vigencia y vista previa", FORM_WINDOW),
    "calendario": ("La pestaña Calendario", MAIN_WINDOW),
    "mi-mes": ("La pestaña Mi mes", MAIN_WINDOW),
    "eliminar": ("El modo eliminar", MAIN_WINDOW),
    "dashboard": ("El dashboard de pantalla completa", LARGE_WINDOW),
    "dashboard-constancia": ("El dashboard, parte de abajo", LARGE_WINDOW),
}
MSG_FULLSCREEN = (
    "    ✗ Captura de PANTALLA COMPLETA (muestra el escritorio): descartada. "
    "Repetirla solo de la ventana (⌘ ⇧ 4 → Espacio → clic)."
)
MSG_PERMISSION = (
    "\nNo se puede leer la carpeta de capturas. En Ajustes del Sistema → Privacidad y "
    "seguridad → Archivos y carpetas, dar acceso a la Terminal, o usar --captures-dir con "
    "otra carpeta."
)
MSG_WINDOW_CLOSED = (
    "\nSe cerró la ventana de la escena antes de recoger la captura: el guion se detiene."
)
MSG_NOT_READY = "    Aviso: la ventana no llegó a su estado final; revisar antes de capturar."
MSG_NOTHING_TO_MARK = "    Aviso: no hay un hábito pendiente que marcar hoy."


class CaptureError(Exception):
    """Something that stops the tool, worded for the person running it."""


class CaptureProblem(StrEnum):
    """Why a screenshot does not fit the scene it was taken for."""

    FULLSCREEN = "fullscreen"
    WRONG_SHAPE = "wrong-shape"


# ---------- Pure pieces (no windows) ----------


def is_fullscreen_capture(
    size: tuple[int, int],
    screen_points: tuple[int, int],
    *,
    scale: int = SCREEN_SCALE,
    margin: int = FULLSCREEN_MARGIN,
) -> bool:
    """Whether an image is exactly as big as the whole screen.

    A window capture is always smaller (at least the menu bar is missing), so this tells
    apart the captures that show the desktop, other programs or notifications.
    """
    width, height = size
    return (
        abs(width - screen_points[0] * scale) <= margin
        and abs(height - screen_points[1] * scale) <= margin
    )


def matches_window_shape(
    size: tuple[int, int],
    window_points: tuple[int, int],
    tolerance: float = ASPECT_TOLERANCE,
) -> bool:
    """Whether the proportions of an image resemble those of the window it should show."""
    expected = window_points[0] / (window_points[1] + TITLE_BAR_HEIGHT)
    return abs(size[0] / size[1] - expected) <= tolerance


def check_capture(
    size: tuple[int, int],
    screen_points: tuple[int, int],
    window_points: tuple[int, int],
) -> CaptureProblem | None:
    """The reason a capture of this size cannot be used, or ``None`` when it fits."""
    if is_fullscreen_capture(size, screen_points):
        return CaptureProblem.FULLSCREEN
    if not matches_window_shape(size, window_points):
        return CaptureProblem.WRONG_SHAPE
    return None


def is_screenshot_name(name: str) -> bool:
    """Whether a file name looks like a macOS screenshot (Spanish or English)."""
    lowered = name.lower()
    return lowered.endswith(".png") and lowered.startswith(SCREENSHOT_PREFIXES)


class CaptureWatcher:
    """Finds the next screenshot in a folder, polled from a timer.

    Only files modified at or after ``since`` count, and each one is returned once. macOS
    writes the file while it shows the thumbnail, so a file is returned only when its size
    is the same in two consecutive polls (and not zero): nothing here waits or sleeps.
    """

    def __init__(self, directory: Path, since: float) -> None:
        self.directory = directory
        self.since = since
        self._seen: set[Path] = set()
        self._pending: tuple[Path, int] | None = None

    def poll(self) -> Path | None:
        """The newest new screenshot once it is completely written, otherwise ``None``."""
        candidate = self._newest()
        if candidate is None:
            self._pending = None
            return None
        try:
            size = candidate.stat().st_size
        except FileNotFoundError:
            self._pending = None
            return None
        if size > 0 and self._pending == (candidate, size):
            self._pending = None
            self._seen.add(candidate)
            return candidate
        self._pending = (candidate, size)
        return None

    def _newest(self) -> Path | None:
        candidates: list[tuple[float, Path]] = []
        for path in self.directory.iterdir():
            if path in self._seen or not is_screenshot_name(path.name):
                continue
            try:
                modified = path.stat().st_mtime
            except FileNotFoundError:
                continue  # removed between the listing and the stat
            if modified >= self.since:
                candidates.append((modified, path))
        return max(candidates)[1] if candidates else None


def _pillow_image() -> ModuleType:
    """The ``PIL.Image`` module, or a clear error when Pillow is not installed."""
    try:
        return importlib.import_module("PIL.Image")
    except ImportError as error:
        raise CaptureError(PILLOW_MISSING) from error


def compose_gif(
    frames: Sequence[Path],
    destination: Path,
    *,
    canvas: tuple[int, int] = GIF_CANVAS,
    seconds: float = GIF_FRAME_SECONDS,
    background: str = GIF_BACKGROUND,
) -> int:
    """Join the screenshots into a looping GIF and return how many frames it has.

    Each image is drawn at its normal size (retina captures are halved), centered on a flat
    background of the theme.
    """
    if not frames:
        raise ValueError("a GIF needs at least one frame")
    image_module = _pillow_image()
    images = []
    for path in frames:
        with image_module.open(path) as original:
            image = original.convert("RGBA")
        scale = min(
            1 / SCREEN_SCALE,
            (canvas[0] - GIF_MARGIN) / image.width,
            (canvas[1] - GIF_MARGIN) / image.height,
        )
        size = (round(image.width * scale), round(image.height * scale))
        image = image.resize(size, image_module.Resampling.LANCZOS)
        base = image_module.new("RGBA", canvas, background)
        base.alpha_composite(image, ((canvas[0] - size[0]) // 2, (canvas[1] - size[1]) // 2))
        images.append(
            base.convert("RGB").quantize(
                colors=GIF_COLORS,
                method=image_module.Quantize.MEDIANCUT,
                dither=image_module.Dither.FLOYDSTEINBERG,
            )
        )
    images[0].save(
        destination,
        save_all=True,
        append_images=images[1:],
        loop=0,
        duration=round(seconds * 1000),
        optimize=True,
        disposal=1,
    )
    return len(images)


def missing_frames(directory: Path) -> list[str]:
    """The file names of the GIF frames that are not saved in ``directory`` yet."""
    return [f"{name}.png" for name in GIF_FRAMES if not (directory / f"{name}.png").exists()]


def display_path(path: Path) -> str:
    """The path relative to the repository when it lives there, absolute otherwise."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def rebuild_gif(directory: Path) -> bool:
    """Build ``demo.gif`` from the frames saved in ``directory``; say which ones are missing."""
    missing = missing_frames(directory)
    if missing:
        print(f"Cannot build the GIF: missing {', '.join(missing)}", file=sys.stderr, flush=True)
        return False
    destination = directory / GIF_NAME
    count = compose_gif([directory / f"{name}.png" for name in GIF_FRAMES], destination)
    megabytes = destination.stat().st_size / 1024 / 1024
    print(
        f"\nGIF built from {count} frames: {display_path(destination)} ({megabytes:.1f} MB)",
        flush=True,
    )
    return True


def require_macos(platform: str) -> None:
    """Taking screenshots relies on the macOS capture shortcut and window chrome."""
    if platform != "darwin":
        raise CaptureError(
            "taking the screenshots needs macOS (--rebuild-gif works on any system)"
        )


def capture_clock() -> FixedClock:
    """A clock stopped at 10:00 of the current day, so dates and greetings do not move."""
    moment = datetime.now().replace(hour=CAPTURE_HOUR, minute=0, second=0, microsecond=0)
    return FixedClock(moment)


# ---------- Driving the app ----------


@dataclass(frozen=True, slots=True)
class Scene:
    """A state of the app to capture.

    ``show`` puts the app in the scene and returns the window to capture; ``settle`` runs once
    the layout has caught up (scrolling, waiting for the dashboard) and returns whether the
    scene is ready.
    """

    name: str
    title: str
    target: str
    show: Callable[[], tk.Misc]
    settle: Callable[[], bool] | None = None


@dataclass(slots=True)
class _Waiting:
    scene: Scene
    window: tk.Misc
    watcher: CaptureWatcher


def capture_instructions(position: int, total: int, scene: Scene, destination: str) -> str:
    """What the person is told to capture for a scene."""
    return (
        f"\n[{position}/{total}] {scene.title}\n"
        f"    Capturar {scene.target}:  ⌘ ⇧ 4 → Espacio → clic en la ventana "
        "(con Option apretado, sin sombra)\n"
        f"    Se guardará como {destination}"
    )


def _silent_notifier(title: str, message: str) -> bool:
    """Reminders must not pop a system notification in the middle of a capture."""
    return False


class FormPilot:
    """Operates the open habit form through its widgets, as a person would.

    The form keeps its choices in ``dialog.form_state`` but only reads them when it builds a
    widget, so a choice has to go through the widgets for the window to show it.
    """

    def __init__(self, dialog: HabitFormDialog) -> None:
        self.dialog = dialog

    def _descendants(self, widget: tk.Misc | None = None) -> Iterator[tk.Misc]:
        parent = self.dialog if widget is None else widget
        for child in parent.winfo_children():
            yield child
            yield from self._descendants(child)

    def _widgets[W: tk.Misc](self, kind: type[W]) -> list[W]:
        return [widget for widget in self._descendants() if isinstance(widget, kind)]

    # ----- doing things -----

    def type_into(self, field: TextField, text: str) -> None:
        for entry in self._widgets(tk.Entry):
            if entry.winfo_name() == field.value:
                entry.delete(0, "end")
                entry.insert(0, text)
                return
        raise CaptureError(f"the form has no field {field.value!r}")

    def menu(self, options: Sequence[str]) -> SoftMenu:
        """The menu offering exactly these options."""
        wanted = tuple(options)
        for menu in self._widgets(SoftMenu):
            if tuple(menu.options) == wanted:
                return menu
        raise CaptureError(f"the form has no menu with the options {wanted!r}")

    def choose(self, options: Sequence[str], index: int) -> None:
        """Choose an entry of a menu: show it as chosen and run the menu's command."""
        menu = self.menu(options)
        menu.current(index)
        if menu.command is not None:
            menu.command()

    def press(self, text: str) -> None:
        for button in self._widgets(SoftButton):
            if button.text == text:
                button.command()
                return
        raise CaptureError(f"the form has no button {text!r}")

    def press_chip(self, text: str) -> None:
        """Press a chip without a color dot (the area chips have one)."""
        for chip in self._widgets(SelectionChip):
            if chip.text == text and chip.color is None:
                chip.command()
                return
        raise CaptureError(f"the form has no chip {text!r}")

    def press_area(self, name: str) -> None:
        for chip in self._widgets(SelectionChip):
            if chip.text == name and chip.color is not None:
                chip.command()
                return
        raise CaptureError(f"the form has no area {name!r}")

    def toggle_days(self, days: Iterable[Weekday]) -> None:
        """Toggle weekdays in the first row of weekday chips of the form."""
        rows = self._widgets(WeekdayChipRow)
        if not rows:
            raise CaptureError("the form shows no row of weekdays")
        for day in days:
            rows[0].chips[day].command()

    def pick_dates(self, days: Iterable[date]) -> None:
        """Toggle days in the calendar that picks several dates."""
        pickers = [picker for picker in self._widgets(DatePicker) if picker.mode == "multiple"]
        if not pickers:
            raise CaptureError("the form shows no calendar to pick dates")
        for day in days:
            pickers[0].toggle(day)

    # ----- scrolling -----

    def scroll_canvas(self) -> tk.Canvas:
        """The canvas that scrolls the body of the form (the only one wired to a scrollbar)."""
        for canvas in self._widgets(tk.Canvas):
            if str(canvas.cget("yscrollcommand")):
                return canvas
        raise CaptureError("the form has no scrolling area")

    def scroll_to(self, fraction: float) -> None:
        """Scroll to a fraction of the body: 0.0 is the top and 1.0 the bottom."""
        self.dialog.update_idletasks()
        self.scroll_canvas().yview_moveto(fraction)

    def scroll_to_widget(self, widget: tk.Misc, margin: int = FORM_SCROLL_MARGIN) -> None:
        """Scroll so that ``widget`` sits near the top of the visible area."""
        canvas = self.scroll_canvas()
        self.dialog.update_idletasks()
        region = [float(str(value)) for value in canvas.tk.splitlist(canvas.cget("scrollregion"))]
        if len(region) != 4 or region[3] <= region[1]:
            return  # the layout has not reported its height yet
        top = widget.winfo_rooty() - canvas.winfo_rooty() + canvas.canvasy(0)
        canvas.yview_moveto(max(0.0, top - margin) / (region[3] - region[1]))


class CaptureScript:
    """Puts the app in each scene and collects the screenshot taken of it.

    ``hidden`` is for tests: the windows stay withdrawn and no capture is awaited. ``root``
    lets a test provide the window to build the app on; ``clock`` and ``dialogs`` replace the
    stopped clock and the system dialogs.
    """

    def __init__(
        self,
        output: Path,
        captures_dir: Path,
        *,
        validate: bool = True,
        hidden: bool = False,
        root: tk.Tk | None = None,
        clock: Clock | None = None,
        dialogs: Dialogs | None = None,
    ) -> None:
        self.output = output
        self.captures_dir = captures_dir
        self.validate = validate
        self.hidden = hidden
        self.clock = clock if clock is not None else capture_clock()
        snapshot = build_demo_snapshot(self.clock.now().date())
        self.service = HabitService(MemoryRepository(snapshot), self.clock)
        self.root = root if root is not None else tk.Tk()
        # Not the "demo" title: the window in the images should look like the regular app.
        self.window = MainWindow(
            self.root, self.service, clock=self.clock, dialogs=dialogs, notifier=_silent_notifier
        )
        self.root.geometry(f"{WINDOW_SIZE}{MAIN_WINDOW_POSITION}")
        if hidden:
            self.root.withdraw()

        self.dialog: HabitFormDialog | None = None
        self.form: FormPilot | None = None
        self.saved: list[Path] = []
        self.scenes = self._build_scenes()
        self.index = -1
        self._waiting: _Waiting | None = None
        self._finished = False

    @property
    def completed(self) -> bool:
        """Whether every scene has its capture."""
        return len(self.saved) == len(self.scenes)

    def run(self) -> bool:
        """Run the session until the last scene (or the window is closed).

        Returns whether every scene was captured.
        """
        # An error in a timer would otherwise open the app's own error dialog over the capture
        # and leave the terminal waiting for a screenshot that is never asked for.
        self.root.report_callback_exception = self.report_error
        self.root.after(START_DELAY_MS, self.advance)
        self.root.after(POLL_START_MS, self.poll)
        self.root.lift()
        self.root.mainloop()
        return self.completed

    def report_error(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        """Print an error raised in a Tk callback in the terminal and end the session."""
        if isinstance(exc_value, CaptureError):
            print(f"\ncapture_screens: {exc_value}", file=sys.stderr, flush=True)
        else:
            traceback.print_exception(exc_type, exc_value, exc_traceback)
        self.finish()

    # ----- scenes: each one leaves the app in a state and returns the window to capture -----

    def _build_scenes(self) -> list[Scene]:
        handlers: dict[str, tuple[Callable[[], tk.Misc], Callable[[], bool] | None]] = {
            "hoy": (self._show_today, None),
            "marcado": (self._show_marked, None),
            "formulario": (self._show_form, self._scroll_form_top),
            "formulario-fechas": (self._show_form_dates, self._scroll_form_to_frequency),
            "formulario-final": (self._show_form_details, self._scroll_form_bottom),
            "calendario": (self._show_calendar, None),
            "mi-mes": (self._show_month, None),
            "eliminar": (self._show_delete_mode, None),
            "dashboard": (self._show_dashboard, self._dashboard_is_up),
            "dashboard-constancia": (self._show_dashboard_bottom, self._scroll_dashboard_down),
        }
        scenes = []
        for name in SCENES:
            title, target = SCENE_TEXTS[name]
            show, settle = handlers[name]
            scenes.append(Scene(name, title, target, show, settle))
        return scenes

    def _show_today(self) -> tk.Misc:
        self.window.show_tab(Tab.TODAY)
        return self.root

    def _show_marked(self) -> tk.Misc:
        # The first habit that is due today, still pending and asks for no value when marked.
        today = self.service.today()
        for habit in self.service.habits():
            if habit.applies_on(today) and not habit.is_done(today) and habit.measurement is None:
                self.service.mark(habit.id, True, day=today)
                break
        else:
            print(MSG_NOTHING_TO_MARK, flush=True)
        self.window.today_view.refresh()
        return self.root

    def _require_form(self) -> FormPilot:
        if self.form is None:
            raise CaptureError("the form is not open: its scenes must run in order")
        return self.form

    def _show_form(self) -> tk.Misc:
        self._close_form()
        dialog = HabitFormDialog(
            self.root, self.service, on_saved=lambda _habit: self.window.today_view.refresh()
        )
        dialog.geometry(FORM_POSITION)
        if self.hidden:
            dialog.withdraw()
        self.dialog = dialog
        form = self.form = FormPilot(dialog)

        area = next(area for area in self.service.areas() if area.id == SAMPLE_AREA_ID)
        form.type_into(TextField.NAME, SAMPLE_NAME)
        form.type_into(TextField.DESCRIPTION, SAMPLE_MOTIVATION)
        form.press_area(area.name)
        form.choose(form_texts.FREQUENCY_OPTIONS, FrequencyChoice.TIMES_PER_WEEK)
        form.toggle_days(SAMPLE_DAYS)
        return dialog

    def _show_form_dates(self) -> tk.Misc:
        form = self._require_form()
        form.choose(form_texts.FREQUENCY_OPTIONS, FrequencyChoice.FIXED_DATES)
        today = self.service.today()
        form.pick_dates(today + timedelta(days=offset) for offset in SAMPLE_DATE_OFFSETS)
        return form.dialog

    def _show_form_details(self) -> tk.Misc:
        form = self._require_form()
        today = self.service.today()
        form.choose(form_texts.FREQUENCY_OPTIONS, FrequencyChoice.TIMES_PER_WEEK)
        form.choose(form_texts.MEASUREMENT_OPTIONS, MeasurementChoice.DURATION)
        form.type_into(TextField.GOAL, SAMPLE_GOAL)
        form.press_chip(form_texts.WITH_END)
        end = today + timedelta(days=SAMPLE_END_OFFSET)
        form.type_into(TextField.END, end.isoformat())
        form.press(form_texts.SHOW_ADVANCED)
        form.press_chip(form_texts.WANT_REMINDER)
        form.type_into(TextField.REMINDER_TIME, SAMPLE_REMINDER_TIME)
        return form.dialog

    def _scroll_form_top(self) -> bool:
        self._require_form().scroll_to(0.0)
        return True

    def _scroll_form_to_frequency(self) -> bool:
        form = self._require_form()
        form.scroll_to_widget(form.menu(form_texts.FREQUENCY_OPTIONS))
        return True

    def _scroll_form_bottom(self) -> bool:
        self._require_form().scroll_to(1.0)
        return True

    def _close_form(self) -> None:
        if self.dialog is not None and widget_exists(self.dialog):
            self.dialog.destroy()
        self.dialog = None
        self.form = None

    def _show_calendar(self) -> tk.Misc:
        self._close_form()
        self.window.show_tab(Tab.CALENDAR)
        return self.root

    def _show_month(self) -> tk.Misc:
        self.window.show_tab(Tab.MONTH)
        return self.root

    def _show_delete_mode(self) -> tk.Misc:
        self.window.show_tab(Tab.TODAY)
        delete_mode = self.window.today_view.delete_mode
        delete_mode.enter()
        habits = self.service.habits()
        for position in DELETE_SELECTION:
            delete_mode.toggle(habits[position])
        return self.root

    def _show_dashboard(self) -> tk.Misc:
        # Large enough for the window to switch to the dashboard by itself.
        self.window.today_view.delete_mode.cancel()
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight() - DASHBOARD_BOTTOM_MARGIN
        self.root.geometry(f"{width}x{height}+0+{DASHBOARD_TOP}")
        if self.hidden:
            self.window.show_dashboard()  # a withdrawn window reports no change of size
        return self.root

    def _show_dashboard_bottom(self) -> tk.Misc:
        return self.root  # the same window; the scene only scrolls it

    def _dashboard_is_up(self) -> bool:
        return self.window.mode is Mode.FULLSCREEN

    def _scroll_dashboard_down(self) -> bool:
        dashboard = self.window.dashboard
        if dashboard is None:
            return False
        dashboard.update_idletasks()
        dashboard.scroll_canvas.yview_moveto(1.0)
        return True

    # ----- moving along the scenes -----

    def advance(self) -> Scene | None:
        """Show the next scene, or finish after the last one. Returns the scene shown."""
        self.index += 1
        if self.index >= len(self.scenes):
            self.finish()
            return None
        scene = self.scenes[self.index]
        window = scene.show()
        if self.hidden:
            self.root.update_idletasks()
            if scene.settle is not None:
                scene.settle()
        else:
            window.lift()
            self.root.after(SETTLE_DELAY_MS, self._settle, scene, window, 0)
        return scene

    def _settle(self, scene: Scene, window: tk.Misc, attempt: int) -> None:
        """Give the scene time to reach its final state, then ask for the capture."""
        if self._finished or not widget_exists(window):
            return
        ready = scene.settle() if scene.settle is not None else True
        if not ready and attempt < MAX_SETTLE_ATTEMPTS:
            self.root.after(SETTLE_POLL_MS, self._settle, scene, window, attempt + 1)
            return
        if not ready:
            print(MSG_NOT_READY, flush=True)
        self.wait_for_capture(scene, window)

    def wait_for_capture(
        self, scene: Scene, window: tk.Misc, *, since: float | None = None
    ) -> None:
        """Tell the person what to capture and start watching for the file.

        Only screenshots modified at or after ``since`` (by default, one second ago) count.
        """
        window.update()
        started = time.time() - 1 if since is None else since
        self._waiting = _Waiting(scene, window, CaptureWatcher(self.captures_dir, started))
        destination = display_path(self.output / f"{scene.name}.png")
        print(
            capture_instructions(self.index + 1, len(self.scenes), scene, destination), flush=True
        )

    def poll(self) -> None:
        """Look for the awaited screenshot and schedule the next look.

        Meant to be driven by ``after``; the session moves on when a screenshot is accepted.
        """
        waiting = self._waiting
        if waiting is not None:
            self._poll_for(waiting)
        if not self._finished and widget_exists(self.root):
            self.root.after(POLL_INTERVAL_MS, self.poll)

    def _poll_for(self, waiting: _Waiting) -> None:
        if not widget_exists(waiting.window):
            print(MSG_WINDOW_CLOSED, flush=True)
            self.finish()
            return
        try:
            capture = waiting.watcher.poll()
        except PermissionError:
            print(MSG_PERMISSION, flush=True)
            self.finish()
            return
        if capture is None:
            return
        window_size = (waiting.window.winfo_width(), waiting.window.winfo_height())
        if self.accept(waiting.scene, window_size, capture):
            self._waiting = None
            self.advance()

    def accept(self, scene: Scene, window_size: tuple[int, int], capture: Path) -> bool:
        """Validate a screenshot and, if it fits, save it as the scene's image.

        ``window_size`` is the size in points of the window that should be in the capture.
        Returns whether the capture was accepted.
        """
        image_module = _pillow_image()
        try:
            with image_module.open(capture) as image:
                size: tuple[int, int] = image.size
                if self.validate:
                    screen = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
                    problem = check_capture(size, screen, window_size)
                    if problem is CaptureProblem.FULLSCREEN:
                        print(MSG_FULLSCREEN, flush=True)
                        return False
                    if problem is CaptureProblem.WRONG_SHAPE:
                        print(
                            f"    ✗ La forma de esa captura ({size[0]}x{size[1]}) no parece "
                            f"{scene.target}. Repetirla (o usar --no-validate).",
                            flush=True,
                        )
                        return False
                destination = self.output / f"{scene.name}.png"
                image.save(destination, optimize=True)
        except OSError as error:
            print(f"    ✗ No se pudo procesar la captura: {error}", flush=True)
            return False
        self.saved.append(destination)
        print(f"    ✓ Guardada: {display_path(destination)} ({size[0]}x{size[1]})", flush=True)
        return True

    def finish(self) -> None:
        """End the session: build the GIF if every scene was captured, and close the app."""
        if self._finished:
            return
        self._finished = True
        self._waiting = None
        if self.completed:
            rebuild_gif(self.output)
        else:
            print(
                f"\nSaved {len(self.saved)} of {len(self.scenes)} captures; the GIF was not "
                "built. Run again with --rebuild-gif once every frame is saved.",
                flush=True,
            )
        print(
            f"\nListo. Las capturas originales siguen en {self.captures_dir}: se pueden borrar.",
            flush=True,
        )
        self.window.close()


# ---------- Command line ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture_screens.py",
        description=(
            "Guided capture of the README screenshots. The app opens in demo mode, the script "
            "puts it in each scene and picks up the macOS screenshot taken of it "
            "(Command-Shift-4, Space, click on the window). Then it builds the GIF."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        metavar="DIR",
        help="where to save the images (default: %(default)s)",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path.home() / "Desktop",
        metavar="DIR",
        help="folder where macOS saves the screenshots (default: %(default)s)",
    )
    parser.add_argument(
        "--rebuild-gif",
        action="store_true",
        help="rebuild demo.gif from the PNGs already saved in --output, without opening the app",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="accept any screenshot, without checking its size and shape",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.rebuild_gif:
            _pillow_image()
            return 0 if rebuild_gif(args.output) else 1
        require_macos(sys.platform)
        _pillow_image()
        if not args.captures_dir.is_dir():
            raise CaptureError(f"the screenshots folder does not exist: {args.captures_dir}")
        args.output.mkdir(parents=True, exist_ok=True)
        script = CaptureScript(args.output, args.captures_dir, validate=not args.no_validate)
    except CaptureError as error:
        print(f"capture_screens: {error}", file=sys.stderr)
        return 1
    except (OSError, tk.TclError) as error:
        print(f"capture_screens: {error}", file=sys.stderr)
        return 1
    print("Guion de capturas. La app se abre con datos de demostración; seguir las indicaciones.")
    try:
        completed = script.run()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
