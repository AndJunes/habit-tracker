"""The themed drop-down menu and the manager that keeps a single list open per window."""

import contextlib
import tkinter as tk
from collections.abc import Callable, Sequence
from typing import overload

from ..theme import palette
from ..theme.cursors import pointer_cursor
from ..theme.drawing import rounded_rect
from ..theme.focus import ACTIVATION_KEYS, focus_ring, track_focus
from ..theme.fonts import INPUT_FONT_SIZE, font
from ..theme.tkutil import PerRoot, TkEvent, current_grab, widget_exists
from .global_clicks import click_dispatcher

_FIELD_RADIUS = 10
_OPTION_RADIUS = 8
_DOT_DIAMETER = 10
_TEXT_X = 14
_TEXT_X_WITH_DOT = 32  # the text starts here when options have a color dot
_POPUP_GAP = 2  # space between the field and its list
_ARROW_MARGIN = 18  # distance of the arrow from the right edge of the field
_CHECK_MARGIN = 20  # distance of the selected option's tick from the right edge


def _draw_dot(canvas: tk.Canvas, x: float, cy: float, color: str) -> None:
    """The dot that shows the color of an option."""
    radius = _DOT_DIAMETER / 2
    canvas.create_oval(x, cy - radius, x + _DOT_DIAMETER, cy + radius, fill=color, outline="")


class MenuManager:
    """Knows which menu of a window has its list open, so there is never more than one.

    It also owns the click listener: the open menu's "click outside closes" handler
    is registered on the window's single click dispatcher when the list opens and
    removed when it closes. Nothing else is bound or unbound.
    """

    def __init__(self, root: tk.Misc) -> None:
        self._clicks = click_dispatcher(root)
        self._open: SoftMenu | None = None

    @property
    def open_menu(self) -> "SoftMenu | None":
        """The menu whose list is showing, if any."""
        return self._open

    def opened(self, menu: "SoftMenu") -> None:
        """Called by a menu as its list opens: closes the previous one and listens for clicks."""
        if self._open is not None:
            self._open.close()
        self._open = menu
        self._clicks.register(menu, menu.handle_click)

    def closed(self, menu: "SoftMenu") -> None:
        """Called by a menu as its list closes: stops listening for clicks."""
        if self._open is menu:
            self._open = None
        self._clicks.unregister(menu)


_managers = PerRoot(MenuManager)


def menu_manager(widget: tk.Misc) -> MenuManager:
    """The menu manager of ``widget``'s window."""
    return _managers.get(widget)


