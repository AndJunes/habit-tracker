"""Message boxes behind a small interface, and the way service failures reach the person.

Controllers talk to :class:`Dialogs` instead of ``tkinter.messagebox`` so that tests can
answer the questions without a screen.
"""

import logging
from collections.abc import Callable
from tkinter import messagebox
from typing import Protocol

from ...domain.errors import ValidationError
from ...ports import StorageError
from ..strings import error_message
from ..views import texts

log = logging.getLogger(__name__)


class Dialogs(Protocol):
    def ask_yes_no(self, title: str, message: str) -> bool: ...

    def show_info(self, title: str, message: str) -> None: ...

    def show_warning(self, title: str, message: str) -> None: ...

    def show_error(self, title: str, message: str) -> None: ...


class TkDialogs:
    """The standard Tk message boxes, shown over the application's main window."""

    def ask_yes_no(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message)

    def show_info(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message)

    def show_warning(self, title: str, message: str) -> None:
        messagebox.showwarning(title, message)

    def show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message)


def attempt(dialogs: Dialogs, action: Callable[[], object]) -> bool:
    """Run a change to the data; tell the person if it fails. ``True`` when it went through.

    A rejected value is explained in plain words, a failed write gets an error dialog and
    is logged with its traceback. Either way the caller carries on: no control is left
    waiting for a result that is not coming.
    """
    try:
        action()
    except ValidationError as error:
        dialogs.show_warning(texts.NOTICE_TITLE, error_message(error))
        return False
    except StorageError:
        log.exception("a change to the data could not be stored")
        dialogs.show_error(texts.SAVE_ERROR_TITLE, texts.SAVE_ERROR_MESSAGE)
        return False
    return True
