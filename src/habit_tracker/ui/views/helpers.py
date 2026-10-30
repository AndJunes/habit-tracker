"""Small pieces several screens need: canvases, text fitting, the editing gesture and the keyboard.

The keyboard side is shared by the lists of habits of the "Hoy" tab and of the dashboard: a row
that can be reached with Tab, the ring it shows while it has the focus, the keys that act on it
and the memory that puts the focus back on a row after the list is drawn again.
"""

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from ...domain.models import Habit
from ..theme import palette
from ..theme.drawing import mix_colors
from ..theme.focus import RING_WIDTH, activate_with_keys, focus_ring, track_focus
from ..theme.fonts import measure
from ..theme.tkutil import TkEvent, widget_exists

# Right click, Control-click and button 2 (the right button on some systems): edit the habit.
EDIT_SEQUENCES = ("<Button-2>", "<Button-3>", "<Control-Button-1>")

# The keyboard counterpart of the right click (both cases, so that Caps Lock does not matter).
EDIT_KEYS = ("<e>", "<E>")

# How much white is mixed into the icon of a habit that is not due today, to dim it.
_MUTED_ICON_MIX = 0.45

_ELLIPSIS = "…"

# The ring is a line RING_WIDTH thick centered on this line, half of it in from the row's edge:
# the whole stroke stays within the row.
FOCUS_RING_INSET = RING_WIDTH // 2
FOCUS_RING_TAG = "focus_ring"

# The controls of a row that can have the keyboard focus.
ROW_FOCUS = "row"
TRASH_FOCUS = "trash"

type Box = tuple[float, float, float, float]

# Which control of which habit: (habit id, ROW_FOCUS or TRASH_FOCUS).
type FocusKey = tuple[int, str]


def noop() -> None:
    """The command of a control that is drawn but cannot be used."""


def for_habit(action: Callable[[Habit], object], habit: Habit) -> Callable[[TkEvent], object]:
    """An event handler that applies ``action`` to ``habit``, whatever the event is.

    Each call has its own scope, so building handlers in a loop cannot end up with all of
    them pointing at the last habit.
    """
    return lambda _event: action(habit)


def new_canvas(master: tk.Misc, width: float, height: float, background: str) -> tk.Canvas:
    """A canvas that blends into its container (no border, the container's background)."""
    return tk.Canvas(master, width=width, height=height, bg=background, highlightthickness=0)


def clear_children(widget: tk.Misc) -> None:
    """Destroy everything inside ``widget`` so that it can be filled in again."""
    for child in widget.winfo_children():
        child.destroy()


def muted_icon_color(color: str) -> str:
    """The pale version of an area color, for habits that are not due today."""
    return mix_colors(color, palette.WHITE, _MUTED_ICON_MIX)


def truncate_text(text_font: tkfont.Font, text: str, available: float) -> str:
    """Cut ``text`` and end it with "…" when it is wider than ``available`` pixels."""
    if measure(text_font, text) <= available:
        return text
    while text and measure(text_font, text + _ELLIPSIS) > available:
        text = text[:-1]
    return text + _ELLIPSIS


@contextmanager
def tagged_items(canvas: tk.Canvas, tag: str) -> Iterator[None]:
    """Give ``tag`` to every canvas item drawn inside the block, so one binding covers a row."""
    before = len(canvas.find_all())
    yield
    for item in canvas.find_all()[before:]:
        canvas.addtag_withtag(tag, item)


# ---------- Keyboard ----------


def focused_widget(widget: tk.Misc) -> tk.Misc | None:
    """The widget with the keyboard focus in ``widget``'s window.

    While the application is not the active one, it is the widget that gets the focus back
    when the application is activated again.
    """
    try:
        return widget.focus_lastfor()
    except (KeyError, tk.TclError):  # a window Tkinter did not create, or one that is gone
        return None


def is_inside(widget: tk.Misc, container: tk.Misc) -> bool:
    """Whether ``widget`` is ``container`` or one of the widgets under it."""
    path, prefix = str(widget), str(container)
    return path == prefix or path.startswith(prefix + ".")


class RowFocusRing:
    """Draws the focus ring on ``canvas`` while ``focus_widget`` has the keyboard focus.

    ``focus_widget`` is the row's own canvas, or the anchor standing in for it when the row is
    only a group of items of a larger canvas. The ring is a separate item: taking it away leaves
    the row exactly as it was drawn.
    """

    def __init__(
        self, focus_widget: tk.Canvas, canvas: tk.Canvas, box: Box, radius: float
    ) -> None:
        self._canvas = canvas
        self._box = box
        self._radius = radius
        self._has_focus = track_focus(focus_widget, self._repaint)

    def _repaint(self) -> None:
        if not widget_exists(self._canvas):
            return
        self._canvas.delete(FOCUS_RING_TAG)
        if self._has_focus():
            x1, y1, x2, y2 = self._box
            item = focus_ring(self._canvas, x1, y1, x2, y2, self._radius)
            self._canvas.addtag_withtag(FOCUS_RING_TAG, item)


def make_reachable(
    focus_widget: tk.Canvas,
    canvas: tk.Canvas,
    box: Box,
    radius: float,
    *,
    activate: Callable[[], object],
    edit: Callable[[], object] | None = None,
) -> None:
    """Make a row work with the keyboard.

    ``focus_widget`` joins the Tab order and shows the ring inside ``box`` of ``canvas`` while it
    has the focus. Space and Enter call ``activate`` (what a click on the row does); the ``e`` key
    calls ``edit`` (what a right click does), when the row can be edited.
    """
    RowFocusRing(focus_widget, canvas, box, radius)
    activate_with_keys(focus_widget, activate)
    if edit is not None:
        activate_with_keys(focus_widget, edit, EDIT_KEYS)


def focus_anchor(card: tk.Canvas, x: float, y: float, background: str) -> tk.Canvas:
    """A one-pixel canvas hung from ``card`` that stands in for a row in the Tab order.

    The rows of the dashboard are items of one big canvas, and canvas items cannot take the
    keyboard focus. The anchor is painted like the row behind it, so it is not seen.
    """
    anchor = new_canvas(card, 1, 1, background)
    card.create_window(x, y, anchor="nw", window=anchor)
    return anchor


class FocusMemory:
    """Gives the focus back to the same control of the same habit after a list is redrawn.

    Redrawing destroys every row and builds new ones, and the widget that had the focus goes
    with them. Call :meth:`begin` before destroying them, :meth:`add` for each control that can
    take the focus as the new rows are built, and :meth:`restore` at the end. If the focus was
    anywhere else, or on a control that no longer exists, nothing is moved.
    """

    def __init__(self) -> None:
        self._keys: dict[str, FocusKey] = {}  # widget path -> control
        self._widgets: dict[FocusKey, tk.Misc] = {}
        self._remembered: FocusKey | None = None

    def begin(self, master: tk.Misc) -> None:
        """Note which control has the focus, and forget the controls about to be destroyed."""
        focused = focused_widget(master)
        self._remembered = self._keys.get(str(focused)) if focused is not None else None
        self._keys.clear()
        self._widgets.clear()

    def add(self, key: FocusKey, widget: tk.Misc) -> None:
        """Register a control of the list that was just drawn."""
        self._keys[str(widget)] = key
        self._widgets[key] = widget

    def restore(self) -> None:
        """Put the focus on the new version of the control that had it, if there is one."""
        key, self._remembered = self._remembered, None
        widget = self._widgets.get(key) if key is not None else None
        if widget is not None:
            widget.focus_set()
