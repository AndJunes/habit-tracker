import tkinter as tk
from collections.abc import Callable
from typing import cast

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.focus import ACTIVATION_KEYS
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


# ---------- Keyboard ----------


def ring_items(menu: SoftMenu) -> list[int]:
    """The focus ring: the polygons outlined in the focus color."""
    return [
        item
        for item in menu.find_all()
        if menu.type(item) == "polygon"
        and str(menu.itemcget(item, "outline")) == palette.FOCUS_RING
    ]


def lit_rows(menu: SoftMenu) -> list[int]:
    """The rows painted with the highlight (the lilac rounded background)."""
    return [
        index
        for index, row in enumerate(rows_of(menu))
        if any(
            row.type(item) == "polygon" and str(row.itemcget(item, "fill")) == palette.LILAC_SOFT
            for item in row.find_all()
        )
    ]


def row_look(row: tk.Canvas) -> list[tuple[str | None, tuple[float, ...], str]]:
    """Everything a row shows: the type, position and fill of each of its items."""
    return [
        (row.type(item), tuple(row.coords(item)), str(row.itemcget(item, "fill")))
        for item in row.find_all()
    ]


def give_focus_or_skip(window: tk.Toplevel, widget: tk.Misc) -> None:
    """Gives ``widget`` the real keyboard focus, or skips the test saying why it could not."""
    window.update()
    widget.focus_force()
    window.update()
    if window.focus_get() is not widget:
        pytest.skip("the window did not get the keyboard focus")


