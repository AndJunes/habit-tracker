"""The "Mi mes" tab: the current month at a glance, all read-only.

It is the compact version (a single 556 px column) of the dashboard's month section: the
greeting with the day's ring, the bars by area, the balance donut, the daily pace and the
consistency map.

The view computes nothing: the service hands over every figure of the month in one go, and
the charts that are shared with the dashboard do the drawing.
"""

import calendar
import tkinter as tk
import tkinter.font as tkfont
from datetime import date

from ...clock import Clock, SystemClock
from ...domain.stats import MonthStats
from ...service import HabitService
from ..charts import area_bars, balance_donut, consistency_map, donut_legend, month_pace
from ..theme import palette
from ..theme.fonts import font, measure
from . import chart_rows, texts
from .helpers import clear_children, new_canvas
from .stats_banner import MONTH_BANNER, draw_stats_banner

CONTENT_WIDTH = 556  # the window is 620 wide
CARD_GAP = 12  # air between cards, kept small so that everything fits in about 700 px
_LAST_CARD_GAP = 6
_CHART_TOP = 24  # charts start below the card title

_BAR_ROW_HEIGHT = 26  # what area_bars takes per row
_BALANCE_HEIGHT = 146
_DONUT_RADIUS = 45
_DONUT_THICKNESS = 14
_DONUT_X = 60
_DONUT_LEGEND_X = 150
_DONUT_LEGEND_STEP = 20
_PACE_CARD_HEIGHT = _CHART_TOP + 86

_MAP_ROW_STEP = 22  # consistency_map's default row height
_MAP_FIRST_ROW_Y = 26
_MAP_GUIDE_GAP = 8
_MAP_LEGEND_GAP = 16
_MAP_BOTTOM_PADDING = 12

_TITLE_SIZE = 15
_NOTE_SIZE = 9


