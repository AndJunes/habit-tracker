import tkinter as tk
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.cursors import DEFAULT_CURSOR, pointer_cursor
from habit_tracker.ui.widgets.date_picker import (
    CELL_GAP,
    CELL_HEIGHT,
    HEADER_HEIGHT,
    DatePicker,
)
from habit_tracker.ui.widgets.soft_button import SoftButton

TODAY = date(2026, 10, 29)
PREVIOUS_ARROW = "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}"
NEXT_ARROW = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"


def nov(day: int) -> date:
    return date(2026, 11, day)


def chip_texts(picker: DatePicker) -> list[str]:
    """The labels of the chips under the grid, in the order they are laid out."""
    return [
        chip.text for chip in picker.chips_frame.winfo_children() if isinstance(chip, SoftButton)
    ]


def chip_colors(picker: DatePicker) -> list[tuple[str, str]]:
    return [
        (chip.background, chip.text_color)
        for chip in picker.chips_frame.winfo_children()
        if isinstance(chip, SoftButton)
    ]


def drawn_days(picker: DatePicker) -> set[int]:
    """The day numbers painted on the grid."""
    canvas = picker.canvas
    texts = (
        str(canvas.itemcget(item, "text"))
        for item in canvas.find_all()
        if canvas.type(item) == "text"
    )
    return {int(text) for text in texts if text.isdigit()}


def cell_of(picker: DatePicker, number: int) -> tuple[str | None, str, str]:
    """``(fill, outline, number color)`` of a day's cell; the fill is ``None`` when it has none."""
    canvas = picker.canvas
    items = canvas.find_all()
    for index, item in enumerate(items):
        if canvas.type(item) == "text" and str(canvas.itemcget(item, "text")) == str(number):
            before = items[index - 1]
            has_cell = canvas.type(before) == "polygon"
            return (
                str(canvas.itemcget(before, "fill")) if has_cell else None,
                str(canvas.itemcget(before, "outline")) if has_cell else "",
                str(canvas.itemcget(item, "fill")),
            )
    raise AssertionError(f"day {number} is not drawn")


def month_title(picker: DatePicker) -> str:
    labels = [w for w in picker.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]
    return str(labels[0].cget("text"))


def make_picker(master: tk.Misc, **options: Any) -> DatePicker:
    options.setdefault("today", TODAY)
    return DatePicker(master, **options)


class TestSelection:
    def test_it_picks_drops_and_never_duplicates(self, tk_root: tk.Tk) -> None:
        changes: list[int] = []
        picker = make_picker(tk_root, selection=[nov(5)], on_change=lambda: changes.append(1))
        assert (picker.year, picker.month) == (2026, 11)  # it opens on the month of what is picked
        picker.toggle(nov(12))
        picker.toggle(nov(12))  # a second click drops it
        picker.toggle(nov(27))
        picker.toggle(nov(5))
        assert picker.dates() == [nov(27)]
        assert len(changes) == 4
        picker.toggle(nov(3))
        assert picker.dates() == [nov(3), nov(27)]  # always oldest first
        assert chip_texts(picker) == ["3 nov  ✕", "27 nov  ✕", "Quitar todas"]
        picker.remove(nov(3))
        picker.clear()
        assert picker.dates() == []
        assert picker.chips_frame.winfo_children() == []

    def test_dropping_what_is_not_picked_changes_nothing_and_says_nothing(
        self, tk_root: tk.Tk
    ) -> None:
        changes: list[int] = []
        picker = make_picker(tk_root, on_change=lambda: changes.append(1))
        picker.remove(nov(5))
        picker.clear()
        assert changes == []

    def test_a_single_chip_has_no_remove_all_shortcut(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[nov(5)])
        assert chip_texts(picker) == ["5 nov  ✕"]

    def test_a_chip_drops_its_own_date(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[nov(5), nov(9)])
        first = picker.chips_frame.winfo_children()[0]
        assert isinstance(first, SoftButton)
        first.command()
        assert picker.dates() == [nov(9)]

    def test_remove_all_clears_the_selection(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[nov(5), nov(9), nov(11)])
        everything = picker.chips_frame.winfo_children()[-1]
        assert isinstance(everything, SoftButton)
        everything.command()
        assert picker.dates() == []

    def test_chips_wrap_after_five_to_a_row(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[nov(day) for day in range(1, 8)])
        rows = {
            int(chip.grid_info()["row"])
            for chip in picker.chips_frame.winfo_children()
            if isinstance(chip, SoftButton)
        }
        assert rows == {0, 1}

    def test_the_selection_can_be_replaced_from_outside(self, tk_root: tk.Tk) -> None:
        changes: list[int] = []
        picker = make_picker(tk_root, selection=[nov(5)], on_change=lambda: changes.append(1))
        picker.set_selection([nov(9), nov(2)])
        assert picker.dates() == [nov(2), nov(9)]
        assert chip_texts(picker) == ["2 nov  ✕", "9 nov  ✕", "Quitar todas"]
        assert changes == []  # the owner made the change, so it is not told about it


