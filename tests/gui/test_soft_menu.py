import tkinter as tk
from collections.abc import Callable
from typing import cast

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.widgets.global_clicks import click_dispatcher
from habit_tracker.ui.widgets.soft_menu import SoftMenu, menu_manager

OPTIONS = ["uno", "dos", "tres", "cuatro"]


def rows_of(menu: SoftMenu) -> list[tk.Canvas]:
    """The option rows inside the open list (popup > border frame > rows frame)."""
    assert menu.popup is not None
    border = menu.popup.winfo_children()[0]
    return [
        row for row in border.winfo_children()[0].winfo_children() if isinstance(row, tk.Canvas)
    ]


def field_outline(menu: SoftMenu) -> str:
    return str(menu.itemcget(menu.find_all()[0], "outline"))


def show_popup(menu: SoftMenu) -> None:
    """Maps the (transparent) list so it is viewable and receives events."""
    assert menu.popup is not None
    menu.popup.attributes("-alpha", 0.0)
    menu.popup.update()
    assert menu.popup.winfo_viewable()


class TestSelection:
    def test_current_reads_and_changes_the_chosen_index(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        assert menu.current() == 0
        menu.current(2)
        assert menu.current() == 2
        text = next(i for i in menu.find_all() if menu.type(i) == "text")
        assert menu.itemcget(text, "text") == "tres"

    def test_a_menu_without_options_has_nothing_chosen(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, [])
        assert menu.current() == -1
        menu.toggle()
        assert menu.popup is None

    def test_choosing_an_option_changes_it_closes_the_list_and_notifies(
        self, tk_root: tk.Tk
    ) -> None:
        chosen: list[int] = []
        menu = SoftMenu(tk_root, OPTIONS, command=lambda: chosen.append(menu.current()))
        menu.current(2)
        menu.open()
        assert len(rows_of(menu)) == 4  # a row per option
        menu.select(3)
        assert menu.current() == 3
        assert menu.popup is None
        assert chosen == [3]

    def test_closing_without_choosing_does_not_notify(self, tk_root: tk.Tk) -> None:
        chosen: list[int] = []
        menu = SoftMenu(tk_root, OPTIONS, command=lambda: chosen.append(menu.current()))
        menu.open()
        menu.close()
        assert chosen == []
        assert menu.current() == 0

    def test_a_real_click_on_a_row_chooses_it(self, window: tk.Toplevel) -> None:
        chosen: list[int] = []
        menu = SoftMenu(window, OPTIONS, command=lambda: chosen.append(menu.current()))
        menu.pack()
        window.update()
        menu.open()
        show_popup(menu)
        rows_of(menu)[1].event_generate("<Button-1>", x=5, y=5)
        assert chosen == [1]
        assert menu.popup is None


class TestField:
    def test_arrow_and_border_show_whether_the_list_is_open(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        assert field_outline(menu) == palette.BORDER

        def arrow_points_down() -> bool:
            arrow = menu.find_all()[-1]
            coords = menu.coords(arrow)
            return coords[3] > coords[1]  # the middle point is lower than the ends

        assert arrow_points_down()
        menu.open()
        assert field_outline(menu) == palette.LILAC
        assert not arrow_points_down()
        menu.close()
        assert field_outline(menu) == palette.BORDER
        assert arrow_points_down()

    def test_dots_show_the_color_of_each_option(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS, dots=["#111111", "#222222", "#333333", "#444444"])
        menu.current(1)
        dot = next(i for i in menu.find_all() if menu.type(i) == "oval")
        assert menu.itemcget(dot, "fill") == "#222222"
        menu.open()
        fills = [
            row.itemcget(item, "fill")
            for row in rows_of(menu)
            for item in row.find_all()
            if row.type(item) == "oval"
        ]
        assert fills == ["#111111", "#222222", "#333333", "#444444"]

    def test_the_chosen_row_is_bold_with_a_tick(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        menu.current(2)
        menu.open()
        for index, row in enumerate(rows_of(menu)):
            kinds = [row.type(item) for item in row.find_all()]
            assert ("line" in kinds) == (index == 2)


class TestClosing:
    def test_a_click_outside_closes_without_choosing_and_inside_does_not(
        self, tk_root: tk.Tk, fake_event: Callable[..., object]
    ) -> None:
        # Regression: open, click outside without choosing anything, and the list stuck.
        menu = SoftMenu(tk_root, ["uno", "dos", "tres"])
        menu.current(1)
        menu.open()

        def click_on(widget: object) -> None:
            menu.handle_click(cast("tk.Event[tk.Misc]", fake_event(widget)))

        click_on(rows_of(menu)[0])  # inside the list
        click_on(menu)  # on the field itself, which toggles by its own binding
        click_on(menu.popup)
        assert menu.popup is not None
        click_on(tk_root)  # outside
        assert menu.popup is None
        assert menu.current() == 1

    def test_a_real_click_elsewhere_in_the_window_closes_the_list(
        self, window: tk.Toplevel
    ) -> None:
        menu = SoftMenu(window, OPTIONS)
        elsewhere = tk.Canvas(window, width=30, height=30)
        menu.pack()
        elsewhere.pack()
        window.update()
        menu.open()
        elsewhere.event_generate("<Button-1>", x=2, y=2)
        assert menu.popup is None

    def test_after_opening_and_closing_without_choosing_the_menu_works_again(
        self, window: tk.Toplevel
    ) -> None:
        menu = SoftMenu(window, OPTIONS)
        elsewhere = tk.Canvas(window, width=30, height=30)
        menu.pack()
        elsewhere.pack()
        window.update()
        for _ in range(3):
            menu.open()
            assert menu.popup is not None
            elsewhere.event_generate("<Button-1>", x=2, y=2)
            assert menu.popup is None
        assert len(click_dispatcher(window)) == 0

    def test_toggle_closes_a_visible_list(self, window: tk.Toplevel) -> None:
        menu = SoftMenu(window, OPTIONS)
        menu.pack()
        window.update()
        menu.toggle()
        assert menu.popup is not None
        show_popup(menu)
        menu.toggle()
        assert menu.popup is None

    def test_toggle_recovers_when_the_system_hid_the_list(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, ["uno", "dos", "tres"])
        menu.open()
        hidden = menu.popup
        assert hidden is not None
        assert not hidden.winfo_viewable()  # never mapped: the list is not on screen
        menu.toggle()  # one click: clears the leftover and opens again
        assert menu.popup is not None
        assert menu.popup is not hidden
        assert not hidden.winfo_exists()  # no ghost list stays alive

    def test_only_one_list_is_open_at_a_time(self, tk_root: tk.Tk) -> None:
        chosen: list[str] = []
        first = SoftMenu(tk_root, ["a", "b"], command=lambda: chosen.append("first"))
        second = SoftMenu(tk_root, ["x", "y"])
        first.open()
        first.close()
        assert chosen == []
        first.open()
        second.open()
        assert first.popup is None
        assert second.popup is not None
        assert menu_manager(tk_root).open_menu is second
        second.close()
        assert menu_manager(tk_root).open_menu is None
        first.open()
        first.select(1)
        assert chosen == ["first"]

    def test_opening_twice_does_not_leave_a_ghost_list(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        menu.open()
        first = menu.popup
        menu.open()
        assert first is not None
        assert not first.winfo_exists()
        assert menu.popup is not first

    def test_destroying_the_menu_while_open_leaves_no_listener(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        menu.open()
        assert len(click_dispatcher(tk_root)) == 1
        menu.destroy()
        assert len(click_dispatcher(tk_root)) == 0
        assert menu_manager(tk_root).open_menu is None


class TestOwnerDialog:
    def test_escape_closes_the_list_and_keeps_the_dialogs_own_shortcut(
        self, window: tk.Toplevel
    ) -> None:
        calls: list[str] = []
        window.bind("<Escape>", lambda _event: calls.append("dialog"))
        menu = SoftMenu(window, OPTIONS)
        menu.pack()
        menu.open()
        window.focus_force()
        window.update()
        if window.focus_get() is None:
            pytest.skip("keyboard focus cannot be given to a window in this environment")
        window.event_generate("<Escape>")
        assert menu.popup is None
        assert calls == ["dialog"]
        window.event_generate("<Escape>")  # the dialog's shortcut survived the list
        assert calls == ["dialog", "dialog"]

    def test_closing_removes_only_the_escape_binding_the_list_added(
        self, window: tk.Toplevel
    ) -> None:
        window.bind("<Escape>", lambda _event: None)
        menu = SoftMenu(window, OPTIONS)

        def escape_lines() -> list[str]:
            return [line for line in window.bind("<Escape>").splitlines() if line.strip()]

        before = escape_lines()
        assert len(before) == 1
        menu.open()
        assert len(escape_lines()) == 2  # the list added its own shortcut
        menu.close()
        assert escape_lines() == before  # and removed only that one

    def test_the_owner_lends_its_modal_and_gets_it_back(self, window: tk.Toplevel) -> None:
        menu = SoftMenu(window, OPTIONS)
        menu.pack()
        window.update()
        window.grab_set()
        try:
            assert str(window.grab_current()) == str(window)
            menu.open()
            assert window.grab_current() is None  # a grab would swallow the outside clicks
            menu.close()
            assert str(window.grab_current()) == str(window)
        finally:
            window.grab_release()

    def test_a_dialog_that_was_not_modal_is_not_made_modal(self, window: tk.Toplevel) -> None:
        menu = SoftMenu(window, OPTIONS)
        menu.pack()
        window.update()
        assert window.grab_current() is None
        menu.open()
        menu.close()
        assert window.grab_current() is None
