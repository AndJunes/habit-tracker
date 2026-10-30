"""The "Calendario" tab: the month grid, the legend and the card of important dates."""

import tkinter as tk
from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.domain.models import ImportantDate
from habit_tracker.service import HabitService
from habit_tracker.ui.theme import palette
from habit_tracker.ui.views import texts
from habit_tracker.ui.views.calendar import (
    CELL_HEIGHT,
    CELL_WIDTH,
    CONTENT_WIDTH,
    CalendarView,
)

from .conftest import Tree

PREVIOUS, NEXT = texts.PREVIOUS_MONTH, texts.NEXT_MONTH


@pytest.fixture
def make_view(window: tk.Toplevel) -> Callable[[HabitService], CalendarView]:
    def make(service: HabitService) -> CalendarView:
        view = CalendarView(window, service)
        view.pack()
        window.update()
        return view

    return make


@pytest.fixture
def view(make_view: Callable[[HabitService], CalendarView], service: HabitService) -> CalendarView:
    return make_view(service)


def click(widget: tk.Misc) -> None:
    widget.update()
    widget.event_generate("<Button-1>", x=5, y=5)
    widget.update()


def items(canvas: tk.Canvas, kind: str) -> list[int]:
    return [item for item in canvas.find_all() if canvas.type(item) == kind]


def bounds(canvas: tk.Canvas) -> tuple[int, int, int, int]:
    box = canvas.bbox("all")
    assert box is not None
    return box


class TestNavigation:
    def test_it_opens_on_the_month_of_the_service_clock(self, view: CalendarView) -> None:
        assert (view.year, view.month) == (2026, 10)
        assert view.month_label.cget("text") == "octubre 2026"

    def test_the_arrows_move_one_month_at_a_time(self, view: CalendarView) -> None:
        buttons = Tree.buttons(view)

        click(buttons[NEXT])
        assert view.month_label.cget("text") == "noviembre 2026"

        click(buttons[PREVIOUS])
        click(buttons[PREVIOUS])
        assert view.month_label.cget("text") == "septiembre 2026"

    def test_going_forward_from_december_enters_january_of_the_next_year(
        self, view: CalendarView
    ) -> None:
        view.year, view.month = 2026, 12

        view.next_month()

        assert (view.year, view.month) == (2027, 1)
        assert view.month_label.cget("text") == "enero 2027"

    def test_going_back_from_january_enters_december_of_the_previous_year(
        self, view: CalendarView
    ) -> None:
        view.year, view.month = 2027, 1

        view.previous_month()

        assert (view.year, view.month) == (2026, 12)

    def test_a_month_with_six_weeks_is_taller_than_one_with_four(self, view: CalendarView) -> None:
        view.year, view.month = 2026, 2  # February 2026 starts on a Sunday: five weeks
        view.refresh()
        five = int(view.grid_canvas["height"])
        view.year, view.month = 2026, 8  # August 2026 needs six
        view.refresh()
        six = int(view.grid_canvas["height"])

        assert six - five == CELL_HEIGHT + 5


class TestGrid:
    def test_every_day_of_the_month_has_a_cell_and_the_weekday_names_head_the_columns(
        self, view: CalendarView
    ) -> None:
        names = Tree.texts(view.grid_canvas)

        assert names[:7] == ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
        assert names[7:] == [str(day) for day in range(1, 32)]

    def test_each_area_done_on_a_day_adds_a_dot_of_its_color(
        self, view: CalendarView, service: HabitService
    ) -> None:
        expected = sum(len(ids) for ids in service.completed_areas_by_day(2026, 10).values())

        dots = items(view.grid_canvas, "oval")

        assert expected > 0
        assert len(dots) == expected

    def test_the_dots_use_the_color_of_the_area(
        self, view: CalendarView, service: HabitService
    ) -> None:
        colors = {area.color for area in service.areas()}

        used = {str(view.grid_canvas.itemcget(i, "fill")) for i in items(view.grid_canvas, "oval")}

        assert used <= colors

    def test_today_is_lit_in_lilac_and_only_today(self, view: CalendarView) -> None:
        canvas = view.grid_canvas

        lit = [
            i for i in items(canvas, "polygon") if canvas.itemcget(i, "outline") == palette.LILAC
        ]

        assert len(lit) == 1
        assert canvas.itemcget(lit[0], "fill") == palette.LILAC_SOFT

    def test_past_days_have_a_faint_border_and_future_days_none(self, view: CalendarView) -> None:
        canvas = view.grid_canvas
        outlines = [str(canvas.itemcget(i, "outline")) for i in items(canvas, "polygon")]

        # Oct 1-28 are past, the 29th is today, Oct 30-31 are future.
        assert outlines.count(palette.CELL_BORDER) == 28
        assert outlines.count("") == 2

    def test_a_cell_is_74_by_52_pixels(self, view: CalendarView) -> None:
        canvas = view.grid_canvas
        today_cell = next(
            i for i in items(canvas, "polygon") if canvas.itemcget(i, "outline") == palette.LILAC
        )
        x1, y1, x2, y2 = canvas.bbox(today_cell)

        assert (CELL_WIDTH, CELL_HEIGHT) == (74, 52)
        assert x2 - x1 >= CELL_WIDTH - 4  # the lilac ring is inset by one pixel
        assert y2 - y1 >= CELL_HEIGHT - 4

    def test_the_grid_is_as_wide_as_the_content(self, view: CalendarView) -> None:
        assert int(view.grid_canvas["width"]) == CONTENT_WIDTH == 548


