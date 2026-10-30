"""Text entry with the theme's colors."""

import tkinter as tk
from typing import Any

from ..theme import palette
from ..theme.fonts import INPUT_FONT_SIZE, font


def themed_entry(master: tk.Misc, **options: Any) -> tk.Entry:
    """A flat ``tk.Entry`` in the theme's colors; its border shows the focus ring color."""
    return tk.Entry(
        master,
        bg=palette.WHITE,
        fg=palette.INK,
        font=font("sans", INPUT_FONT_SIZE, master=master),
        bd=0,
        relief="flat",
        highlightthickness=1,
        highlightbackground=palette.BORDER,
        highlightcolor=palette.FOCUS_RING,
        insertbackground=palette.INK,
        **options,
    )
