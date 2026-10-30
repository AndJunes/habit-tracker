import tkinter as tk
from collections.abc import Callable
from typing import Any, cast

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.drawing import mix_colors
from habit_tracker.ui.widgets.scrollbar import SoftScrollbar, bind_mousewheel

TRACK_HEIGHT = 200


@pytest.fixture
def orders() -> list[tuple[object, ...]]:
    return []


def make_bar(master: tk.Misc, orders: list[tuple[object, ...]]) -> SoftScrollbar:
    bar = SoftScrollbar(master, lambda *order: orders.append(order))
    bar.configure(height=TRACK_HEIGHT)
    return bar


def thumb_color(bar: SoftScrollbar) -> str:
    return str(bar.itemcget(bar.find_all()[0], "fill"))


class TestThumb:
    def test_all_content_visible_means_no_thumb(
        self, tk_root: tk.Tk, orders: list[tuple[object, ...]]
    ) -> None:
        bar = make_bar(tk_root, orders)
        bar.set(0, 1)
        assert bar.thumb_bounds() is None
        assert bar.find_all() == ()

    def test_the_thumb_follows_the_visible_fraction(
        self, tk_root: tk.Tk, orders: list[tuple[object, ...]]
    ) -> None:
        bar = make_bar(tk_root, orders)
        bar.set(0.0, 0.25)  # the first quarter is visible
        top, bottom = bar.thumb_bounds() or (None, None)
        assert top == 0
        assert round(bottom or 0) == TRACK_HEIGHT // 4
        assert bar.find_all()
        bar.set(0.75, 1.0)  # the last quarter: the thumb reaches the bottom
        assert round((bar.thumb_bounds() or (0, 0))[1]) == TRACK_HEIGHT

    def test_the_thumb_never_gets_shorter_than_the_minimum(
        self, tk_root: tk.Tk, orders: list[tuple[object, ...]]
    ) -> None:
        bar = make_bar(tk_root, orders)
        bar.set(0, 0.01)  # huge content
        top, bottom = bar.thumb_bounds() or (0, 0)
        assert bottom - top == SoftScrollbar.MIN_THUMB_LENGTH

    def test_it_accepts_the_strings_a_canvas_sends(
        self, tk_root: tk.Tk, orders: list[tuple[object, ...]]
    ) -> None:
        bar = make_bar(tk_root, orders)
        bar.set("0.0", "0.5")
        assert (bar.first, bar.last) == (0.0, 0.5)

    def test_before_it_is_shown_its_height_comes_from_the_requested_size(
        self, tk_root: tk.Tk
    ) -> None:
        bar = SoftScrollbar(tk_root, lambda *order: None)  # still the default "7c" height
        bar.set(0, 0.5)  # must not fail to compute the thumb
        assert bar.find_all()


class TestInteraction:
    @pytest.fixture
    def bar(self, window: tk.Toplevel, orders: list[tuple[object, ...]]) -> SoftScrollbar:
        bar = make_bar(window, orders)
        bar.pack()
        window.update()
        assert bar.winfo_height() == TRACK_HEIGHT
        return bar

    def test_dragging_the_thumb_asks_to_move_to_a_fraction(
        self, bar: SoftScrollbar, orders: list[tuple[object, ...]]
    ) -> None:
        bar.set(0, 0.25)
        bar.event_generate("<ButtonPress-1>", x=5, y=10)  # grabs the thumb
        assert bar.dragging
        bar.event_generate("<B1-Motion>", x=5, y=85)  # 75 px down
        assert orders[-1] == ("moveto", 0.375)  # half the travel of the 3/4 that is left
        bar.event_generate("<B1-Motion>", x=5, y=10_000)
        assert orders[-1] == ("moveto", 0.75)  # it cannot go past the end
        bar.event_generate("<ButtonRelease-1>", x=5, y=85)
        assert not bar.dragging

    def test_motion_without_a_grab_does_nothing(
        self, bar: SoftScrollbar, orders: list[tuple[object, ...]]
    ) -> None:
        bar.set(0, 0.25)
        bar.event_generate("<B1-Motion>", x=5, y=85)
        assert orders == []

    def test_clicking_the_track_scrolls_a_page_towards_the_click(
        self, bar: SoftScrollbar, orders: list[tuple[object, ...]]
    ) -> None:
        bar.set(0, 0.25)
        bar.event_generate("<ButtonPress-1>", x=5, y=180)  # below the thumb
        assert orders[-1] == ("scroll", 1, "pages")
        assert not bar.dragging
        bar.set(0.5, 0.75)
        bar.event_generate("<ButtonPress-1>", x=5, y=5)  # above the thumb
        assert orders[-1] == ("scroll", -1, "pages")

    def test_pressing_with_nothing_to_scroll_does_nothing(
        self, bar: SoftScrollbar, orders: list[tuple[object, ...]]
    ) -> None:
        bar.set(0, 1)
        bar.event_generate("<ButtonPress-1>", x=5, y=100)
        assert orders == []

    def test_the_thumb_is_stronger_under_the_pointer_or_while_dragged(
        self, bar: SoftScrollbar
    ) -> None:
        bar.set(0, 0.25)
        pale = mix_colors(palette.LILAC, palette.WHITE, 0.4)
        assert thumb_color(bar) == pale
        bar.event_generate("<Enter>")
        assert thumb_color(bar) == palette.LILAC
        bar.event_generate("<Leave>")
        assert thumb_color(bar) == pale
        bar.event_generate("<ButtonPress-1>", x=5, y=10)
        assert thumb_color(bar) == palette.LILAC


