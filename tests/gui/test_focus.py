import tkinter as tk

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.focus import (
    ACTIVATION_KEYS,
    RING_WIDTH,
    activate_with_keys,
    focus_ring,
    track_focus,
)


def test_the_ring_is_an_outline_in_the_focus_color_with_no_fill(tk_root: tk.Tk) -> None:
    canvas = tk.Canvas(tk_root, width=100, height=40)
    item = focus_ring(canvas, 1, 1, 99, 39, 10)
    assert canvas.itemcget(item, "outline") == palette.FOCUS_RING
    assert canvas.itemcget(item, "fill") == ""
    assert float(canvas.itemcget(item, "width")) == RING_WIDTH


def test_a_tracked_canvas_is_reachable_with_tab(tk_root: tk.Tk) -> None:
    canvas = tk.Canvas(tk_root)
    track_focus(canvas, lambda: None)
    assert bool(int(str(canvas.cget("takefocus"))))


def test_the_focus_flag_follows_focus_in_and_out_and_asks_for_a_redraw(
    tk_root: tk.Tk,
) -> None:
    canvas = tk.Canvas(tk_root)
    redraws: list[int] = []
    has_focus = track_focus(canvas, lambda: redraws.append(1))
    assert not has_focus()
    canvas.event_generate("<FocusIn>")
    assert has_focus()
    canvas.event_generate("<FocusOut>")
    assert not has_focus()
    assert len(redraws) == 2


def test_every_activation_key_is_bound(tk_root: tk.Tk) -> None:
    canvas = tk.Canvas(tk_root)
    activate_with_keys(canvas, lambda: None)
    assert all(canvas.bind(key) for key in ACTIVATION_KEYS)


def test_pressing_a_key_with_the_focus_calls_the_command(window: tk.Toplevel) -> None:
    canvas = tk.Canvas(window, width=40, height=40)
    canvas.pack()
    calls: list[int] = []
    activate_with_keys(canvas, lambda: calls.append(1))
    window.update()
    canvas.focus_force()
    window.update()
    if window.focus_get() is not canvas:
        pytest.skip("the window did not get the keyboard focus")
    canvas.event_generate("<space>")
    canvas.event_generate("<Return>")
    assert calls == [1, 1]
