"""The interface the application layer needs from a data store."""

from datetime import date
from typing import Protocol

from .domain.models import Area, Habit, ImportantDate, PriorityNote, Snapshot


class StorageError(Exception):
    """The data store could not be read or written."""


class Repository(Protocol):
    """Persistence operations, one entity at a time.

    Implementations raise :class:`StorageError` when an operation fails and
    must leave the stored data unchanged in that case.
    """

    def load(self) -> Snapshot: ...

    def save_area(self, area: Area) -> None:
        """Insert the area or update the one with the same id."""

    def save_habit(self, habit: Habit) -> None:
        """Insert the habit or update the one with the same id.

        Only the configuration is written: completions go through
        :meth:`set_completion`.
        """

    def delete_habit(self, habit_id: int) -> None:
        """Delete the habit and its completions."""

    def set_completion(
        self, habit_id: int, day: date, *, done: bool, value: float | None = None
    ) -> None:
        """Mark ``day`` as done (with an optional measured value) or clear it."""

    def save_priority(self, note: PriorityNote | None) -> None:
        """Replace the priority note; ``None`` clears it."""

    def add_important_date(self, item: ImportantDate) -> None: ...

    def remove_important_date(self, item: ImportantDate) -> None: ...