class FakeCanvas:
    """Records the scroll requests it receives."""

    def __init__(self) -> None:
        self.moves: list[int] = []

    def yview_scroll(self, amount: int, unit: str) -> None:
        assert unit == "units"
        self.moves.append(amount)


class FakeWidget:
    """Collects bindings; can refuse ``<TouchpadScroll>`` the way Tk 8.x does."""

    def __init__(self, *, knows_touchpad: bool) -> None:
        self.knows_touchpad = knows_touchpad
        self.bindings: dict[str, Callable[[Any], None]] = {}

    def bind(self, sequence: str, function: Callable[[Any], None]) -> None:
        if sequence == "<TouchpadScroll>" and not self.knows_touchpad:
            raise tk.TclError('bad event type or keysym "TouchpadScroll"')
        self.bindings[sequence] = function


class FakeScrollEvent:
    def __init__(self, delta: int) -> None:
        self.delta = delta


def scroll_with(widget: FakeWidget, sequence: str, delta: int) -> None:
    widget.bindings[sequence](FakeScrollEvent(delta))


class TestMouseWheel:
    def test_tk8_has_no_touchpad_event_and_sends_small_deltas(self) -> None:
        widget, canvas = FakeWidget(knows_touchpad=False), FakeCanvas()
        bind_mousewheel(cast("tk.Misc", widget), cast("tk.Canvas", canvas))
        assert "<TouchpadScroll>" not in widget.bindings  # refusing it must not blow up
        scroll_with(widget, "<MouseWheel>", 1)
        scroll_with(widget, "<MouseWheel>", -3)
        assert canvas.moves == [-12, 36]

    def test_tk9_wheel_comes_in_notches_and_the_trackpad_packs_dx_and_dy(self) -> None:
        widget, canvas = FakeWidget(knows_touchpad=True), FakeCanvas()
        bind_mousewheel(cast("tk.Misc", widget), cast("tk.Canvas", canvas))
        scroll_with(widget, "<MouseWheel>", 120)
        scroll_with(widget, "<MouseWheel>", -240)
        scroll_with(widget, "<TouchpadScroll>", (3 << 16) | (-7 & 0xFFFF))  # dx = 3, dy = -7
        scroll_with(widget, "<TouchpadScroll>", (3 << 16) | 0)  # no vertical movement
        assert canvas.moves == [-60, 120, 7]

    def test_a_real_wheel_event_moves_the_canvas(self, window: tk.Toplevel) -> None:
        canvas = tk.Canvas(
            window, width=100, height=100, yscrollincrement=1, scrollregion=(0, 0, 100, 1000)
        )
        canvas.pack()
        bind_mousewheel(canvas, canvas)
        window.update()
        before = canvas.yview()[0]
        canvas.event_generate("<MouseWheel>", delta=-120)
        assert canvas.yview()[0] > before
