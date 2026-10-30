"""Month charts shared by the "Mi mes" tab (compact, one column) and full screen (dashboard).

Each function receives an already created Canvas and draws from ``(x, y)`` at the
width it is given, so the same drawing serves narrow in the window and wide in the
dashboard without duplicating code. Most of them return the height they used, so the
view knows how tall to make its cards.

Nothing about habits is computed here: views ask the service for the numbers and
pass rows that are ready to paint. Colors and drawing helpers come from the theme.

The pieces:

* :func:`area_bars`: "Tu mes por área", a progress bar for each area.
* :func:`balance_donut`: "Balance del mes", the donut with the total in the middle.
* :func:`donut_legend`: the dot legend that goes with the donut.
* :func:`legend_rows` and :func:`draw_legend_rows`: the category legend of the calendars.
* :func:`month_pace`: "Ritmo del mes", one bar for each elapsed day.
* :func:`consistency_map`: "Constancia del mes", the grid of cells for each area.
"""

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from ..domain.enums import DayStatus
from ..domain.models import Area
from .theme import palette
from .theme.drawing import DonutSegment, area_icon, donut, rounded_rect
from .theme.fonts import font, measure

# Texts the person sees (the interface speaks Spanish).
_NO_HABITS_TEXT = "todavía no hay hábitos que mostrar"
_NO_DAYS_TEXT = "todavía no hay días registrados este mes"
_DONUT_UNIT_TEXT = "checks"
_LEGEND_DONE_TEXT = "cumplido"
_LEGEND_MISSED_TEXT = "sin culpa"
_LEGEND_UPCOMING_TEXT = "por venir"

# Font sizes (all "sans" unless noted)
_LABEL_SIZE = 10  # names, counts and messages
_CAPTION_SIZE = 9  # map names and legends
_SMALL_SIZE = 8  # donut unit, map guide numbers
_TICK_SIZE = 7  # day numbers under the pace bars

# Area bars
_BAR_ROW_HEIGHT = 26
_BAR_LABEL_Y = 6  # center of the name and percentage line inside a row
_BAR_TOP = 13
_BAR_BOTTOM = 22
_BAR_RADIUS = 4
_BARS_EMPTY_TEXT_Y = 13

# Donut
_DONUT_NUMBER_DY = -7
_DONUT_UNIT_DY = 11

# Category legend (dot, space, name)
_LEGEND_DOT = 9
_LEGEND_DOT_GAP = 6
_LEGEND_GAP = 16  # between two items of a row

# Donut legend
_DONUT_LEGEND_STEP = 20
_DONUT_LEGEND_TEXT_X = 18

# Month pace
_PACE_HEIGHT = 78
_PACE_EMPTY_TEXT_Y = 43
_PACE_BAR_GAP = 4
_PACE_BASE_Y = 64  # the common floor of all bars
_PACE_MIN_BAR = 8
_PACE_BAR_RANGE = 54  # how much taller than the minimum the fullest bar gets
_PACE_BAR_RADIUS = 3
_PACE_LABEL_DY = 9
_PACE_MAX_LABELED_BARS = 16  # with more bars, only odd days get a number

# Consistency map
_CELL_RADIUS = 3
_CELL_DASH = (2, 2)
_GUIDE_DAYS = (1, 10, 20, 30)
_GUIDE_DY = 8  # from the last row to the guide numbers
_MAP_PADDING = 16  # below the last row when there is no legend
_LEGEND_DY = 16  # from the guide numbers to the legend
_SWATCH_SIZE = 12
_SWATCH_TEXT_X = 18
_SWATCH_GAP = 16


class AreaBar(NamedTuple):
    """One row of :func:`area_bars`."""

    name: str
    percent: int  # 0-100
    color: str
    soft_color: str


class LegendEntry(NamedTuple):
    """One row of :func:`donut_legend`."""

    name: str
    color: str
    amount: int  # how many times the area was done


class ConsistencyRow(NamedTuple):
    """One row of :func:`consistency_map`: the status of each day of the month for an area."""

    area_id: str
    name: str
    color: str
    soft_color: str
    statuses: Mapping[int, DayStatus]


