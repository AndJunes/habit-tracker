"""The "Calendario" tab: the month grid, where every day shows a colored dot per area done.

A good month looks like a rainbow; a day without marks is simply left blank, with no numbers
and no guilt. Below the grid go the legend of the areas and, when the month has any, the card
with its important dates.
"""

import calendar
import tkinter as tk
from datetime import date

from ...service import HabitService
from ..calendar_es import MONTHS, WEEKDAYS_SHORT
from ..charts import draw_legend_rows, legend_rows
from ..theme import palette
from ..theme.drawing import flag, rounded_rect
from ..theme.fonts import font, measure
from ..widgets.soft_button import SoftButton
from . import texts
from .day_cells import DayCellStyle, completed_area_colors, draw_day_cell
from .helpers import new_canvas, truncate_text

# Seven columns of 74 px with 5 px between them fill 548 px exactly.
CELL_WIDTH = 74
CELL_HEIGHT = 52
CELL_GAP = 5
CONTENT_WIDTH = 7 * CELL_WIDTH + 6 * CELL_GAP
WEEKDAY_STRIP_HEIGHT = 20  # the "lun mar mié..." line above the cells

_CELL_STYLE = DayCellStyle(radius=9, dots_y=36)
_NAV_BUTTON_SIZE = 34

_LEGEND_FIRST_ROW_Y = 11
_LEGEND_ROW_HEIGHT = 22

# The card of important dates: padding, a heading line, then a line per date.
_DATES_PADDING = 14
_DATES_HEADING_HEIGHT = 20
_DATES_ROW_HEIGHT = 24
_DATES_TEXT_X = 18
_DATES_TITLE_X = 34  # where the day number starts, next to the flag


