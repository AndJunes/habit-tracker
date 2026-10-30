"""Canvas drawing helpers: Tk has no rounded corners or progress rings, so they are drawn.

House rule: every Canvas is created with ``highlightthickness=0`` and the
background of its container, so it blends in.
"""

import tkinter as tk
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from ...domain.models import Area
from .palette import (
    FLAG,
    FLAG_POLE,
    INK,
    LILAC,
    LILAC_SOFT,
    NEUTRAL_AREA_COLOR,
    WHITE,
)

type IconShape = Literal["circle", "square"]

# (color, fraction of the whole) for each slice of a donut.
type DonutSegment = tuple[str, float]

# How much white is mixed into an area color that has no stored soft color.
SOFT_AREA_COLOR_MIX = 0.82

# An arc of a full turn would vanish, so "complete" is drawn a hair short of 360 degrees.
_FULL_TURN_EXTENT = -359.9
_RING_START_ANGLE = 90  # arcs start at 12 o'clock

# The area icons are drawn for a 34 px badge; everything scales from that radius.
_ICON_REFERENCE_RADIUS = 17.0
_SQUARE_ICON_CORNER = 0.6  # corner radius of the square badge, as a fraction of its radius


def mix_colors(color_a: str, color_b: str, amount: float) -> str:
    """Mixes two ``#rrggbb`` colors: ``amount`` 0 gives the first, 1 gives the second."""
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        value_a = int(a[i : i + 2], 16)
        value_b = int(b[i : i + 2], 16)
        channels.append(round(value_a + (value_b - value_a) * amount))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def area_color_or_default(area: Area | None) -> str:
    """The color of an area, or a neutral gray when the area is unknown."""
    return area.color if area else NEUTRAL_AREA_COLOR


def soft_color_of(area: Area | None) -> str:
    """The pale tint of an area for backgrounds, lightening its color when none is stored."""
    if area and area.soft_color:
        return area.soft_color
    return mix_colors(area_color_or_default(area), WHITE, SOFT_AREA_COLOR_MIX)


def rounded_rect(
    canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **options: Any
) -> int:
    """A rectangle with rounded corners (a smoothed polygon)."""
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]  # fmt: skip
    return canvas.create_polygon(points, smooth=True, **options)


def ring(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    radius: float,
    thickness: float,
    fraction: float,
    color: str = LILAC,
    track_color: str = LILAC_SOFT,
) -> None:
    """A progress ring; ``fraction`` goes from 0 to 1."""
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    canvas.create_oval(*box, outline=track_color, width=thickness)
    if fraction > 0:
        extent = _FULL_TURN_EXTENT if fraction >= 1 else -fraction * 360
        canvas.create_arc(
            *box,
            start=_RING_START_ANGLE,
            extent=extent,
            style="arc",
            outline=color,
            width=thickness,
        )


def donut(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    radius: float,
    thickness: float,
    segments: Sequence[DonutSegment],
    empty_color: str = LILAC_SOFT,
) -> None:
    """A balance donut; the fractions of ``segments`` add up to at most 1.

    With nothing to show, only the empty ring is drawn.
    """
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    total = sum(fraction for _, fraction in segments)
    if total <= 0:
        canvas.create_oval(*box, outline=empty_color, width=thickness)
        return
    accumulated = 0.0
    for color, fraction in segments:
        if fraction <= 0:
            continue
        extent = _FULL_TURN_EXTENT if fraction >= 0.999 else -fraction * 360
        canvas.create_arc(
            *box,
            start=_RING_START_ANGLE - accumulated * 360,
            extent=extent,
            style="arc",
            outline=color,
            width=thickness,
        )
        accumulated += fraction


def flag(canvas: tk.Canvas, x: float, y: float, scale: float = 1.0) -> None:
    """The small pink flag of the important dates; ``x, y`` is the top of the pole."""
    e = scale
    canvas.create_line(x, y, x, y + 12 * e, fill=FLAG_POLE, width=1.6, capstyle="round")
    canvas.create_polygon(
        x, y, x + 7 * e, y, x + 5 * e, y + 2.6 * e, x + 7 * e, y + 5.2 * e, x, y + 5.2 * e,
        fill=FLAG, outline="",
    )  # fmt: skip


def checkbox(
    canvas: tk.Canvas, x: float, y: float, side: float, color: str, checked: bool
) -> None:
    """The habit's box: filled with a white tick, or empty with a colored border."""
    radius = side * 0.32
    if checked:
        rounded_rect(canvas, x, y, x + side, y + side, radius, fill=color, outline="")
        tick = [
            x + side * 0.26, y + side * 0.52,
            x + side * 0.44, y + side * 0.72,
            x + side * 0.78, y + side * 0.30,
        ]  # fmt: skip
        canvas.create_line(tick, fill=WHITE, width=2.6, capstyle="round", joinstyle="round")
    else:
        rounded_rect(canvas, x, y, x + side, y + side, radius, fill=WHITE, outline=color, width=2)


