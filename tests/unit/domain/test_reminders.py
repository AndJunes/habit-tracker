"""When a habit's reminder is due: its time, its grace period and the days it applies."""

from collections.abc import Callable
from datetime import date, datetime, time

import pytest

from habit_tracker.domain.enums import IntervalUnit, Period, Weekday
from habit_tracker.domain.frequency import FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import Habit, Reminder
from habit_tracker.domain.reminders import GRACE_MINUTES, is_reminder_due

HabitFactory = Callable[..., Habit]

TODAY = date(2026, 6, 11)  # a Thursday
EVENING = Reminder(at=time(20, 0))
FRIDAYS = Weekdays(frozenset({Weekday.FRIDAY}))


def at(hour: int, minute: int, second: int = 0, *, day: int = 11) -> datetime:
    return datetime(2026, 6, day, hour, minute, second)


def june(*days: int) -> list[date]:
    return [date(2026, 6, number) for number in days]


def test_the_grace_period_is_one_hour() -> None:
    assert GRACE_MINUTES == 60


def test_a_habit_without_a_reminder_is_never_due(make_habit: HabitFactory) -> None:
    assert not is_reminder_due(make_habit(reminder=None), at(20, 0))


# ---------- The time window ----------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        pytest.param(at(19, 59), False, id="a-minute-early"),
        pytest.param(at(20, 0), True, id="exactly-on-time"),
        pytest.param(at(20, 1), True, id="a-minute-late"),
        pytest.param(at(20, 59), True, id="last-minute-of-the-grace-period"),
        pytest.param(at(21, 0), False, id="an-hour-late"),
        pytest.param(at(23, 30), False, id="hours-late"),
        pytest.param(at(6, 0), False, id="hours-early"),
    ],
)
def test_a_reminder_is_due_from_its_time_until_the_grace_period_ends(
    make_habit: HabitFactory, now: datetime, expected: bool
) -> None:
    assert is_reminder_due(make_habit(reminder=EVENING), now) is expected


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        pytest.param(at(19, 59, 59), False, id="a-second-before-the-minute"),
        pytest.param(at(20, 0, 59), True, id="seconds-into-the-minute"),
        pytest.param(at(20, 59, 59), True, id="seconds-before-the-end"),
        pytest.param(at(21, 0, 0), False, id="the-end"),
    ],
)
def test_the_window_is_measured_in_whole_minutes(
    make_habit: HabitFactory, now: datetime, expected: bool
) -> None:
    assert is_reminder_due(make_habit(reminder=EVENING), now) is expected


def test_a_reminder_does_not_carry_over_midnight(make_habit: HabitFactory) -> None:
    late = make_habit(reminder=Reminder(at=time(23, 30)))
    assert is_reminder_due(late, at(23, 59))
    assert not is_reminder_due(late, at(0, 10, day=12))


# ---------- Done habits ----------


def test_a_habit_already_done_today_is_not_reminded(make_habit: HabitFactory) -> None:
    habit = make_habit(reminder=EVENING, done=june(11))
    assert not is_reminder_due(habit, at(20, 0))


def test_a_habit_done_only_on_other_days_is_still_reminded(make_habit: HabitFactory) -> None:
    habit = make_habit(reminder=EVENING, done=june(9, 10, 12))
    assert is_reminder_due(habit, at(20, 0))


# ---------- Which days ----------


def test_a_reminder_with_chosen_weekdays_only_fires_on_them(make_habit: HabitFactory) -> None:
    morning = Reminder(at=time(8, 0), weekdays=frozenset({Weekday.MONDAY, Weekday.FRIDAY}))
    habit = make_habit(reminder=morning)
    assert not is_reminder_due(habit, at(8, 0))  # Thursday
    assert is_reminder_due(habit, at(8, 0, day=12))  # Friday
    assert is_reminder_due(habit, at(8, 0, day=8))  # Monday