class CalendarView(tk.Frame):
    """The "Calendario" tab. It starts on the current month and can move to others."""

    def __init__(self, master: tk.Misc, service: HabitService) -> None:
        super().__init__(master, bg=palette.PAPER)
        self.service = service
        today = service.today()
        self.year = today.year
        self.month = today.month

        # An inner frame keeps the content centered: the window is 620 wide and the content 548.
        content = tk.Frame(self, bg=palette.PAPER)
        content.pack(padx=22, pady=(18, 22))

        navigation = tk.Frame(content, bg=palette.PAPER)
        navigation.pack(fill="x", pady=(0, 12))
        SoftButton(
            navigation,
            texts.PREVIOUS_MONTH,
            self.previous_month,
            palette.BUTTON_LILAC_BACKGROUND,
            palette.MUTED,
            height=_NAV_BUTTON_SIZE,
            radius=10,
            width=_NAV_BUTTON_SIZE,
        ).pack(side="left")
        self.month_label = tk.Label(
            navigation, bg=palette.PAPER, font=font("serif", 19, master=self), fg=palette.INK_TITLE
        )
        self.month_label.pack(side="left", expand=True)
        SoftButton(
            navigation,
            texts.NEXT_MONTH,
            self.next_month,
            palette.BUTTON_LILAC_BACKGROUND,
            palette.MUTED,
            height=_NAV_BUTTON_SIZE,
            radius=10,
            width=_NAV_BUTTON_SIZE,
        ).pack(side="right")

        # The grid is one canvas that is drawn again from scratch.
        self.grid_canvas = new_canvas(content, CONTENT_WIDTH, 10, palette.PAPER)
        self.grid_canvas.pack()
        self.legend_canvas = new_canvas(content, CONTENT_WIDTH, _LEGEND_ROW_HEIGHT, palette.PAPER)
        self.legend_canvas.pack(pady=(12, 0))
        # The card of important dates only shows when the month has any.
        self.dates_canvas = new_canvas(content, CONTENT_WIDTH, 10, palette.PAPER)

        self.refresh()

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

    def refresh(self) -> None:
        """Redraw everything: the month title, the grid, the legend and the dates card."""
        self.month_label.config(text=f"{MONTHS[self.month - 1]} {self.year}")
        important_dates = self.service.important_dates(self.year, self.month)
        self._draw_grid({day for day, _ in important_dates})
        self._draw_legend()
        self._draw_important_dates(important_dates)

    def _draw_grid(self, flagged_days: set[int]) -> None:
        canvas = self.grid_canvas
        canvas.delete("all")  # a clean slate: nothing piles up
        today = self.service.today()
        colors = completed_area_colors(self.service, self.year, self.month)

        # monthcalendar gives the weeks Monday to Sunday, with 0 for days of other months.
        weeks = calendar.monthcalendar(self.year, self.month)
        canvas.config(
            height=WEEKDAY_STRIP_HEIGHT + len(weeks) * CELL_HEIGHT + (len(weeks) - 1) * CELL_GAP
        )

        header_font = font("sans", 9, "bold", master=canvas)
        for column, name in enumerate(WEEKDAYS_SHORT):
            center_x = column * (CELL_WIDTH + CELL_GAP) + CELL_WIDTH / 2
            canvas.create_text(
                center_x,
                WEEKDAY_STRIP_HEIGHT / 2 - 2,
                text=name,
                font=header_font,
                fill=palette.WEEKDAY_HEADER,
            )

        for row, week in enumerate(weeks):
            for column, number in enumerate(week):
                if number == 0:
                    continue  # a gap that belongs to another month
                draw_day_cell(
                    canvas,
                    column * (CELL_WIDTH + CELL_GAP),
                    WEEKDAY_STRIP_HEIGHT + row * (CELL_HEIGHT + CELL_GAP),
                    CELL_WIDTH,
                    CELL_HEIGHT,
                    date(self.year, self.month, number),
                    today,
                    _CELL_STYLE,
                    flagged=number in flagged_days,
                    area_colors=colors.get(number, []),
                )

    def _draw_legend(self) -> None:
        canvas = self.legend_canvas
        canvas.delete("all")
        legend_font = font("sans", 10, "bold", master=canvas)
        # Eight areas do not fit on one line: they are split into as many centered rows as
        # needed and the canvas grows just enough.
        rows = legend_rows(self.service.areas(), legend_font, CONTENT_WIDTH)
        height = draw_legend_rows(
            canvas, rows, CONTENT_WIDTH, _LEGEND_FIRST_ROW_Y, _LEGEND_ROW_HEIGHT, legend_font
        )
        canvas.config(height=max(height, _LEGEND_ROW_HEIGHT))

    def _draw_important_dates(self, important_dates: list[tuple[int, str]]) -> None:
        canvas = self.dates_canvas
        canvas.delete("all")
        if not important_dates:
            canvas.pack_forget()  # a month without dates shows no card
            return
        canvas.pack(pady=(14, 0))

        height = (
            _DATES_PADDING
            + _DATES_HEADING_HEIGHT
            + _DATES_ROW_HEIGHT * len(important_dates)
            + _DATES_PADDING
        )
        canvas.config(height=height)
        rounded_rect(
            canvas, 1, 1, CONTENT_WIDTH - 1, height - 1, 14,
            fill=palette.ROW_BACKGROUND, outline=palette.BORDER,
        )  # fmt: skip
        canvas.create_text(
            _DATES_TEXT_X,
            16,
            text=texts.CALENDAR_DATES_TITLE,
            anchor="nw",
            font=font("sans", 9, "bold", master=canvas),
            fill=palette.MUTED,
        )

        number_font = font("sans", 11, "bold", master=canvas)
        title_font = font("sans", 11, master=canvas)
        for index, (day, title) in enumerate(important_dates):
            center_y = _DATES_PADDING + _DATES_HEADING_HEIGHT + index * _DATES_ROW_HEIGHT + 12
            flag(canvas, _DATES_TEXT_X, center_y - 6, scale=0.8)
            day_text = f"{day:02d}"
            canvas.create_text(
                _DATES_TITLE_X,
                center_y,
                text=day_text,
                anchor="w",
                font=number_font,
                fill=palette.INK_TITLE,
            )
            title_x = _DATES_TITLE_X + measure(number_font, day_text)
            canvas.create_text(
                title_x,
                center_y,
                text=truncate_text(
                    title_font, f" — {title}", CONTENT_WIDTH - _DATES_TEXT_X - title_x
                ),
                anchor="w",
                font=title_font,
                fill=palette.MUTED_DARK,
            )