class TestLegend:
    def test_the_categories_legend_fits_inside_the_width_of_the_tab(
        self, view: CalendarView, service: HabitService
    ) -> None:
        legend = view.legend_canvas

        left, _, right, _ = bounds(legend)

        assert left >= 0
        assert right <= CONTENT_WIDTH
        assert int(legend["height"]) >= 44  # eight areas take at least two rows

    def test_every_area_is_listed_once_and_in_order(
        self, view: CalendarView, service: HabitService
    ) -> None:
        assert Tree.texts(view.legend_canvas) == [area.name for area in service.areas()]


class TestImportantDates:
    def go_to_november(self, view: CalendarView) -> None:
        view.next_month()

    def test_a_month_without_dates_shows_no_card(self, view: CalendarView) -> None:
        assert view.dates_canvas.winfo_manager() == ""

    def test_a_month_with_dates_lists_each_one_under_a_heading(self, view: CalendarView) -> None:
        self.go_to_november(view)

        assert view.dates_canvas.winfo_manager() == "pack"
        assert Tree.texts(view.dates_canvas) == [
            "FECHAS DEL MES",
            "03",
            " — Entrega del informe",
            "10",
            " — Examen de inglés",
            "20",
            " — Viaje de fin de semana",
        ]

    def test_the_card_is_as_tall_as_its_lines(self, view: CalendarView) -> None:
        self.go_to_november(view)

        assert int(view.dates_canvas["height"]) == 14 + 20 + 24 * 3 + 14

    def test_going_to_a_month_without_dates_hides_the_card_again(self, view: CalendarView) -> None:
        self.go_to_november(view)
        view.next_month()  # December

        assert view.dates_canvas.winfo_manager() == ""

    def test_the_days_with_a_date_get_a_pink_flag_in_the_grid_and_in_the_card(
        self, view: CalendarView
    ) -> None:
        self.go_to_november(view)

        def flags(canvas: tk.Canvas) -> int:
            return sum(
                1 for i in items(canvas, "polygon") if canvas.itemcget(i, "fill") == palette.FLAG
            )

        assert flags(view.grid_canvas) == 3
        assert flags(view.dates_canvas) == 3

    def test_a_title_that_is_too_long_is_cut_with_an_ellipsis(
        self, make_view: Callable[[HabitService], CalendarView], service: HabitService
    ) -> None:
        service.add_important_date(date(2026, 10, 30), "Una reunión con un título " * 8)
        view = make_view(service)

        title = Tree.texts(view.dates_canvas)[2]
        item = next(
            i
            for i in items(view.dates_canvas, "text")
            if view.dates_canvas.itemcget(i, "text") == title
        )

        assert title.endswith("…")
        assert bounds_of(view.dates_canvas, item)[2] <= CONTENT_WIDTH - 18

    def test_dates_that_were_added_later_show_up_on_refresh(
        self, view: CalendarView, service: HabitService
    ) -> None:
        service.add_important_date(date(2026, 10, 31), "Fiesta")

        view.refresh()

        assert view.dates_canvas.winfo_manager() == "pack"
        assert " — Fiesta" in Tree.texts(view.dates_canvas)

    def test_a_removed_date_disappears(self, view: CalendarView, service: HabitService) -> None:
        item = ImportantDate(date(2026, 10, 31), "Fiesta")
        service.add_important_date(item.day, item.title)
        view.refresh()

        service.remove_important_date(item)
        view.refresh()

        assert view.dates_canvas.winfo_manager() == ""


def bounds_of(canvas: tk.Canvas, item: int) -> tuple[int, int, int, int]:
    box = canvas.bbox(item)
    assert box is not None
    return box
