"""The text colors of the interface reach a contrast of 4.5 : 1 on every surface they sit on.

The ratio is the one of WCAG 2.2 (relative luminance of sRGB). WCAG is written for web content, so
here it is a reference, not a legal requirement.
"""

import pytest

from habit_tracker.seed import default_areas
from habit_tracker.ui.theme import palette

MINIMUM = 4.5


def luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


AREA_SURFACES = [area.soft_color for area in default_areas()]
GENERAL_SURFACES = [
    palette.PAPER,
    palette.ROW_BACKGROUND,
    palette.LILAC_SOFT,
    palette.BACKGROUND,
    palette.BUTTON_LILAC_BACKGROUND,
    palette.CELL_PAST,
    palette.CELL_FUTURE,
    palette.TAB_INACTIVE_BACKGROUND,
    palette.PEACH_BACKGROUND,
    *AREA_SURFACES,
]

# Each text color with the surfaces it is drawn on.
TEXT_ON_SURFACES: dict[str, tuple[str, list[str]]] = {
    "INK": (palette.INK, GENERAL_SURFACES),
    "INK_TITLE": (palette.INK_TITLE, GENERAL_SURFACES),
    "MUTED": (palette.MUTED, GENERAL_SURFACES),
    "MUTED_LIGHT": (palette.MUTED_LIGHT, GENERAL_SURFACES),
    "MUTED_DARK": (palette.MUTED_DARK, GENERAL_SURFACES),
    "WEEKDAY_HEADER": (palette.WEEKDAY_HEADER, [palette.PAPER, palette.BACKGROUND]),
    "NUMBER_PAST": (palette.NUMBER_PAST, [palette.CELL_PAST, palette.PAPER]),
    "NUMBER_FUTURE": (palette.NUMBER_FUTURE, [palette.CELL_FUTURE, palette.PAPER]),
    "NUMBER_TODAY": (palette.NUMBER_TODAY, [palette.LILAC_SOFT, palette.PAPER]),
    "RING_TEXT": (palette.RING_TEXT, [palette.LILAC_SOFT, palette.PAPER, palette.BACKGROUND]),
    "ACCENT_TEXT": (palette.ACCENT_TEXT, [palette.LILAC_SOFT, palette.PAPER]),
    "TAB_INACTIVE_TEXT": (palette.TAB_INACTIVE_TEXT, [palette.TAB_INACTIVE_BACKGROUND]),
    "TAB_ACTIVE_TEXT": (palette.TAB_ACTIVE_TEXT, [palette.TAB_ACTIVE_BACKGROUND]),
    "BUTTON_LILAC_TEXT": (
        palette.BUTTON_LILAC_TEXT,
        [palette.BUTTON_LILAC_BACKGROUND, palette.PAPER],
    ),
    "BUTTON_PINK_TEXT": (
        palette.BUTTON_PINK_TEXT,
        [palette.BUTTON_PINK_BACKGROUND, palette.PAPER],
    ),
    "PEACH_LABEL": (palette.PEACH_LABEL, [palette.PEACH_BACKGROUND]),
    "PEACH_NOTE": (palette.PEACH_NOTE, [palette.PEACH_BACKGROUND]),
    "PEACH_INK": (palette.PEACH_INK, [palette.PEACH_BACKGROUND]),
    "DATE_CHIP_DAY": (palette.DATE_CHIP_DAY, [palette.DATE_CHIP_BACKGROUND]),
    "DATE_CHIP_MONTH": (palette.DATE_CHIP_MONTH, [palette.DATE_CHIP_BACKGROUND]),
}


def test_the_contrast_of_black_on_white_is_the_maximum() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#777777") == pytest.approx(1.0)


@pytest.mark.parametrize("name", sorted(TEXT_ON_SURFACES))
def test_a_text_color_reaches_the_minimum_on_each_of_its_surfaces(name: str) -> None:
    color, surfaces = TEXT_ON_SURFACES[name]
    worst = min(surfaces, key=lambda surface: contrast(color, surface))
    assert contrast(color, worst) >= MINIMUM, (
        f"{name} {color} on {worst} is {contrast(color, worst):.2f} : 1"
    )

