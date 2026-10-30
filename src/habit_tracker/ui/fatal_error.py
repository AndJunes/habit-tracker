"""A last-resort error dialog, for failures that happen before the window exists."""

import tkinter as tk
from tkinter import messagebox


def show_fatal_error(title: str, message: str) -> None:
    """Show ``message`` in a dialog; do nothing when there is no display to show it on."""
    try:
        root = tk.Tk()
    except tk.TclError:  # no display: the message was already printed to the console
        return
    try:
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
    finally:
        root.destroy()
