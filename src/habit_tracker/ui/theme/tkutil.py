"""Helpers over Tk's object model: root lookup, per-root instances and liveness checks."""

import tkinter as tk
import weakref
from collections.abc import Callable
from typing import cast

# ``tk.Event`` can be subscripted only from Python 3.14, so annotations go through this alias,
# which is not evaluated until a type checker asks for it.
type TkEvent = tk.Event[tk.Misc]


def default_root() -> tk.Tk:
    """The implicit root window Tkinter uses when no master is given."""
    # Tkinter offers no public accessor for its implicit root.
    root = getattr(tk, "_default_root", None)
    if not isinstance(root, tk.Tk):
        raise RuntimeError("no Tk root window exists yet")
    return root


def root_of(widget: tk.Misc | None = None) -> tk.Tk:
    """The root window ``widget`` belongs to (the implicit root when ``widget`` is ``None``)."""
    if widget is None:
        return default_root()
    return cast("tk.Tk", widget.nametowidget("."))


def widget_exists(widget: tk.Misc) -> bool:
    """Whether ``widget`` has not been destroyed yet (``False`` once its application is gone)."""
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


def current_grab(widget: tk.Misc) -> tk.Misc | None:
    """The widget that holds the grab in ``widget``'s application, if any."""
    # typeshed leaves ``Misc.grab_current`` unannotated.
    return cast("Callable[[], tk.Misc | None]", widget.grab_current)()


class PerRoot[T]:
    """Lazily builds one ``T`` for every Tk root window and hands the same one back.

    Fonts, the open menu and the global click dispatcher all belong to a window,
    not to the process: this keeps them out of module-level state and lets a new
    root start from scratch.
    """

    def __init__(self, factory: Callable[[tk.Tk], T]) -> None:
        self._factory = factory
        self._instances: weakref.WeakKeyDictionary[tk.Tk, T] = weakref.WeakKeyDictionary()

    def get(self, widget: tk.Misc | None = None) -> T:
        """The instance of ``widget``'s root (of the implicit root when ``widget`` is ``None``)."""
        root = root_of(widget)
        instance = self._instances.get(root)
        if instance is None:
            instance = self._factory(root)
            self._instances[root] = instance
        return instance