def trash_can(
    canvas: tk.Canvas, cx: float, cy: float, scale: float = 1.0, color: str = INK
) -> None:
    """The trash can: handle, lid, body and its two stripes."""
    e = scale
    line_width = 1.8 * e + 0.6
    canvas.create_line(
        cx - 2.5 * e, cy - 7.5 * e, cx + 2.5 * e, cy - 7.5 * e,
        fill=color, width=line_width, capstyle="round",
    )  # fmt: skip
    canvas.create_line(
        cx - 7 * e, cy - 5 * e, cx + 7 * e, cy - 5 * e,
        fill=color, width=line_width, capstyle="round",
    )  # fmt: skip
    canvas.create_polygon(
        cx - 5.5 * e, cy - 2.5 * e, cx + 5.5 * e, cy - 2.5 * e,
        cx + 4.2 * e, cy + 7.5 * e, cx - 4.2 * e, cy + 7.5 * e,
        fill="", outline=color, width=line_width, joinstyle="round",
    )  # fmt: skip
    for dx in (-1.8, 1.8):
        canvas.create_line(
            cx + dx * e, cy - 0.3 * e, cx + dx * e, cy + 5 * e,
            fill=color, width=1.4 * e + 0.4, capstyle="round",
        )  # fmt: skip


# ---------- Area icons ----------
# Each painter draws one white glyph on the badge. ``e`` is the scale relative to the
# reference badge; ``badge_color`` is the badge fill, for glyph parts that cut out.


def _paint_health(canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str) -> None:
    """A heart: two lobes and the tip."""
    canvas.create_oval(cx - 6 * e, cy - 5 * e, cx, cy + 1 * e, fill=WHITE, outline="")
    canvas.create_oval(cx, cy - 5 * e, cx + 6 * e, cy + 1 * e, fill=WHITE, outline="")
    canvas.create_polygon(
        cx - 5.6 * e, cy - 0.5 * e, cx + 5.6 * e, cy - 0.5 * e, cx, cy + 6.5 * e,
        fill=WHITE, outline="",
    )  # fmt: skip


def _paint_career(canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str) -> None:
    """A briefcase: a handle on top of a rounded body."""
    handle = [
        cx - 2.5 * e, cy - 3 * e, cx - 2.5 * e, cy - 5.5 * e,
        cx + 2.5 * e, cy - 5.5 * e, cx + 2.5 * e, cy - 3 * e,
    ]  # fmt: skip
    canvas.create_line(handle, fill=WHITE, width=1.6 * e + 0.6, joinstyle="round")
    rounded_rect(
        canvas, cx - 7 * e, cy - 3 * e, cx + 7 * e, cy + 6 * e, 2.5 * e, fill=WHITE, outline=""
    )


def _paint_finance(canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str) -> None:
    """A banknote: a rounded frame with a coin in the middle."""
    rounded_rect(
        canvas, cx - 7.5 * e, cy - 4.5 * e, cx + 7.5 * e, cy + 4.5 * e, 2 * e,
        fill="", outline=WHITE, width=1.6 * e + 0.6,
    )  # fmt: skip
    canvas.create_oval(
        cx - 2.2 * e, cy - 2.2 * e, cx + 2.2 * e, cy + 2.2 * e,
        outline=WHITE, width=1.4 * e + 0.5,
    )  # fmt: skip


def _paint_relationships(
    canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str
) -> None:
    """Two people side by side: head and shoulders each."""
    for side in (-1, 1):
        dx = side * 3.5 * e
        canvas.create_oval(
            cx + dx - 2.2 * e, cy - 6 * e, cx + dx + 2.2 * e, cy - 1.6 * e,
            fill=WHITE, outline="",
        )  # fmt: skip
        canvas.create_arc(
            cx + dx - 3.5 * e, cy - 1 * e, cx + dx + 3.5 * e, cy + 6 * e,
            start=0, extent=180, fill=WHITE, outline="",
        )  # fmt: skip


def _paint_growth(canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str) -> None:
    """A sprout: a stem and two leaves."""
    canvas.create_line(
        cx, cy + 7 * e, cx, cy - 1 * e, fill=WHITE, width=1.8 * e + 0.6, capstyle="round"
    )
    canvas.create_polygon(
        cx, cy + 1 * e, cx - 6.5 * e, cy - 1 * e, cx - 3 * e, cy - 6 * e,
        fill=WHITE, outline="", smooth=True,
    )  # fmt: skip
    canvas.create_polygon(
        cx, cy - 1 * e, cx + 6.5 * e, cy - 3 * e, cx + 3.5 * e, cy - 7.5 * e,
        fill=WHITE, outline="", smooth=True,
    )  # fmt: skip


