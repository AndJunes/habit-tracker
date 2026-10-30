import tkinter as tk

import pytest

from habit_tracker.ui.theme import tkutil
from habit_tracker.ui.theme.tkutil import PerRoot, current_grab, root_of, widget_exists


def test_root_of_finds_the_root_from_any_depth(tk_root: tk.Tk) -> None:
    frame = tk.Frame(tk_root)
    canvas = tk.Canvas(frame)
    toplevel = tk.Toplevel(tk_root)
    assert root_of(tk_root) is tk_root
    assert root_of(canvas) is tk_root
    assert root_of(toplevel) is tk_root
    assert root_of() is tkutil.default_root()


def test_widget_exists_turns_false_once_destroyed(tk_root: tk.Tk) -> None:
    canvas = tk.Canvas(tk_root)
    assert widget_exists(canvas)
    canvas.destroy()
    assert not widget_exists(canvas)


def test_widget_exists_is_false_when_the_whole_application_is_gone() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    canvas = tk.Canvas(root)
    root.destroy()
    assert not widget_exists(canvas)


def test_per_root_builds_one_instance_for_each_root(
    tk_root: tk.Tk, private_window: tk.Toplevel
) -> None:
    built: list[tk.Tk] = []

    def factory(root: tk.Tk) -> object:
        built.append(root)
        return object()

    per_root = PerRoot(factory)
    first = per_root.get(tk_root)
    assert per_root.get(tk.Canvas(tk_root)) is first
    other = per_root.get(private_window)
    assert other is not first
    assert built == [tk_root, root_of(private_window)]


def test_current_grab_is_none_without_a_grab(tk_root: tk.Tk) -> None:
    assert current_grab(tk_root) is None


def test_current_grab_reports_the_widget_that_holds_it(window: tk.Toplevel) -> None:
    window.grab_set()
    try:
        assert str(current_grab(window)) == str(window)
    finally:
        window.grab_release()
    assert current_grab(window) is None
