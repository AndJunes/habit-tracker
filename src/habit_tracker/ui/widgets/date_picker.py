"""A monthly calendar in which days can be picked: the habit form's date selector.

It is the small sibling of the calendar view: the same grid of rounded cells and the same
palette, but here each cell can be clicked. There are two modes:

* ``"multiple"``: each click picks or drops a day (specific dates, "times per month" with
  dates). The picked dates are listed below as chips with a ✕ to drop them one by one.
* ``"single"``: one date (the start and the end of a habit); clicking the picked one drops it.

The limits are the habit's period of validity: days outside it are dimmed and do not react. If
the limits move and a date that was already picked ends up outside, it is NOT dropped silently:
it is painted pink (cell and chip) so the conflict is visible and the date can be removed.

The widget only holds dates. It knows nothing about habits or files, and it is told what day
"today" is instead of reading the clock.
"""

import calendar
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable
from datetime import date
from functools import partial
from typing import Literal

from ..calendar_es import MONTHS, WEEKDAYS_SHORT, short_date_text
from ..theme import palette
from ..theme.cursors import DEFAULT_CURSOR, pointer_cursor
from ..theme.drawing import rounded_rect
from ..theme.fonts import font
from ..theme.tkutil import TkEvent
from .soft_button import SoftButton

type PickerMode = Literal["multiple", "single"]

CELL_GAP = 4  # air between cells
CELL_HEIGHT = 32
HEADER_HEIGHT = 20  # the strip of "lun mar mié…"
MAX_WEEK_ROWS = 6  # a month never spans more than six weeks, so that height is always reserved
CHIPS_PER_ROW = 5
DEFAULT_WIDTH = 408

_DAYS_IN_WEEK = 7
_CELL_RADIUS = 9
_CELL_INSET = 1
_TODAY_OUTLINE_WIDTH = 2
_HEADER_TEXT_LIFT = 2  # the weekday names sit a little above the middle of their strip

_NAV_BUTTON_SIZE = 30
_NAV_BUTTON_RADIUS = 10
_NAV_GAP = 6
_CHIP_GAP = 6
_CHIP_HEIGHT = 26
_CHIP_RADIUS = 9
_CHIP_PAD_X = 10
_CHIPS_TOP_GAP = 6

_PREVIOUS = "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}"
_NEXT = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
_DROP_MARK = "✕"
_DROP_ALL = "Quitar todas"


