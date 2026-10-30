"""One day of a month grid, drawn the same way in the Calendar tab and on the dashboard."""

import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ...service import HabitService
from ..theme import palette
from ..theme.drawing import area_color_or_default, flag, rounded_rect
from ..theme.fonts import font

_NUMBER_X = 8
_NUMBER_Y = 7
_FLAG_FROM_RIGHT = 16  # the flag's pole is this far from the cell's right edge
_FLAG_SCALE = 0.85
_DOT_SIZE = 6
_DOT_STEP = 9  # between the centers of two dots
_TODAY_BORDER = 2


@dataclass(frozen=True, slots=True)
class DayCellStyle:
    """What differs between the grids: corner radius, height of the dots and how many fit."""

    radius: int
    dots_y: int
    max_dots: int | None = None


def draw_day_cell(
    canvas: tk.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    day: date,
    today: date,
    style: DayCellStyle,
    *,
    flagged: bool,
    area_colors: Sequence[str],
) -> None:
    """Draw the cell of ``day`` with its top-left corner at ``(x, y)``.

    Today is lit in lilac, the future has no border and the past a barely visible one.
    A pink flag marks a day with an important date and each color in ``area_colors`` (one
    per area done that day) becomes a small dot.
    """
    if day == today:
        # Inset by 1 px so that the lilac ring is not clipped at the canvas edge.
        rounded_rect(
            canvas, x + 1, y + 1, x + width - 1, y + height - 1, style.radius,
            fill=palette.LILAC_SOFT, outline=palette.LILAC, width=_TODAY_BORDER,
        )  # fmt: skip
        number_color = palette.NUMBER_TODAY
    elif day > today:
        rounded_rect(
            canvas, x, y, x + width, y + height, style.radius,
            fill=palette.CELL_FUTURE, outline="",
        )  # fmt: skip
        number_color = palette.NUMBER_FUTURE
    else:
        rounded_rect(
            canvas, x, y, x + width, y + height, style.radius,
            fill=palette.CELL_PAST, outline=palette.CELL_BORDER, width=1,
        )  # fmt: skip
        number_color = palette.NUMBER_PAST

    canvas.create_text(
        x + _NUMBER_X,
        y + _NUMBER_Y,
        anchor="nw",
        text=str(day.day),
        font=font("sans", 9, "bold", master=canvas),
        fill=number_color,
    )
    if flagged:
        flag(canvas, x + width - _FLAG_FROM_RIGHT, y + _NUMBER_Y, scale=_FLAG_SCALE)
    for index, color in enumerate(area_colors[: style.max_dots]):
        dot_x = x + _NUMBER_X + index * _DOT_STEP
        canvas.create_oval(
            dot_x, y + style.dots_y, dot_x + _DOT_SIZE, y + style.dots_y + _DOT_SIZE,
            fill=color, outline="",
        )  # fmt: skip


def completed_area_colors(service: HabitService, year: int, month: int) -> dict[int, list[str]]:
    """``{day of month: [color of each area done that day]}``, ready for the dots of a grid."""
    areas = {area.id: area for area in service.areas()}
    return {
        day: [area_color_or_default(areas.get(area_id)) for area_id in area_ids]
        for day, area_ids in service.completed_areas_by_day(year, month).items()
    }
