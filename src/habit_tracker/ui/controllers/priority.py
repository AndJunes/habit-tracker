"""The field where the single task for tomorrow is written."""

import tkinter as tk

from ...service import HabitService
from ..views import texts
from .dialogs import Dialogs, TkDialogs, attempt


class PriorityEditor:
    """Holds what is typed for tomorrow's priority, apart from the widgets that show it.

    The screens redraw themselves whenever a habit is marked, and the dashboard rebuilds
    its entry from scratch. Because the text lives in :attr:`variable`, which every entry is
    bound to, nothing typed is lost on the way: :meth:`sync` only loads the saved text while
    the person has not typed anything of their own.
    """

    def __init__(
        self, service: HabitService, master: tk.Misc, *, dialogs: Dialogs | None = None
    ) -> None:
        self._service = service
        self._dialogs = dialogs or TkDialogs()
        self._edited = False
        self._loading = False
        self.variable = tk.StringVar(master=master)
        self.variable.trace_add("write", self._on_write)
        self.sync()

    @property
    def edited(self) -> bool:
        """Whether the field holds text the person typed that has not been saved yet."""
        return self._edited

    def sync(self) -> None:
        """Show the text saved for tomorrow, unless the person is in the middle of writing."""
        if self._edited:
            return
        self._loading = True
        try:
            self.variable.set(self._service.priority_for_tomorrow() or "")
        finally:
            self._loading = False

    def save(self) -> bool:
        """Save the text as tomorrow's priority. ``True`` when it was stored."""
        text = self.variable.get().strip()
        if not text:
            self._dialogs.show_info(texts.NOTICE_TITLE, texts.PRIORITY_EMPTY)
            return False
        if not attempt(self._dialogs, lambda: self._service.set_priority_for_tomorrow(text)):
            return False
        self._edited = False
        self._dialogs.show_info(texts.DONE_TITLE, texts.PRIORITY_SAVED)
        return True

    def _on_write(self, *_args: str) -> None:
        if not self._loading:
            self._edited = True
