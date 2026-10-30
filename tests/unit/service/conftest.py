"""Fixtures for the service tests: a fixed clock, in-memory repositories and a flaky wrapper."""

from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date, datetime
from typing import Any

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.errors import ErrorCode, ValidationError
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import Area, Habit, ImportantDate, PriorityNote, Snapshot
from habit_tracker.ports import Repository, StorageError
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository

HabitFactory = Callable[..., Habit]
RepositoryFactory = Callable[..., MemoryRepository]
ServiceFactory = Callable[..., HabitService]
RaisesCode = Callable[[ErrorCode], AbstractContextManager[None]]


class FlakyRepository:
    """Wraps a repository, records every write attempt and fails on demand.

    While ``failing`` is true every write raises :class:`StorageError` before the
    wrapped repository is touched, as the :class:`Repository` contract requires.
    """

    def __init__(self, inner: Repository) -> None:
        self.inner = inner
        self.failing = False
        self.writes: list[str] = []

    def _write(self, operation: str) -> None:
        self.writes.append(operation)
        if self.failing:
            raise StorageError(f"{operation} failed")

    def load(self) -> Snapshot:
        return self.inner.load()

    def save_area(self, area: Area) -> None:
        self._write("save_area")
        self.inner.save_area(area)

    def save_habit(self, habit: Habit) -> None:
        self._write("save_habit")
        self.inner.save_habit(habit)

    def delete_habit(self, habit_id: int) -> None:
        self._write("delete_habit")
        self.inner.delete_habit(habit_id)

    def set_completion(
        self, habit_id: int, day: date, *, done: bool, value: float | None = None
    ) -> None:
        self._write("set_completion")
        self.inner.set_completion(habit_id, day, done=done, value=value)

    def save_priority(self, note: PriorityNote | None) -> None:
        self._write("save_priority")
        self.inner.save_priority(note)

    def add_important_date(self, item: ImportantDate) -> None:
        self._write("add_important_date")
        self.inner.add_important_date(item)

    def remove_important_date(self, item: ImportantDate) -> None:
        self._write("remove_important_date")
        self.inner.remove_important_date(item)


@pytest.fixture
def clock() -> FixedClock:
    """Thursday June 11, 2026, nine in the morning. Tests move it by setting ``current``."""
    return FixedClock(datetime(2026, 6, 11, 9, 0))


@pytest.fixture
def areas() -> list[Area]:
    return [
        Area(id="gym", name="Gym", color="#5DADE2"),
        Area(id="english", name="English", color="#9B59B6"),
    ]


@pytest.fixture
def make_habit() -> HabitFactory:
    """Build a habit with sensible defaults; keyword arguments override any field.

    ``done`` is a shortcut for days completed without a measured value.
    """

    def factory(*, done: Iterable[date] = (), **overrides: Any) -> Habit:
        fields: dict[str, Any] = {
            "id": 1,
            "name": "Gym",
            "area_id": "gym",
            "frequency": Daily(),
            "start": date(2026, 6, 1),
        }
        fields.update(overrides)
        completions: dict[date, float | None] = dict.fromkeys(done)
        completions.update(fields.pop("completions", {}))
        return Habit(completions=completions, **fields)

    return factory


@pytest.fixture
def make_repository(areas: list[Area]) -> RepositoryFactory:
    """An in-memory repository that already holds the sample areas and the given habits."""

    def factory(
        *habits: Habit,
        important_dates: Iterable[ImportantDate] = (),
        priority: PriorityNote | None = None,
    ) -> MemoryRepository:
        snapshot = Snapshot(
            areas=list(areas),
            habits=list(habits),
            important_dates=list(important_dates),
            priority=priority,
        )
        return MemoryRepository(snapshot)

    return factory


@pytest.fixture
def make_service(clock: FixedClock, make_repository: RepositoryFactory) -> ServiceFactory:
    """A service on the fixed clock; it uses ``repository`` or a new one holding ``habits``."""

    def factory(*habits: Habit, repository: Repository | None = None) -> HabitService:
        chosen = repository if repository is not None else make_repository(*habits)
        return HabitService(chosen, clock)

    return factory


@pytest.fixture
def make_flaky() -> Callable[[Repository], FlakyRepository]:
    return FlakyRepository


@pytest.fixture
def raises_code() -> RaisesCode:
    """``with raises_code(code):`` expects a :class:`ValidationError` carrying that code."""

    @contextmanager
    def expect(code: ErrorCode) -> Iterator[None]:
        with pytest.raises(ValidationError) as caught:
            yield
        assert caught.value.code is code

    return expect
