"""The themed vertical scrollbar and the wheel/trackpad binding that drives a canvas."""

import contextlib
import tkinter as tk
from collections.abc import Callable

from ..theme import palette
from ..theme.drawing import mix_colors, rounded_rect
from ..theme.tkutil import TkEvent

# Mouse wheel scrolling, in pixels (the canvas must have ``yscrollincrement=1``).
_WHEEL_NOTCH = 120  # Tk 9 reports wheel deltas in multiples of this
_TK9_PIXELS_PER_NOTCH = 60
_TK8_PIXELS_PER_DELTA = 12  # Tk 8.x reports small deltas (1, 2, 3...)

# <TouchpadScroll> packs dx and dy into the 32 bits of ``delta``; dy is the low half, signed.
_HALF_WORD_MASK = 0xFFFF
_HALF_WORD_SIGN = 0x8000
_HALF_WORD_RANGE = 0x10000

_IDLE_THUMB_MIX = 0.4  # how much white is mixed into the thumb color when the pointer is away


def bind_mousewheel(widget: tk.Misc, canvas: tk.Canvas) -> None:
    """Makes the wheel and the trackpad scroll ``canvas`` while the pointer is over ``widget``.

    The canvas must have ``yscrollincrement=1`` (it scrolls in pixels). It works on
    any Tk version:

    * Tk 9 splits scrolling into two events: the wheel arrives in multiples of ±120
      per notch (``<MouseWheel>``) and the trackpad as ``<TouchpadScroll>``, with dx
      and dy packed together in ``delta``.
    * Tk 8.x has no ``<TouchpadScroll>``: binding it raises an error, and the
      trackpad arrives as ``<MouseWheel>`` with small deltas (1, 2, 3...).
    """

    def on_wheel(event: TkEvent) -> None:
        if abs(event.delta) >= _WHEEL_NOTCH:
            pixels = (-event.delta // _WHEEL_NOTCH) * _TK9_PIXELS_PER_NOTCH
        else:
            pixels = -event.delta * _TK8_PIXELS_PER_DELTA
        canvas.yview_scroll(pixels, "units")

    def on_trackpad(event: TkEvent) -> None:
        dy = event.delta & _HALF_WORD_MASK
        if dy >= _HALF_WORD_SIGN:
            dy -= _HALF_WORD_RANGE
        if dy:
            canvas.yview_scroll(-dy, "units")  # pixel by pixel

    widget.bind("<MouseWheel>", on_wheel)
    # Tk 8.x does not know the event; the trackpad already comes through <MouseWheel> there.
    with contextlib.suppress(tk.TclError):
        widget.bind("<TouchpadScroll>", on_trackpad)


class SoftScrollbar(tk.Canvas):
    """A vertical scrollbar in the theme: a rounded lilac thumb, shown only when it is needed.

    It replaces the native one, which on macOS changes with dark mode and clashes
    with the pastel palette.

    It is used like ``ttk.Scrollbar``: the canvas feeds it with
    ``yscrollcommand=bar.set`` and the bar sends its orders to ``command`` (normally
    ``canvas.yview``): dragging the thumb asks for ``("moveto", fraction)`` and a
    click on the track asks for ``("scroll", ±1, "pages")``.
    """

    WIDTH = 14
    THUMB_THICKNESS = 8  # width of the thumb inside WIDTH
    MIN_THUMB_LENGTH = 32  # so there is always something to grab

    def __init__(
        self,
        master: tk.Misc,
        command: Callable[..., object],
        parent_background: str = palette.PAPER,
    ) -> None:
        super().__init__(master, width=self.WIDTH, bg=parent_background, highlightthickness=0)
        self.command = command
        self.first, self.last = 0.0, 1.0
        self._drag_anchor: tuple[int, float] | None = (
            None  # (click y, start fraction) while dragging
        )
        self.hovered = False
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda _event: self._set_hovered(True))
        self.bind("<Leave>", lambda _event: self._set_hovered(False))

    @property
    def dragging(self) -> bool:
        """Whether the thumb is being dragged."""
        return self._drag_anchor is not None

    def set(self, first: float | str, last: float | str) -> None:
        """Called by the canvas whenever the view changes: the visible fraction of the content."""
        self.first, self.last = float(first), float(last)
        self._draw()

    def thumb_bounds(self) -> tuple[float, float] | None:
        """``(top, bottom)`` of the thumb in pixels, or ``None`` when all content is visible."""
        visible = self.last - self.first
        if visible >= 1.0:
            return None
        height = self._height_in_pixels()
        length = max(self.MIN_THUMB_LENGTH, visible * height)
        travel = height - length
        top = self.first / (1.0 - visible) * travel
        return top, top + length

    def _height_in_pixels(self) -> int:
        shown = self.winfo_height()
        # Before it is shown, Tk reports the requested size as text ("7c" = 7 centimeters).
        return shown if shown > 1 else int(self.winfo_pixels(self.cget("height")))

    def _draw(self) -> None:
        self.delete("all")
        bounds = self.thumb_bounds()
        if bounds is None:
            return
        top, bottom = bounds
        margin = (self.WIDTH - self.THUMB_THICKNESS) / 2
        active = self.hovered or self.dragging
        color = (
            palette.LILAC if active else mix_colors(palette.LILAC, palette.WHITE, _IDLE_THUMB_MIX)
        )
        rounded_rect(
            self, margin, top + 1, margin + self.THUMB_THICKNESS, bottom - 1,
            self.THUMB_THICKNESS / 2, fill=color, outline="",
        )  # fmt: skip

    def _set_hovered(self, hovered: bool) -> None:
        self.hovered = hovered
        self._draw()

    def _on_press(self, event: TkEvent) -> None:
        bounds = self.thumb_bounds()
        if bounds is None:
            return
        top, bottom = bounds
        if top <= event.y <= bottom:
            self._drag_anchor = (event.y, self.first)  # grabbed the thumb
            self._draw()
        else:
            self.command("scroll", 1 if event.y > bottom else -1, "pages")

    def _on_drag(self, event: TkEvent) -> None:
        bounds = self.thumb_bounds()
        if self._drag_anchor is None or bounds is None:
            return
        anchor_y, first_at_anchor = self._drag_anchor
        top, bottom = bounds
        travel = self._height_in_pixels() - (bottom - top)
        if travel <= 0:
            return
        visible = self.last - self.first
        target = first_at_anchor + (event.y - anchor_y) / travel * (1.0 - visible)
        self.command("moveto", min(max(target, 0.0), 1.0 - visible))

    def _on_release(self, _event: TkEvent) -> None:
        self._drag_anchor = None
        self._draw()
