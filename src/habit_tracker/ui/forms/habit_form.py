"""The dialog to create or edit a habit.

A modal window with a scrolling body; the footer (the error and the buttons) stays fixed at
the bottom so it is always visible. From top to bottom the sections are:

    name and motivation · area (color chips) · frequency (six kinds, each with its own zone) ·
    how to measure · validity (start and end, with a calendar) · notes · advanced options
    (folded) · live preview

What the person picks is kept in :class:`~habit_tracker.ui.forms.form_state.FormState`, not in
the widgets, so changing an option never loses what was chosen for another one. The state also
builds the habit and checks what is the form's to check; the service checks the rest. Any
problem is written in the footer without closing the dialog or clearing anything: the dialog
closes only after the habit was stored.

The keyboard reaches everything: Tab goes through the fields in the order they are drawn (the
body first, then the footer's buttons), the scrolling area follows the focus so that the field
being used is always in view, and Escape closes the dialog without saving.
"""

import logging
import tkinter as tk
from collections.abc import Callable
from typing import Any

from ...domain.errors import ValidationError
from ...domain.models import Habit
from ...ports import StorageError
from ...service import HabitService
from ..theme import palette
from ..theme.fonts import font
from ..theme.tkutil import TkEvent
from ..widgets.scrollbar import SoftScrollbar, bind_mousewheel
from ..widgets.soft_button import SoftButton
from ..widgets.soft_menu import menu_manager
from . import texts
from .form_state import FormError, FormState, describe_error
from .modal import make_modal
from .parts import FORM_WIDTH, LABEL_SIZE, PADDING, PAGE_WIDTH
from .scrolling import scroll_into_view
from .section_advanced import AdvancedSection
from .section_basics import AreaSection, HeaderSection, NameSection, NotesSection
from .section_frequency import FrequencySection
from .section_measurement import MeasurementSection
from .section_preview import PreviewSection
from .section_validity import ValiditySection

logger = logging.getLogger(__name__)

WINDOW_WIDTH = PAGE_WIDTH + SoftScrollbar.WIDTH
MIN_WINDOW_HEIGHT = 520
MAX_WINDOW_HEIGHT = 780
SCREEN_MARGIN = 140  # screen height kept free around the window
PARENT_TOP_OFFSET = 24  # how far below the top of its parent the dialog opens

_BODY_PADDING = (18, 10)  # top and bottom of the scrolling body
_FOOTER_PADDING = (8, 14)
_BUTTONS_TOP_GAP = 6


