import tkinter as tk

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.cursors import pointer_cursor
from habit_tracker.ui.theme.drawing import mix_colors
from habit_tracker.ui.theme.focus import ACTIVATION_KEYS, RING_WIDTH
from habit_tracker.ui.theme.fonts import font, measure
from habit_tracker.ui.widgets.soft_button import SoftButton, TrashButton, TrashState


def body_fill(button: tk.Canvas) -> str:
    """Fill of the rounded body, which is the first item drawn."""
    return str(button.itemcget(button.find_all()[0], "fill"))


def body_outline(button: tk.Canvas) -> str:
    return str(button.itemcget(button.find_all()[0], "outline"))


def can_color(button: tk.Canvas) -> str:
    """Color of the trash can (the last item is one of its stripes)."""
    return str(button.itemcget(button.find_all()[-1], "fill"))


def hover(button: tk.Canvas, *, over: bool) -> None:
    button.event_generate("<Enter>" if over else "<Leave>")


class TestSoftButton:
    def test_it_is_as_wide_as_its_text_plus_padding(self, tk_root: tk.Tk) -> None:
        button = SoftButton(tk_root, "Guardar", lambda: None, palette.LILAC, palette.WHITE)
        label_font = font("sans", 12, "bold", master=tk_root)
        assert int(button["width"]) == measure(label_font, "Guardar") + 2 * 18
        assert int(button["height"]) == 38

    def test_explicit_size_and_font_are_respected(self, tk_root: tk.Tk) -> None:
        small = font("sans", 10, "bold", master=tk_root)
        button = SoftButton(
            tk_root, "x", lambda: None, palette.LILAC, palette.WHITE,
            button_font=small, height=26, width=80, parent_background=palette.PEACH_BACKGROUND,
        )  # fmt: skip
        assert (int(button["width"]), int(button["height"])) == (80, 26)
        assert button.cget("bg") == palette.PEACH_BACKGROUND
        text = next(i for i in button.find_all() if button.type(i) == "text")
        assert button.itemcget(text, "text") == "x"

    def test_a_click_calls_the_command(self, window: tk.Toplevel) -> None:
        clicks: list[str] = []
        button = SoftButton(
            window, "Ok", lambda: clicks.append("ok"), palette.LILAC, palette.WHITE
        )
        button.pack()
        window.update()
        button.event_generate("<Button-1>", x=3, y=3)
        assert clicks == ["ok"]
        assert str(button.cget("cursor")) == pointer_cursor(button)

    def test_it_darkens_under_the_pointer_and_recovers(self, window: tk.Toplevel) -> None:
        button = SoftButton(window, "Ok", lambda: None, palette.LILAC, palette.WHITE)
        button.pack()
        window.update()
        assert body_fill(button) == palette.LILAC
        hover(button, over=True)
        assert body_fill(button) == mix_colors(palette.LILAC, palette.BLACK, 0.05)
        hover(button, over=False)
        assert body_fill(button) == palette.LILAC

    def test_a_disabled_button_is_drawn_but_has_no_click_hover_or_pointer(
        self, window: tk.Toplevel
    ) -> None:
        clicks: list[str] = []
        button = SoftButton(
            window, "Ok", lambda: clicks.append("ok"), palette.TRASH_INACTIVE, palette.WHITE,
            enabled=False,
        )  # fmt: skip
        button.pack()
        window.update()
        assert button.find_all()
        assert not button.bind("<Button-1>")
        assert not button.bind("<Enter>")
        assert str(button.cget("cursor")) == "arrow"
        button.event_generate("<Button-1>", x=3, y=3)
        hover(button, over=True)
        assert clicks == []
        assert body_fill(button) == palette.TRASH_INACTIVE


