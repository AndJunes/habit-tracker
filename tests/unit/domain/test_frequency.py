"""Frequency value types: when a habit is due, its latest due day and its next one."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from habit_tracker.domain.enums import IntervalUnit, Period, Weekday
from habit_tracker.domain.errors import ErrorCode
from habit_tracker.domain.frequency import (
    Daily,
    FixedDates,
    Frequency,
    Interval,
    Quota,
    Weekdays,
)

RaisesCode = Callable[[ErrorCode], AbstractContextManager[None]]

TODAY = date(2026, 6, 11)  # a Thursday
START = date(2026, 5, 1)  # a Friday

MONDAY_AND_FRIDAY = Weekdays(frozenset({Weekday.MONDAY, Weekday.FRIDAY}))
FRIDAYS = Weekdays(frozenset({Weekday.FRIDAY}))
CHOSEN_DATES = FixedDates(
    (date(2026, 5, 20), date(2026, 6, 3), date(2026, 6, 10), date(2026, 6, 20))
)


def months(every: int) -> Interval:
    return Interval(every, IntervalUnit.MONTHS)


# ---------- Daily ----------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 5, 31), False, id="before-start"),
        pytest.param(date(2026, 6, 1), True, id="start-day"),
        pytest.param(date(2026, 6, 2), True, id="after-start"),
    ],
)
def test_daily_is_due_from_the_start_day_onwards(day: date, expected: bool) -> None:
    assert Daily().occurs_on(day, date(2026, 6, 1)) is expected


def test_daily_latest_due_day_is_the_day_itself() -> None:
    assert Daily().last_on_or_before(TODAY, START) == TODAY


def test_daily_has_no_due_day_before_the_start() -> None:
    assert Daily().last_on_or_before(date(2026, 4, 30), START) is None


def test_daily_first_due_day_after_is_the_next_day() -> None:
    assert Daily().first_after(TODAY, START) == date(2026, 6, 12)


def test_daily_first_due_day_before_the_start_is_the_start() -> None:
    assert Daily().first_after(date(2026, 4, 1), START) == START


# ---------- Weekdays ----------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 6, 12), True, id="friday"),
        pytest.param(date(2026, 6, 11), False, id="thursday"),
        pytest.param(date(2026, 6, 13), False, id="saturday"),
    ],
)
def test_weekdays_are_due_only_on_the_chosen_days(day: date, expected: bool) -> None:
    assert FRIDAYS.occurs_on(day, START) is expected


def test_weekdays_are_not_due_on_a_chosen_day_before_the_start() -> None:
    friday_before_start = date(2026, 4, 24)
    assert not FRIDAYS.occurs_on(friday_before_start, START)
    assert FRIDAYS.occurs_on(START, START)  # the start day is itself a Friday


def test_weekdays_with_several_days_are_due_on_each_of_them() -> None:
    week = [date(2026, 6, number) for number in range(8, 15)]
    due = [day for day in week if MONDAY_AND_FRIDAY.occurs_on(day, START)]
    assert due == [date(2026, 6, 8), date(2026, 6, 12)]


def test_weekdays_latest_due_day_looks_back_across_days_off() -> None:
    assert MONDAY_AND_FRIDAY.last_on_or_before(TODAY, START) == date(2026, 6, 8)


def test_weekdays_latest_due_day_includes_the_day_itself() -> None:
    assert MONDAY_AND_FRIDAY.last_on_or_before(date(2026, 6, 12), START) == date(2026, 6, 12)


def test_weekdays_have_no_due_day_before_the_start() -> None:
    assert MONDAY_AND_FRIDAY.last_on_or_before(date(2026, 4, 30), START) is None


def test_weekdays_first_due_day_after_skips_days_off() -> None:
    assert MONDAY_AND_FRIDAY.first_after(TODAY, START) == date(2026, 6, 12)
    assert MONDAY_AND_FRIDAY.first_after(date(2026, 6, 12), START) == date(2026, 6, 15)


def test_weekdays_first_due_day_is_never_before_the_start() -> None:
    wednesday_start = date(2026, 5, 6)
    assert MONDAY_AND_FRIDAY.first_after(date(2026, 4, 1), wednesday_start) == date(2026, 5, 8)


def test_weekdays_given_as_numbers_become_weekday_members() -> None:
    frequency = Weekdays(frozenset({0, 4}))  # type: ignore[arg-type]
    assert {type(day) for day in frequency.days} == {Weekday}


# ---------- Quota ----------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(TODAY, True, id="today"),
        pytest.param(date(2026, 6, 8), True, id="monday"),
        pytest.param(date(2026, 4, 30), False, id="before-start"),
    ],
)
def test_quota_is_due_any_day_from_the_start(day: date, expected: bool) -> None:
    assert Quota(times=3).occurs_on(day, START) is expected


def test_quota_preferred_days_do_not_change_when_it_is_due() -> None:
    plain = Quota(times=3)
    hinted = Quota(times=3, preferred=frozenset({Weekday.MONDAY, Weekday.WEDNESDAY}))
    days = [date(2026, 6, number) for number in range(1, 31)]
    assert [hinted.occurs_on(day, START) for day in days] == [
        plain.occurs_on(day, START) for day in days
    ]


def test_quota_defaults_to_a_weekly_period_without_preferred_days() -> None:
    quota = Quota(times=3)
    assert quota.period is Period.WEEK
    assert quota.preferred == frozenset()


def test_quota_period_given_as_text_becomes_a_period() -> None:
    assert Quota(times=2, period="month").period is Period.MONTH  # type: ignore[arg-type]


def test_quota_preferred_days_given_as_numbers_become_weekdays() -> None:
    quota = Quota(times=2, preferred=frozenset({0, 2}))  # type: ignore[arg-type]
    assert quota.preferred == frozenset({Weekday.MONDAY, Weekday.WEDNESDAY})
    assert {type(day) for day in quota.preferred} == {Weekday}


@pytest.mark.parametrize(
    ("times", "period"),
    [
        pytest.param(1, Period.WEEK, id="minimum-weekly"),
        pytest.param(7, Period.WEEK, id="maximum-weekly"),
        pytest.param(1, Period.MONTH, id="minimum-monthly"),
        pytest.param(31, Period.MONTH, id="maximum-monthly"),
    ],
)
def test_quota_accepts_the_limits_of_its_period(times: int, period: Period) -> None:
    assert Quota(times=times, period=period).times == times


@pytest.mark.parametrize(
    ("times", "period"),
    [
        pytest.param(0, Period.WEEK, id="zero"),
        pytest.param(-1, Period.WEEK, id="negative"),
        pytest.param(8, Period.WEEK, id="above-weekly-limit"),
        pytest.param(32, Period.MONTH, id="above-monthly-limit"),
        pytest.param(True, Period.WEEK, id="bool"),
        pytest.param(False, Period.MONTH, id="false"),
        pytest.param(3.0, Period.WEEK, id="float"),
    ],
)
def test_quota_rejects_times_outside_its_period_or_not_an_integer(
    times: Any, period: Period, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.QUOTA_OUT_OF_RANGE):
        Quota(times=times, period=period)


def test_quota_rejects_an_unknown_period() -> None:
    with pytest.raises(ValueError, match="year"):
        Quota(times=2, period="year")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 6, 11), (date(2026, 6, 8), date(2026, 6, 14)), id="thursday"),
        pytest.param(date(2026, 6, 8), (date(2026, 6, 8), date(2026, 6, 14)), id="monday"),
        pytest.param(date(2026, 6, 14), (date(2026, 6, 8), date(2026, 6, 14)), id="sunday"),
        pytest.param(date(2026, 12, 31), (date(2026, 12, 28), date(2027, 1, 3)), id="new-year"),
        pytest.param(date(2026, 6, 1), (date(2026, 6, 1), date(2026, 6, 7)), id="month-start"),
    ],
)
def test_weekly_quota_period_runs_from_monday_to_sunday(
    day: date, expected: tuple[date, date]
) -> None:
    assert Quota(times=3).period_bounds(day) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 6, 11), (date(2026, 6, 1), date(2026, 6, 30)), id="thirty-days"),
        pytest.param(date(2026, 7, 31), (date(2026, 7, 1), date(2026, 7, 31)), id="thirty-one"),
        pytest.param(date(2026, 2, 10), (date(2026, 2, 1), date(2026, 2, 28)), id="february"),
        pytest.param(date(2028, 2, 10), (date(2028, 2, 1), date(2028, 2, 29)), id="leap-february"),
        pytest.param(date(2026, 12, 1), (date(2026, 12, 1), date(2026, 12, 31)), id="december"),
    ],
)
def test_monthly_quota_period_is_the_calendar_month(
    day: date, expected: tuple[date, date]
) -> None:
    assert Quota(times=2, period=Period.MONTH).period_bounds(day) == expected


# ---------- FixedDates ----------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 6, 3), True, id="chosen-day"),
        pytest.param(date(2026, 6, 4), False, id="other-day"),
        pytest.param(date(2026, 6, 20), True, id="chosen-day-in-the-future"),
    ],
)
def test_fixed_dates_are_due_only_on_the_chosen_days(day: date, expected: bool) -> None:
    assert CHOSEN_DATES.occurs_on(day, START) is expected


def test_fixed_dates_before_the_start_are_never_due() -> None:
    june_start = date(2026, 6, 1)
    assert not CHOSEN_DATES.occurs_on(date(2026, 5, 20), june_start)
    assert CHOSEN_DATES.last_on_or_before(date(2026, 5, 31), june_start) is None
    assert CHOSEN_DATES.first_after(date(2026, 1, 1), june_start) == date(2026, 6, 3)


def test_fixed_dates_are_kept_sorted_and_without_repeats() -> None:
    frequency = FixedDates((date(2026, 6, 10), date(2026, 5, 20), date(2026, 6, 10)))
    assert frequency.dates == (date(2026, 5, 20), date(2026, 6, 10))


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 6, 9), date(2026, 6, 3), id="between-two-dates"),
        pytest.param(date(2026, 6, 10), date(2026, 6, 10), id="on-a-date"),
        pytest.param(date(2026, 12, 1), date(2026, 6, 20), id="after-the-last"),
        pytest.param(date(2026, 5, 19), None, id="before-the-first"),
    ],
)
def test_fixed_dates_latest_due_day(day: date, expected: date | None) -> None:
    assert CHOSEN_DATES.last_on_or_before(day, START) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 6, 10), date(2026, 6, 20), id="after-a-date"),
        pytest.param(date(2026, 6, 4), date(2026, 6, 10), id="between-two-dates"),
        pytest.param(date(2026, 1, 1), date(2026, 5, 20), id="before-the-first"),
        pytest.param(date(2026, 6, 20), None, id="after-the-last"),
    ],
)
def test_fixed_dates_first_due_day_after(day: date, expected: date | None) -> None:
    assert CHOSEN_DATES.first_after(day, START) == expected


def test_fixed_dates_more_than_a_year_apart_are_still_neighbours() -> None:
    frequency = FixedDates((date(2025, 1, 10), date(2026, 6, 10)))
    start = date(2025, 1, 1)
    assert frequency.last_on_or_before(date(2026, 6, 9), start) == date(2025, 1, 10)
    assert frequency.first_after(date(2025, 1, 10), start) == date(2026, 6, 10)
    assert frequency.first_after(date(2026, 6, 10), start) is None


@pytest.mark.parametrize(
    ("build", "code"),
    [
        pytest.param(lambda: FixedDates(()), ErrorCode.DATES_REQUIRED, id="no-dates"),
        pytest.param(
            lambda: FixedDates(("2026-06-01",)),  # type: ignore[arg-type]
            ErrorCode.DATE_INVALID,
            id="date-as-text",
        ),
        pytest.param(
            lambda: FixedDates((datetime(2026, 6, 1, 9, 0),)),
            ErrorCode.DATE_INVALID,
            id="datetime-instead-of-date",
        ),
    ],
)
def test_fixed_dates_reject_missing_or_malformed_dates(
    build: Callable[[], object], code: ErrorCode, raises_code: RaisesCode
) -> None:
    with raises_code(code):
        build()


# ---------- Interval: days and weeks ----------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 6, 1), True, id="start-day"),
        pytest.param(date(2026, 6, 4), True, id="three-days-later"),
        pytest.param(date(2026, 6, 10), True, id="nine-days-later"),
        pytest.param(date(2026, 6, 2), False, id="off-day"),
        pytest.param(date(2026, 5, 29), False, id="before-start"),
    ],
)
def test_every_three_days_counts_from_the_start(day: date, expected: bool) -> None:
    assert Interval(3, IntervalUnit.DAYS).occurs_on(day, date(2026, 6, 1)) is expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 5, 4), True, id="start-day"),
        pytest.param(date(2026, 5, 11), False, id="after-one-week"),
        pytest.param(date(2026, 5, 18), True, id="after-two-weeks"),
        pytest.param(date(2026, 6, 1), True, id="after-four-weeks"),
        pytest.param(date(2026, 6, 15), True, id="after-six-weeks"),
    ],
)
def test_every_two_weeks_counts_from_the_start(day: date, expected: bool) -> None:
    assert Interval(2, IntervalUnit.WEEKS).occurs_on(day, date(2026, 5, 4)) is expected


def test_interval_latest_and_next_due_days_step_from_the_start() -> None:
    every_three_days = Interval(3, IntervalUnit.DAYS)
    start = date(2026, 6, 1)
    assert every_three_days.last_on_or_before(TODAY, start) == date(2026, 6, 10)
    assert every_three_days.first_after(TODAY, start) == date(2026, 6, 13)
    assert every_three_days.first_after(date(2026, 6, 10), start) == date(2026, 6, 13)


def test_interval_has_no_due_day_before_the_start_and_first_one_is_the_start() -> None:
    every_three_days = Interval(3, IntervalUnit.DAYS)
    start = date(2026, 6, 1)
    assert every_three_days.last_on_or_before(date(2026, 5, 31), start) is None
    assert every_three_days.first_after(date(2026, 5, 20), start) == start


def test_every_two_weeks_latest_and_next_due_days() -> None:
    every_two_weeks = Interval(2, IntervalUnit.WEEKS)
    start = date(2026, 5, 4)
    assert every_two_weeks.last_on_or_before(TODAY, start) == date(2026, 6, 1)
    assert every_two_weeks.first_after(TODAY, start) == date(2026, 6, 15)


# ---------- Interval: months ----------


def test_every_two_months_counts_whole_months_from_the_start() -> None:
    frequency = months(2)
    start = date(2026, 1, 15)
    assert frequency.occurs_on(date(2026, 3, 15), start)
    assert frequency.occurs_on(date(2026, 5, 15), start)
    assert not frequency.occurs_on(date(2026, 2, 15), start)
    assert not frequency.occurs_on(date(2026, 4, 15), start)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 2, 28), True, id="clamped-to-february-28"),
        pytest.param(date(2026, 2, 27), False, id="day-before-clamped"),
        pytest.param(date(2026, 3, 31), True, id="back-to-the-31st"),
        pytest.param(date(2026, 3, 28), False, id="does-not-drift-to-the-28th"),
        pytest.param(date(2026, 4, 30), True, id="clamped-to-april-30"),
        pytest.param(date(2026, 4, 28), False, id="april-28"),
    ],
)
def test_monthly_interval_from_the_31st_is_due_on_the_clamped_day(
    day: date, expected: bool
) -> None:
    assert months(1).occurs_on(day, date(2026, 1, 31)) is expected


def test_monthly_interval_from_the_31st_never_drifts_after_a_short_month() -> None:
    start = date(2026, 1, 31)
    walked = [start]
    while len(walked) < 12:
        following = months(1).first_after(walked[-1], start)
        assert following is not None
        walked.append(following)
    assert walked == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
        date(2026, 6, 30),
        date(2026, 7, 31),
        date(2026, 8, 31),
        date(2026, 9, 30),
        date(2026, 10, 31),
        date(2026, 11, 30),
        date(2026, 12, 31),
    ]


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2026, 2, 27), date(2026, 1, 31), id="before-the-clamped-day"),
        pytest.param(date(2026, 2, 28), date(2026, 2, 28), id="on-the-clamped-day"),
        pytest.param(date(2026, 3, 30), date(2026, 2, 28), id="after-the-clamped-day"),
        pytest.param(date(2026, 3, 31), date(2026, 3, 31), id="back-to-the-31st"),
    ],
)
def test_monthly_interval_latest_due_day_uses_the_clamped_day(day: date, expected: date) -> None:
    assert months(1).last_on_or_before(day, date(2026, 1, 31)) == expected


def test_monthly_interval_from_the_31st_uses_february_29_in_a_leap_year() -> None:
    start = date(2028, 1, 31)
    assert months(1).occurs_on(date(2028, 2, 29), start)
    assert not months(1).occurs_on(date(2028, 2, 28), start)
    assert months(1).first_after(start, start) == date(2028, 2, 29)
    assert months(1).first_after(date(2028, 2, 29), start) == date(2028, 3, 31)


def test_yearly_interval_from_february_29_falls_on_february_28_until_the_next_leap_year() -> None:
    start = date(2028, 2, 29)
    walked = [start]
    while len(walked) < 5:
        following = months(12).first_after(walked[-1], start)
        assert following is not None
        walked.append(following)
    assert walked == [
        date(2028, 2, 29),
        date(2029, 2, 28),
        date(2030, 2, 28),
        date(2031, 2, 28),
        date(2032, 2, 29),
    ]


def test_monthly_interval_crosses_the_year_boundary() -> None:
    start = date(2025, 11, 30)
    assert months(1).first_after(date(2025, 11, 30), start) == date(2025, 12, 30)
    assert months(1).first_after(date(2025, 12, 30), start) == date(2026, 1, 30)
    assert months(1).first_after(date(2026, 1, 30), start) == date(2026, 2, 28)


def test_interval_of_fourteen_months_reaches_past_a_year() -> None:
    frequency = months(14)
    start = date(2025, 1, 10)
    assert frequency.occurs_on(date(2026, 3, 10), start)
    assert not frequency.occurs_on(date(2025, 9, 10), start)
    assert frequency.last_on_or_before(TODAY, start) == date(2026, 3, 10)
    assert frequency.first_after(date(2026, 3, 10), start) == date(2027, 5, 10)


def test_monthly_interval_has_no_due_day_before_the_start() -> None:
    start = date(2026, 1, 31)
    assert months(1).last_on_or_before(date(2026, 1, 30), start) is None
    assert months(1).first_after(date(2025, 6, 1), start) == start


# ---------- All types: the three questions agree with each other ----------

SCAN_CASES = [
    pytest.param(Daily(), date(2026, 6, 1), id="daily"),
    pytest.param(MONDAY_AND_FRIDAY, date(2026, 5, 6), id="monday-and-friday"),
    pytest.param(Weekdays(frozenset({Weekday.SUNDAY})), date(2026, 5, 6), id="sundays"),
    pytest.param(Quota(3), date(2026, 5, 1), id="weekly-quota"),
    pytest.param(Quota(2, Period.MONTH), date(2026, 5, 1), id="monthly-quota"),
    pytest.param(Interval(3, IntervalUnit.DAYS), date(2026, 5, 30), id="every-3-days"),
    pytest.param(Interval(2, IntervalUnit.WEEKS), date(2026, 5, 4), id="every-2-weeks"),
    pytest.param(months(1), date(2026, 1, 31), id="monthly-from-the-31st"),
    pytest.param(months(2), date(2026, 1, 31), id="every-2-months-from-the-31st"),
    pytest.param(months(5), date(2028, 2, 29), id="every-5-months-from-leap-day"),
    pytest.param(months(14), date(2025, 1, 10), id="every-14-months"),
    pytest.param(CHOSEN_DATES, date(2026, 6, 1), id="fixed-dates"),
    pytest.param(
        FixedDates((date(2026, 5, 20), date(2026, 6, 20), date(2027, 8, 1))),
        date(2026, 5, 1),
        id="fixed-dates-over-a-year-apart",
    ),
]


@pytest.mark.parametrize(("frequency", "start"), SCAN_CASES)
def test_latest_and_next_due_days_match_a_day_by_day_scan(
    frequency: Frequency, start: date
) -> None:
    window = [start - timedelta(days=15) + timedelta(days=offset) for offset in range(1100)]
    due = [day for day in window if frequency.occurs_on(day, start)]
    for day in window[:500]:
        expected_last = max((item for item in due if item <= day), default=None)
        expected_next = min((item for item in due if item > day), default=None)
        assert frequency.last_on_or_before(day, start) == expected_last, f"last on/before {day}"
        assert frequency.first_after(day, start) == expected_next, f"first after {day}"


# ---------- Interval constructor ----------


@pytest.mark.parametrize(
    "every",
    [
        pytest.param(0, id="zero"),
        pytest.param(-3, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param(2.0, id="float"),
    ],
)
def test_interval_rejects_an_every_that_is_not_a_positive_integer(
    every: Any, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.INTERVAL_INVALID):
        Interval(every, IntervalUnit.DAYS)


def test_interval_unit_given_as_text_becomes_an_interval_unit() -> None:
    assert Interval(2, "weeks").unit is IntervalUnit.WEEKS  # type: ignore[arg-type]


def test_interval_rejects_an_unknown_unit() -> None:
    with pytest.raises(ValueError, match="fortnights"):
        Interval(2, "fortnights")  # type: ignore[arg-type]


# ---------- Weekdays constructor ----------


def test_weekdays_require_at_least_one_day(raises_code: RaisesCode) -> None:
    with raises_code(ErrorCode.WEEKDAYS_REQUIRED):
        Weekdays(frozenset())


def test_weekdays_reject_a_number_that_is_not_a_weekday() -> None:
    with pytest.raises(ValueError, match="7"):
        Weekdays(frozenset({7}))  # type: ignore[arg-type]


# ---------- Value semantics ----------


@pytest.mark.parametrize(
    ("frequency", "attribute"),
    [
        pytest.param(FRIDAYS, "days", id="weekdays"),
        pytest.param(Quota(times=3), "times", id="quota"),
        pytest.param(CHOSEN_DATES, "dates", id="fixed-dates"),
        pytest.param(Interval(2, IntervalUnit.WEEKS), "every", id="interval"),
    ],
)
def test_frequencies_cannot_be_modified(frequency: Frequency, attribute: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(frequency, attribute, None)


def test_frequencies_with_the_same_data_are_equal_and_share_a_hash() -> None:
    assert Interval(2, IntervalUnit.WEEKS) == Interval(2, IntervalUnit.WEEKS)
    assert hash(Interval(2, IntervalUnit.WEEKS)) == hash(Interval(2, IntervalUnit.WEEKS))
    assert Daily() == Daily()
    assert Quota(3) != Quota(3, Period.MONTH)