class HabitFormDialog(tk.Toplevel):
    """A modal form. ``habit=None`` creates a habit; otherwise it edits that one.

    ``on_saved`` is called with the saved habit once it has been stored, and the
    dialog closes only after a successful save.
    """

    def __init__(
        self,
        master: tk.Misc,
        service: HabitService,
        *,
        habit: Habit | None = None,
        on_saved: Callable[[Habit], object],
    ) -> None:
        super().__init__(master)
        self._service = service
        self._on_saved = on_saved
        self._saving = False
        self._finished = False
        self._preview: PreviewSection | None = None
        self.form_state = FormState(service.areas(), service.today(), habit=habit)
        state = self.form_state

        self.title(texts.TITLE_EDIT if state.is_editing else texts.TITLE_NEW)
        self.configure(bg=palette.PAPER)
        self.resizable(False, True)

        self._error_label = self._build_footer()
        self._scroller, self._page, body = self._build_scroll_area()

        HeaderSection(body, state)
        self._name = NameSection(
            body, state, on_change=self._refresh_preview, on_submit=self.submit
        )
        self._area = AreaSection(body, state, on_change=self._on_area_changed)
        self._frequency = FrequencySection(
            body,
            state,
            on_change=self._refresh_preview,
            on_choice_changed=self._on_choice_changed,
        )
        self._measurement = MeasurementSection(
            body,
            state,
            on_change=self._refresh_preview,
            on_choice_changed=self._on_choice_changed,
        )
        self._validity = ValiditySection(body, state, on_change=self._on_validity_changed)
        self._notes = NotesSection(body, state)
        self._advanced = AdvancedSection(body, state, on_change=self._refresh_preview)
        self._preview = PreviewSection(body, state)

        self._place(master)
        self._refresh_preview()
        self._name.focus()
        self._bind_keyboard()
        self.after(0, lambda: make_modal(self))

    @property
    def error_text(self) -> str:
        """What the footer says: empty unless the last attempt to save failed."""
        return str(self._error_label.cget("text"))

    @property
    def is_saving(self) -> bool:
        """Whether a save is in progress (a second one is ignored until it ends)."""
        return self._saving

    def submit(self) -> None:
        """Validates and saves; the dialog closes only if the habit was stored.

        A problem with the form or a rule of the domain is written in the footer, and so is a
        failure of the store: in every case the dialog stays open with everything that was
        typed, ready to try again.
        """
        if self._saving or self._finished:
            return
        self._saving = True
        self._set_error("")
        try:
            saved = self.form_state.save(self._service)
        except (FormError, ValidationError) as error:
            self._set_error(describe_error(error))
        except StorageError:
            logger.exception("the habit could not be saved")
            self._set_error(texts.SAVE_FAILED)
        else:
            self._finished = True
            self.destroy()
            self._on_saved(saved)
        finally:
            self._saving = False

    # ---------- The window ----------

    def _build_footer(self) -> tk.Label:
        """The fixed bottom strip: the error line and the two buttons. Returns the error line."""
        footer = tk.Frame(self, bg=palette.PAPER)
        footer.pack(side="bottom", fill="x", padx=PADDING, pady=_FOOTER_PADDING)
        error_label = tk.Label(
            footer,
            text="",
            bg=palette.PAPER,
            fg=palette.TRASH_ACTIVE,
            font=font("sans", LABEL_SIZE, "bold", master=self),
            wraplength=FORM_WIDTH,
            justify="left",
            name="error",
        )
        error_label.pack(anchor="w")
        buttons = tk.Frame(footer, bg=palette.PAPER)
        buttons.pack(fill="x", pady=(_BUTTONS_TOP_GAP, 0))
        SoftButton(
            buttons,
            texts.CANCEL,
            self.destroy,
            palette.BUTTON_PINK_BACKGROUND,
            palette.BUTTON_PINK_TEXT,
        ).pack(side="left")
        SoftButton(
            buttons,
            texts.SAVE_EDIT if self.form_state.is_editing else texts.SAVE_NEW,
            self.submit,
            palette.LILAC,
            palette.WHITE,
        ).pack(side="right")
        return error_label

    def _build_scroll_area(self) -> tuple[tk.Canvas, tk.Frame, tk.Frame]:
        """The scrolling area above the footer. Returns its canvas, its page and the body."""
        # The theme's scrollbar and the same wheel and trackpad handling as the dashboard.
        holder = tk.Frame(self, bg=palette.PAPER)
        holder.pack(side="top", fill="both", expand=True)
        scrollbar = SoftScrollbar(holder, self._scroll)
        scrollbar.pack(side="right", fill="y")
        scroller = tk.Canvas(
            holder,
            bg=palette.PAPER,
            highlightthickness=0,
            width=PAGE_WIDTH,
            yscrollincrement=1,
            yscrollcommand=scrollbar.set,
        )
        scroller.pack(side="left", fill="both", expand=True)

        page = tk.Frame(scroller, bg=palette.PAPER)
        scroller.create_window(0, 0, anchor="nw", window=page, width=PAGE_WIDTH)
        page.bind(
            "<Configure>",
            lambda _event: scroller.configure(scrollregion=(0, 0, 0, page.winfo_reqheight())),
        )
        # A binding on the dialog hears all of its widgets: the Toplevel is in their bindtags.
        bind_mousewheel(self, scroller)

        body = tk.Frame(page, bg=palette.PAPER)
        body.pack(fill="x", padx=PADDING, pady=_BODY_PADDING)
        return scroller, page, body

    def _scroll(self, *order: Any) -> None:
        self._scroller.yview(*order)

    # ---------- The keyboard ----------

    def _bind_keyboard(self) -> None:
        # Bindings on the dialog hear all of its widgets: the Toplevel is in their bindtags.
        # The Escape binding goes first, ahead of the one a menu adds to this same dialog
        # while its list is open (see ``_on_escape``).
        self.bind("<Escape>", self._on_escape)
        self.bind("<FocusIn>", self._on_focus_in, add="+")

    def _on_escape(self, _event: TkEvent) -> str | None:
        """Close the dialog without saving, as the Cancel button does."""
        if menu_manager(self).open_menu is not None:
            # An open list listens to this key as well, from a binding added after this one:
            # it closes the list, and the dialog stays for another Escape.
            return None
        self.destroy()
        return "break"

    def _on_focus_in(self, event: TkEvent) -> None:
        """Scroll so that the widget that just got the focus (with Tab, say) is in view."""
        widget = event.widget
        # The list of a menu is a window of its own, and the footer does not scroll.
        if isinstance(widget, tk.Misc) and widget.winfo_toplevel() is self:
            scroll_into_view(self._scroller, self._page, widget)

    def _place(self, master: tk.Misc) -> None:
        """Sizes the dialog to the screen and opens it near the top of its parent."""
        height = min(
            MAX_WINDOW_HEIGHT, max(MIN_WINDOW_HEIGHT, self.winfo_screenheight() - SCREEN_MARGIN)
        )
        parent = master.winfo_toplevel()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - WINDOW_WIDTH) // 2)
        y = parent.winfo_rooty() + PARENT_TOP_OFFSET
        self.geometry(f"{WINDOW_WIDTH}x{height}+{x}+{y}")

    # ---------- Keeping the sections in step ----------

    def _refresh_preview(self) -> None:
        if self._preview is not None:  # not before the sections exist
            self._preview.refresh()

    def _on_area_changed(self) -> None:
        self._measurement.rebuild()  # the suggested units depend on the area
        self._refresh_preview()

    def _on_choice_changed(self) -> None:
        # What the advanced options offer depends on both menus: the rest days exist only with
        # "every day" and the reference goals only when something is measured.
        self._advanced.rebuild()

    def _on_validity_changed(self) -> None:
        self._frequency.update_limits()
        self._refresh_preview()

    def _set_error(self, text: str) -> None:
        self._error_label.configure(text=text)
