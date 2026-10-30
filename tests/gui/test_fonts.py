import tkinter as tk
import tkinter.font as tkfont

import pytest

from habit_tracker.ui.theme.fonts import FontRegistry, font, font_registry, measure
from habit_tracker.ui.theme.tkutil import default_root


def test_the_same_request_gives_the_same_font(tk_root: tk.Tk) -> None:
    first = font("sans", 11, master=tk_root)
    second = font("sans", 11, master=tk_root)
    assert first is second
    assert first.actual("family") == second.actual("family")
    assert first.actual("size") == 11


def test_without_master_the_implicit_root_is_used(tk_root: tk.Tk) -> None:
    assert font("sans", 10) is font("sans", 10, master=default_root())


def test_size_weight_and_kind_make_different_fonts(tk_root: tk.Tk) -> None:
    base = font("sans", 10, master=tk_root)
    assert font("sans", 12, master=tk_root) is not base
    bold = font("sans", 10, "bold", master=tk_root)
    assert bold is not base
    assert bold.actual("weight") == "bold"
    assert base.actual("weight") == "normal"
    assert font("serif", 10, master=tk_root) is not base
    assert font("script", 10, master=tk_root) is not base


def test_a_widget_finds_the_registry_of_its_root(tk_root: tk.Tk) -> None:
    canvas = tk.Canvas(tk_root)
    assert font_registry(canvas) is font_registry(tk_root)
    assert font("sans", 9, master=canvas) is font("sans", 9, master=tk_root)


def test_each_root_has_its_own_registry(tk_root: tk.Tk, private_window: tk.Toplevel) -> None:
    other = font_registry(private_window)
    assert other is not font_registry(tk_root)
    assert other.font("sans", 9) is not font_registry(tk_root).font("sans", 9)
    assert other.font("sans", 9) is font("sans", 9, master=private_window)


def test_measure_returns_the_width_in_pixels(tk_root: tk.Tk) -> None:
    sans = font("sans", 11, master=tk_root)
    assert measure(sans, "") == 0
    assert measure(sans, "hola") == sans.measure("hola") > 0
    assert measure(sans, "hola mundo") > measure(sans, "hola")


@pytest.mark.parametrize(
    ("installed", "expected"),
    [
        (("Didot", "Georgia", "Avenir", "Caveat"), ("Didot", "Avenir", "Caveat")),
        (
            ("DM Serif Display", "Georgia", "Nunito", "Noteworthy"),
            ("DM Serif Display", "Nunito", "Noteworthy"),
        ),
        (("Georgia", "Trebuchet MS", "Marker Felt"), ("Georgia", "Trebuchet MS", "Marker Felt")),
        (("Comic Sans",), ("Times", "Helvetica", "Helvetica")),
    ],
)
def test_family_is_the_first_installed_candidate_or_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tk_root: tk.Tk,
    installed: tuple[str, ...],
    expected: tuple[str, str, str],
) -> None:
    monkeypatch.setattr(tkfont, "families", lambda *args, **kwargs: installed)
    registry = FontRegistry(tk_root)
    families = (registry.family("serif"), registry.family("sans"), registry.family("script"))
    assert families == expected