def area_bars(canvas: tk.Canvas, x: float, y: float, width: float, rows: Sequence[AreaBar]) -> int:
    """The progress bars of "Tu mes por área".

    Each area takes a line of text (name on the left, "NN%" on the right in the area's
    color) and its bar below: the full track in the pastel tone and, on top, the
    proportional fill in the strong color.

    Returns the height used (26 px per row; also 26 when there is nothing, because the
    empty-state message takes that same strip).
    """
    if not rows:
        canvas.create_text(
            x + width / 2,
            y + _BARS_EMPTY_TEXT_Y,
            text=_NO_HABITS_TEXT,
            font=font("sans", _LABEL_SIZE, master=canvas),
            fill=palette.MUTED_LIGHT,
        )
        return _BAR_ROW_HEIGHT

    bold = font("sans", _LABEL_SIZE, "bold", master=canvas)
    for index, (name, percent, color, soft_color) in enumerate(rows):
        row_y = y + index * _BAR_ROW_HEIGHT
        canvas.create_text(
            x, row_y + _BAR_LABEL_Y, text=name, anchor="w", font=bold, fill=palette.INK
        )
        canvas.create_text(
            x + width, row_y + _BAR_LABEL_Y, text=f"{percent}%", anchor="e", font=bold, fill=color
        )
        # The full track in the area's pastel tone...
        rounded_rect(
            canvas, x, row_y + _BAR_TOP, x + width, row_y + _BAR_BOTTOM, _BAR_RADIUS,
            fill=soft_color, outline="",
        )  # fmt: skip
        # ...and the proportional fill on top in the strong color.
        if percent > 0:
            rounded_rect(
                canvas, x, row_y + _BAR_TOP, x + width * percent / 100, row_y + _BAR_BOTTOM,
                _BAR_RADIUS, fill=color, outline="",
            )  # fmt: skip
    return len(rows) * _BAR_ROW_HEIGHT


def balance_donut(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    radius: float,
    thickness: float,
    segments: Sequence[DonutSegment],
    total: int,
    number_size: int = 17,
) -> None:
    """The donut of "Balance del mes" with the big total in the middle.

    ``segments`` are ``(color, fraction)`` pairs adding up to at most 1, already
    computed by the view. It may be empty: only the pale ring is drawn then, which is
    the intended look when the month has just started. The total goes in the middle in
    serif with the word "checks" below; ``number_size`` enlarges the total for big
    donuts (the compact one in "Mi mes" uses 17, the dashboard's looks better with 21).
    """
    donut(canvas, cx, cy, radius, thickness, segments)
    canvas.create_text(
        cx,
        cy + _DONUT_NUMBER_DY,
        text=str(total),
        font=font("serif", number_size, master=canvas),
        fill=palette.INK_TITLE,
    )
    canvas.create_text(
        cx,
        cy + _DONUT_UNIT_DY,
        text=_DONUT_UNIT_TEXT,
        font=font("sans", _SMALL_SIZE, master=canvas),
        fill=palette.MUTED,
    )


def legend_rows(
    areas: Sequence[Area], legend_font: tkfont.Font, max_width: float, gap: float = _LEGEND_GAP
) -> list[list[tuple[Area, int]]]:
    """Splits the areas into rows that fit in ``max_width``.

    Keeps the calendars' legend from being cut off when there are many areas (with
    eight it no longer fits on one line). Returns a list of rows, each a list of
    ``(area, item width)``; an item is dot + space + name.
    """
    rows: list[list[tuple[Area, int]]] = []
    current: list[tuple[Area, int]] = []
    used = 0.0
    for area in areas:
        width = _LEGEND_DOT + _LEGEND_DOT_GAP + measure(legend_font, area.name)
        if current and used + gap + width > max_width:
            rows.append(current)
            current, used = [], 0
        used += width + (gap if current else 0)
        current.append((area, width))
    if current:
        rows.append(current)
    return rows


def draw_legend_rows(
    canvas: tk.Canvas,
    rows: Sequence[Sequence[tuple[Area, int]]],
    total_width: float,
    first_y: float,
    row_height: float,
    legend_font: tkfont.Font,
    gap: float = _LEGEND_GAP,
) -> float:
    """Draws the rows of :func:`legend_rows`, each centered in ``total_width``.

    ``first_y`` is the vertical center of the first row. Returns the height used.
    """
    for index, row in enumerate(rows):
        cy = first_y + index * row_height
        row_width = sum(width for _, width in row) + gap * (len(row) - 1)
        x = (total_width - row_width) / 2
        for area, width in row:
            radius = _LEGEND_DOT / 2
            canvas.create_oval(
                x, cy - radius, x + _LEGEND_DOT, cy + radius, fill=area.color, outline=""
            )
            canvas.create_text(
                x + _LEGEND_DOT + _LEGEND_DOT_GAP,
                cy,
                anchor="w",
                text=area.name,
                font=legend_font,
                fill=palette.MUTED_DARK,
            )
            x += width + gap
    return len(rows) * row_height


