import re

import pytest

from habit_tracker.domain.models import Area
from habit_tracker.seed import default_areas
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.drawing import area_color_or_default, mix_colors, soft_color_of

HEX_COLOR = re.compile(r"#[0-9a-f]{6}")


def test_every_palette_color_is_a_lowercase_hex_value() -> None:
    colors = {name: value for name, value in vars(palette).items() if name.isupper()}
    assert colors
    assert all(HEX_COLOR.fullmatch(value) for value in colors.values()), colors


def test_palette_aliases_point_at_the_colors_they_reuse() -> None:
    assert palette.TAB_ACTIVE_BACKGROUND == palette.PAPER
    assert palette.TAB_ACTIVE_TEXT == palette.INK_TITLE
    assert palette.TRASH_REST == palette.BUTTON_PINK_TEXT
    assert palette.TRASH_ACTIVE == palette.FLAG
    assert palette.TRASH_ACTIVE_BACKGROUND == palette.DATE_CHIP_BACKGROUND


@pytest.mark.parametrize(
    ("color_a", "color_b", "amount", "expected"),
    [
        ("#000000", "#ffffff", 0.0, "#000000"),
        ("#000000", "#ffffff", 1.0, "#ffffff"),
        ("#000000", "#ffffff", 0.5, "#808080"),
        ("#a98fd0", "#000000", 0.05, "#a188c6"),
        ("#a98fd0", "#ffffff", 0.4, "#cbbce3"),
        ("a98fd0", "ffffff", 0.0, "#a98fd0"),
    ],
)
def test_mix_colors(color_a: str, color_b: str, amount: float, expected: str) -> None:
    assert mix_colors(color_a, color_b, amount) == expected


def test_soft_color_of_lightens_the_color_with_the_same_formula_as_the_stored_ones() -> None:
    # The soft colors stored for the default areas are their color mixed 82% with white.
    for area in default_areas():
        bare = Area(area.id, area.name, area.color)
        assert soft_color_of(bare) == area.soft_color


def test_soft_color_of_prefers_the_stored_soft_color() -> None:
    assert soft_color_of(Area("x", "X", "#112233", "#aabbcc")) == "#aabbcc"


def test_unknown_areas_use_the_neutral_gray() -> None:
    assert area_color_or_default(None) == palette.NEUTRAL_AREA_COLOR == "#b4aabf"
    assert soft_color_of(None) == mix_colors(palette.NEUTRAL_AREA_COLOR, palette.WHITE, 0.82)


def test_area_color_or_default_returns_the_area_color() -> None:
    assert area_color_or_default(Area("x", "X", "#112233")) == "#112233"
