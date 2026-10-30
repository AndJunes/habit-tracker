import tkinter as tk

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.cursors import pointer_cursor
from habit_tracker.ui.theme.drawing import mix_colors
from habit_tracker.ui.theme.fonts import font
from habit_tracker.ui.widgets.chips import SelectionChip

AREA_COLOR = "#6488d8"


def body(chip: tk.Canvas) -> tuple[str, str]:
    """``(fill, outline)`` of the rounded body, which is the first item drawn."""
    first = chip.find_all()[0]
    return str(chip.itemcget(first, "fill")), str(chip.itemcget(first, "outline"))


def label(chip: tk.Canvas) -> int:
    return next(item for item in chip.find_all() if chip.type(item) == "text")


def test_at_rest_it_is_white_with_the_theme_border(tk_root: tk.Tk) -> None:
    chip = SelectionChip(tk_root, "Salud", lambda: None)
    assert (chip.selected, chip.hovered) == (False, False)
    assert body(chip) == (palette.WHITE, palette.BORDER)
    assert chip.itemcget(label(chip), "fill") == palette.INK
    assert chip.itemcget(label(chip), "font") == str(font("sans", 9, master=tk_root))
    assert str(chip.cget("cursor")) == pointer_cursor(chip)


def test_selected_it_takes_the_pastel_of_its_color_and_a_bold_title_ink(tk_root: tk.Tk) -> None:
    chip = SelectionChip(tk_root, "Salud", lambda: None, color=AREA_COLOR)
    chip.set_selected(True)
    assert chip.selected
    assert body(chip) == (mix_colors(AREA_COLOR, palette.WHITE, 0.85), AREA_COLOR)
    assert chip.itemcget(label(chip), "fill") == palette.INK_TITLE
    assert chip.itemcget(label(chip), "font") == str(font("sans", 9, "bold", master=tk_root))
    chip.set_selected(False)
    assert body(chip) == (palette.WHITE, palette.BORDER)


def test_without_a_color_the_accent_is_lilac(tk_root: tk.Tk) -> None:
    chip = SelectionChip(tk_root, "lun", lambda: None)
    chip.set_selected(True)
    assert body(chip) == (mix_colors(palette.LILAC, palette.WHITE, 0.85), palette.LILAC)


def test_with_a_color_a_dot_precedes_the_left_aligned_text(tk_root: tk.Tk) -> None:
    chip = SelectionChip(tk_root, "Salud", lambda: None, color=AREA_COLOR)
    kinds = [chip.type(item) for item in chip.find_all()]
    assert kinds == ["polygon", "oval", "text"]
    dot = chip.find_all()[1]
    assert chip.itemcget(dot, "fill") == AREA_COLOR
    assert chip.itemcget(label(chip), "anchor") == "w"


def test_without_a_color_the_text_is_centered_with_no_dot(tk_root: tk.Tk) -> None:
    chip = SelectionChip(tk_root, "lun", lambda: None, width=60)
    assert [chip.type(item) for item in chip.find_all()] == ["polygon", "text"]
    assert chip.coords(label(chip))[0] == 30


def test_the_pointer_hints_at_the_chip_and_selection_wins_over_hover(window: tk.Toplevel) -> None:
    chip = SelectionChip(window, "Salud", lambda: None)
    chip.pack()
    window.update()
    chip.event_generate("<Enter>")
    assert chip.hovered
    assert body(chip) == (palette.ROW_BACKGROUND, palette.BORDER)
    chip.set_selected(True)
    assert body(chip)[1] == palette.LILAC
    chip.event_generate("<Leave>")
    assert not chip.hovered


def test_a_click_only_reports_to_the_command(window: tk.Toplevel) -> None:
    clicks: list[str] = []
    chip = SelectionChip(window, "Salud", lambda: clicks.append("salud"))
    chip.pack()
    window.update()
    chip.event_generate("<Button-1>", x=3, y=3)
    assert clicks == ["salud"]
    assert not chip.selected  # the group, not the chip, decides what is selected