def _paint_experiences(
    canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str
) -> None:
    """Two mountains and a sun."""
    canvas.create_polygon(
        cx - 8 * e, cy + 5 * e, cx - 3 * e, cy - 2 * e, cx + 0.5 * e, cy + 5 * e,
        fill=WHITE, outline="",
    )  # fmt: skip
    canvas.create_polygon(
        cx - 1.5 * e, cy + 5 * e, cx + 3.5 * e, cy - 5 * e, cx + 8 * e, cy + 5 * e,
        fill=WHITE, outline="",
    )  # fmt: skip
    canvas.create_oval(cx - 7 * e, cy - 7 * e, cx - 4 * e, cy - 4 * e, fill=WHITE, outline="")


def _paint_purpose(canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str) -> None:
    """A target: two rings and the center dot."""
    canvas.create_oval(
        cx - 6.5 * e, cy - 6.5 * e, cx + 6.5 * e, cy + 6.5 * e,
        outline=WHITE, width=1.6 * e + 0.6,
    )  # fmt: skip
    canvas.create_oval(
        cx - 3.5 * e, cy - 3.5 * e, cx + 3.5 * e, cy + 3.5 * e,
        outline=WHITE, width=1.4 * e + 0.5,
    )  # fmt: skip
    canvas.create_oval(cx - 1 * e, cy - 1 * e, cx + 1 * e, cy + 1 * e, fill=WHITE, outline="")


def _paint_lifestyle(canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str) -> None:
    """A house: roof, body and a door in the badge color."""
    canvas.create_polygon(
        cx - 7.5 * e, cy - 0.5 * e, cx, cy - 7 * e, cx + 7.5 * e, cy - 0.5 * e,
        fill=WHITE, outline="",
    )  # fmt: skip
    canvas.create_rectangle(
        cx - 5 * e, cy + 0.5 * e, cx + 5 * e, cy + 7 * e, fill=WHITE, outline=""
    )
    canvas.create_rectangle(
        cx - 1.3 * e, cy + 2.5 * e, cx + 1.3 * e, cy + 7 * e, fill=badge_color, outline=""
    )


def _paint_sun(canvas: tk.Canvas, cx: float, cy: float, e: float, badge_color: str) -> None:
    """A small sun: the icon of areas that have none of their own."""
    canvas.create_oval(
        cx - 3.5 * e, cy - 3.5 * e, cx + 3.5 * e, cy + 3.5 * e,
        outline=WHITE, width=1.6 * e + 0.6,
    )  # fmt: skip
    rays = ((0, -6), (0, 6), (-6, 0), (6, 0), (-4.3, -4.3), (4.3, 4.3), (-4.3, 4.3), (4.3, -4.3))
    for dx, dy in rays:
        canvas.create_line(
            cx + dx * e * 0.95, cy + dy * e * 0.95, cx + dx * e * 1.35, cy + dy * e * 1.35,
            fill=WHITE, width=1.5 * e + 0.5, capstyle="round",
        )  # fmt: skip


type _IconPainter = Callable[[tk.Canvas, float, float, float, str], None]

# Keyed by the ids of the default areas, which are what gets stored with the data.
_AREA_ICONS: Mapping[str, _IconPainter] = {
    "salud": _paint_health,
    "carrera": _paint_career,
    "finanzas": _paint_finance,
    "relaciones": _paint_relationships,
    "crecimiento": _paint_growth,
    "experiencias": _paint_experiences,
    "proposito": _paint_purpose,
    "estilo_vida": _paint_lifestyle,
}


def area_icon(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    radius: float,
    area_id: str,
    color: str,
    shape: IconShape = "circle",
) -> None:
    """A colored badge with a white glyph that depends on ``area_id``.

    Ids that are not one of the default areas get the sun glyph.
    ``shape`` is ``"circle"`` (habit list) or ``"square"`` (consistency map).
    """
    if shape == "square":
        rounded_rect(
            canvas, cx - radius, cy - radius, cx + radius, cy + radius,
            radius * _SQUARE_ICON_CORNER, fill=color, outline="",
        )  # fmt: skip
    else:
        canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline=""
        )
    paint = _AREA_ICONS.get(area_id, _paint_sun)
    paint(canvas, cx, cy, radius / _ICON_REFERENCE_RADIUS, color)
