"""The application service: the one entry point the interface talks to.

It keeps the data in memory, applies the domain rules and writes every change
through the repository first, so that a failed write never leaves the memory
and the store out of step.
"""

from datetime import date, datetime, timedelta

from .clock import Clock
from .domain import reminders, stats, streaks
from .domain.errors import ErrorCode, ValidationError
from .domain.frequency import Frequency, Quota
from .domain.models import (
    Area,
    Habit,
    ImportantDate,
    Measurement,
    PriorityNote,
    Reminder,
    Snapshot,
    is_finite_number,
)
from .domain.stats import MonthStats
from .domain.validation import validate_habit_fields
from .ports import Repository


class HabitService:
    def __init__(self, repository: Repository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock
        self._snapshot: Snapshot = repository.load()
        # (habit id, day) of the reminders already shown. It only lives as long
        # as the application is open, which is when reminders can sound.
        self._notified: set[tuple[int, date]] = set()

    # ---------- Queries ----------

    def today(self) -> date:
        return self._clock.now().date()

    def areas(self) -> tuple[Area, ...]:
        return tuple(self._snapshot.areas)

    def habits(self) -> tuple[Habit, ...]:
        return tuple(self._snapshot.habits)

    def active_habits(self) -> tuple[Habit, ...]:
        """The habits that have not ended yet."""
        today = self.today()
        return tuple(habit for habit in self._snapshot.habits if habit.is_active(today))

    def find_habit(self, habit_id: int) -> Habit | None:
        return next((habit for habit in self._snapshot.habits if habit.id == habit_id), None)

    def get_habit(self, habit_id: int) -> Habit:
        habit = self.find_habit(habit_id)
        if habit is None:
            raise ValidationError(ErrorCode.HABIT_NOT_FOUND, habit_id=habit_id)
        return habit

    def area_of(self, habit: Habit) -> Area | None:
        return next((area for area in self._snapshot.areas if area.id == habit.area_id), None)

    def current_streak(self, habit: Habit) -> int:
        return streaks.current_streak(habit, self.today())

    def longest_streak(self) -> int:
        return stats.longest_streak(self._snapshot.habits, self.today())

    def done_in_period(self, habit: Habit, day: date | None = None) -> int:
        """How many times a quota habit was done in the week or month of ``day`` (today)."""
        if not isinstance(habit.frequency, Quota):
            raise ValueError("done_in_period needs a habit with a quota frequency")
        return streaks.count_in_period(habit, habit.frequency, day or self.today())

    def next_due(self, habit: Habit, since: date | None = None) -> date | None:
        """The first day after ``since`` (today) on which the habit is due."""
        return habit.next_scheduled(since or self.today())

    def day_progress(self, day: date | None = None) -> tuple[int, int]:
        return stats.day_progress(self._snapshot.habits, day or self.today())

    def completed_areas_by_day(self, year: int, month: int) -> dict[int, list[str]]:
        return stats.completed_areas_by_day(self._snapshot.habits, year, month)

    def month_stats(self, year: int, month: int) -> MonthStats:
        return stats.month_stats(
            self._snapshot.areas, self._snapshot.habits, year, month, self.today()
        )

    def important_dates(self, year: int, month: int) -> list[tuple[int, str]]:
        return stats.important_dates_in_month(self._snapshot.important_dates, year, month)

    def priority_for_today(self) -> str | None:
        """The text written last night, if it is meant for today."""
        note = self._snapshot.priority
        return note.text if note and note.for_day == self.today() and note.text else None

    def priority_for_tomorrow(self) -> str | None:
        """The text already written for tomorrow, to prefill the field."""
        note = self._snapshot.priority
        tomorrow = self.today() + timedelta(days=1)
        return note.text if note and note.for_day == tomorrow and note.text else None

    def pending_reminders(self, now: datetime | None = None) -> list[Habit]:
        """The habits whose reminder is due now, each reported once per day."""
        now = now or self._clock.now()
        due: list[Habit] = []
        for habit in self._snapshot.habits:
            key = (habit.id, now.date())
            if key in self._notified or not reminders.is_reminder_due(habit, now):
                continue
            self._notified.add(key)
            due.append(habit)
        return due

    # ---------- Actions ----------

    def mark(
        self, habit_id: int, done: bool, *, day: date | None = None, value: float | None = None
    ) -> None:
        """Mark or unmark ``day`` (today) as done.

        A measured value is stored only for measured habits; marking again
        without a value keeps the one already recorded. Unmarking removes both.
        """
        habit = self.get_habit(habit_id)
        day = day or self.today()
        if value is not None and (not is_finite_number(value) or value < 0):
            raise ValidationError(ErrorCode.VALUE_INVALID, value=value)
        stored = None
        if done and habit.measurement is not None:
            stored = value if value is not None else habit.completions.get(day)
        self._repository.set_completion(habit.id, day, done=done, value=stored)
        if done:
            habit.completions[day] = stored
        else:
            habit.completions.pop(day, None)

    def add_habit(
        self,
        *,
        name: str,
        area_id: str,
        frequency: Frequency,
        description: str = "",
        notes: str = "",
        start: date | None = None,
        end: date | None = None,
        measurement: Measurement | None = None,
        reminder: Reminder | None = None,
    ) -> Habit:
        """Create a habit. Everything is validated before anything is stored."""
        start = start or self.today()
        name = validate_habit_fields(
            name=name,
            area_id=area_id,
            areas=self._snapshot.areas,
            start=start,
            end=end,
            frequency=frequency,
            habits=self._snapshot.habits,
        )
        habit = Habit(
            id=max((item.id for item in self._snapshot.habits), default=0) + 1,
            name=name,
            area_id=area_id,
            frequency=frequency,
            start=start,
            end=end,
            description=description.strip(),
            notes=notes.strip(),
            measurement=measurement,
            reminder=reminder,
        )
        self._repository.save_habit(habit)
        self._snapshot.habits.append(habit)
        return habit

    def edit_habit(
        self,
        habit_id: int,
        *,
        name: str,
        area_id: str,
        frequency: Frequency,
        description: str = "",
        notes: str = "",
        start: date | None = None,
        end: date | None = None,
        measurement: Measurement | None = None,
        reminder: Reminder | None = None,
    ) -> Habit:
        """Replace a habit's configuration; its history is kept as it is.

        Every field is replaced, so a field left out is cleared. Only ``start`` falls
        back to the current value when it is not given.
        """
        current = self.get_habit(habit_id)
        start = start or current.start
        name = validate_habit_fields(
            name=name,
            area_id=area_id,
            areas=self._snapshot.areas,
            start=start,
            end=end,
            frequency=frequency,
            habits=self._snapshot.habits,
            own_id=habit_id,
        )
        updated = Habit(
            id=current.id,
            name=name,
            area_id=area_id,
            frequency=frequency,
            start=start,
            end=end,
            description=description.strip(),
            notes=notes.strip(),
            measurement=measurement,
            reminder=reminder,
            completions=current.completions,
        )
        self._repository.save_habit(updated)
        self._snapshot.habits[self._snapshot.habits.index(current)] = updated
        return updated

    def delete_habit(self, habit_id: int) -> None:
        habit = self.get_habit(habit_id)
        self._repository.delete_habit(habit.id)
        self._snapshot.habits.remove(habit)
        # A habit created later may reuse this id and must still get its reminder.
        self._notified = {key for key in self._notified if key[0] != habit.id}

    def set_priority_for_tomorrow(self, text: str) -> None:
        """Save the one task for tomorrow; empty text clears it."""
        text = text.strip()
        note = PriorityNote(self.today() + timedelta(days=1), text) if text else None
        self._repository.save_priority(note)
        self._snapshot.priority = note

    def add_important_date(self, day: date, title: str) -> ImportantDate:
        title = title.strip()
        if not title:
            raise ValidationError(ErrorCode.TITLE_REQUIRED)
        item = ImportantDate(day, title)
        if item not in self._snapshot.important_dates:
            self._repository.add_important_date(item)
            self._snapshot.important_dates.append(item)
        return item

    def remove_important_date(self, item: ImportantDate) -> None:
        if item in self._snapshot.important_dates:
            self._repository.remove_important_date(item)
            self._snapshot.important_dates.remove(item)
