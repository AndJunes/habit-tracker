import tkinter as tk
from datetime import date
from typing import ClassVar

import pytest

from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.enums import DayStatus
from habit_tracker.domain.models import Area, Snapshot
from habit_tracker.domain.stats import MonthStats, month_stats
from habit_tracker.seed import default_areas
from habit_tracker.ui import charts
from habit_tracker.ui.charts import (
    AreaBar,
    ConsistencyRow,
    LegendEntry,
    area_bars,
    balance_donut,
    consistency_map,
    donut_legend,
    draw_legend_rows,
    legend_rows,
    month_pace,
)
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.drawing import soft_color_of
from habit_tracker.ui.theme.fonts import font, measure

TODAY = date(2026, 10, 29)


@pytest.fixture
def canvas(tk_root: tk.Tk) -> tk.Canvas:
    return tk.Canvas(tk_root, width=1300, height=600)


@pytest.fixture
def snapshot() -> Snapshot:
    return build_demo_snapshot(TODAY)


@pytest.fixture
def stats(snapshot: Snapshot) -> MonthStats:
    return month_stats(snapshot.areas, snapshot.habits, TODAY.year, TODAY.month, TODAY)


def texts(canvas: tk.Canvas) -> list[str]:
    return [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]


def fills(canvas: tk.Canvas, kind: str) -> list[str]:
    return [canvas.itemcget(i, "fill") for i in canvas.find_all() if canvas.type(i) == kind]


def bounds(canvas: tk.Canvas) -> tuple[float, float, float, float]:
    bbox = canvas.bbox("all")
    assert bbox is not None
    return bbox


def consistency_rows(stats: MonthStats, areas: list[Area]) -> list[ConsistencyRow]:
    by_id = {area.id: area for area in areas}
    return [
        ConsistencyRow(area_id, by_id[area_id].name, by_id[area_id].color,
                       soft_color_of(by_id[area_id]), statuses)
        for area_id, statuses in stats.matrix.items()
    ]  # fmt: skip


class TestAreaBars:
    ROWS: ClassVar[list[AreaBar]] = [
        AreaBar("Salud", 80, "#65a882", "#e3efe8"),
        AreaBar("Carrera", 0, "#6488d8", "#e3eaf8"),
        AreaBar("Finanzas", 100, "#e6b84c", "#faf2df"),
    ]

    def test_it_returns_26_px_per_row(self, canvas: tk.Canvas) -> None:
        assert area_bars(canvas, 0, 0, 300, self.ROWS) == 3 * 26

    def test_each_area_has_its_name_and_percentage(self, canvas: tk.Canvas) -> None:
        area_bars(canvas, 0, 0, 300, self.ROWS)
        assert texts(canvas) == ["Salud", "80%", "Carrera", "0%", "Finanzas", "100%"]

    def test_the_fill_is_proportional_and_skipped_at_zero(self, canvas: tk.Canvas) -> None:
        area_bars(canvas, 10, 0, 300, self.ROWS)
        bars = [canvas.coords(i) for i in canvas.find_all() if canvas.type(i) == "polygon"]
        assert len(bars) == 5  # a track per area plus a fill for the two that have progress
        track_widths = {max(c[::2]) - min(c[::2]) for c in bars}
        assert 300 in track_widths
        assert 240 in track_widths  # 80% of 300

    def test_with_nothing_it_shows_a_message_in_the_same_26_px(self, canvas: tk.Canvas) -> None:
        assert area_bars(canvas, 0, 0, 300, []) == 26
        assert texts(canvas) == ["todavía no hay hábitos que mostrar"]

    def test_it_draws_the_months_percentages(self, canvas: tk.Canvas, stats: MonthStats) -> None:
        rows = [AreaBar(a.name, pct, a.color, soft_color_of(a)) for a, pct in stats.percentages]
        assert area_bars(canvas, 20, 48, 400, rows) == 26 * len(rows) > 0
        assert bounds(canvas)[0] >= 0


