"""Fixtures shared by the storage tests: a repository on a temporary file and sample data."""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import date, datetime, time
from pathlib import Path

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import (
    Area,
    Habit,
    ImportantDate,
    Measurement,
    PriorityNote,
    Reminder,
    Snapshot,
)
from habit_tracker.storage.sqlite import SqliteRepository

RawConnect = Callable[[Path], sqlite3.Connection]


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 30, 1, 40, 5))


@pytest.fixture
def raw_connect() -> Iterator[RawConnect]:
    """Open plain second connections to a file, for looking inside it or breaking it."""
    opened: list[sqlite3.Connection] = []

    def connect(path: Path) -> sqlite3.Connection:
        con = sqlite3.connect(path, autocommit=False, timeout=0.1)
        opened.append(con)
        return con

    yield connect
    for con in opened:
        con.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "habits.sqlite3"


@pytest.fixture
def repository(db_path: Path) -> Iterator[SqliteRepository]:
    repo = SqliteRepository(db_path)
    yield repo
    repo.close()


@pytest.fixture
def snapshot() -> Snapshot:
    """One habit of every frequency, with measurements, reminders and history."""
    return Snapshot(
        areas=[
            Area("health", "Health", "#65a882", "#e3efe8"),
            Area("career", "Career", "#6488d8"),
            Area("home", "Home", "#e6b84c", "#faf2df"),
        ],
        habits=[
            Habit(
                id=1,
                name="Walk",
                area_id="health",
                frequency=Daily(),
                start=date(2026, 9, 1),
                description="Clear my head",
                notes="Take the park route",
                completions={date(2026, 9, 1): None, date(2026, 9, 2): None},
            ),
            Habit(
                id=2,
                name="Gym",
                area_id="health",
                frequency=Weekdays(frozenset({Weekday.MONDAY, Weekday.THURSDAY})),
                start=date(2026, 9, 1),
                end=date(2026, 12, 31),
                reminder=Reminder(time(7, 30), frozenset({Weekday.MONDAY})),
            ),
            Habit(
                id=3,
                name="Read",
                area_id="career",
                frequency=Quota(3, Period.WEEK, frozenset({Weekday.SATURDAY})),
                start=date(2026, 9, 1),
                measurement=Measurement(MeasurementKind.QUANTITY, 20, "pages", 5, 40),
                reminder=Reminder(time(21, 0)),
                completions={date(2026, 9, 5): 24.5, date(2026, 9, 6): None},
            ),
            Habit(
                id=4,
                name="Pay bills",
                area_id="home",
                frequency=FixedDates((date(2026, 11, 5), date(2026, 12, 5))),
                start=date(2026, 9, 1),
            ),
            Habit(
                id=5,
                name="Meditate",
                area_id="health",
                frequency=Interval(2, IntervalUnit.WEEKS),
                start=date(2026, 9, 1),
                measurement=Measurement(MeasurementKind.DURATION, 15, "min"),
                completions={date(2026, 9, 15): 12.0},
            ),
        ],
        important_dates=[
            ImportantDate(date(2026, 11, 3), "Exam"),
            ImportantDate(date(2026, 11, 20), "Delivery"),
        ],
        priority=PriorityNote(date(2026, 10, 31), "Finish the report"),
    )
