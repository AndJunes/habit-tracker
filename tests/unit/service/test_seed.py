"""The areas the application starts with before anything has been saved."""

import re

from habit_tracker.seed import default_areas

AREA_IDS = [
    "salud",
    "carrera",
    "finanzas",
    "relaciones",
    "crecimiento",
    "experiencias",
    "proposito",
    "estilo_vida",
]
HEX_COLOR = re.compile(r"#[0-9a-f]{6}")


def test_the_default_areas_are_the_eight_life_areas_in_their_usual_order() -> None:
    assert [area.id for area in default_areas()] == AREA_IDS


def test_every_default_area_has_a_name_and_two_hex_colors() -> None:
    for area in default_areas():
        assert area.name
        assert HEX_COLOR.fullmatch(area.color), area
        assert HEX_COLOR.fullmatch(area.soft_color), area


def test_each_call_returns_a_new_list_that_can_be_changed_freely() -> None:
    first = default_areas()
    first.clear()
    assert [area.id for area in default_areas()] == AREA_IDS


def test_two_calls_return_equal_areas() -> None:
    assert default_areas() == default_areas()
