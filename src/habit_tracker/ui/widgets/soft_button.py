"""Flat rounded buttons: the soft button and the trash can used in delete mode."""

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from typing import Literal

from ..theme import palette
from ..theme.cursors import DEFAULT_CURSOR, pointer_cursor
from ..theme.drawing import mix_colors, rounded_rect, trash_can
from ..theme.focus import activate_with_keys, focus_ring, track_focus
from ..theme.fonts import font, measure
from ..theme.tkutil import TkEvent

type TrashState = Literal["normal", "active", "inactive"]

# How much black is mixed into a fill to darken it under the pointer.
HOVER_DARKEN = 0.05
ACTIVE_TRASH_HOVER_DARKEN = 0.07


class SoftButton(tk.Canvas):
    """A flat button with rounded corners.

    With ``enabled=False`` it is drawn the same way (with whatever muted colors it
    is given) but has no pointer cursor, no click and no keyboard access: the action
    is visible, though it cannot be used yet.

    Enabled, it can be reached with Tab and pressed with Space or Enter; the focus ring
    shows only while the keyboard has the focus.
    """

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], object],
        background: str,
        text_color: str,
        button_font: tkfont.Font | None = None,
        height: int = 38,
        radius: int = 12,
        pad_x: int = 18,
        width: int | None = None,
        parent_background: str = palette.PAPER,
        enabled: bool = True,
    ) -> None:
        self.button_font = button_font or font("sans", 12, "bold", master=master)
        width = width or (measure(self.button_font, text) + 2 * pad_x)
        super().__init__(
            master,
            width=width,
            height=height,
            bg=parent_background,
            highlightthickness=0,
            cursor=pointer_cursor(master) if enabled else DEFAULT_CURSOR,
        )
        self.command = command
        self.background = background
        self.hover_background = mix_colors(background, palette.BLACK, HOVER_DARKEN)
        self.text_color = text_color
        self.text = text
        self.radius = radius
        self._hovered = False
        self._has_focus: Callable[[], bool] = lambda: False
        if enabled:
            self._has_focus = track_focus(self, self._redraw)
        else:
            self.configure(takefocus=False)
        self._redraw()
        if enabled:
            self.bind("<Button-1>", lambda _event: self.command())
            self.bind("<Enter>", lambda _event: self._set_hovered(True))
            self.bind("<Leave>", lambda _event: self._set_hovered(False))
            activate_with_keys(self, lambda: self.command())

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered
        self._redraw()

    def _redraw(self) -> None:
        self._draw(self.hover_background if self._hovered else self.background)

    def _draw(self, fill: str) -> None:
        self.delete("all")
        width = int(self["width"])
        height = int(self["height"])
        rounded_rect(self, 1, 1, width - 1, height - 1, self.radius, fill=fill, outline="")
        if self._has_focus():
            focus_ring(self, 1, 1, width - 1, height - 1, self.radius)
        self.create_text(
            width / 2, height / 2, text=self.text, font=self.button_font, fill=self.text_color
        )


class TrashButton(tk.Canvas):
    """The trash can of delete mode: a square button with the states a destructive action needs.

    * ``"normal"``: at rest, barely hinted (thin border, muted pink can).
    * hover: lights up under the pointer; handled by the button itself while it is
      ``"normal"`` or ``"active"``, so it is not a state to request.
    * ``"active"``: marked for deletion (filled pink, white can).
    * ``"inactive"``: switched off; visible, but it neither responds nor shows the pointer.

    A click deletes nothing: it only calls ``command``. The view decides what it
    means (normally, toggling the selection). Space and Enter do the same as a click, and
    the button can be reached with Tab in every state but ``"inactive"``.
    """

    SIDE = 36
    _RADIUS = 11

    def __init__(
        self,
        master: tk.Misc,
        command: Callable[[], object],
        state: TrashState = "normal",
        parent_background: str = palette.PAPER,
    ) -> None:
        super().__init__(
            master, width=self.SIDE, height=self.SIDE, bg=parent_background, highlightthickness=0
        )
        self.command = command
        self.state: TrashState = state
        self.hovered = False
        self._pointer = pointer_cursor(master)
        self._has_focus = track_focus(self, self._draw)
        self._sync_reachability()
        self._draw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda _event: self._set_hovered(True))
        self.bind("<Leave>", lambda _event: self._set_hovered(False))
        activate_with_keys(self, lambda: self._on_click(None))

    def set_state(self, state: TrashState) -> None:
        """Switches between ``"normal"``, ``"active"`` and ``"inactive"`` and redraws."""
        self.state = state
        self._sync_reachability()
        self._draw()

    def _sync_reachability(self) -> None:
        """An inactive button is skipped by Tab, like it ignores the pointer."""
        self.configure(takefocus=self.state != "inactive")

    def _on_click(self, _event: TkEvent | None) -> None:
        if self.state != "inactive":
            self.command()

    def _set_hovered(self, hovered: bool) -> None:
        self.hovered = hovered
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        if self.state == "inactive":
            fill, border, can_color = palette.WHITE, palette.CELL_BORDER, palette.TRASH_INACTIVE
        elif self.state == "active":
            # Marked: filled pink, a shade darker under the pointer.
            if self.hovered:
                fill = mix_colors(palette.TRASH_ACTIVE, palette.BLACK, ACTIVE_TRASH_HOVER_DARKEN)
            else:
                fill = palette.TRASH_ACTIVE
            border, can_color = "", palette.WHITE
        elif self.hovered:
            fill = palette.TRASH_HOVER_BACKGROUND
            border = can_color = palette.TRASH_ACTIVE
        else:
            fill, border, can_color = palette.WHITE, palette.BORDER, palette.TRASH_REST
        self.configure(cursor=DEFAULT_CURSOR if self.state == "inactive" else self._pointer)
        rounded_rect(
            self, 1, 1, self.SIDE - 1, self.SIDE - 1, self._RADIUS, fill=fill, outline=border
        )
        if self._has_focus():
            focus_ring(self, 1, 1, self.SIDE - 1, self.SIDE - 1, self._RADIUS)
        trash_can(self, cx=self.SIDE / 2, cy=self.SIDE / 2, scale=1.0, color=can_color)
