"""One application-wide click listener that fans out to whoever registered a handler.

``bind_all`` on its own is a trap: ``unbind_all`` removes every ``bind_all`` of that
event, from every widget. Instead, a single dispatcher is bound once per window and
each interested widget adds and removes only its own handler.
"""

import tkinter as tk
from collections.abc import Callable, Hashable

from ..theme.tkutil import PerRoot, TkEvent

type ClickHandler = Callable[[TkEvent], object]

_SEQUENCE = "<Button-1>"


class GlobalClickDispatcher:
    """Calls the registered handlers on every left click anywhere in the window."""

    def __init__(self, root: tk.Misc) -> None:
        self._handlers: dict[Hashable, ClickHandler] = {}
        root.bind_all(_SEQUENCE, self._dispatch, add="+")

    def register(self, key: Hashable, handler: ClickHandler) -> None:
        """Adds ``handler`` under ``key``; registering the same key again replaces it."""
        self._handlers[key] = handler

    def unregister(self, key: Hashable) -> None:
        """Removes the handler of ``key``; unknown keys are ignored."""
        self._handlers.pop(key, None)

    def __len__(self) -> int:
        return len(self._handlers)

    def _dispatch(self, event: TkEvent) -> None:
        # A copy, because handlers unregister themselves while running.
        for handler in tuple(self._handlers.values()):
            handler(event)


_dispatchers = PerRoot(GlobalClickDispatcher)


def click_dispatcher(widget: tk.Misc) -> GlobalClickDispatcher:
    """The dispatcher of ``widget``'s window, created and bound on first use."""
    return _dispatchers.get(widget)