class TestLimits:
    def test_days_outside_the_period_cannot_be_picked(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, minimum=nov(10), maximum=nov(25))
        picker.toggle(nov(9))
        picker.toggle(nov(26))
        assert picker.dates() == []
        picker.toggle(nov(10))
        picker.toggle(nov(25))
        assert picker.dates() == [nov(10), nov(25)]  # the borders belong to the period

    def test_moving_the_limits_flags_what_falls_outside_without_dropping_it(
        self, tk_root: tk.Tk
    ) -> None:
        picker = make_picker(tk_root, minimum=nov(10), maximum=nov(25))
        picker.toggle(nov(10))
        picker.toggle(nov(25))
        picker.set_limits(nov(12), nov(25))  # the start moved: one date is left outside
        assert picker.out_of_range_dates() == [nov(10)]
        assert picker.dates() == [nov(10), nov(25)]  # nothing is dropped silently
        assert not picker.in_range(nov(10))
        assert picker.in_range(nov(12))

    def test_without_limits_every_day_is_in_range(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root)
        assert picker.in_range(date(1999, 1, 1))
        assert picker.in_range(date(2100, 12, 31))

    def test_dimmed_days_have_no_cell_and_a_faint_number(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[nov(15)], minimum=nov(10), maximum=nov(20))
        assert cell_of(picker, 5) == (None, "", palette.NUMBER_FUTURE)
        assert cell_of(picker, 25) == (None, "", palette.NUMBER_FUTURE)
        assert cell_of(picker, 12) == (palette.ROW_BACKGROUND, "", palette.INK)

    def test_picked_days_are_lilac_inside_the_period_and_pink_outside(
        self, tk_root: tk.Tk
    ) -> None:
        picker = make_picker(
            tk_root, selection=[nov(5), nov(15)], minimum=nov(10), maximum=nov(20)
        )
        assert cell_of(picker, 15) == (palette.LILAC, "", palette.WHITE)
        assert cell_of(picker, 5) == (palette.TRASH_ACTIVE, "", palette.WHITE)
        assert chip_colors(picker)[0] == (palette.TRASH_ACTIVE_BACKGROUND, palette.TRASH_ACTIVE)
        assert chip_colors(picker)[1] == (palette.LILAC_SOFT, palette.INK_TITLE)

    def test_the_month_that_opens_is_today_moved_into_the_period(self, tk_root: tk.Tk) -> None:
        assert (make_picker(tk_root).year, make_picker(tk_root).month) == (2026, 10)
        after = make_picker(tk_root, minimum=nov(10))
        assert (after.year, after.month) == (2026, 11)
        before = make_picker(tk_root, maximum=date(2026, 9, 15))
        assert (before.year, before.month) == (2026, 9)

    def test_the_month_that_opens_is_the_first_picked_date_not_today(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[date(2027, 3, 4), date(2027, 1, 9)])
        assert (picker.year, picker.month) == (2027, 1)


class TestNavigation:
    def test_it_moves_between_months_and_across_years(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[date(2026, 12, 20)])
        picker.next_month()
        assert (picker.year, picker.month) == (2027, 1)
        picker.previous_month()
        picker.previous_month()
        assert (picker.year, picker.month) == (2026, 11)
        picker.year, picker.month = 2027, 1
        picker.previous_month()
        assert (picker.year, picker.month) == (2026, 12)

    def test_the_title_names_the_visible_month(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[date(2026, 12, 20)])
        assert month_title(picker) == "diciembre 2026"
        picker.next_month()
        assert month_title(picker) == "enero 2027"

    def test_the_arrow_buttons_move_the_month(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[nov(5)])
        arrows = [
            w for w in picker.winfo_children()[0].winfo_children() if isinstance(w, SoftButton)
        ]
        assert [arrow.text for arrow in arrows] == [PREVIOUS_ARROW, NEXT_ARROW]
        arrows[1].command()
        assert (picker.year, picker.month) == (2026, 12)
        arrows[0].command()
        arrows[0].command()
        assert (picker.year, picker.month) == (2026, 10)

    @pytest.mark.parametrize(
        ("year", "days"), [(2028, 29), (2026, 28), (2100, 28), (2000, 29), (2024, 29)]
    )
    def test_february_has_twenty_nine_days_only_in_leap_years(
        self, tk_root: tk.Tk, year: int, days: int
    ) -> None:
        picker = make_picker(tk_root, selection=[date(year, 2, 1)])
        assert drawn_days(picker) == set(range(1, days + 1))

    @pytest.mark.parametrize(("month", "days"), [(1, 31), (4, 30), (12, 31), (9, 30)])
    def test_every_month_draws_its_own_number_of_days(
        self, tk_root: tk.Tk, month: int, days: int
    ) -> None:
        picker = make_picker(tk_root, selection=[date(2026, month, 1)])
        assert drawn_days(picker) == set(range(1, days + 1))

    def test_the_last_day_of_the_year_can_be_picked_and_dropped(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, selection=[date(2026, 12, 31)])
        picker.toggle(date(2026, 12, 31))
        assert picker.dates() == []

    def test_today_has_a_lilac_outline_until_it_is_picked(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root)  # opens in October 2026
        assert cell_of(picker, 29) == (palette.ROW_BACKGROUND, palette.LILAC, palette.INK)
        picker.toggle(TODAY)
        assert cell_of(picker, 29) == (palette.LILAC, "", palette.WHITE)


