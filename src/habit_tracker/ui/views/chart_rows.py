"""Turns the month's figures into the rows the charts draw, for My month and the dashboard."""

from collections.abc import Sequence

from ...domain.models import Area
from ...domain.stats import MonthStats
from ..charts import AreaBar, ConsistencyRow, LegendEntry
from ..theme.drawing import DonutSegment, soft_color_of


def area_bar_rows(month: MonthStats) -> list[AreaBar]:
    """One progress bar per area that has habits."""
    return [
        AreaBar(area.name, percent, area.color, soft_color_of(area))
        for area, percent in month.percentages
    ]


def donut_segments(month: MonthStats) -> list[DonutSegment]:
    """The share of the month's checks that each area contributes; none for an empty month."""
    if not month.total:
        return []
    return [(area.color, count / month.total) for area, count in month.counts_by_area if count > 0]


def donut_legend_rows(month: MonthStats) -> list[LegendEntry]:
    return [LegendEntry(area.name, area.color, count) for area, count in month.counts_by_area]


def consistency_rows(areas: Sequence[Area], month: MonthStats) -> list[ConsistencyRow]:
    """One row per area that has habits, in the order the areas are listed."""
    return [
        ConsistencyRow(area.id, area.name, area.color, soft_color_of(area), month.matrix[area.id])
        for area in areas
        if area.id in month.matrix
    ]


def pace_maximum(month: MonthStats) -> int:
    """The tallest possible pace bar is "every area done that day"."""
    return max(len(month.matrix), 1)
