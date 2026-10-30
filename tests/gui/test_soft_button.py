import tkinter as tk

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.cursors import pointer_cursor
from habit_tracker.ui.theme.drawing import mix_colors
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