class TestKeyboard:
    """The key handlers are called directly, so these do not depend on the real focus."""

    @staticmethod
    def make(window: tk.Toplevel, command: Callable[[], object] | None = None) -> SoftMenu:
        menu = SoftMenu(window, OPTIONS, command=command)
        menu.pack()
        window.update()
        return menu

    def test_the_field_is_reachable_with_tab(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        assert str(menu.cget("takefocus")).lower() in ("1", "true")

    def test_the_field_binds_the_opening_navigation_and_tab_keys(self, tk_root: tk.Tk) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        keys = (*ACTIVATION_KEYS, "<Down>", "<Up>", "<Home>", "<End>", "<Tab>")
        assert all(menu.bind(key) for key in keys)

    def test_the_ring_shows_only_while_the_keyboard_has_the_focus_closed_or_open(
        self, window: tk.Toplevel
    ) -> None:
        menu = self.make(window)
        assert ring_items(menu) == []
        menu.event_generate("<FocusIn>")
        assert len(ring_items(menu)) == 1
        assert field_outline(menu) == palette.BORDER  # the field is still the first item
        assert menu.type(menu.find_all()[-1]) == "line"  # and the arrow the last
        menu.open()
        assert len(ring_items(menu)) == 1
        assert field_outline(menu) == palette.LILAC
        menu.close()
        assert len(ring_items(menu)) == 1
        menu.event_generate("<FocusOut>")
        assert ring_items(menu) == []
        menu.open()
        assert ring_items(menu) == []

    def test_down_opens_the_list_with_the_chosen_option_highlighted(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        menu.current(2)
        assert menu._on_down(fake_event()) == "break"
        assert menu.popup is not None
        assert menu.highlighted == 2
        assert lit_rows(menu) == [2]

    def test_space_and_enter_open_the_closed_list_the_same_way(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        menu.current(1)
        assert menu._on_confirm(fake_event()) == "break"
        assert menu.popup is not None
        assert (menu.highlighted, lit_rows(menu)) == (1, [1])

    def test_up_down_home_and_end_move_the_highlight_without_wrapping(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        event = fake_event()
        menu._on_down(event)  # opens, highlighting the chosen option (the first)
        show_popup(menu)
        assert menu._on_down(event) == "break"
        menu._on_down(event)
        assert (menu.highlighted, lit_rows(menu)) == (2, [2])
        for _ in range(5):
            menu._on_down(event)
        assert menu.highlighted == 3  # it stops at the last option
        assert menu._on_up(event) == "break"
        assert menu.highlighted == 2
        assert menu._on_home(event) == "break"
        assert menu.highlighted == 0
        assert menu._on_end(event) == "break"
        assert (menu.highlighted, lit_rows(menu)) == (3, [3])
        for _ in range(5):
            menu._on_up(event)
        assert (menu.highlighted, lit_rows(menu)) == (0, [0])  # and at the first

    def test_the_highlight_does_not_change_the_choice_until_it_is_confirmed(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        chosen: list[int] = []
        menu = self.make(window, command=lambda: chosen.append(menu.current()))
        event = fake_event()
        menu._on_down(event)
        show_popup(menu)
        menu._on_down(event)
        menu._on_end(event)
        assert (menu.highlighted, lit_rows(menu)) == (3, [3])
        assert menu.current() == 0
        assert chosen == []
        field_text = next(i for i in menu.find_all() if menu.type(i) == "text")
        assert menu.itemcget(field_text, "text") == "uno"  # the field still shows the choice

    def test_enter_chooses_the_highlighted_option_and_closes_the_list(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        chosen: list[int] = []
        menu = self.make(window, command=lambda: chosen.append(menu.current()))
        event = fake_event()
        menu._on_down(event)
        show_popup(menu)
        menu._on_down(event)
        assert menu._on_confirm(event) == "break"
        assert menu.current() == 1
        assert menu.popup is None
        assert menu.highlighted is None
        assert chosen == [1]

    def test_opening_with_the_mouse_highlights_nothing(self, window: tk.Toplevel) -> None:
        menu = self.make(window)
        menu.current(2)
        menu.open()
        assert menu.highlighted is None
        assert lit_rows(menu) == []

    def test_with_nothing_highlighted_up_and_down_start_from_the_chosen_option(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        event = fake_event()
        menu.current(1)
        menu.open()
        show_popup(menu)
        menu._on_down(event)
        assert menu.highlighted == 2
        menu.close()
        menu.current(2)
        menu.open()
        show_popup(menu)
        menu._on_up(event)
        assert menu.highlighted == 1

    def test_confirming_with_nothing_highlighted_closes_without_choosing(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        chosen: list[int] = []
        menu = self.make(window, command=lambda: chosen.append(menu.current()))
        menu.current(2)
        menu.open()
        show_popup(menu)
        assert menu._on_confirm(fake_event()) == "break"
        assert menu.popup is None
        assert menu.current() == 2
        assert chosen == []

    def test_tab_closes_the_list_without_choosing_and_lets_the_focus_move_on(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        chosen: list[int] = []
        menu = self.make(window, command=lambda: chosen.append(menu.current()))
        event = fake_event()
        menu._on_down(event)
        show_popup(menu)
        menu._on_down(event)
        assert menu._on_tab(event) is None  # not "break": Tk still moves the focus
        assert menu.popup is None
        assert menu.current() == 0
        assert chosen == []
        assert menu._on_tab(event) is None  # with the list closed there is nothing to do

    def test_up_home_and_end_pass_through_when_the_list_is_closed(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        event = fake_event()
        assert menu._on_up(event) is None
        assert menu._on_home(event) is None
        assert menu._on_end(event) is None
        assert menu.popup is None

    def test_the_pointer_and_the_keyboard_share_one_highlight_and_the_last_one_wins(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        event = fake_event()
        menu._on_down(event)
        show_popup(menu)
        rows = rows_of(menu)
        rows[2].event_generate("<Enter>")
        assert (menu.highlighted, lit_rows(menu)) == (2, [2])  # the pointer took over
        menu._on_down(event)
        assert (menu.highlighted, lit_rows(menu)) == (3, [3])  # and the keyboard took it back
        rows[2].event_generate("<Leave>")  # leaving a row that is not marked changes nothing
        assert (menu.highlighted, lit_rows(menu)) == (3, [3])
        rows[3].event_generate("<Leave>")
        assert (menu.highlighted, lit_rows(menu)) == (None, [])

    def test_the_keyboard_highlight_looks_exactly_like_the_hover(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        menu.open()
        show_popup(menu)
        row = rows_of(menu)[1]
        row.event_generate("<Enter>")
        hovered = row_look(row)
        row.event_generate("<Leave>")
        assert row_look(row) != hovered
        menu._on_down(fake_event())  # nothing is marked, so it starts at the first and moves
        assert menu.highlighted == 1
        assert row_look(row) == hovered

    def test_closing_clears_the_highlight(
        self, window: tk.Toplevel, fake_event: Callable[..., object]
    ) -> None:
        menu = self.make(window)
        menu._on_down(fake_event())
        assert menu.highlighted == 0
        menu.close()
        assert menu.highlighted is None
        menu.open()  # reopened with the mouse: nothing carries over
        assert menu.highlighted is None
        assert lit_rows(menu) == []

    def test_a_list_the_system_hid_counts_as_closed_for_the_keys(
        self, tk_root: tk.Tk, fake_event: Callable[..., object]
    ) -> None:
        menu = SoftMenu(tk_root, OPTIONS)
        menu.open()
        hidden = menu.popup
        assert hidden is not None
        assert not hidden.winfo_viewable()  # never mapped: the list is not on screen
        menu._on_down(fake_event())  # one key press: clears the leftover and opens again
        assert menu.popup is not None
        assert menu.popup is not hidden
        assert not hidden.winfo_exists()
        assert menu.highlighted == 0

    def test_escape_with_the_focus_on_the_field_reaches_the_owners_binding(
        self, window: tk.Toplevel
    ) -> None:
        menu = self.make(window)
        menu.open()
        assert str(window) in menu.bindtags()  # a key pressed on the field bubbles up to it
        assert window.bind("<Escape>")  # where the list put its Escape shortcut

    def test_a_click_does_not_give_the_field_the_keyboard_focus(self, window: tk.Toplevel) -> None:
        menu = self.make(window)
        menu.event_generate("<Button-1>", x=3, y=3)
        assert menu.popup is not None  # the click did open the list
        assert window.focus_get() is not menu
        assert ring_items(menu) == []


class TestRealKeys:
    """These send real key events, so they need the window to have the keyboard focus."""

    @staticmethod
    def focused_menu(window: tk.Toplevel, command: Callable[[], object] | None = None) -> SoftMenu:
        menu = SoftMenu(window, OPTIONS, command=command)
        menu.pack()
        give_focus_or_skip(window, menu)
        return menu

    def test_opening_the_list_does_not_move_the_keyboard_focus(self, window: tk.Toplevel) -> None:
        menu = self.focused_menu(window)
        menu.event_generate("<Down>")
        assert menu.popup is not None
        show_popup(menu)
        assert window.focus_get() is menu

    @pytest.mark.parametrize("key", ["<space>", "<Return>"])
    def test_open_move_and_choose_with_the_keyboard(self, window: tk.Toplevel, key: str) -> None:
        chosen: list[int] = []
        menu = self.focused_menu(window, command=lambda: chosen.append(menu.current()))
        menu.event_generate(key)
        assert menu.popup is not None
        show_popup(menu)
        menu.event_generate("<Down>")
        menu.event_generate(key)
        assert chosen == [1]
        assert menu.popup is None

    def test_escape_closes_the_list_without_choosing(self, window: tk.Toplevel) -> None:
        chosen: list[int] = []
        menu = self.focused_menu(window, command=lambda: chosen.append(menu.current()))
        menu.event_generate("<Down>")
        show_popup(menu)
        menu.event_generate("<Down>")
        menu.event_generate("<Escape>")
        assert menu.popup is None
        assert menu.current() == 0
        assert chosen == []

    def test_tab_closes_the_list(self, window: tk.Toplevel) -> None:
        menu = self.focused_menu(window)
        menu.event_generate("<Down>")
        show_popup(menu)
        assert menu.popup is not None
        menu.event_generate("<Tab>")
        assert menu.popup is None
