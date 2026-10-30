"""The lilac banner with the date, a greeting and the three figures of the day.

My month shows it compact and the dashboard wide; the drawing is the same, so it is written
once and each screen passes the measures of its own.
"""

import tkinter as tk
from dataclasses import dataclass
from datetime import date

from ..calendar_es import MONTHS, WEEKDAYS_LONG
from ..theme import palette
from ..theme.drawing import ring, rounded_rect
from ..theme.fonts import font
from . import texts

_NOON = 12
_EVENING = 19  # from this hour on it is "buenas noches"


@dataclass(frozen=True, slots=True)
class StatsBannerLayout:
    """The measures of one banner. Positions are relative to the canvas that holds it."""

    width: int
    height: int
    corner_radius: int
    text_x: int  # left edge of the date and the greeting
    date_y: int
    greeting_y: int
    greeting_size: int
    ring_x: int
    ring_y: int
    ring_radius: int
    ring_thickness: int
    ring_text_size: int
    ring_label_y: int  # the word "hoy" under the ring
    streak_x: int
    total_x: int
    number_y: int  # the big numbers of the streak and the total
    number_size: int
    label_y: int  # their captions


MONTH_BANNER = StatsBannerLayout(
    width=556, height=96, corner_radius=18, text_x=22, date_y=32, greeting_y=62,
    greeting_size=19, ring_x=318, ring_y=42, ring_radius=22, ring_thickness=6,
    ring_text_size=10, ring_label_y=78, streak_x=408, total_x=496, number_y=42,
    number_size=19, label_y=74,
)  # fmt: skip

DASHBOARD_BANNER = StatsBannerLayout(
    width=1280, height=100, corner_radius=22, text_x=26, date_y=36, greeting_y=68,
    greeting_size=22, ring_x=1000, ring_y=44, ring_radius=26, ring_thickness=7,
    ring_text_size=11, ring_label_y=84, streak_x=1105, total_x=1205, number_y=44,
    number_size=22, label_y=84,
)  # fmt: skip


def greeting_for_hour(hour: int) -> str:
    """ "Buenos días" until noon, "buenas tardes" until 19:00 and "buenas noches" after that."""
    if hour < _NOON:
        return texts.GREETING_MORNING
    if hour < _EVENING:
        return texts.GREETING_AFTERNOON
    return texts.GREETING_EVENING


def long_date_text(day: date) -> str:
    """``date(2026, 10, 29)`` becomes ``"jueves 29 de octubre"``."""
    return f"{WEEKDAYS_LONG[day.weekday()]} {day.day} de {MONTHS[day.month - 1]}"


def draw_stats_banner(
    canvas: tk.Canvas,
    layout: StatsBannerLayout,
    *,
    today: date,
    hour: int,
    progress: tuple[int, int],
    longest_streak: int,
    month_checks: int,
) -> None:
    """Draw the banner: date and greeting on the left, the day's ring, the best streak and the
    month's checks on the right. ``progress`` is ``(done, due)`` for today."""
    rounded_rect(
        canvas, 1, 1, layout.width - 1, layout.height - 1, layout.corner_radius,
        fill=palette.LILAC_SOFT, outline=palette.BORDER,
    )  # fmt: skip
    canvas.create_text(
        layout.text_x,
        layout.date_y,
        text=long_date_text(today),
        anchor="w",
        font=font("script", 15, master=canvas),
        fill=palette.LILAC,
    )
    canvas.create_text(
        layout.text_x,
        layout.greeting_y,
        text=greeting_for_hour(hour),
        anchor="w",
        font=font("serif", layout.greeting_size, master=canvas),
        fill=palette.INK_TITLE,
    )

    caption_font = font("sans", 8, master=canvas)

    # The ring track is BORDER because the default one (LILAC_SOFT) would vanish on the banner.
    done, due = progress
    ring(
        canvas, layout.ring_x, layout.ring_y, layout.ring_radius, layout.ring_thickness,
        done / due if due else 0, track_color=palette.BORDER,
    )  # fmt: skip
    canvas.create_text(
        layout.ring_x,
        layout.ring_y,
        text=f"{done}/{due}",
        font=font("sans", layout.ring_text_size, "bold", master=canvas),
        fill=palette.RING_TEXT,
    )
    canvas.create_text(
        layout.ring_x,
        layout.ring_label_y,
        text=texts.STAT_TODAY,
        font=caption_font,
        fill=palette.MUTED,
    )

    figures = (
        (layout.streak_x, longest_streak, palette.ACCENT_STREAK, texts.STAT_LONGEST_STREAK),
        (layout.total_x, month_checks, palette.ACCENT_TOTAL, texts.STAT_MONTH_CHECKS),
    )
    for x, number, color, caption in figures:
        canvas.create_text(
            x,
            layout.number_y,
            text=str(number),
            font=font("serif", layout.number_size, master=canvas),
            fill=color,
        )
        canvas.create_text(x, layout.label_y, text=caption, font=caption_font, fill=palette.MUTED)