class DatePicker(tk.Frame):
    """A month grid for picking dates, optionally limited to ``[minimum, maximum]``.

    ``on_change`` is called each time the selection changes. ``today`` only decides which
    cell gets the outline and which month opens when nothing is picked.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        today: date,
        mode: PickerMode = "multiple",
        selection: Iterable[date] = (),
        minimum: date | None = None,
        maximum: date | None = None,
        on_change: Callable[[], object] | None = None,
        width: int = DEFAULT_WIDTH,
    ) -> None:
        super().__init__(master, bg=palette.PAPER)
        self.mode: PickerMode = mode
        self.minimum = minimum
        self.maximum = maximum
        self.on_change = on_change
        self.hovered_day: int | None = None  # day of the visible month under the pointer
        self._today = today
        self._width = width
        self._selection = set(selection)

        # The month that opens: the first picked date, or today moved into the period if it
        # falls outside of it.
        shown = min(self._selection) if self._selection else self._clamp(today)
        self.year, self.month = shown.year, shown.month

        # Navigation: previous month, the month's name, next month
        navigation = tk.Frame(self, bg=palette.PAPER)
        navigation.pack(fill="x", pady=(0, _NAV_GAP))
        self._nav_button(navigation, _PREVIOUS, self.previous_month).pack(side="left")
        self._month_label = tk.Label(
            navigation, bg=palette.PAPER, font=font("serif", 15, master=self), fg=palette.INK_TITLE
        )
        self._month_label.pack(side="left", expand=True)
        self._nav_button(navigation, _NEXT, self.next_month).pack(side="right")

        # The grid: a canvas that is redrawn whole.
        height = HEADER_HEIGHT + MAX_WEEK_ROWS * (CELL_HEIGHT + CELL_GAP)
        self.canvas = tk.Canvas(
            self, width=width, height=height, bg=palette.PAPER, highlightthickness=0
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _event: self._set_hovered(None))

        # The picked dates, as chips that are dropped with a click.
        self.chips_frame = tk.Frame(self, bg=palette.PAPER)
        if mode == "multiple":
            self.chips_frame.pack(fill="x", pady=(_CHIPS_TOP_GAP, 0))

        self.refresh()

    # ---------- What the form asks ----------

    def dates(self) -> list[date]:
        """The picked dates, oldest first."""
        return sorted(self._selection)

    def in_range(self, day: date) -> bool:
        """Whether ``day`` falls inside the period of validity."""
        return (self.minimum is None or day >= self.minimum) and (
            self.maximum is None or day <= self.maximum
        )

    def out_of_range_dates(self) -> list[date]:
        """The picked dates that fell outside the period, to warn about them."""
        return [day for day in self.dates() if not self.in_range(day)]

    @property
    def cell_width(self) -> float:
        return (self._width - (_DAYS_IN_WEEK - 1) * CELL_GAP) / _DAYS_IN_WEEK

    def day_at(self, x: float, y: float) -> int | None:
        """The day of the visible month under that canvas position, or ``None``.

        ``None`` for the header strip, the air between cells and the blank cells that belong
        to the neighboring months.
        """
        cell_width = self.cell_width
        if y < HEADER_HEIGHT or x < 0:
            return None
        column = int(x // (cell_width + CELL_GAP))
        row = int((y - HEADER_HEIGHT) // (CELL_HEIGHT + CELL_GAP))
        if column >= _DAYS_IN_WEEK:
            return None
        inside_x = x - column * (cell_width + CELL_GAP) <= cell_width
        inside_y = (y - HEADER_HEIGHT) - row * (CELL_HEIGHT + CELL_GAP) <= CELL_HEIGHT
        if not (inside_x and inside_y):
            return None  # in the air between cells
        weeks = calendar.monthcalendar(self.year, self.month)
        if row >= len(weeks):
            return None
        return weeks[row][column] or None

    # ---------- What the form orders ----------

    def set_limits(self, minimum: date | None, maximum: date | None) -> None:
        self.minimum, self.maximum = minimum, maximum
        self.refresh()

    def set_selection(self, days: Iterable[date]) -> None:
        self._selection = set(days)
        self.refresh()

    def remove(self, day: date) -> None:
        if day in self._selection:
            self._selection.discard(day)
            self._changed()

    def clear(self) -> None:
        if self._selection:
            self._selection.clear()
            self._changed()

    def toggle(self, day: date) -> None:
        """Picks or drops a day. Outside the period nothing happens."""
        if not self.in_range(day):
            return
        if day in self._selection:
            self._selection.discard(day)
        elif self.mode == "single":
            self._selection = {day}
        else:
            self._selection.add(day)  # a set: picking twice does not duplicate
        self._changed()

    @staticmethod
    def _nav_button(parent: tk.Frame, text: str, command: Callable[[], object]) -> SoftButton:
        return SoftButton(
            parent, text, command, palette.BUTTON_LILAC_BACKGROUND, palette.MUTED,
            height=_NAV_BUTTON_SIZE, radius=_NAV_BUTTON_RADIUS, width=_NAV_BUTTON_SIZE,
        )  # fmt: skip

    # ---------- Moving between months ----------

    def previous_month(self) -> None:
        self.month -= 1
        if self.month == 0:
            self.month, self.year = 12, self.year - 1
        self.refresh()

    def next_month(self) -> None:
        self.month += 1
        if self.month == 13:
            self.month, self.year = 1, self.year + 1
        self.refresh()

    # ---------- Drawing ----------

    def refresh(self) -> None:
        self._draw_grid()
        self._draw_chips()

    def _clamp(self, day: date) -> date:
        if self.minimum is not None and day < self.minimum:
            return self.minimum
        if self.maximum is not None and day > self.maximum:
            return self.maximum
        return day

    def _changed(self) -> None:
        self.refresh()
        if self.on_change is not None:
            self.on_change()

    def _draw_grid(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._month_label.configure(text=f"{MONTHS[self.month - 1]} {self.year}")
        cell_width = self.cell_width

        header_font = font("sans", 9, "bold", master=self)
        for column, name in enumerate(WEEKDAYS_SHORT):
            cx = column * (cell_width + CELL_GAP) + cell_width / 2
            canvas.create_text(
                cx,
                HEADER_HEIGHT / 2 - _HEADER_TEXT_LIFT,
                text=name,
                font=header_font,
                fill=palette.WEEKDAY_HEADER,
            )

        # ``monthcalendar`` copes with months of 28 to 31 days and with leap years.
        for row, week in enumerate(calendar.monthcalendar(self.year, self.month)):
            for column, number in enumerate(week):
                if number == 0:
                    continue  # blank cell of another month
                self._draw_cell(
                    date(self.year, self.month, number),
                    column * (cell_width + CELL_GAP),
                    HEADER_HEIGHT + row * (CELL_HEIGHT + CELL_GAP),
                )

    def _draw_cell(self, day: date, x: float, y: float) -> None:
        picked = day in self._selection
        free = self.in_range(day)
        cell_width = self.cell_width
        fill: str | None
        if picked:
            # Picked inside the period: lilac. Outside of it: the pink of a warning.
            fill = palette.LILAC if free else palette.TRASH_ACTIVE
            ink = palette.WHITE
        elif not free:
            fill, ink = None, palette.NUMBER_FUTURE  # dimmed: no cell at all
        elif day.day == self.hovered_day:
            fill, ink = palette.LILAC_SOFT, palette.INK_TITLE
        else:
            fill, ink = palette.ROW_BACKGROUND, palette.INK

        if fill is not None:
            outlined = day == self._today and not picked
            rounded_rect(
                self.canvas,
                x + _CELL_INSET,
                y + _CELL_INSET,
                x + cell_width - _CELL_INSET,
                y + CELL_HEIGHT - _CELL_INSET,
                _CELL_RADIUS,
                fill=fill,
                outline=palette.LILAC if outlined else "",
                width=_TODAY_OUTLINE_WIDTH,
            )
        self.canvas.create_text(
            x + cell_width / 2,
            y + CELL_HEIGHT / 2,
            text=str(day.day),
            font=font("sans", 10, "bold" if picked else "normal", master=self),
            fill=ink,
        )

    def _draw_chips(self) -> None:
        for widget in self.chips_frame.winfo_children():
            widget.destroy()
        if self.mode != "multiple" or not self._selection:
            return
        chip_font = font("sans", 9, "bold", master=self)
        days = self.dates()
        for index, day in enumerate(days):
            outside = not self.in_range(day)
            self._add_chip(
                index,
                f"{short_date_text(day)}  {_DROP_MARK}",
                partial(self.remove, day),
                palette.TRASH_ACTIVE_BACKGROUND if outside else palette.LILAC_SOFT,
                palette.TRASH_ACTIVE if outside else palette.INK_TITLE,
                chip_font,
            )
        if len(days) > 1:  # with several, a shortcut to start over
            self._add_chip(
                len(days), _DROP_ALL, self.clear,
                palette.BUTTON_PINK_BACKGROUND, palette.BUTTON_PINK_TEXT, chip_font,
            )  # fmt: skip

    def _add_chip(
        self,
        index: int,
        text: str,
        command: Callable[[], object],
        background: str,
        text_color: str,
        chip_font: tkfont.Font,
    ) -> None:
        SoftButton(
            self.chips_frame, text, command, background, text_color,
            button_font=chip_font, height=_CHIP_HEIGHT, radius=_CHIP_RADIUS, pad_x=_CHIP_PAD_X,
        ).grid(
            row=index // CHIPS_PER_ROW, column=index % CHIPS_PER_ROW,
            padx=(0, _CHIP_GAP), pady=(0, _CHIP_GAP), sticky="w",
        )  # fmt: skip

    # ---------- Pointer ----------

    def _on_click(self, event: TkEvent) -> None:
        number = self.day_at(event.x, event.y)
        if number:
            self.toggle(date(self.year, self.month, number))

    def _on_motion(self, event: TkEvent) -> None:
        number = self.day_at(event.x, event.y)
        clickable = number is not None and self.in_range(date(self.year, self.month, number))
        self.canvas.configure(cursor=pointer_cursor(self.canvas) if clickable else DEFAULT_CURSOR)
        self._set_hovered(number if clickable else None)

    def _set_hovered(self, number: int | None) -> None:
        if number != self.hovered_day:
            self.hovered_day = number
            self._draw_grid()