class TestBalanceDonut:
    def test_the_total_goes_in_the_middle_in_serif(
        self, canvas: tk.Canvas, tk_root: tk.Tk
    ) -> None:
        balance_donut(canvas, 60, 60, 45, 14, [("#65a882", 0.5)], 12)
        assert texts(canvas) == ["12", "checks"]
        total = next(i for i in canvas.find_all() if canvas.type(i) == "text")
        assert canvas.itemcget(total, "font") == str(font("serif", 17, master=tk_root))

    def test_the_number_can_be_enlarged_for_big_donuts(
        self, canvas: tk.Canvas, tk_root: tk.Tk
    ) -> None:
        balance_donut(canvas, 60, 60, 54, 16, [], 0, number_size=21)
        total = next(i for i in canvas.find_all() if canvas.type(i) == "text")
        assert canvas.itemcget(total, "font") == str(font("serif", 21, master=tk_root))
        assert [canvas.type(i) for i in canvas.find_all()].count("arc") == 0  # only the empty ring

    def test_it_draws_one_arc_per_segment(self, canvas: tk.Canvas) -> None:
        balance_donut(canvas, 60, 60, 45, 14, [("#111111", 0.5), ("#222222", 0.25)], 9)
        assert [canvas.type(i) for i in canvas.find_all()].count("arc") == 2


class TestLegendRows:
    @pytest.mark.parametrize(("size", "weight", "width"), [(10, "bold", 548), (9, "bold", 442)])
    def test_eight_areas_wrap_into_rows_that_fit_and_keep_their_order(
        self, tk_root: tk.Tk, size: int, weight: str, width: int
    ) -> None:
        areas = default_areas()
        legend_font = font("sans", size, "bold", master=tk_root)
        rows = legend_rows(areas, legend_font, width)
        assert len(rows) >= 2  # eight categories no longer fit on a single line
        assert [a.id for row in rows for a, _ in row] == [a.id for a in areas]
        assert all(sum(w for _, w in row) + 16 * (len(row) - 1) <= width for row in rows)

    def test_item_width_is_dot_space_and_name(self, tk_root: tk.Tk) -> None:
        legend_font = font("sans", 9, "bold", master=tk_root)
        [[(area, width)]] = legend_rows(default_areas()[:1], legend_font, 500)
        assert width == 9 + 6 + measure(legend_font, area.name)

    def test_no_areas_make_no_rows_and_one_area_makes_one(self, tk_root: tk.Tk) -> None:
        legend_font = font("sans", 9, "bold", master=tk_root)
        assert legend_rows([], legend_font, 548) == []
        assert len(legend_rows(default_areas()[:1], legend_font, 548)) == 1

    def test_a_row_is_centered_and_the_height_is_rows_times_row_height(
        self, canvas: tk.Canvas, tk_root: tk.Tk
    ) -> None:
        legend_font = font("sans", 9, "bold", master=tk_root)
        rows = legend_rows(default_areas(), legend_font, 442)
        assert draw_legend_rows(canvas, rows, 548, 11, 22, legend_font) == len(rows) * 22
        left, _, right, _ = bounds(canvas)
        assert left >= 0
        assert right <= 548
        assert sorted(texts(canvas)) == sorted(a.name for a in default_areas())


class TestDonutLegend:
    def test_it_returns_the_block_height_and_aligns_the_counts_on_the_right(
        self, canvas: tk.Canvas
    ) -> None:
        rows = [LegendEntry("Salud", "#65a882", 3), LegendEntry("Carrera", "#6488d8", 12)]
        assert donut_legend(canvas, 150, 20, 300, rows) == 40
        assert texts(canvas) == ["Salud", "3", "Carrera", "12"]
        counts = [i for i in canvas.find_all() if canvas.type(i) == "text" and
                  canvas.itemcget(i, "anchor") == "e"]  # fmt: skip
        assert {canvas.coords(i)[0] for i in counts} == {450}
        assert fills(canvas, "oval") == ["#65a882", "#6488d8"]

    def test_the_step_can_be_changed(self, canvas: tk.Canvas) -> None:
        rows = [LegendEntry("Salud", "#65a882", 3)] * 3
        assert donut_legend(canvas, 0, 0, 100, rows, step=24) == 72