def test_a_reminder_without_weekdays_fires_on_the_days_the_habit_is_due(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(frequency=FRIDAYS, reminder=Reminder(at=time(8, 0)))
    assert not is_reminder_due(habit, at(8, 0))  # Thursday: not due
    assert is_reminder_due(habit, at(8, 0, day=12))  # Friday


def test_chosen_weekdays_take_precedence_over_the_habit_schedule(
    make_habit: HabitFactory,
) -> None:
    mondays = Reminder(at=time(8, 0), weekdays=frozenset({Weekday.MONDAY}))
    habit = make_habit(frequency=FRIDAYS, reminder=mondays)
    assert is_reminder_due(habit, at(8, 0, day=8))  # Monday: chosen, although not due
    assert not is_reminder_due(habit, at(8, 0, day=12))  # Friday: due, but not chosen


def test_a_reminder_without_weekdays_follows_fixed_dates(make_habit: HabitFactory) -> None:
    reminder = Reminder(at=time(8, 0))
    on_the_day = make_habit(frequency=FixedDates((TODAY,)), reminder=reminder)
    another_day = make_habit(frequency=FixedDates((date(2026, 6, 12),)), reminder=reminder)
    assert is_reminder_due(on_the_day, at(8, 0))
    assert not is_reminder_due(another_day, at(8, 0))


def test_a_reminder_without_weekdays_follows_an_interval(make_habit: HabitFactory) -> None:
    reminder = Reminder(at=time(8, 0))
    every_two_days = Interval(2, IntervalUnit.DAYS)
    due_today = make_habit(frequency=every_two_days, start=date(2026, 6, 9), reminder=reminder)
    off_today = make_habit(frequency=every_two_days, start=date(2026, 6, 10), reminder=reminder)
    assert is_reminder_due(due_today, at(8, 0))
    assert not is_reminder_due(off_today, at(8, 0))


# ---------- Quotas ----------


def test_a_quota_reminder_stops_once_the_week_is_complete(make_habit: HabitFactory) -> None:
    habit = make_habit(frequency=Quota(times=2), reminder=EVENING, done=june(8, 9))
    assert not is_reminder_due(habit, at(20, 0))


def test_a_quota_reminder_keeps_going_while_the_week_is_incomplete(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(frequency=Quota(times=2), reminder=EVENING, done=june(8))
    assert is_reminder_due(habit, at(20, 0))


def test_a_quota_completed_in_a_previous_week_does_not_silence_this_week(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(frequency=Quota(times=2), reminder=EVENING, done=june(1, 2))
    assert is_reminder_due(habit, at(20, 0))


def test_a_monthly_quota_reminder_stops_once_the_month_is_complete(
    make_habit: HabitFactory,
) -> None:
    monthly = Quota(times=2, period=Period.MONTH)
    complete = make_habit(frequency=monthly, reminder=EVENING, done=june(1, 3))
    incomplete = make_habit(frequency=monthly, reminder=EVENING, done=june(1))
    assert not is_reminder_due(complete, at(20, 0))
    assert is_reminder_due(incomplete, at(20, 0))


def test_a_completed_quota_stays_silent_even_on_a_chosen_weekday(
    make_habit: HabitFactory,
) -> None:
    thursdays = Reminder(at=time(20, 0), weekdays=frozenset({Weekday.THURSDAY}))
    habit = make_habit(frequency=Quota(times=2), reminder=thursdays, done=june(8, 9))
    assert not is_reminder_due(habit, at(20, 0))


# ---------- The habit's life span ----------


def test_a_reminder_after_the_habit_ended_is_not_due(make_habit: HabitFactory) -> None:
    habit = make_habit(reminder=EVENING, end=date(2026, 6, 10))
    assert not is_reminder_due(habit, at(20, 0))


def test_a_reminder_before_the_habit_starts_is_not_due(make_habit: HabitFactory) -> None:
    habit = make_habit(reminder=EVENING, start=date(2026, 6, 12))
    assert not is_reminder_due(habit, at(20, 0))


def test_a_reminder_fires_on_the_start_day(make_habit: HabitFactory) -> None:
    habit = make_habit(reminder=EVENING, start=TODAY)
    assert is_reminder_due(habit, at(20, 0))


def test_a_reminder_fires_on_the_end_day(make_habit: HabitFactory) -> None:
    habit = make_habit(reminder=EVENING, end=TODAY)
    assert is_reminder_due(habit, at(20, 0))


def test_chosen_weekdays_do_not_extend_the_habit_beyond_its_life_span(
    make_habit: HabitFactory,
) -> None:
    thursdays = Reminder(at=time(20, 0), weekdays=frozenset({Weekday.THURSDAY}))
    ended = make_habit(reminder=thursdays, end=date(2026, 6, 10))
    assert not is_reminder_due(ended, at(20, 0))
