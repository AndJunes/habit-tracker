"""The Habit model: its life span, what counts as done, and its scheduling queries."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date

import pytest

from habit_tracker.domain.enums import IntervalUnit, Weekday
from habit_tracker.domain.errors import ErrorCode
from habit_tracker.domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import RECOMMENDED_MAX_HABITS, Habit

HabitFactory = Callable[..., Habit]
RaisesCode = Callable[[ErrorCode], AbstractContextManager[None]]

TODAY = date(2026, 6, 11)  # a Thursday


def test_the_recommended_number_of_habits_is_six() -> None:
    assert RECOMMENDED_MAX_HABITS == 6


# ---------- Construction ----------


def test_habit_rejects_an_end_before_its_start(
    make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.END_BEFORE_START):
        make_habit(start=date(2026, 6, 10), end=date(2026, 6, 1))


def test_habit_may_end_on_its_start_day(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 10), end=date(2026, 6, 10))
    assert habit.applies_on(date(2026, 6, 10))


# ---------- applies_on ----------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 5, 31), False, id="before-start"),
        pytest.param(date(2026, 6, 1), True, id="start-day"),
        pytest.param(date(2026, 6, 5), True, id="end-day"),
        pytest.param(date(2026, 6, 6), False, id="after-end"),
    ],
)
def test_habit_applies_only_between_its_start_and_its_end(
    make_habit: HabitFactory, day: date, expected: bool
) -> None:
    habit = make_habit(start=date(2026, 6, 1), end=date(2026, 6, 5))
    assert habit.applies_on(day) is expected


def test_habit_without_end_applies_indefinitely(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 1))
    assert habit.applies_on(date(2030, 1, 1))


def test_habit_applies_on_the_days_its_frequency_says(make_habit: HabitFactory) -> None:
    fridays = make_habit(frequency=Weekdays(frozenset({Weekday.FRIDAY})))
    assert fridays.applies_on(date(2026, 6, 12))
    assert not fridays.applies_on(date(2026, 6, 11))


def test_habit_end_cuts_off_a_frequency_that_would_continue(make_habit: HabitFactory) -> None:
    fixed = make_habit(
        frequency=FixedDates((date(2026, 6, 3), date(2026, 6, 20))), end=date(2026, 6, 10)
    )
    assert fixed.applies_on(date(2026, 6, 3))
    assert not fixed.applies_on(date(2026, 6, 20))


# ---------- is_done / is_active ----------


def test_a_day_is_done_when_it_is_a_completion(make_habit: HabitFactory) -> None:
    habit = make_habit(done=[TODAY])
    assert habit.is_done(TODAY)
    assert not habit.is_done(date(2026, 6, 10))


def test_a_day_with_a_recorded_value_is_done(make_habit: HabitFactory) -> None:
    habit = make_habit(completions={TODAY: 3.0})
    assert habit.is_done(TODAY)


def test_a_recorded_value_of_zero_is_still_a_done_day(make_habit: HabitFactory) -> None:
    habit = make_habit(completions={TODAY: 0.0})
    assert habit.is_done(TODAY)


@pytest.mark.parametrize(
    ("end", "expected"),
    [
        pytest.param(None, True, id="no-end"),
        pytest.param(date(2026, 12, 31), True, id="ends-later"),
        pytest.param(TODAY, True, id="ends-today"),
        pytest.param(date(2026, 6, 10), False, id="ended-yesterday"),
    ],
)
def test_habit_is_active_until_its_end_day_has_passed(
    make_habit: HabitFactory, end: date | None, expected: bool
) -> None:
    assert make_habit(end=end).is_active(TODAY) is expected


# ---------- previous_scheduled / next_scheduled ----------


def test_previous_scheduled_includes_the_day_itself_by_default(make_habit: HabitFactory) -> None:
    habit = make_habit()
    assert habit.previous_scheduled(TODAY) == TODAY


def test_previous_scheduled_can_exclude_the_day_itself(make_habit: HabitFactory) -> None:
    habit = make_habit()
    assert habit.previous_scheduled(TODAY, inclusive=False) == date(2026, 6, 10)


def test_previous_scheduled_is_none_before_the_start(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 1))
    assert habit.previous_scheduled(date(2026, 5, 31)) is None
    assert habit.previous_scheduled(date(2026, 6, 1), inclusive=False) is None


def test_previous_scheduled_of_an_ended_habit_starts_from_its_last_day(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(start=date(2026, 6, 1), end=date(2026, 6, 5))
    assert habit.previous_scheduled(TODAY) == date(2026, 6, 5)
    assert habit.previous_scheduled(TODAY, inclusive=False) == date(2026, 6, 5)


def test_previous_scheduled_of_an_ended_habit_with_gaps_finds_its_last_due_day(
    make_habit: HabitFactory,
) -> None:
    mondays = make_habit(
        frequency=Weekdays(frozenset({Weekday.MONDAY})),
        start=date(2026, 5, 1),
        end=date(2026, 6, 10),
    )
    assert mondays.previous_scheduled(date(2026, 12, 1)) == date(2026, 6, 8)


def test_next_scheduled_is_strictly_after_the_day(make_habit: HabitFactory) -> None:
    habit = make_habit()
    assert habit.next_scheduled(TODAY) == date(2026, 6, 12)


def test_next_scheduled_before_the_start_is_the_start(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 7, 1))
    assert habit.next_scheduled(TODAY) == date(2026, 7, 1)


def test_next_scheduled_is_none_once_the_habit_has_ended(make_habit: HabitFactory) -> None:
    habit = make_habit(end=TODAY)
    assert habit.next_scheduled(TODAY) is None


def test_next_scheduled_may_land_on_the_end_day(make_habit: HabitFactory) -> None:
    habit = make_habit(end=date(2026, 6, 12))
    assert habit.next_scheduled(TODAY) == date(2026, 6, 12)


def test_next_scheduled_is_none_when_the_next_due_day_is_after_the_end(
    make_habit: HabitFactory,
) -> None:
    fridays = make_habit(frequency=Weekdays(frozenset({Weekday.FRIDAY})), end=date(2026, 6, 11))
    assert fridays.next_scheduled(TODAY) is None


@pytest.mark.parametrize(
    "frequency",
    [
        pytest.param(Daily(), id="daily"),
        pytest.param(Quota(times=3), id="quota"),
        pytest.param(Interval(3, IntervalUnit.DAYS), id="interval"),
    ],
)
def test_next_scheduled_follows_each_frequency_after_the_start(
    make_habit: HabitFactory, frequency: Daily | Quota | Interval
) -> None:
    habit = make_habit(frequency=frequency, start=date(2026, 6, 20))
    assert habit.next_scheduled(date(2026, 6, 1)) == date(2026, 6, 20)