class TestMonthPace:
    def counts(self, days: int) -> list[tuple[int, int]]:
        return [(day, day % 4) for day in range(1, days + 1)]

    def test_with_no_days_it_shows_a_message_and_takes_78_px(self, canvas: tk.Canvas) -> None:
        assert month_pace(canvas, 0, 0, 500, [], 1, 5) == 78
        assert texts(canvas) == ["todavía no hay días registrados este mes"]

    def test_there_is_a_bar_per_day_and_today_lights_up(self, canvas: tk.Canvas) -> None:
        assert month_pace(canvas, 0, 0, 500, self.counts(10), 3, 5) == 78
        bars = fills(canvas, "polygon")
        assert len(bars) == 10
        assert bars.count(palette.LILAC) == 1
        assert bars[4] == palette.LILAC  # day 5
        assert set(bars) - {palette.LILAC} == {palette.PACE_BAR}
        assert texts(canvas) == [str(day) for day in range(1, 11)]

    def test_bars_grow_from_a_common_floor_by_their_count(self, canvas: tk.Canvas) -> None:
        month_pace(canvas, 0, 10, 500, [(1, 0), (2, 3)], 3, 99)
        low, high = (canvas.coords(i) for i in canvas.find_all() if canvas.type(i) == "polygon")
        assert max(low[1::2]) == max(high[1::2])  # same floor
        low_height = max(low[1::2]) - min(low[1::2])
        high_height = max(high[1::2]) - min(high[1::2])
        assert high_height - low_height == pytest.approx(54, abs=1)

    def test_with_more_than_16_bars_only_odd_days_are_numbered(self, canvas: tk.Canvas) -> None:
        month_pace(canvas, 0, 0, 500, self.counts(17), 3, 99)
        assert texts(canvas) == [str(day) for day in range(1, 18, 2)]
        canvas.delete("all")
        month_pace(canvas, 0, 0, 500, self.counts(16), 3, 99)
        assert len(texts(canvas)) == 16

    def test_bars_use_the_full_width(self, canvas: tk.Canvas) -> None:
        month_pace(canvas, 20, 0, 500, self.counts(29), 3, 29)
        left, _, right, _ = bounds(canvas)
        assert left == pytest.approx(20, abs=1)
        assert right == pytest.approx(520, abs=2)

    def test_it_draws_the_demo_month(self, canvas: tk.Canvas, stats: MonthStats) -> None:
        maximum = max([count for _, count in stats.counts_by_day] + [1])
        assert month_pace(canvas, 0, 0, 400, stats.counts_by_day, maximum, TODAY.day) == 78
        assert len(fills(canvas, "polygon")) == TODAY.day


