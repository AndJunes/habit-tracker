import tkinter as tk

import pytest

from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.cursors import pointer_cursor
from habit_tracker.ui.theme.drawing import mix_colors
from habit_tracker.ui.theme.focus import ACTIVATION_KEYS, RING_WIDTH
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


# ---------- Keyboard ----------


def ring_items(chip: tk.Canvas) -> list[int]:
    """The focus ring: the polygons outlined in the focus color."""
    return [
        item
        for item in chip.find_all()
        if chip.type(item) == "polygon"
        and str(chip.itemcget(item, "outline")) == palette.FOCUS_RING
    ]


def give_focus_or_skip(window: tk.Toplevel, widget: tk.Misc) -> None:
    """Gives ``widget`` the real keyboard focus, or skips the test saying why it could not."""
    window.update()
    widget.focus_force()
    window.update()
    if window.focus_get() is not widget:
        pytest.skip("the window did not get the keyboard focus")


def test_a_chip_is_reachable_with_tab(tk_root: tk.Tk) -> None:
    chip = SelectionChip(tk_root, "Salud", lambda: None)
    assert str(chip.cget("takefocus")).lower() in ("1", "true")


def test_every_activation_key_is_bound(tk_root: tk.Tk) -> None:
    chip = SelectionChip(tk_root, "Salud", lambda: None)
    assert all(chip.bind(key) for key in ACTIVATION_KEYS)


def test_the_ring_shows_only_while_the_chip_has_the_focus(window: tk.Toplevel) -> None:
    chip = SelectionChip(window, "Salud", lambda: None, color=AREA_COLOR)
    chip.pack()
    window.update()
    assert ring_items(chip) == []
    chip.event_generate("<FocusIn>")
    assert len(ring_items(chip)) == 1
    assert body(chip) == (palette.WHITE, palette.BORDER)  # the body is still the first item
    chip.event_generate("<FocusOut>")
    assert ring_items(chip) == []
    assert [chip.type(item) for item in chip.find_all()] == ["polygon", "oval", "text"]


def test_the_ring_keeps_selection_and_hover_and_stays_inside_the_chip(
    window: tk.Toplevel,
) -> None:
    chip = SelectionChip(window, "Salud", lambda: None, color=AREA_COLOR)
    chip.pack()
    window.update()
    chip.event_generate("<FocusIn>")
    chip.set_selected(True)
    assert body(chip) == (mix_colors(AREA_COLOR, palette.WHITE, 0.85), AREA_COLOR)
    assert len(ring_items(chip)) == 1
    chip.set_selected(False)
    chip.event_generate("<Enter>")
    assert body(chip) == (palette.ROW_BACKGROUND, palette.BORDER)
    assert len(ring_items(chip)) == 1
    coords = chip.coords(ring_items(chip)[0])
    xs, ys = coords[0::2], coords[1::2]
    margin = RING_WIDTH / 2  # the outline is centered on the path
    assert min(xs) >= margin
    assert min(ys) >= margin
    assert max(xs) <= int(chip["width"]) - margin
    assert max(ys) <= int(chip["height"]) - margin


def test_a_click_does_not_give_the_chip_the_keyboard_focus(window: tk.Toplevel) -> None:
    chip = SelectionChip(window, "Salud", lambda: None)
    chip.pack()
    window.update()
    chip.event_generate("<Button-1>", x=3, y=3)
    assert window.focus_get() is not chip
    assert ring_items(chip) == []


@pytest.mark.parametrize("key", ACTIVATION_KEYS)
def test_space_and_enter_report_to_the_command_without_selecting(
    window: tk.Toplevel, key: str
) -> None:
    clicks: list[str] = []
    chip = SelectionChip(window, "Salud", lambda: clicks.append("salud"))
    chip.pack()
    give_focus_or_skip(window, chip)
    chip.event_generate(key)
    assert clicks == ["salud"]
    assert not chip.selected  # the group, not the chip, decides what is selected