class TestTrashButton:
    @pytest.fixture
    def trash(self, window: tk.Toplevel) -> tuple[TrashButton, list[str]]:
        clicks: list[str] = []
        button = TrashButton(window, lambda: clicks.append("click"))
        button.pack()
        window.update()
        return button, clicks

    def test_at_rest_it_is_barely_hinted(self, trash: tuple[TrashButton, list[str]]) -> None:
        button, _ = trash
        assert button.state == "normal"
        assert (body_fill(button), body_outline(button)) == (palette.WHITE, palette.BORDER)
        assert can_color(button) == palette.TRASH_REST
        assert str(button.cget("cursor")) == pointer_cursor(button)

    def test_under_the_pointer_it_lights_up_and_recovers(
        self, trash: tuple[TrashButton, list[str]]
    ) -> None:
        button, _ = trash
        hover(button, over=True)
        assert body_fill(button) == palette.TRASH_HOVER_BACKGROUND
        assert body_outline(button) == can_color(button) == palette.TRASH_ACTIVE
        hover(button, over=False)
        assert body_fill(button) == palette.WHITE

    def test_active_is_filled_pink_with_a_white_can_and_darker_under_the_pointer(
        self, trash: tuple[TrashButton, list[str]]
    ) -> None:
        button, _ = trash
        button.set_state("active")
        assert button.state == "active"
        assert body_fill(button) == palette.TRASH_ACTIVE
        assert body_outline(button) == ""
        assert can_color(button) == palette.WHITE
        hover(button, over=True)
        assert body_fill(button) == mix_colors(palette.TRASH_ACTIVE, palette.BLACK, 0.07)

    def test_inactive_is_muted_without_pointer_and_ignores_hover(
        self, trash: tuple[TrashButton, list[str]]
    ) -> None:
        button, _ = trash
        button.set_state("inactive")
        assert (body_fill(button), body_outline(button)) == (palette.WHITE, palette.CELL_BORDER)
        assert can_color(button) == palette.TRASH_INACTIVE
        assert str(button.cget("cursor")) == "arrow"
        hover(button, over=True)
        assert can_color(button) == palette.TRASH_INACTIVE

    @pytest.mark.parametrize(("state", "calls"), [("normal", 1), ("active", 1), ("inactive", 0)])
    def test_the_click_only_reaches_the_command_when_not_inactive(
        self, trash: tuple[TrashButton, list[str]], state: TrashState, calls: int
    ) -> None:
        button, clicks = trash
        button.set_state(state)
        button.event_generate("<Button-1>", x=3, y=3)
        assert len(clicks) == calls

    def test_going_back_from_inactive_restores_the_pointer(
        self, trash: tuple[TrashButton, list[str]]
    ) -> None:
        button, _ = trash
        button.set_state("inactive")
        button.set_state("normal")
        assert str(button.cget("cursor")) == pointer_cursor(button)


# ---------- Keyboard ----------


def ring_items(canvas: tk.Canvas) -> list[int]:
    """The focus ring: the polygons outlined in the focus color."""
    return [
        item
        for item in canvas.find_all()
        if canvas.type(item) == "polygon"
        and str(canvas.itemcget(item, "outline")) == palette.FOCUS_RING
    ]


def reachable_with_tab(widget: tk.Misc) -> bool:
    return str(widget.cget("takefocus")).lower() in ("1", "true")


def give_focus_or_skip(window: tk.Toplevel, widget: tk.Misc) -> None:
    """Gives ``widget`` the real keyboard focus, or skips the test saying why it could not."""
    window.update()
    widget.focus_force()
    window.update()
    if window.focus_get() is not widget:
        pytest.skip("the window did not get the keyboard focus")


def gain_focus(widget: tk.Misc) -> None:
    """Simulates the focus arriving, which is enough for what the widget draws."""
    widget.event_generate("<FocusIn>")


def lose_focus(widget: tk.Misc) -> None:
    widget.event_generate("<FocusOut>")