class TestPointer:
    @staticmethod
    def center(picker: DatePicker, row: int, column: int) -> tuple[float, float]:
        width = picker.cell_width
        return (
            column * (width + CELL_GAP) + width / 2,
            HEADER_HEIGHT + row * (CELL_HEIGHT + CELL_GAP) + CELL_HEIGHT / 2,
        )

    def test_positions_map_to_days_and_the_air_between_cells_maps_to_nothing(
        self, tk_root: tk.Tk
    ) -> None:
        picker = make_picker(tk_root, selection=[nov(1)])  # November 2026 starts on a Sunday
        assert picker.day_at(*self.center(picker, 0, 6)) == 1
        assert picker.day_at(*self.center(picker, 1, 0)) == 2
        assert picker.day_at(*self.center(picker, 0, 0)) is None  # a blank cell of October
        assert (
            picker.day_at(picker.cell_width + 2, self.center(picker, 1, 0)[1]) is None
        )  # the air
        assert picker.day_at(self.center(picker, 1, 0)[0], 5) is None  # the weekday names
        assert picker.day_at(-1, 50) is None
        assert picker.day_at(picker.cell_width * 7 + 6 * CELL_GAP + 1, 50) is None

    def test_real_clicks_hit_the_right_cell(self, window: tk.Toplevel) -> None:
        picker = make_picker(window, selection=[nov(1)])
        picker.clear()
        picker.pack()
        window.update()
        x, y = self.center(picker, 0, 6)  # Sunday the 1st
        picker.canvas.event_generate("<Button-1>", x=int(x), y=int(y))
        x, y = self.center(picker, 1, 0)  # Monday the 2nd
        picker.canvas.event_generate("<Button-1>", x=int(x), y=int(y))
        assert picker.dates() == [nov(1), nov(2)]
        x, y = self.center(picker, 0, 0)  # a blank cell
        picker.canvas.event_generate("<Button-1>", x=int(x), y=int(y))
        assert picker.dates() == [nov(1), nov(2)]

    def test_the_pointer_lights_up_the_cell_under_it_and_only_if_it_can_be_clicked(
        self, window: tk.Toplevel
    ) -> None:
        picker = make_picker(window, selection=[nov(5)], minimum=nov(5))
        picker.pack()
        window.update()
        x, y = self.center(picker, 2, 3)  # third row, Thursday
        picker.canvas.event_generate("<Motion>", x=int(x), y=int(y))
        assert picker.hovered_day == 12
        assert cell_of(picker, 12) == (palette.LILAC_SOFT, "", palette.INK_TITLE)
        assert str(picker.canvas.cget("cursor")) == pointer_cursor(picker.canvas)
        x, y = self.center(picker, 0, 3)  # Wednesday the 4th is before the period
        picker.canvas.event_generate("<Motion>", x=int(x), y=int(y))
        assert picker.hovered_day is None
        assert str(picker.canvas.cget("cursor")) == DEFAULT_CURSOR
        picker.canvas.event_generate("<Motion>", x=int(self.center(picker, 2, 3)[0]), y=int(y))
        picker.canvas.event_generate("<Leave>")
        assert picker.hovered_day is None


class TestSingleMode:
    def test_a_new_pick_replaces_the_old_one_and_picking_it_again_drops_it(
        self, tk_root: tk.Tk
    ) -> None:
        picker = make_picker(tk_root, mode="single", selection=[date(2026, 12, 1)])
        picker.toggle(date(2026, 12, 15))
        assert picker.dates() == [date(2026, 12, 15)]  # it replaces, it does not accumulate
        picker.toggle(date(2026, 12, 15))
        assert picker.dates() == []

    def test_it_shows_no_chips(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, mode="single", selection=[nov(5)])
        assert picker.chips_frame.winfo_manager() == ""
        assert chip_texts(picker) == []

    def test_it_reports_each_change(self, tk_root: tk.Tk) -> None:
        picks: list[list[date]] = []
        holder: list[DatePicker] = []

        def changed() -> None:
            picks.append(holder[0].dates())

        picker = make_picker(tk_root, mode="single", on_change=changed)
        holder.append(picker)
        picker.toggle(nov(3))
        picker.toggle(nov(4))
        picker.toggle(nov(4))
        assert picks == [[nov(3)], [nov(4)], []]

    def test_the_callback_can_be_set_after_creation(self, tk_root: tk.Tk) -> None:
        calls: list[Callable[[], object]] = []
        picker = make_picker(tk_root, mode="single")
        picker.on_change = lambda: calls.append(picker.dates)
        picker.toggle(nov(3))
        assert len(calls) == 1
