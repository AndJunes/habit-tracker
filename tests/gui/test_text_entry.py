import tkinter as tk

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.fonts import font
from habit_tracker.ui.widgets.text_entry import themed_entry


def test_the_entry_uses_the_theme_colors_and_font(tk_root: tk.Tk) -> None:
    entry = themed_entry(tk_root)
    assert isinstance(entry, tk.Entry)
    assert entry.cget("bg") == palette.WHITE
    assert entry.cget("fg") == palette.INK
    assert entry.cget("highlightbackground") == palette.BORDER
    assert entry.cget("highlightcolor") == palette.FOCUS_RING
    assert entry.cget("insertbackground") == palette.INK
    assert int(entry.cget("highlightthickness")) == 1
    assert str(entry.cget("font")) == str(font("sans", 11, master=tk_root))


def test_extra_options_reach_the_entry(tk_root: tk.Tk) -> None:
    variable = tk.StringVar(tk_root, "hola")
    entry = themed_entry(tk_root, textvariable=variable, width=14)
    assert int(entry.cget("width")) == 14
    assert entry.get() == "hola"