class TestSoftButtonKeyboard:
    def test_an_enabled_button_is_reachable_with_tab(self, tk_root: tk.Tk) -> None:
        button = SoftButton(tk_root, "Ok", lambda: None, palette.LILAC, palette.WHITE)
        assert reachable_with_tab(button)

    def test_every_activation_key_is_bound(self, tk_root: tk.Tk) -> None:
        button = SoftButton(tk_root, "Ok", lambda: None, palette.LILAC, palette.WHITE)
        assert all(button.bind(key) for key in ACTIVATION_KEYS)

    def test_a_disabled_button_is_skipped_by_tab_and_has_no_keys(self, tk_root: tk.Tk) -> None:
        button = SoftButton(
            tk_root, "Ok", lambda: None, palette.TRASH_INACTIVE, palette.WHITE, enabled=False
        )
        assert not reachable_with_tab(button)
        assert not any(button.bind(key) for key in ACTIVATION_KEYS)
        assert not button.bind("<FocusIn>")

    def test_a_disabled_button_never_draws_the_ring(self, window: tk.Toplevel) -> None:
        button = SoftButton(
            window, "Ok", lambda: None, palette.TRASH_INACTIVE, palette.WHITE, enabled=False
        )
        button.pack()
        window.update()
        gain_focus(button)
        assert ring_items(button) == []

    def test_at_rest_only_the_body_and_the_label_are_drawn(self, window: tk.Toplevel) -> None:
        button = SoftButton(window, "Ok", lambda: None, palette.LILAC, palette.WHITE)
        button.pack()
        window.update()
        assert [button.type(item) for item in button.find_all()] == ["polygon", "text"]
        assert ring_items(button) == []

    def test_the_ring_is_drawn_over_the_body_only_while_it_has_the_focus(
        self, window: tk.Toplevel
    ) -> None:
        button = SoftButton(window, "Ok", lambda: None, palette.LILAC, palette.WHITE)
        button.pack()
        window.update()
        gain_focus(button)
        assert len(ring_items(button)) == 1
        assert body_fill(button) == palette.LILAC  # the body is still the first item
        assert button.itemcget(button.find_all()[-1], "text") == "Ok"  # the label stays on top
        lose_focus(button)
        assert ring_items(button) == []
        assert [button.type(item) for item in button.find_all()] == ["polygon", "text"]

    def test_the_ring_stays_inside_the_button(self, window: tk.Toplevel) -> None:
        button = SoftButton(window, "Guardar", lambda: None, palette.LILAC, palette.WHITE)
        button.pack()
        window.update()
        gain_focus(button)
        coords = button.coords(ring_items(button)[0])
        xs, ys = coords[0::2], coords[1::2]
        margin = RING_WIDTH / 2  # the outline is centered on the path
        assert min(xs) >= margin
        assert min(ys) >= margin
        assert max(xs) <= int(button["width"]) - margin
        assert max(ys) <= int(button["height"]) - margin

    def test_hover_and_focus_are_independent(self, window: tk.Toplevel) -> None:
        button = SoftButton(window, "Ok", lambda: None, palette.LILAC, palette.WHITE)
        button.pack()
        window.update()
        darker = mix_colors(palette.LILAC, palette.BLACK, 0.05)
        gain_focus(button)
        hover(button, over=True)
        assert (body_fill(button), len(ring_items(button))) == (darker, 1)
        hover(button, over=False)
        assert (body_fill(button), len(ring_items(button))) == (palette.LILAC, 1)
        hover(button, over=True)
        lose_focus(button)
        assert (body_fill(button), len(ring_items(button))) == (darker, 0)

    def test_a_click_does_not_give_the_button_the_keyboard_focus(
        self, window: tk.Toplevel
    ) -> None:
        button = SoftButton(window, "Ok", lambda: None, palette.LILAC, palette.WHITE)
        button.pack()
        window.update()
        button.event_generate("<Button-1>", x=3, y=3)
        assert window.focus_get() is not button
        assert ring_items(button) == []

    @pytest.mark.parametrize("key", ACTIVATION_KEYS)
    def test_space_and_enter_call_the_command(self, window: tk.Toplevel, key: str) -> None:
        clicks: list[str] = []
        button = SoftButton(
            window, "Ok", lambda: clicks.append("ok"), palette.LILAC, palette.WHITE
        )
        button.pack()
        give_focus_or_skip(window, button)
        button.event_generate(key)
        assert clicks == ["ok"]

    def test_the_keys_do_nothing_on_a_disabled_button(self, window: tk.Toplevel) -> None:
        clicks: list[str] = []
        button = SoftButton(
            window, "Ok", lambda: clicks.append("ok"), palette.TRASH_INACTIVE, palette.WHITE,
            enabled=False,
        )  # fmt: skip
        button.pack()
        give_focus_or_skip(window, button)
        for key in ACTIVATION_KEYS:
            button.event_generate(key)
        assert clicks == []


