"""Fixtures shared by the domain tests: a habit factory, sample areas and an error helper."""

from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date
from typing import Any

import pytest

from habit_tracker.domain.errors import ErrorCode, ValidationError
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import Area, Habit

HabitFactory = Callable[..., Habit]
RaisesCode = Callable[[ErrorCode], AbstractContextManager[None]]


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
            "start": date(2026, 5, 1),
        }
        fields.update(overrides)
        completions: dict[date, float | None] = dict.fromkeys(done)
        completions.update(fields.pop("completions", {}))
        return Habit(completions=completions, **fields)

    return factory


@pytest.fixture
def areas() -> list[Area]:
    return [
        Area(id="gym", name="Gym", color="#5DADE2"),
        Area(id="english", name="English", color="#9B59B6"),
    ]


@pytest.fixture
def raises_code() -> RaisesCode:
    """``with raises_code(code):`` expects a :class:`ValidationError` carrying that code."""

    @contextmanager
    def expect(code: ErrorCode) -> Iterator[None]:
        with pytest.raises(ValidationError) as caught:
            yield
        assert caught.value.code is code

    return expect