class MonthView(tk.Frame):
    """The "Mi mes" tab: five stacked cards, always about the current month.

    ``clock`` supplies the hour for the greeting; the day itself comes from the service.
    """

    def __init__(
        self, master: tk.Misc, service: HabitService, *, clock: Clock | None = None
    ) -> None:
        super().__init__(master, bg=palette.PAPER)
        self.service = service
        self._clock = clock or SystemClock()
        self.refresh()

    def refresh(self) -> None:
        """Redraw every card (called whenever the tab is shown)."""
        # The old cards go first, or each refresh would pile new ones on top.
        clear_children(self)
        today = self.service.today()
        month = self.service.month_stats(today.year, today.month)  # computed once
        self._draw_banner(today, month)
        self._draw_area_bars(month)
        self._draw_balance(month)
        self._draw_pace(month, today.day)
        self._draw_consistency(month, today.year, today.month)

    # ---------- Helpers ----------

    def _new_card(self, height: float, *, last: bool = False) -> tk.Canvas:
        """The canvas of a card, already packed with the air that goes below it."""
        canvas = new_canvas(self, CONTENT_WIDTH, height, palette.PAPER)
        canvas.pack(pady=(0, _LAST_CARD_GAP if last else CARD_GAP))
        return canvas

    def _draw_title(
        self,
        canvas: tk.Canvas,
        text: str,
        note: str | None = None,
        *,
        note_font: tkfont.Font | None = None,
        note_color: str = palette.MUTED_LIGHT,
    ) -> None:
        """The serif title of a card, with an optional small note beside it (sans 9 by default)."""
        title_font = font("serif", _TITLE_SIZE, master=canvas)
        canvas.create_text(0, 10, text=text, anchor="w", font=title_font, fill=palette.INK_TITLE)
        if note:
            canvas.create_text(
                measure(title_font, text) + 10,
                11,
                text=note,
                anchor="w",
                font=note_font or font("sans", _NOTE_SIZE, master=canvas),
                fill=note_color,
            )

    # ---------- 1. Banner: greeting and the three figures of the day ----------

    def _draw_banner(self, today: date, month: MonthStats) -> None:
        canvas = self._new_card(MONTH_BANNER.height)
        draw_stats_banner(
            canvas,
            MONTH_BANNER,
            today=today,
            hour=self._clock.now().hour,
            progress=self.service.day_progress(today),
            longest_streak=self.service.longest_streak(),
            month_checks=month.total,
        )

    # ---------- 2. "Tu mes por área": a progress bar per area ----------

    def _draw_area_bars(self, month: MonthStats) -> None:
        rows = chart_rows.area_bar_rows(month)
        canvas = self._new_card(_CHART_TOP + max(len(rows), 1) * _BAR_ROW_HEIGHT)
        self._draw_title(canvas, texts.MONTH_BY_AREA_TITLE)
        # With no rows the chart draws its own consolation message.
        area_bars(canvas, 0, _CHART_TOP, CONTENT_WIDTH, rows)

    # ---------- 3. "Balance del mes": which areas are being fed ----------

    def _draw_balance(self, month: MonthStats) -> None:
        canvas = self._new_card(_BALANCE_HEIGHT)
        self._draw_title(canvas, texts.MONTH_BALANCE_TITLE, texts.MONTH_BALANCE_NOTE)
        center_y = _CHART_TOP + 60
        balance_donut(
            canvas, _DONUT_X, center_y, _DONUT_RADIUS, _DONUT_THICKNESS,
            chart_rows.donut_segments(month), month.total,
        )  # fmt: skip
        # The legend sits to the right, centered on the donut; its y is the top of the block.
        legend = chart_rows.donut_legend_rows(month)
        donut_legend(
            canvas,
            _DONUT_LEGEND_X,
            center_y - len(legend) * _DONUT_LEGEND_STEP / 2,
            CONTENT_WIDTH - _DONUT_LEGEND_X,
            legend,
            step=_DONUT_LEGEND_STEP,
        )

    # ---------- 4. "Ritmo del mes": a bar per elapsed day ----------

    def _draw_pace(self, month: MonthStats, today_day: int) -> None:
        canvas = self._new_card(_PACE_CARD_HEIGHT)
        self._draw_title(canvas, texts.MONTH_PACE_TITLE, texts.MONTH_PACE_NOTE)
        # Today's bar lights up in lilac: this view is always about the current month.
        month_pace(
            canvas, 0, _CHART_TOP, CONTENT_WIDTH, month.counts_by_day,
            chart_rows.pace_maximum(month), today_day,
        )  # fmt: skip

    # ---------- 5. "Constancia del mes": a map of cells per area ----------

    def _draw_consistency(self, month: MonthStats, year: int, month_number: int) -> None:
        rows = chart_rows.consistency_rows(self.service.areas(), month)
        days = calendar.monthrange(year, month_number)[1]

        guide_y = _MAP_FIRST_ROW_Y + len(rows) * _MAP_ROW_STEP + _MAP_GUIDE_GAP
        legend_y = guide_y + _MAP_LEGEND_GAP
        canvas = self._new_card(legend_y + _MAP_BOTTOM_PADDING, last=True)
        self._draw_title(
            canvas,
            texts.MONTH_CONSISTENCY_TITLE,
            texts.MONTH_CONSISTENCY_NOTE,
            note_font=font("script", 12, master=canvas),
            note_color=palette.LILAC,
        )
        if not rows:
            canvas.create_text(
                CONTENT_WIDTH / 2,
                _MAP_FIRST_ROW_Y + 13,
                text=texts.NO_HABITS_TO_SHOW,
                font=font("sans", 10, master=canvas),
                fill=palette.MUTED_LIGHT,
            )
            return
        # The map draws its rows, guide numbers and legend with its default measures.
        consistency_map(canvas, 0, _MAP_FIRST_ROW_Y, CONTENT_WIDTH, rows, days)
