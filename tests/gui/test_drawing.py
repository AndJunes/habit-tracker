import tkinter as tk

import pytest

from habit_tracker.seed import default_areas
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.drawing import (
    area_icon,
    checkbox,
    donut,
    flag,
    ring,
    rounded_rect,
    trash_can,
)


def kinds(canvas: tk.Canvas) -> list[str]:
    return [canvas.type(item) for item in canvas.find_all()]


def arcs(canvas: tk.Canvas) -> list[tuple[float, float]]:
    """``(start, extent)`` of every arc on the canvas."""
    return [
        (float(canvas.itemcget(item, "start")), float(canvas.itemcget(item, "extent")))
        for item in canvas.find_all()
        if canvas.type(item) == "arc"
    ]


@pytest.fixture
def canvas(tk_root: tk.Tk) -> tk.Canvas:
    return tk.Canvas(tk_root, width=200, height=200)


def test_rounded_rect_is_a_smoothed_polygon_inside_its_box(canvas: tk.Canvas) -> None:
    item = rounded_rect(canvas, 10, 20, 110, 70, 12, fill="red", outline="")
    assert canvas.type(item) == "polygon"
    assert canvas.itemcget(item, "smooth") in {"1", "true"}
    xs, ys = canvas.coords(item)[::2], canvas.coords(item)[1::2]
    assert (min(xs), min(ys), max(xs), max(ys)) == (10, 20, 110, 70)


def test_rounded_rect_clamps_the_radius_to_half_the_shortest_side(canvas: tk.Canvas) -> None:
    item = rounded_rect(canvas, 0, 0, 100, 10, 50)
    assert canvas.coords(item)[:2] == [5.0, 0.0]  # first point sits one clamped radius in


def test_ring_draws_the_track_and_an_arc_only_when_there_is_progress(canvas: tk.Canvas) -> None:
    ring(canvas, 50, 50, 30, 6, 0)
    assert kinds(canvas) == ["oval"]
    ring(canvas, 50, 50, 30, 6, 0.25)
    assert kinds(canvas) == ["oval", "oval", "arc"]
    assert arcs(canvas) == [(90.0, -90.0)]


def test_a_complete_ring_stops_a_hair_short_of_a_full_turn(canvas: tk.Canvas) -> None:
    ring(canvas, 50, 50, 30, 6, 1)
    assert arcs(canvas) == [(90.0, -359.9)]


def test_donut_without_segments_is_only_the_empty_ring(canvas: tk.Canvas) -> None:
    donut(canvas, 50, 50, 30, 8, [])
    assert kinds(canvas) == ["oval"]
    assert canvas.itemcget(canvas.find_all()[0], "outline") == palette.LILAC_SOFT


def test_donut_arcs_follow_one_another_and_skip_empty_segments(canvas: tk.Canvas) -> None:
    donut(canvas, 50, 50, 30, 8, [("#111111", 0.5), ("#222222", 0), ("#333333", 0.25)])
    # The second arc starts where the first ended (-90 degrees, which Tk reports as 270).
    assert arcs(canvas) == [(90.0, -180.0), (270.0, -90.0)]


def test_checkbox_checked_has_a_tick_and_unchecked_only_a_border(canvas: tk.Canvas) -> None:
    checkbox(canvas, 10, 10, 22, "#65a882", True)
    assert kinds(canvas) == ["polygon", "line"]
    assert canvas.itemcget(canvas.find_all()[0], "fill") == "#65a882"
    canvas.delete("all")
    checkbox(canvas, 10, 10, 22, "#65a882", False)
    assert kinds(canvas) == ["polygon"]
    assert canvas.itemcget(canvas.find_all()[0], "outline") == "#65a882"


def test_flag_is_a_pole_and_a_pennant(canvas: tk.Canvas) -> None:
    flag(canvas, 10, 10)
    assert kinds(canvas) == ["line", "polygon"]
    pole, pennant = canvas.find_all()
    assert canvas.itemcget(pole, "fill") == palette.FLAG_POLE
    assert canvas.itemcget(pennant, "fill") == palette.FLAG


def test_trash_can_is_handle_lid_body_and_two_stripes(canvas: tk.Canvas) -> None:
    trash_can(canvas, 20, 20, color="#ff0000")
    assert kinds(canvas) == ["line", "line", "polygon", "line", "line"]
    handle, lid, body, *stripes = canvas.find_all()
    assert {canvas.itemcget(item, "fill") for item in (handle, lid, *stripes)} == {"#ff0000"}
    assert canvas.itemcget(body, "outline") == "#ff0000"


def describe(canvas: tk.Canvas) -> list[tuple[str, tuple[float, ...]]]:
    return [(canvas.type(item), tuple(canvas.coords(item))) for item in canvas.find_all()]


AREA_IDS = [area.id for area in default_areas()]


def test_each_default_area_has_a_glyph_of_its_own(canvas: tk.Canvas, tk_root: tk.Tk) -> None:
    drawings = []
    for area_id in [*AREA_IDS, "unknown"]:
        badge = tk.Canvas(tk_root)
        area_icon(badge, 50, 50, 17, area_id, "#6488d8")
        drawings.append(describe(badge))
    assert len(AREA_IDS) == 8
    assert len({tuple(drawing) for drawing in drawings}) == 9


def test_unknown_areas_get_the_sun(canvas: tk.Canvas, tk_root: tk.Tk) -> None:
    area_icon(canvas, 50, 50, 17, "otra", "#6488d8")
    sun = tk.Canvas(tk_root)
    area_icon(sun, 50, 50, 17, "sol", "#6488d8")
    assert describe(canvas) == describe(sun)
    assert kinds(canvas) == ["oval", "oval", *["line"] * 8]


def test_the_badge_is_a_circle_or_a_rounded_square(canvas: tk.Canvas) -> None:
    area_icon(canvas, 50, 50, 17, "salud", "#6488d8")
    assert kinds(canvas)[0] == "oval"
    canvas.delete("all")
    area_icon(canvas, 50, 50, 17, "salud", "#6488d8", "square")
    assert kinds(canvas)[0] == "polygon"
    assert canvas.itemcget(canvas.find_all()[0], "fill") == "#6488d8"


@pytest.mark.parametrize("area_id", [*AREA_IDS, "unknown"])
@pytest.mark.parametrize("radius", [11, 13, 17])
def test_glyphs_stay_inside_their_badge(canvas: tk.Canvas, area_id: str, radius: int) -> None:
    area_icon(canvas, 100, 100, radius, area_id, "#6488d8")
    for item in canvas.find_all():
        coords = canvas.coords(item)
        assert all(100 - radius <= value <= 100 + radius for value in coords), (area_id, coords)


def test_the_house_door_is_cut_out_in_the_badge_color(canvas: tk.Canvas) -> None:
    area_icon(canvas, 50, 50, 17, "estilo_vida", "#8493a8")
    assert canvas.itemcget(canvas.find_all()[-1], "fill") == "#8493a8"
