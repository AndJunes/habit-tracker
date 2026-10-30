"""Mouse cursors by platform."""

import tkinter as tk

DEFAULT_CURSOR = "arrow"

_AQUA_POINTER = "pointinghand"
_GENERIC_POINTER = "hand2"


def pointer_cursor(widget: tk.Misc) -> str:
    """The "clickable" cursor: the native pointing hand on macOS, ``hand2`` elsewhere."""
    if widget.tk.call("tk", "windowingsystem") == "aqua":
        return _AQUA_POINTER
    return _GENERIC_POINTER
