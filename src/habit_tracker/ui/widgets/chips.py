"""Chips: rounded toggles for picking within a group."""

import tkinter as tk
from collections.abc import Callable

from ..theme import palette
from ..theme.cursors import pointer_cursor
from ..theme.drawing import mix_colors, rounded_rect
from ..theme.focus import activate_with_keys, focus_ring, track_focus
from ..theme.fonts import FontWeight, font, measure

_RADIUS = 10
_DOT_DIAMETER = 10
_DOT_AND_GAP = 16  # width of the color dot plus the space before the text

# How much white is mixed into the chip's color to get its selected background.
_SELECTED_PASTEL_MIX = 0.85


class SelectionChip(tk.Canvas):
    """A rounded chip for choosing within a group (the form's areas, the weekdays).

    Centered text and, when ``color`` is given, a dot of that option's color. Selected,
    it is painted with the pastel of its color and a border to match; at rest it is
    white with the theme border, and it hints at being clickable under the pointer.
    The group is coordinated by the view: the chip only reports its click and knows
    how to draw itself selected or not (:meth:`set_selected`).

    It can be reached with Tab and pressed with Space or Enter, which report to the command
    like a click; the focus ring shows only while the keyboard has the focus.
    """

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], object],
        color: str | None = None,
        width: int = 96,
        height: int = 34,
        parent_background: str = palette.PAPER,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            bg=parent_background,
            highlightthickness=0,
            cursor=pointer_cursor(master),
        )
        self.text = text
        self.command = command
        self.color = color
        self._chip_width = width
        self._chip_height = height
        self.selected = False
        self.hovered = False
        self._has_focus = track_focus(self, self._draw)
        self._draw()
        self.bind("<Button-1>", lambda _event: self.command())
        self.bind("<Enter>", lambda _event: self._set_hovered(True))
        self.bind("<Leave>", lambda _event: self._set_hovered(False))
        activate_with_keys(self, lambda: self.command())

    def set_selected(self, selected: bool) -> None:
        """Draws the chip as selected or not."""
        self.selected = selected
        self._draw()

    def _set_hovered(self, hovered: bool) -> None:
        self.hovered = hovered
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        accent = self.color or palette.LILAC
        weight: FontWeight
        if self.selected:
            fill = mix_colors(accent, palette.WHITE, _SELECTED_PASTEL_MIX)
            border, ink, weight = accent, palette.INK_TITLE, "bold"
        else:
            fill = palette.ROW_BACKGROUND if self.hovered else palette.WHITE
            border, ink, weight = palette.BORDER, palette.INK, "normal"
        rounded_rect(
            self, 1, 1, self._chip_width - 1, self._chip_height - 1, _RADIUS,
            fill=fill, outline=border,
        )  # fmt: skip
        if self._has_focus():
            focus_ring(self, 1, 1, self._chip_width - 1, self._chip_height - 1, _RADIUS)

        chip_font = font("sans", 9, weight, master=self)
        text_width = measure(chip_font, self.text)
        cy = self._chip_height / 2
        if self.color:
            # Dot and text, centered as a single block.
            x0 = (self._chip_width - (_DOT_AND_GAP + text_width)) / 2
            radius = _DOT_DIAMETER / 2
            self.create_oval(
                x0, cy - radius, x0 + _DOT_DIAMETER, cy + radius, fill=self.color, outline=""
            )
            self.create_text(
                x0 + _DOT_AND_GAP, cy, anchor="w", text=self.text, font=chip_font, fill=ink
            )
        else:
            self.create_text(self._chip_width / 2, cy, text=self.text, font=chip_font, fill=ink)
