import tkinter as tk
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.cursors import DEFAULT_CURSOR, pointer_cursor
from habit_tracker.ui.theme.focus import ACTIVATION_KEYS
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


# ---------- Keyboard ----------


def reachable_with_tab(widget: tk.Misc) -> bool:
    return str(widget.cget("takefocus")).lower() in ("1", "true")


def ring_day(picker: DatePicker) -> int | None:
    """The day number (of the visible month) that carries the focus ring, or ``None``."""
    canvas = picker.canvas
    rings = [
        item
        for item in canvas.find_all()
        if canvas.type(item) == "polygon"
        and str(canvas.itemcget(item, "outline")) == palette.FOCUS_RING
    ]
    assert len(rings) <= 1
    if not rings:
        return None
    coords = canvas.coords(rings[0])
    xs, ys = coords[0::2], coords[1::2]
    return picker.day_at((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def give_focus_or_skip(window: tk.Toplevel, widget: tk.Misc) -> None:
    """Gives ``widget`` the real keyboard focus, or skips the test saying why it could not."""
    window.update()
    widget.focus_force()
    window.update()
    if window.focus_get() is not widget:
        pytest.skip("the window did not get the keyboard focus")


def gain_focus(picker: DatePicker) -> None:
    """Simulates the focus arriving on the grid, which is enough for what it draws."""
    picker.canvas.event_generate("<FocusIn>")


def chip_buttons(picker: DatePicker) -> list[SoftButton]:
    return [w for w in picker.chips_frame.winfo_children() if isinstance(w, SoftButton)]


class TestKeyboardCursor:
    def test_the_month_buttons_the_grid_and_the_chips_are_reachable_with_tab_in_visual_order(
        self, tk_root: tk.Tk
    ) -> None:
        picker = make_picker(tk_root, selection=[nov(5), nov(9)])
        navigation, grid, chips = picker.winfo_children()
        assert grid is picker.canvas
        assert chips is picker.chips_frame
        arrows = [w for w in navigation.winfo_children() if isinstance(w, SoftButton)]
        assert len(arrows) == 2
        assert len(chip_buttons(picker)) == 3  # two dates and "Quitar todas"
        assert all(reachable_with_tab(w) for w in (*arrows, grid, *chip_buttons(picker)))

    def test_the_grid_binds_the_arrows_the_page_keys_and_the_activation_keys(
        self, tk_root: tk.Tk
    ) -> None:
        picker = make_picker(tk_root)
        keys = ("<Left>", "<Right>", "<Up>", "<Down>", "<Prior>", "<Next>", *ACTIVATION_KEYS)
        assert all(picker.canvas.bind(key) for key in keys)

    @pytest.mark.parametrize(
        ("options", "expected"),
        [
            pytest.param({}, TODAY, id="today-when-it-can-be-picked"),
            pytest.param({"minimum": nov(10)}, nov(10), id="first-pickable-day-after-today"),
            pytest.param(
                {"maximum": date(2026, 9, 15)}, date(2026, 9, 1), id="first-pickable-day-before"
            ),
            pytest.param(
                {"selection": [date(2027, 3, 4), date(2027, 1, 9)]},
                date(2027, 1, 9),
                id="first-picked-date-of-the-visible-month",
            ),
            pytest.param(
                {"selection": [nov(5)]}, nov(5), id="picked-date-when-today-is-elsewhere"
            ),
            pytest.param(
                {"selection": [nov(5)], "today": nov(20)}, nov(20), id="today-in-the-visible-month"
            ),
        ],
    )
    def test_where_the_cursor_starts(
        self, tk_root: tk.Tk, options: dict[str, Any], expected: date
    ) -> None:
        picker = make_picker(tk_root, **options)
        assert picker.cursor == expected
        assert (picker.year, picker.month) == (expected.year, expected.month)

    def test_days_and_weeks_move_the_cursor_and_the_visible_month_follows(
        self, tk_root: tk.Tk
    ) -> None:
        picker = make_picker(tk_root)  # October 2026, the cursor on the 29th
        picker.move_cursor_days(1)
        assert (picker.cursor, picker.month) == (date(2026, 10, 30), 10)
        picker.move_cursor_days(2)  # past the end of the month
        assert (picker.cursor, picker.year, picker.month) == (nov(1), 2026, 11)
        assert month_title(picker) == "noviembre 2026"
        picker.move_cursor_days(-1)  # and back
        assert (picker.cursor, picker.month) == (date(2026, 10, 31), 10)
        picker.move_cursor_days(7)
        assert (picker.cursor, picker.month) == (nov(7), 11)
        picker.move_cursor_days(-7)
        assert (picker.cursor, picker.month) == (date(2026, 10, 31), 10)

    def test_moving_across_the_end_of_the_year_changes_the_year(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, today=date(2026, 12, 28))
        picker.move_cursor_days(7)
        assert picker.cursor == date(2027, 1, 4)
        assert (picker.year, picker.month) == (2027, 1)
        assert month_title(picker) == "enero 2027"
        picker.move_cursor_days(-7)
        assert (picker.cursor, picker.year, picker.month) == (date(2026, 12, 28), 2026, 12)

    @pytest.mark.parametrize(
        ("start", "months", "expected"),
        [
            pytest.param(date(2026, 10, 29), 1, nov(29), id="next-month"),
            pytest.param(date(2026, 1, 31), 1, date(2026, 2, 28), id="shorter-month"),
            pytest.param(date(2028, 1, 31), 1, date(2028, 2, 29), id="leap-february"),
            pytest.param(date(2026, 12, 15), 1, date(2027, 1, 15), id="into-next-year"),
            pytest.param(date(2027, 1, 15), -1, date(2026, 12, 15), id="into-previous-year"),
            pytest.param(date(2026, 3, 31), -1, date(2026, 2, 28), id="back-to-a-shorter-month"),
        ],
    )
    def test_page_keys_move_a_month_and_clamp_the_day_when_it_does_not_exist(
        self, tk_root: tk.Tk, start: date, months: int, expected: date
    ) -> None:
        picker = make_picker(tk_root, today=start)
        picker.move_cursor_months(months)
        assert picker.cursor == expected
        assert (picker.year, picker.month) == (expected.year, expected.month)

    def test_the_month_buttons_carry_the_cursor_along(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root)  # the cursor is on October 29th
        picker.next_month()
        assert picker.cursor == nov(29)
        picker.previous_month()
        picker.previous_month()
        assert picker.cursor == date(2026, 9, 29)

    def test_the_cursor_may_rest_outside_the_period_but_that_day_cannot_be_picked(
        self, tk_root: tk.Tk
    ) -> None:
        changes: list[int] = []
        picker = make_picker(
            tk_root, today=nov(15), minimum=nov(10), maximum=nov(20),
            on_change=lambda: changes.append(1),
        )  # fmt: skip
        picker.move_cursor_days(-7)
        assert picker.cursor == nov(8)  # before the period
        picker.toggle_cursor()
        picker.move_cursor_days(14)
        assert picker.cursor == nov(22)  # after it
        picker.toggle_cursor()
        assert picker.dates() == []
        assert changes == []
        picker.move_cursor_days(-12)
        picker.toggle_cursor()
        picker.move_cursor_days(10)
        picker.toggle_cursor()
        assert picker.dates() == [nov(10), nov(20)]  # the borders belong to the period
        assert changes == [1, 1]

    def test_toggling_picks_and_drops_the_day_under_the_cursor(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, today=nov(10))
        picker.toggle_cursor()
        picker.move_cursor_days(1)
        picker.toggle_cursor()
        assert picker.dates() == [nov(10), nov(11)]
        picker.move_cursor_days(-1)
        picker.toggle_cursor()
        assert picker.dates() == [nov(11)]

    def test_in_single_mode_toggling_leaves_exactly_one_date(self, tk_root: tk.Tk) -> None:
        picker = make_picker(tk_root, mode="single", today=nov(10), selection=[nov(3)])
        picker.toggle_cursor()
        assert picker.dates() == [nov(10)]  # it replaced the other one
        picker.move_cursor_days(1)
        picker.toggle_cursor()
        assert picker.dates() == [nov(11)]
        picker.toggle_cursor()
        assert picker.dates() == []

    def test_crossing_months_clears_the_hover_but_moving_inside_one_keeps_it(
        self, window: tk.Toplevel
    ) -> None:
        picker = make_picker(window)
        picker.pack()
        window.update()
        x, y = TestPointer.center(picker, 2, 3)
        picker.canvas.event_generate("<Motion>", x=int(x), y=int(y))
        hovered = picker.hovered_day
        assert hovered is not None
        picker.move_cursor_days(1)  # October 30th: the same month
        assert picker.hovered_day == hovered
        picker.move_cursor_days(7)  # November 6th
        assert picker.hovered_day is None


class TestKeyboardRing:
    def test_the_ring_marks_the_cursor_day_only_while_the_grid_has_the_focus(
        self, window: tk.Toplevel
    ) -> None:
        picker = make_picker(window)
        picker.pack()
        window.update()
        assert ring_day(picker) is None
        gain_focus(picker)
        assert ring_day(picker) == 29
        # The cell keeps its own look: the ring is a separate item after the number.
        assert cell_of(picker, 29) == (palette.ROW_BACKGROUND, palette.LILAC, palette.INK)
        picker.canvas.event_generate("<FocusOut>")
        assert ring_day(picker) is None

    def test_the_ring_follows_the_cursor_across_months(self, window: tk.Toplevel) -> None:
        picker = make_picker(window)
        picker.pack()
        window.update()
        gain_focus(picker)
        picker.move_cursor_days(7)
        assert month_title(picker) == "noviembre 2026"
        assert ring_day(picker) == 5

    def test_the_ring_follows_the_month_buttons(self, window: tk.Toplevel) -> None:
        picker = make_picker(window)
        picker.pack()
        window.update()
        gain_focus(picker)
        picker.next_month()
        assert ring_day(picker) == 29
        picker.previous_month()
        picker.previous_month()
        assert (picker.cursor, ring_day(picker)) == (date(2026, 9, 29), 29)

    def test_the_ring_can_mark_a_day_outside_the_period(self, window: tk.Toplevel) -> None:
        picker = make_picker(window, today=nov(15), minimum=nov(10))
        picker.pack()
        window.update()
        gain_focus(picker)
        picker.move_cursor_days(-7)
        assert ring_day(picker) == 8
        assert cell_of(picker, 8) == (None, "", palette.NUMBER_FUTURE)  # still dimmed

    def test_hover_and_ring_are_independent(self, window: tk.Toplevel) -> None:
        picker = make_picker(window)
        picker.pack()
        window.update()
        gain_focus(picker)
        x, y = TestPointer.center(picker, 2, 3)
        picker.canvas.event_generate("<Motion>", x=int(x), y=int(y))
        hovered = picker.day_at(x, y)
        assert hovered is not None
        assert hovered != 29
        assert cell_of(picker, hovered) == (palette.LILAC_SOFT, "", palette.INK_TITLE)
        assert ring_day(picker) == 29

    def test_a_click_moves_the_cursor_to_the_day_without_giving_the_grid_the_focus(
        self, window: tk.Toplevel
    ) -> None:
        picker = make_picker(window, selection=[nov(1)])
        picker.pack()
        window.update()
        assert picker.cursor == nov(1)
        x, y = TestPointer.center(picker, 1, 0)  # Monday the 2nd
        picker.canvas.event_generate("<Button-1>", x=int(x), y=int(y))
        assert picker.cursor == nov(2)
        assert window.focus_get() is not picker.canvas
        assert ring_day(picker) is None

    def test_a_click_on_a_day_outside_the_period_leaves_the_cursor_where_it_was(
        self, window: tk.Toplevel
    ) -> None:
        picker = make_picker(window, today=nov(15), minimum=nov(10))
        picker.pack()
        window.update()
        x, y = TestPointer.center(picker, 1, 2)  # Wednesday the 4th, before the period
        picker.canvas.event_generate("<Button-1>", x=int(x), y=int(y))
        assert picker.cursor == nov(15)
        assert picker.dates() == []


class TestKeyboardFocus:
    def test_removing_a_date_with_the_mouse_does_not_give_the_grid_the_focus(
        self, window: tk.Toplevel
    ) -> None:
        picker = make_picker(window, selection=[nov(5), nov(9)])
        picker.pack()
        window.update()
        chip_buttons(picker)[0].command()  # what a click on its ✕ does
        assert picker.dates() == [nov(9)]
        assert window.focus_get() is not picker.canvas

    def test_removing_a_date_from_its_chip_keeps_the_keyboard_in_the_picker(
        self, window: tk.Toplevel
    ) -> None:
        picker = make_picker(window, selection=[nov(5), nov(9)])
        picker.pack()
        give_focus_or_skip(window, chip_buttons(picker)[0])
        chip_buttons(picker)[0].event_generate("<space>")
        assert picker.dates() == [nov(9)]
        window.update()
        # The chip with the focus was replaced; without this the focus would jump to the top.
        assert window.focus_get() is picker.canvas

    def test_real_keys_move_the_cursor_across_months(self, window: tk.Toplevel) -> None:
        picker = make_picker(window)
        picker.pack()
        give_focus_or_skip(window, picker.canvas)
        canvas = picker.canvas
        canvas.event_generate("<Right>")  # October 30th
        canvas.event_generate("<Down>")  # November 6th
        canvas.event_generate("<Prior>")  # October 6th
        canvas.event_generate("<Next>")  # November 6th
        assert picker.cursor == nov(6)
        canvas.event_generate("<Left>")  # the 5th
        canvas.event_generate("<Up>")  # October 29th
        assert picker.cursor == TODAY
        assert (picker.year, picker.month) == (2026, 10)

    @pytest.mark.parametrize("key", ACTIVATION_KEYS)
    def test_space_and_enter_pick_and_drop_the_day_under_the_cursor(
        self, window: tk.Toplevel, key: str
    ) -> None:
        picker = make_picker(window, today=nov(10))
        picker.pack()
        give_focus_or_skip(window, picker.canvas)
        picker.canvas.event_generate(key)
        assert picker.dates() == [nov(10)]
        picker.canvas.event_generate(key)
        assert picker.dates() == []
