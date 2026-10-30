"""Typography: which font families the theme uses and a cache of the fonts built from them.

The design calls for DM Serif Display, Nunito and Caveat. When they are not
installed the closest fonts that ship with macOS are used instead.
"""

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Collection, Mapping
from typing import Literal

from .tkutil import PerRoot

type FontKind = Literal["serif", "sans", "script"]
type FontWeight = Literal["normal", "bold"]

# Size of the text people type or pick (entries and menus), so both look alike.
INPUT_FONT_SIZE = 11

# For each kind: the families to try in order, and the one used when none is installed.
_FAMILY_CANDIDATES: Mapping[FontKind, tuple[tuple[str, ...], str]] = {
    "serif": (("DM Serif Display", "Didot", "Georgia"), "Times"),
    "sans": (("Nunito", "Avenir Next", "Avenir", "Trebuchet MS"), "Helvetica"),
    "script": (("Caveat", "Bradley Hand", "Noteworthy", "Marker Felt"), "Helvetica"),
}


def _pick_family(candidates: tuple[str, ...], fallback: str, installed: Collection[str]) -> str:
    return next((family for family in candidates if family in installed), fallback)


class FontRegistry:
    """The theme's fonts for one root window; each one is built once and reused.

    Tk fonts live in a window's interpreter, so a registry cannot be shared
    between roots. Use :func:`font_registry` to get the one of a window.
    """

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        installed = set(tkfont.families(root))
        self._families: dict[FontKind, str] = {
            kind: _pick_family(candidates, fallback, installed)
            for kind, (candidates, fallback) in _FAMILY_CANDIDATES.items()
        }
        self._fonts: dict[tuple[FontKind, int, FontWeight], tkfont.Font] = {}

    def family(self, kind: FontKind) -> str:
        """The family chosen for ``kind``."""
        return self._families[kind]

    def font(self, kind: FontKind, size: int, weight: FontWeight = "normal") -> tkfont.Font:
        """The font of that kind, size and weight (the same object on every call)."""
        key = (kind, size, weight)
        cached = self._fonts.get(key)
        if cached is None:
            cached = tkfont.Font(self._root, family=self._families[kind], size=size, weight=weight)
            self._fonts[key] = cached
        return cached


_registries = PerRoot(FontRegistry)


def font_registry(master: tk.Misc | None = None) -> FontRegistry:
    """The font registry of ``master``'s root window (of the implicit root by default)."""
    return _registries.get(master)


def font(
    kind: FontKind, size: int, weight: FontWeight = "normal", *, master: tk.Misc | None = None
) -> tkfont.Font:
    """A theme font: ``"serif"`` for titles, ``"sans"`` for text, ``"script"`` for notes.

    Fonts belong to a root window. ``master`` picks it; without it the implicit
    root is used, which is the only one in a normal run.
    """
    return font_registry(master).font(kind, size, weight)


def measure(font: tkfont.Font, text: str) -> int:
    """How many pixels ``text`` takes in ``font`` (for centering and wrapping)."""
    return font.measure(text)
