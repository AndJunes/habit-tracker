"""A repository that keeps everything in memory, for tests and demos.

It copies on the way in and out, like a real store: changing an object that was
loaded never changes what is stored until a ``save_*`` call says so.
"""

import copy
from datetime import date

from ..domain.models import Area, Habit, ImportantDate, PriorityNote, Snapshot
from ..ports import StorageError


class MemoryRepository:
    def __init__(self, snapshot: Snapshot | None = None) -> None:
        self._snapshot = copy.deepcopy(snapshot) if snapshot is not None else Snapshot()

    def load(self) -> Snapshot:
        return copy.deepcopy(self._snapshot)

    def save_area(self, area: Area) -> None:
        areas = self._snapshot.areas
        for index, existing in enumerate(areas):
            if existing.id == area.id:
                areas[index] = area
                return
        areas.append(area)

    def save_habit(self, habit: Habit) -> None:
        if not any(area.id == habit.area_id for area in self._snapshot.areas):
            raise StorageError(f"habit {habit.id} is in an unknown area: {habit.area_id!r}")
        habits = self._snapshot.habits
        stored = copy.deepcopy(habit)
        for index, existing in enumerate(habits):
            if existing.id == habit.id:
                stored.completions = existing.completions  # history goes through set_completion
                habits[index] = stored
                return
        habits.append(stored)
        habits.sort(key=lambda item: item.id)

    def delete_habit(self, habit_id: int) -> None:
        self._snapshot.habits = [h for h in self._snapshot.habits if h.id != habit_id]

    def set_completion(
        self, habit_id: int, day: date, *, done: bool, value: float | None = None
    ) -> None:
        habit = next((h for h in self._snapshot.habits if h.id == habit_id), None)
        if habit is None:
            raise StorageError(f"habit {habit_id} does not exist")
        if done:
            habit.completions[day] = value
        else:
            habit.completions.pop(day, None)

    def save_priority(self, note: PriorityNote | None) -> None:
        self._snapshot.priority = note

    def add_important_date(self, item: ImportantDate) -> None:
        if item not in self._snapshot.important_dates:
            self._snapshot.important_dates.append(item)

    def remove_important_date(self, item: ImportantDate) -> None:
        if item in self._snapshot.important_dates:
            self._snapshot.important_dates.remove(item)