def donut_legend(
    canvas: tk.Canvas,
    x: float,
    y: float,
    width: float,
    rows: Sequence[LegendEntry],
    step: float = _DONUT_LEGEND_STEP,
) -> float:
    """The legend that goes with the donut: color dot, name and count.

    ``y`` is the top edge of the block; each row is centered in its strip of ``step``
    pixels, with the 9 px dot on the left and the count anchored on the right (at
    ``x + width``), so the column of numbers always lines up.

    Returns the height used: ``len(rows) * step``.
    """
    bold = font("sans", _LABEL_SIZE, "bold", master=canvas)
    radius = _LEGEND_DOT / 2
    for index, (name, color, amount) in enumerate(rows):
        row_y = y + index * step + step / 2
        canvas.create_oval(
            x, row_y - radius, x + _LEGEND_DOT, row_y + radius, fill=color, outline=""
        )
        canvas.create_text(
            x + _DONUT_LEGEND_TEXT_X,
            row_y,
            text=name,
            anchor="w",
            font=bold,
            fill=palette.MUTED_DARK,
        )
        canvas.create_text(
            x + width, row_y, text=str(amount), anchor="e", font=bold, fill=palette.MUTED_LIGHT
        )
    return len(rows) * step


def month_pace(
    canvas: tk.Canvas,
    x: float,
    y: float,
    width: float,
    counts: Sequence[tuple[int, int]],
    maximum: int,
    today_day: int,
) -> int:
    """The daily bars of "Ritmo del mes".

    ``counts`` are ``(day, n)`` pairs with how many areas were done each day. The bars
    share the full width with 4 px of air between them and grow from a common floor:
    8 px of base plus up to 54 px according to ``n / maximum`` (``maximum`` is always
    at least 1, so there is never a division by zero). All use ``PACE_BAR`` except
    today's, which lights up in ``LILAC``. The day number goes below each bar; with
    more than 16 bars, only the odd days (so the numbers do not overlap).

    Returns the height used (78 px, with the message or with bars).
    """
    if not counts:
        canvas.create_text(
            x + width / 2,
            y + _PACE_EMPTY_TEXT_Y,
            text=_NO_DAYS_TEXT,
            font=font("sans", _LABEL_SIZE, master=canvas),
            fill=palette.MUTED_LIGHT,
        )
        return _PACE_HEIGHT

    quantity = len(counts)
    bar_width = (width - _PACE_BAR_GAP * (quantity - 1)) / quantity
    base = y + _PACE_BASE_Y
    for index, (day, count) in enumerate(counts):
        bar_x = x + index * (bar_width + _PACE_BAR_GAP)
        bar_height = _PACE_MIN_BAR + (count / maximum) * _PACE_BAR_RANGE
        color = palette.LILAC if day == today_day else palette.PACE_BAR
        rounded_rect(
            canvas, bar_x, base - bar_height, bar_x + bar_width, base, _PACE_BAR_RADIUS,
            fill=color, outline="",
        )  # fmt: skip
        if quantity <= _PACE_MAX_LABELED_BARS or day % 2 == 1:
            canvas.create_text(
                bar_x + bar_width / 2,
                base + _PACE_LABEL_DY,
                text=str(day),
                font=font("sans", _TICK_SIZE, master=canvas),
                fill=palette.MUTED_LIGHT,
            )
    return _PACE_HEIGHT


