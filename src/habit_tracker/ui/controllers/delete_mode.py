"""Delete mode: the list turns into a selection and the buttons into Cancel / Delete (n)."""

from collections.abc import Callable

from ...domain.models import Habit
from ...service import HabitService
from ..views import texts
from .dialogs import Dialogs, TkDialogs
from .habit_actions import HabitActions


class DeleteMode:
    """Which habits are marked for deletion, shared by every screen that offers the mode.

    The screen reads :attr:`active` and :attr:`selected` to draw itself and passes
    ``on_change``, which every transition calls once the state has settled.
    """

    def __init__(
        self,
        service: HabitService,
        actions: HabitActions,
        *,
        on_change: Callable[[], None],
        dialogs: Dialogs | None = None,
    ) -> None:
        self._service = service
        self._actions = actions
        self._on_change = on_change
        self._dialogs = dialogs or TkDialogs()
        self._active = False
        self._selected: set[int] = set()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def selected(self) -> frozenset[int]:
        """The ids of the habits marked for deletion."""
        return frozenset(self._selected)

    @property
    def count(self) -> int:
        return len(self._selected)

    def is_selected(self, habit: Habit) -> bool:
        return habit.id in self._selected

    def enter(self) -> None:
        """Start selecting. With nothing to delete, say so instead."""
        if not self._service.habits():
            self._dialogs.show_info(texts.NOTICE_TITLE, texts.NO_HABITS_TO_DELETE)
            return
        self._active = True
        self._selected = set()
        self._on_change()

    def cancel(self) -> None:
        """Leave the mode without deleting anything."""
        self.reset()
        self._on_change()

    def toggle(self, habit: Habit) -> None:
        """Mark or unmark a habit as a candidate for deletion."""
        self._selected.symmetric_difference_update({habit.id})
        self._on_change()

    def confirm(self) -> None:
        """Delete the marked habits once the person confirms, and leave the mode.

        If the confirmation is declined, or a deletion fails, the mode stays on with what
        was not deleted still marked, so the button keeps working.
        """
        if self._actions.delete_habits(self._selected):
            self.reset()
            self._on_change()
            return
        remaining = {i for i in self._selected if self._service.find_habit(i) is not None}
        if remaining != self._selected:  # some were deleted before a failure
            self._selected = remaining
            self._on_change()

    def reset(self) -> None:
        """Leave the mode and forget the selection, without telling the screen to redraw."""
        self._active = False
        self._selected = set()