class TestConsistencyMap:
    def row(self, statuses: dict[int, DayStatus]) -> ConsistencyRow:
        return ConsistencyRow("salud", "Salud", "#65a882", "#e3efe8", statuses)

    LABEL_WIDTH = 118

    def cells(self, canvas: tk.Canvas) -> list[int]:
        """The day cells: polygons to the right of the label zone, in drawing order."""
        return [
            i
            for i in canvas.find_all()
            if canvas.type(i) == "polygon" and min(canvas.coords(i)[::2]) >= self.LABEL_WIDTH
        ]

    def cell_styles(self, canvas: tk.Canvas) -> list[tuple[str, str]]:
        """``(fill, outline)`` of every day cell."""
        return [
            (canvas.itemcget(i, "fill"), canvas.itemcget(i, "outline")) for i in self.cells(canvas)
        ]

    def test_each_status_has_its_own_cell_style(self, canvas: tk.Canvas) -> None:
        statuses = {
            1: DayStatus.DONE,
            2: DayStatus.MISSED,
            3: DayStatus.NOT_DUE,
            4: DayStatus.PENDING,
            5: DayStatus.FUTURE,
        }
        consistency_map(canvas, 0, 0, 600, [self.row(statuses)], 6, with_legend=False)
        done, missed, not_due, pending, future, absent = self.cell_styles(canvas)
        assert done == ("#65a882", "")
        assert missed == ("#e3efe8", "")  # a miss is the area's pastel, never red
        assert not_due == (palette.HEAT_NOT_DUE, "")
        dotted = (palette.HEAT_FUTURE, palette.HEAT_FUTURE_BORDER)
        assert pending == future == absent == dotted

    def test_pending_and_future_cells_are_dotted(self, canvas: tk.Canvas) -> None:
        row = self.row({1: DayStatus.PENDING, 2: DayStatus.DONE})
        consistency_map(canvas, 0, 0, 600, [row], 2, with_legend=False)
        pending, done = self.cells(canvas)
        assert str(canvas.itemcget(pending, "dash")) in {"2 2", "(2, 2)"}
        assert canvas.itemcget(done, "dash") == ""

    def test_the_height_is_rows_plus_guide_with_or_without_legend(self, canvas: tk.Canvas) -> None:
        rows = [self.row({}), self.row({})]
        assert consistency_map(canvas, 0, 0, 600, rows, 30, with_legend=False) == 2 * 22 + 16
        assert consistency_map(canvas, 0, 0, 600, rows, 30) == 2 * 22 + 8 + 16 + 12
        assert consistency_map(canvas, 0, 0, 600, rows, 30, row_step=38) == 2 * 38 + 36

    def test_guide_numbers_stop_at_the_end_of_the_month(self, canvas: tk.Canvas) -> None:
        consistency_map(canvas, 0, 0, 600, [self.row({})], 28, with_legend=False)
        assert [t for t in texts(canvas) if t.isdigit()] == ["1", "10", "20"]
        canvas.delete("all")
        consistency_map(canvas, 0, 0, 600, [self.row({})], 31, with_legend=False)
        assert [t for t in texts(canvas) if t.isdigit()] == ["1", "10", "20", "30"]

    def test_the_legend_explains_the_colors(self, canvas: tk.Canvas) -> None:
        consistency_map(canvas, 0, 0, 600, [self.row({})], 30)
        assert texts(canvas)[-3:] == ["cumplido", "sin culpa", "por venir"]
        canvas.delete("all")
        consistency_map(canvas, 0, 0, 600, [self.row({})], 30, with_legend=False)
        assert "cumplido" not in texts(canvas)

    def test_each_row_starts_with_the_area_badge_and_name(self, canvas: tk.Canvas) -> None:
        consistency_map(canvas, 0, 0, 600, [self.row({})], 30, icon_radius=13)
        badge = canvas.find_all()[0]
        assert canvas.itemcget(badge, "fill") == "#65a882"
        assert "Salud" in texts(canvas)
        left, _, right, _ = canvas.bbox(badge)
        assert (right - left) == pytest.approx(26, abs=2)

    def test_it_draws_the_demo_month_in_a_wide_dashboard_layout(
        self, canvas: tk.Canvas, snapshot: Snapshot, stats: MonthStats
    ) -> None:
        rows = consistency_rows(stats, snapshot.areas)
        assert rows
        height = consistency_map(
            canvas, 20, 52, 1240, rows, 31,
            label_width=150, row_step=38, gap=3, icon_radius=13,
        )  # fmt: skip
        assert height == len(rows) * 38 + 36
        _, _, right, _ = bounds(canvas)
        assert right <= 1300


def test_the_module_exposes_one_function_per_chart() -> None:
    assert {
        "area_bars",
        "balance_donut",
        "donut_legend",
        "legend_rows",
        "draw_legend_rows",
        "month_pace",
        "consistency_map",
    } <= set(dir(charts))
