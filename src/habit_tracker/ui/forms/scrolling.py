"""Keeping the widget that has the keyboard focus inside a scrolling area."""

import tkinter as tk

# Air kept between the focused widget and the edge of the visible area.
SCROLL_MARGIN = 12


def scroll_into_view(
    canvas: tk.Canvas, page: tk.Misc, widget: tk.Misc, margin: int = SCROLL_MARGIN
) -> None:
    """Scroll ``canvas`` just enough for ``widget`` to be seen whole, with ``margin`` around it.

    ``page`` is the frame hung from the canvas that holds ``widget``, and the canvas must scroll
    in pixels (``yscrollincrement=1``). Nothing moves if the widget is already in view, is not
    under ``page`` or the canvas has not been laid out yet. A widget taller than the area gets
    its top edge in view.
    """
    offset = _offset_in(widget, page)
    view_height = canvas.winfo_height()
    if offset is None or view_height <= 1:
        return
    top = offset
    bottom = offset + widget.winfo_height()
    view_top = canvas.canvasy(0)
    view_bottom = view_top + view_height
    if top - margin < view_top:
        shift = top - margin - view_top
    elif bottom + margin > view_bottom:
        shift = min(bottom + margin - view_bottom, top - margin - view_top)
    else:
        return
    canvas.yview_scroll(round(shift), "units")


def _offset_in(widget: tk.Misc, page: tk.Misc) -> int | None:
    """How far below the top of ``page`` the widget starts, or ``None`` if it is not under it.

    Each widget's position is relative to its parent, so adding them up does not depend on how
    far the canvas is scrolled, nor on the canvas having repainted since it last moved.
    """
    offset = 0
    current: tk.Misc | None = widget
    while current is not None and current is not page:
        offset += current.winfo_y()
        current = current.master
    return offset if current is page else None