class TestTrashButtonKeyboard:
    @pytest.fixture
    def trash(self, window: tk.Toplevel) -> tuple[TrashButton, list[str]]:
        clicks: list[str] = []
        button = TrashButton(window, lambda: clicks.append("click"))
        button.pack()
        window.update()
        return button, clicks

    @pytest.mark.parametrize(
        ("state", "reachable"), [("normal", True), ("active", True), ("inactive", False)]
    )
    def test_it_is_reachable_with_tab_unless_it_is_inactive(
        self, trash: tuple[TrashButton, list[str]], state: TrashState, reachable: bool
    ) -> None:
        button, _ = trash
        button.set_state(state)
        assert reachable_with_tab(button) is reachable

    def test_leaving_inactive_makes_it_reachable_again(
        self, trash: tuple[TrashButton, list[str]]
    ) -> None:
        button, _ = trash
        button.set_state("inactive")
        button.set_state("normal")
        assert reachable_with_tab(button)

    def test_created_inactive_it_starts_unreachable(self, window: tk.Toplevel) -> None:
        button = TrashButton(window, lambda: None, state="inactive")
        assert not reachable_with_tab(button)

    def test_every_activation_key_is_bound(self, trash: tuple[TrashButton, list[str]]) -> None:
        button, _ = trash
        assert all(button.bind(key) for key in ACTIVATION_KEYS)

    @pytest.mark.parametrize("state", ["normal", "active", "inactive"])
    def test_the_ring_shows_only_while_it_has_the_focus_in_every_state(
        self, trash: tuple[TrashButton, list[str]], state: TrashState
    ) -> None:
        button, _ = trash
        button.set_state(state)
        assert ring_items(button) == []
        gain_focus(button)
        assert len(ring_items(button)) == 1
        lose_focus(button)
        assert ring_items(button) == []

    def test_the_ring_does_not_change_the_body_or_the_can(
        self, trash: tuple[TrashButton, list[str]]
    ) -> None:
        button, _ = trash
        before = (body_fill(button), body_outline(button), can_color(button))
        gain_focus(button)
        assert (body_fill(button), body_outline(button), can_color(button)) == before

    def test_the_ring_stays_inside_the_button(self, trash: tuple[TrashButton, list[str]]) -> None:
        button, _ = trash
        gain_focus(button)
        coords = button.coords(ring_items(button)[0])
        margin = RING_WIDTH / 2
        assert min(coords) >= margin
        assert max(coords) <= TrashButton.SIDE - margin

    def test_hover_and_focus_are_independent(self, trash: tuple[TrashButton, list[str]]) -> None:
        button, _ = trash
        gain_focus(button)
        hover(button, over=True)
        assert body_fill(button) == palette.TRASH_HOVER_BACKGROUND
        assert len(ring_items(button)) == 1
        lose_focus(button)
        assert body_fill(button) == palette.TRASH_HOVER_BACKGROUND
        assert ring_items(button) == []

    def test_a_click_does_not_give_the_button_the_keyboard_focus(
        self, trash: tuple[TrashButton, list[str]], window: tk.Toplevel
    ) -> None:
        button, _ = trash
        button.event_generate("<Button-1>", x=3, y=3)
        assert window.focus_get() is not button
        assert ring_items(button) == []

    @pytest.mark.parametrize("key", ACTIVATION_KEYS)
    @pytest.mark.parametrize(("state", "calls"), [("normal", 1), ("active", 1), ("inactive", 0)])
    def test_space_and_enter_do_what_a_click_does(
        self,
        trash: tuple[TrashButton, list[str]],
        window: tk.Toplevel,
        state: TrashState,
        calls: int,
        key: str,
    ) -> None:
        button, clicks = trash
        button.set_state(state)
        give_focus_or_skip(window, button)
        button.event_generate(key)
        assert len(clicks) == calls