class SoftMenu(tk.Canvas):
    """A themed menu of options, replacing the system Combobox (macOS will not recolor it).

    It is a rounded field that drops its list right below on click: options with a
    lilac hover, the chosen one in bold with a tick and, when ``dots`` (a list of hex
    colors) is given, a colored dot next to each option, so the area menu shows the
    color the habit will get.

    It mimics the Combobox it replaces: ``current()`` returns the chosen index and
    ``current(i)`` sets it; ``command`` is called each time an option is chosen.

    About grabs (who captures the clicks): none is used for the list. On macOS a grab
    swallows clicks from outside without telling anyone, so the list would never learn
    that it should close. Instead the owner dialog lends its modal while the list is
    open, and a global click handler closes the list when a click lands outside it.

    The keyboard works on the field, which keeps the focus the whole time (the list never
    takes it): Space, Enter or Down open the list; once open, Up and Down, Home and End move
    a highlight that looks like the hover of a row, Space or Enter choose the highlighted
    option, Escape closes without choosing and Tab closes it and moves on. The highlight and
    the hover are one and the same marker, so whichever acted last is the one drawn. The
    focus ring is drawn only while the keyboard has the focus.
    """

    OPTION_HEIGHT = 32

    def __init__(
        self,
        master: tk.Misc,
        options: Sequence[str],
        dots: Sequence[str] | None = None,
        width: int = 316,
        height: int = 36,
        parent_background: str = palette.PAPER,
        command: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            bg=parent_background,
            highlightthickness=0,
            cursor=pointer_cursor(master),
        )
        self.options = options
        self.dots = dots
        self.command = command
        self._index = 0 if options else -1
        self._field_width = width
        self._field_height = height
        self._popup: tk.Toplevel | None = None
        self._owner: tk.Misc | None = None  # the dialog that lent its modal to the list
        self._owner_was_modal = False
        self._escape_binding: str | None = None
        self._highlight: int | None = None  # the row marked by the keyboard or the pointer
        self._painters: list[Callable[[bool], None]] = []  # repaint a row, highlighted or not
        self._has_focus = track_focus(self, self._draw)
        self._draw()
        self.bind("<Button-1>", lambda _event: self.toggle())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._bind_keys()

    @property
    def popup(self) -> tk.Toplevel | None:
        """The window of the list while it is open."""
        return self._popup

    @property
    def highlighted(self) -> int | None:
        """The row marked in the open list, or ``None``. Choosing it is a separate step."""
        return self._highlight

    @overload
    def current(self) -> int: ...
    @overload
    def current(self, index: int) -> None: ...
    def current(self, index: int | None = None) -> int | None:
        """Without argument returns the chosen index; with one, changes it."""
        if index is None:
            return self._index
        self._index = index
        self._draw()
        return None

    def select(self, index: int) -> None:
        """Chooses an option as a click would: sets it, closes the list and calls ``command``."""
        self._index = index
        self.close()
        if widget_exists(self):
            self._draw()  # close() draws only when a list was open
        if self.command:
            self.command()

    # ---------- the field ----------

    def _draw(self) -> None:
        self.delete("all")
        is_open = self._popup is not None
        rounded_rect(
            self, 1, 1, self._field_width - 1, self._field_height - 1, _FIELD_RADIUS,
            fill=palette.WHITE, outline=palette.LILAC if is_open else palette.BORDER,
        )  # fmt: skip
        if self._has_focus():
            focus_ring(self, 1, 1, self._field_width - 1, self._field_height - 1, _FIELD_RADIUS)
        if self._index >= 0:
            text_x = _TEXT_X
            if self.dots:
                _draw_dot(self, _TEXT_X, self._field_height / 2, self.dots[self._index])
                text_x = _TEXT_X_WITH_DOT
            self.create_text(
                text_x, self._field_height / 2, anchor="w", text=self.options[self._index],
                font=font("sans", INPUT_FONT_SIZE, master=self), fill=palette.INK,
            )  # fmt: skip
        # The arrow points down when closed and up when open.
        cx, cy = self._field_width - _ARROW_MARGIN, self._field_height / 2
        direction = -1 if is_open else 1
        arrow = [cx - 4, cy - 2 * direction, cx, cy + 2 * direction, cx + 4, cy - 2 * direction]
        self.create_line(arrow, fill=palette.MUTED, width=1.8, capstyle="round", joinstyle="round")

    # ---------- the list ----------

    def _popup_is_visible(self) -> bool:
        popup = self._popup
        return popup is not None and widget_exists(popup) and bool(popup.winfo_viewable())

    def _list_is_showing(self) -> bool:
        """Whether the list is on screen.

        If the system hid the list on its own (for example when the app lost focus) the
        menu would stay "open" with no list: that leftover is cleared here, so the next
        click or key opens it again at once.
        """
        if self._popup is None:
            return False
        if self._popup_is_visible():
            return True
        self.close()
        return False

    def toggle(self) -> None:
        """Opens the list, or closes it if it is showing (the effect of clicking the field)."""
        if self._list_is_showing():
            self.close()
        elif self.options:
            self.open()

    def open(self) -> None:
        """Drops the list below the field, closing any other open list of the window."""
        menu_manager(self).opened(self)

        # The owner dialog lends its modal (its grab) while the list is open: if it kept
        # it, it would capture the clicks and the list would be dead.
        owner = self.winfo_toplevel()
        self._owner = owner
        self._owner_was_modal = current_grab(owner) is not None
        owner.grab_release()

        # A window without title bar, right below the field.
        popup = tk.Toplevel(self)
        self._popup = popup
        popup.overrideredirect(True)
        popup.geometry(
            f"+{self.winfo_rootx()}+{self.winfo_rooty() + self._field_height + _POPUP_GAP}"
        )
        popup.lift()
        self._draw()

        # A frame in the border color that shows 1 px around the list.
        frame = tk.Frame(popup, bg=palette.BORDER)
        frame.pack()
        rows = tk.Frame(frame, bg=palette.WHITE)
        rows.pack(padx=1, pady=1)
        for index, text in enumerate(self.options):
            self._create_option(rows, index, text)

        # Closing: Escape, or a click outside the list (see the class docstring).
        self._escape_binding = owner.bind("<Escape>", lambda _event: self.close(), add="+")

    def _create_option(self, rows: tk.Frame, index: int, text: str) -> None:
        """One row of the list: dot (if any), text and the lilac highlight."""
        row = tk.Canvas(
            rows,
            width=self._field_width - 2,
            height=self.OPTION_HEIGHT,
            bg=palette.WHITE,
            highlightthickness=0,
            cursor=pointer_cursor(self),
        )
        row.pack()
        chosen = index == self._index
        center_y = self.OPTION_HEIGHT / 2

        def paint(highlighted: bool) -> None:
            row.delete("all")
            if highlighted:
                rounded_rect(
                    row, 4, 2, self._field_width - 6, self.OPTION_HEIGHT - 2, _OPTION_RADIUS,
                    fill=palette.LILAC_SOFT, outline="",
                )  # fmt: skip
            text_x = _TEXT_X
            if self.dots:
                _draw_dot(row, _TEXT_X, center_y, self.dots[index])
                text_x = _TEXT_X_WITH_DOT
            row.create_text(
                text_x, center_y, anchor="w", text=text,
                font=font("sans", INPUT_FONT_SIZE, "bold" if chosen else "normal", master=self),
                fill=palette.INK_TITLE if chosen else palette.INK,
            )  # fmt: skip
            if chosen:  # the lilac tick of "this is the current one"
                cx = self._field_width - _CHECK_MARGIN
                tick = [cx - 4, center_y, cx - 1, center_y + 3, cx + 5, center_y - 4]
                row.create_line(
                    tick, fill=palette.LILAC, width=2, capstyle="round", joinstyle="round"
                )

        paint(False)
        self._painters.append(paint)
        row.bind("<Enter>", lambda _event: self._set_highlight(index))
        row.bind("<Leave>", lambda _event: self._clear_highlight(index))
        row.bind("<Button-1>", lambda _event: self.select(index))

    # ---------- the highlight ----------

    def _set_highlight(self, index: int | None) -> None:
        """Marks one row of the open list (``None`` for none) and repaints the two affected."""
        if self._popup is None or index == self._highlight:
            return
        previous, self._highlight = self._highlight, index
        for row in (previous, index):
            if row is not None and row < len(self._painters):
                self._painters[row](row == self._highlight)

    def _clear_highlight(self, index: int) -> None:
        """Unmarks ``index`` unless something else has been marked since."""
        if self._highlight == index:
            self._set_highlight(None)

    def _move_highlight(self, step: int) -> None:
        """Moves the mark ``step`` rows without wrapping; unmarked, it starts at the chosen row."""
        start = self._index if self._highlight is None else self._highlight
        self._set_highlight(min(max(start + step, 0), len(self.options) - 1))

    def _forget_rows(self) -> None:
        """Drops the highlight and the row painters: the rows are about to be destroyed."""
        self._highlight = None
        self._painters = []

    # ---------- the keyboard ----------

    def _bind_keys(self) -> None:
        for key in ACTIVATION_KEYS:
            self.bind(key, self._on_confirm, add="+")
        self.bind("<Down>", self._on_down, add="+")
        self.bind("<Up>", self._on_up, add="+")
        self.bind("<Home>", self._on_home, add="+")
        self.bind("<End>", self._on_end, add="+")
        # Leaving the field closes the list. ``<Tab>`` also matches Shift+Tab on macOS and
        # Windows; X11 reports Shift+Tab as its own keysym, which not every Tk build knows.
        self.bind("<Tab>", self._on_tab, add="+")
        with contextlib.suppress(tk.TclError):
            self.bind("<ISO_Left_Tab>", self._on_tab, add="+")

    def _open_from_keyboard(self) -> None:
        """Opens the list with the chosen option highlighted."""
        if self.options:
            self.open()
            self._set_highlight(self._index)

    def _on_confirm(self, _event: TkEvent) -> str:
        """Space or Enter: open the list, or choose the highlighted option."""
        if not self._list_is_showing():
            self._open_from_keyboard()
        elif self._highlight is None:
            self.close()  # nothing is marked, so there is nothing to choose
        else:
            self.select(self._highlight)
        return "break"  # a dialog must not also take Enter as "accept the form"

    def _on_down(self, _event: TkEvent) -> str:
        if self._list_is_showing():
            self._move_highlight(1)
        else:
            self._open_from_keyboard()
        return "break"

    def _on_up(self, _event: TkEvent) -> str | None:
        if not self._list_is_showing():
            return None
        self._move_highlight(-1)
        return "break"

    def _on_home(self, _event: TkEvent) -> str | None:
        if not self._list_is_showing():
            return None
        self._set_highlight(0)
        return "break"

    def _on_end(self, _event: TkEvent) -> str | None:
        if not self._list_is_showing():
            return None
        self._set_highlight(len(self.options) - 1)
        return "break"

    def _on_tab(self, _event: TkEvent) -> None:
        # No "break": the focus must still move on to the next widget.
        self.close()

    def handle_click(self, event: TkEvent) -> None:
        """Receives every click of the window while the list is open and closes it if outside.

        A click inside the list already chose its row, and a click on this field
        already toggles by itself: only the rest counts as "outside".
        """
        popup = self._popup
        if popup is None:
            return
        clicked = str(event.widget)
        popup_path = str(popup)
        if clicked in (str(self), popup_path) or clicked.startswith(popup_path + "."):
            return
        self.close()

    def close(self) -> None:
        """Closes the list, drops its listeners and gives the modal back to the owner."""
        popup = self._popup
        if popup is None:
            return
        owner, owner_was_modal = self._owner, self._owner_was_modal
        self._forget_rows()
        if widget_exists(popup):
            popup.destroy()
        self._release_listeners()
        self._popup = None  # before drawing, so that the field looks closed again
        # If the dialog itself is already being destroyed there is nothing left to restore.
        if widget_exists(self):
            if owner is not None and owner_was_modal:
                # Fails when the owner is not viewable (e.g. hidden): it cannot be modal then.
                with contextlib.suppress(tk.TclError):
                    owner.grab_set()
            self._draw()

    def _release_listeners(self) -> None:
        """Removes the Escape shortcut and the click handler; the list itself stays referenced."""
        owner, binding = self._owner, self._escape_binding
        self._owner = None
        self._escape_binding = None
        menu_manager(self).closed(self)
        if owner is not None and binding is not None and widget_exists(owner):
            owner.unbind("<Escape>", binding)

    def _on_destroy(self, _event: TkEvent) -> None:
        # The list goes away with its parent; only the global listeners need removing.
        if self._popup is not None:
            self._release_listeners()
            self._popup = None
            self._forget_rows()
