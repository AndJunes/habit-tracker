"""Making a dialog modal once Tk lets it."""

import logging
import tkinter as tk

from ..theme.tkutil import widget_exists

logger = logging.getLogger(__name__)

MODAL_RETRY_MS = 50
MAX_MODAL_ATTEMPTS = 20


def make_modal(window: tk.Toplevel, attempt: int = 0) -> None:
    """Grabs the input for ``window`` as soon as it is on screen.

    Tk refuses a grab until the window is viewable, which happens a moment after it is
    created, so the grab is retried a few times. If the window never becomes viewable the
    dialog stays usable but non-modal, and the reason is logged.
    """
    if not widget_exists(window):
        return
    try:
        window.grab_set()
    except tk.TclError as error:
        if attempt < MAX_MODAL_ATTEMPTS:
            window.after(MODAL_RETRY_MS, lambda: make_modal(window, attempt + 1))
        else:
            logger.warning("gave up making %s modal after %d attempts: %s", window, attempt, error)