def consistency_map(
    canvas: tk.Canvas,
    x: float,
    y: float,
    width: float,
    rows: Sequence[ConsistencyRow],
    days: int,
    label_width: float = 118,
    row_step: float = 22,
    gap: float = 2,
    with_legend: bool = True,
    icon_radius: float | None = None,
) -> float:
    """The heatmap of "Constancia del mes": a row per area, a small cell per day.

    ``days`` is how many days the month has (28 to 31).

    Each row starts with the area's badge (:func:`area_icon`) and its name, inside the
    ``label_width`` zone; the rest of the width is split into square cells with ``gap``
    pixels of air. The colors tell the story without guilt: done is the area's color,
    missed its pastel, not due a neutral gray, and pending or upcoming days stay as a
    dotted cell (nothing has happened yet).

    Below go the guide numbers 1/10/20/30 aligned to their column and, with
    ``with_legend``, the legend (cumplido / sin culpa / por venir). ``icon_radius`` sets
    the badge size; without it the badge takes half a row (with very tall rows it
    should be smaller, as the dashboard does, so the icon can breathe).

    Returns the total height used from ``y`` (rows + guide + legend).
    """
    # The side of each cell: what is left after the label, shared out.
    side = (width - label_width - (days - 1) * gap) / days
    name_font = font("sans", _CAPTION_SIZE, "bold", master=canvas)
    radius = icon_radius if icon_radius else row_step / 2

    for index, (area_id, name, color, soft_color, statuses) in enumerate(rows):
        row_y = y + index * row_step
        # The area's rounded badge and its name, in the label zone.
        area_icon(canvas, x + row_step / 2, row_y + row_step / 2, radius, area_id, color, "square")
        canvas.create_text(
            x + row_step + 6,
            row_y + row_step / 2,
            text=name,
            anchor="w",
            font=name_font,
            fill=palette.INK,
        )

        cell_y = row_y + (row_step - side) / 2  # centered in its row
        for day in range(1, days + 1):
            cell_x = x + label_width + (day - 1) * (side + gap)
            status = statuses.get(day)
            options: dict[str, Any]
            if status is DayStatus.DONE:
                options = {"fill": color, "outline": ""}
            elif status is DayStatus.MISSED:
                # Without guilt: a miss is the area's pastel, not red.
                options = {"fill": soft_color, "outline": ""}
            elif status is DayStatus.NOT_DUE:
                options = {"fill": palette.HEAT_NOT_DUE, "outline": ""}
            else:  # pending and future: a cell with a dotted border
                options = {
                    "fill": palette.HEAT_FUTURE,
                    "outline": palette.HEAT_FUTURE_BORDER,
                    "dash": _CELL_DASH,
                    "width": 1,
                }
            rounded_rect(
                canvas, cell_x, cell_y, cell_x + side, cell_y + side, _CELL_RADIUS, **options
            )

    # The guide numbers, aligned with the column of their day.
    guide_y = y + len(rows) * row_step + _GUIDE_DY
    for day in _GUIDE_DAYS:
        if day <= days:
            number_x = x + label_width + (day - 1) * (side + gap) + side / 2
            canvas.create_text(
                number_x,
                guide_y,
                text=str(day),
                font=font("sans", _SMALL_SIZE, master=canvas),
                fill=palette.MUTED_LIGHT,
            )
    total_height = len(rows) * row_step + _MAP_PADDING

    if with_legend:
        # The color legend, bottom left.
        legend_y = guide_y + _LEGEND_DY
        legend_font = font("sans", _CAPTION_SIZE, "bold", master=canvas)
        swatch_x = x
        swatches = [
            (palette.LILAC, None, _LEGEND_DONE_TEXT),
            (palette.LILAC_SOFT, None, _LEGEND_MISSED_TEXT),
            (palette.HEAT_FUTURE, palette.HEAT_FUTURE_BORDER, _LEGEND_UPCOMING_TEXT),
        ]
        half = _SWATCH_SIZE / 2
        for color, border, text in swatches:
            swatch_options: dict[str, Any]
            if border:
                swatch_options = {"fill": color, "outline": border, "dash": _CELL_DASH, "width": 1}
            else:
                swatch_options = {"fill": color, "outline": ""}
            rounded_rect(
                canvas, swatch_x, legend_y - half, swatch_x + _SWATCH_SIZE, legend_y + half,
                _CELL_RADIUS, **swatch_options,
            )  # fmt: skip
            canvas.create_text(
                swatch_x + _SWATCH_TEXT_X,
                legend_y,
                text=text,
                anchor="w",
                font=legend_font,
                fill=palette.MUTED,
            )
            swatch_x += _SWATCH_TEXT_X + measure(legend_font, text) + _SWATCH_GAP
        total_height = len(rows) * row_step + _GUIDE_DY + _LEGEND_DY + _SWATCH_SIZE

    return total_height
