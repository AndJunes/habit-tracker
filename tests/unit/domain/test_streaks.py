"""Streaks: consecutive due days (or consecutive quota periods) and the best one ever."""

from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.frequency import FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import Habit, Measurement
from habit_tracker.domain.streaks import best_streak, count_in_period, current_streak

HabitFactory = Callable[..., Habit]

TODAY = date(2026, 6, 11)  # a Thursday: its week runs from Monday 8 to Sunday 14

FRIDAYS = Weekdays(frozenset({Weekday.FRIDAY}))
THREE_A_WEEK = Quota(times=3)
CHOSEN_DATES = FixedDates(
    (date(2026, 5, 20), date(2026, 6, 3), date(2026, 6, 10), date(2026, 6, 20))
)


def may(*days: int) -> list[date]:
    return [date(2026, 5, number) for number in days]


def june(*days: int) -> list[date]:
    return [date(2026, 6, number) for number in days]


# ---------- current_streak: daily habits ----------


def test_streak_counts_the_consecutive_done_days_including_today(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(start=date(2026, 6, 1), done=june(9, 10, 11))
    assert current_streak(habit, TODAY) == 3


def test_a_pending_today_does_not_break_the_streak(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 1), done=june(9, 10))
    assert current_streak(habit, TODAY) == 2


def test_a_missed_day_before_today_leaves_no_streak(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 1), done=june(8, 9))
    assert current_streak(habit, TODAY) == 0


def test_a_habit_without_completions_has_no_streak(make_habit: HabitFactory) -> None:
    assert current_streak(make_habit(), TODAY) == 0


def test_a_streak_stops_at_the_first_missed_day_going_back(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 1), done=june(1, 2, 4, 5, 6))
    assert current_streak(habit, TODAY) == 0
    assert current_streak(habit, date(2026, 6, 6)) == 3


def test_a_habit_that_has_not_started_has_no_streak(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 20))
    assert current_streak(habit, TODAY) == 0


def test_a_value_below_the_goal_still_extends_the_streak(make_habit: HabitFactory) -> None:
    goal = Measurement(MeasurementKind.QUANTITY, goal=10, unit="pages")
    habit = make_habit(measurement=goal, completions={TODAY: 2.0})
    assert current_streak(habit, TODAY) == 1


# ---------- current_streak: days off, fixed dates and intervals ----------


def test_streak_of_a_weekday_habit_only_counts_its_own_days(make_habit: HabitFactory) -> None:
    # Fridays May 29 and June 5 are done; Monday to Thursday do not break the streak.
    habit = make_habit(frequency=FRIDAYS, done=[date(2026, 5, 29), date(2026, 6, 5)])
    assert current_streak(habit, TODAY) == 2


def test_a_pending_due_day_that_is_today_does_not_break_a_weekday_streak(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(frequency=FRIDAYS, done=[date(2026, 6, 5)])
    assert current_streak(habit, date(2026, 6, 12)) == 1


def test_streak_ignores_completions_on_days_the_habit_is_not_due(
    make_habit: HabitFactory,
) -> None:
    saturday = date(2026, 5, 30)
    habit = make_habit(frequency=FRIDAYS, done=[date(2026, 5, 29), saturday, date(2026, 6, 5)])
    assert current_streak(habit, TODAY) == 2


def test_fixed_dates_streak_counts_consecutive_occasions(make_habit: HabitFactory) -> None:
    habit = make_habit(frequency=CHOSEN_DATES, done=[date(2026, 5, 20), *june(3, 10)])
    assert current_streak(habit, TODAY) == 3


def test_fixed_dates_most_recent_occasion_is_tolerated_even_after_it_has_passed(
    make_habit: HabitFactory,
) -> None:
    # The occasion of June 10 was not done; it is the latest one, so it does not break the streak.
    habit = make_habit(frequency=CHOSEN_DATES, done=[date(2026, 5, 20), date(2026, 6, 3)])
    assert current_streak(habit, TODAY) == 2


def test_fixed_dates_more_than_a_year_apart_keep_the_streak(make_habit: HabitFactory) -> None:
    dates = (date(2025, 1, 10), date(2026, 6, 10))
    habit = make_habit(frequency=FixedDates(dates), start=date(2025, 1, 1), done=dates)
    assert current_streak(habit, TODAY) == 2


@pytest.mark.parametrize(
    "today",
    [
        pytest.param(TODAY, id="today"),
        pytest.param(date(2027, 8, 1), id="a-year-later"),
    ],
)
def test_fixed_dates_streak_is_stable_once_every_date_has_passed(
    make_habit: HabitFactory, today: date
) -> None:
    dates = (date(2026, 5, 20), date(2026, 6, 1))
    habit = make_habit(frequency=FixedDates(dates), done=dates)
    assert current_streak(habit, today) == 2


def test_interval_streak_with_todays_occurrence_still_pending(make_habit: HabitFactory) -> None:
    # Every 3 days from May 30 it is due on May 30, Jun 2, 5, 8 and today, Jun 11.
    habit = make_habit(
        frequency=Interval(3, IntervalUnit.DAYS),
        start=date(2026, 5, 30),
        done=[date(2026, 5, 30), *june(2, 5, 8)],
    )
    assert current_streak(habit, TODAY) == 4


def test_fourteen_month_interval_streak_is_not_capped_at_a_year(make_habit: HabitFactory) -> None:
    habit = make_habit(
        frequency=Interval(14, IntervalUnit.MONTHS),
        start=date(2025, 1, 10),
        done=[date(2025, 1, 10), date(2026, 3, 10)],
    )
    assert current_streak(habit, TODAY) == 2


# ---------- current_streak: habits that have ended ----------


@pytest.mark.parametrize(
    "today",
    [
        pytest.param(date(2026, 6, 5), id="on-the-last-day"),
        pytest.param(date(2026, 6, 6), id="the-day-after"),
        pytest.param(TODAY, id="six-days-later"),
        pytest.param(date(2027, 1, 1), id="months-later"),
    ],
)
def test_the_streak_of_an_ended_habit_stays_frozen(make_habit: HabitFactory, today: date) -> None:
    habit = make_habit(start=date(2026, 6, 1), end=date(2026, 6, 5), done=june(3, 4, 5))
    assert current_streak(habit, today) == 3


# ---------- current_streak: quotas ----------


def test_quota_streak_counts_whole_periods_and_an_unfinished_current_one_does_not_break_it(
    make_habit: HabitFactory,
) -> None:
    # Two full weeks of three (May 25-31 and Jun 1-7); the current week has none yet.
    habit = make_habit(frequency=THREE_A_WEEK, done=[*may(25, 26, 27), *june(1, 2, 3)])
    assert current_streak(habit, TODAY) == 2


def test_quota_streak_adds_the_current_period_once_it_is_complete(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(frequency=THREE_A_WEEK, done=june(1, 2, 3, 8, 9, 10))
    assert current_streak(habit, TODAY) == 2


def test_quota_streak_is_zero_when_the_last_closed_period_fell_short(
    make_habit: HabitFactory,
) -> None:
    # Last week had 2 of 3 and this week is still empty.
    habit = make_habit(frequency=THREE_A_WEEK, done=june(1, 2))
    assert current_streak(habit, TODAY) == 0


def test_quota_streak_counts_months_for_a_monthly_quota(make_habit: HabitFactory) -> None:
    done = [
        date(2026, 3, 2),
        date(2026, 3, 10),
        date(2026, 4, 5),
        date(2026, 4, 6),
        date(2026, 5, 1),
        date(2026, 5, 20),
        date(2026, 6, 1),  # June has only 1 of 2 so far: pending, it does not break the streak
    ]
    habit = make_habit(
        frequency=Quota(times=2, period=Period.MONTH), start=date(2026, 3, 1), done=done
    )
    assert current_streak(habit, TODAY) == 3


def test_quota_streak_does_not_count_periods_before_the_habit_started(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(
        frequency=Quota(times=1), start=date(2026, 6, 8), done=[date(2026, 6, 1), date(2026, 6, 8)]
    )
    assert current_streak(habit, TODAY) == 1


def test_quota_streak_of_an_ended_habit_is_not_broken_by_a_period_cut_short(
    make_habit: HabitFactory,
) -> None:
    # It ends on Wednesday June 10: its last week (8-14) was cut off and incomplete.
    habit = make_habit(frequency=THREE_A_WEEK, end=date(2026, 6, 10), done=june(1, 2, 3, 8))
    assert current_streak(habit, TODAY) == 1


def test_quota_streak_of_an_ended_habit_is_zero_when_its_last_full_period_fell_short(
    make_habit: HabitFactory,
) -> None:
    # It ends on Sunday June 7: its last week (1-7) closed whole with 1 of 3.
    habit = make_habit(
        frequency=THREE_A_WEEK, end=date(2026, 6, 7), done=[*may(25, 26, 27), *june(1)]
    )
    assert current_streak(habit, TODAY) == 0


@pytest.mark.parametrize(
    "today",
    [
        pytest.param(date(2026, 6, 7), id="on-the-last-day"),
        pytest.param(TODAY, id="the-week-after"),
        pytest.param(date(2026, 7, 1), id="weeks-later"),
        pytest.param(date(2027, 1, 1), id="months-later"),
    ],
)
def test_the_quota_streak_of_an_ended_habit_stays_frozen(
    make_habit: HabitFactory, today: date
) -> None:
    done = [*may(25, 26, 27), *june(1, 2, 3)]
    habit = make_habit(frequency=THREE_A_WEEK, end=date(2026, 6, 7), done=done)
    assert current_streak(habit, today) == 2


def test_quota_streak_of_an_ended_habit_counts_its_last_period_when_it_was_met(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(frequency=THREE_A_WEEK, end=date(2026, 6, 7), done=june(1, 2, 3))
    assert current_streak(habit, TODAY) == 1


def test_quota_preferred_days_do_not_change_the_streak(make_habit: HabitFactory) -> None:
    done = [*may(25, 26, 27), *june(1, 2, 3, 8)]
    plain = make_habit(frequency=THREE_A_WEEK, done=done)
    hinted = make_habit(
        frequency=Quota(times=3, preferred=frozenset({Weekday.MONDAY, Weekday.WEDNESDAY})),
        done=done,
    )
    assert current_streak(hinted, TODAY) == current_streak(plain, TODAY)


# ---------- count_in_period ----------


def test_weekly_quota_counts_only_completions_of_the_current_week(
    make_habit: HabitFactory,
) -> None:
    # Friday June 5 belongs to the previous week.
    habit = make_habit(frequency=THREE_A_WEEK, done=june(5, 8, 10))
    assert count_in_period(habit, THREE_A_WEEK, TODAY) == 2


def test_monthly_quota_counts_only_completions_of_the_current_month(
    make_habit: HabitFactory,
) -> None:
    quota = Quota(times=4, period=Period.MONTH)
    habit = make_habit(frequency=quota, done=[date(2026, 5, 30), *june(2, 10)])
    assert count_in_period(habit, quota, TODAY) == 2


def test_the_week_includes_its_monday_and_its_sunday_but_not_the_neighbours(
    make_habit: HabitFactory,
) -> None:
    quota = Quota(times=7)
    habit = make_habit(frequency=quota, done=june(7, 8, 14, 15))
    assert count_in_period(habit, quota, TODAY) == 2


def test_the_month_includes_its_first_and_last_day_but_not_the_neighbours(
    make_habit: HabitFactory,
) -> None:
    quota = Quota(times=31, period=Period.MONTH)
    habit = make_habit(frequency=quota, done=[date(2026, 5, 31), *june(1, 30), date(2026, 7, 1)])
    assert count_in_period(habit, quota, TODAY) == 2


def test_count_in_period_of_a_period_without_completions_is_zero(
    make_habit: HabitFactory,
) -> None:
    assert count_in_period(make_habit(frequency=THREE_A_WEEK), THREE_A_WEEK, TODAY) == 0


# ---------- best_streak ----------


def test_best_streak_remembers_a_run_that_was_broken_later(make_habit: HabitFactory) -> None:
    # A run of 3 (June 2-4) that is over, and a new run of 1 (June 11).
    habit = make_habit(start=date(2026, 6, 1), done=june(2, 3, 4, 11))
    assert best_streak(habit, TODAY) == 3
    assert current_streak(habit, TODAY) == 1


def test_best_streak_equals_the_current_one_when_it_was_never_broken(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(start=date(2026, 6, 1), done=june(7, 8, 9, 10, 11))
    assert best_streak(habit, TODAY) == 5


def test_best_streak_of_a_habit_without_completions_is_zero(make_habit: HabitFactory) -> None:
    assert best_streak(make_habit(), TODAY) == 0


def test_best_streak_picks_the_longest_of_several_runs(make_habit: HabitFactory) -> None:
    habit = make_habit(start=date(2026, 6, 1), done=june(1, 2, 4, 5, 6, 7, 9))
    assert best_streak(habit, TODAY) == 4


def test_best_streak_of_a_weekday_habit_skips_the_days_off(make_habit: HabitFactory) -> None:
    # Fridays May 8, 15 and 22 done; May 29 missed; June 5 done.
    habit = make_habit(frequency=FRIDAYS, done=may(8, 15, 22) + june(5))
    assert best_streak(habit, TODAY) == 3


def test_best_streak_of_fixed_dates_counts_consecutive_occasions(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(frequency=CHOSEN_DATES, done=[date(2026, 5, 20), *june(3, 10)])
    assert best_streak(habit, TODAY) == 3


def test_best_streak_of_an_ended_habit_is_the_same_whenever_it_is_asked(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(start=date(2026, 6, 1), end=date(2026, 6, 5), done=june(3, 4, 5))
    assert best_streak(habit, date(2026, 6, 5)) == 3
    assert best_streak(habit, date(2027, 1, 1)) == 3


@pytest.fixture
def broken_weekly_quota(make_habit: HabitFactory) -> Habit:
    """Two a week; six weeks from May 4 with 2, 2, 2, 1, 2, 2 completions."""
    done = [
        *may(4, 5),
        *may(11, 12),
        *may(18, 19),
        *may(25),
        *june(1, 2),
        *june(8, 9),
    ]
    return make_habit(frequency=Quota(times=2), start=date(2026, 5, 4), done=done)


def test_best_quota_streak_is_the_longest_run_of_met_periods(broken_weekly_quota: Habit) -> None:
    assert best_streak(broken_weekly_quota, TODAY) == 3


def test_current_quota_streak_can_be_shorter_than_the_best_one(broken_weekly_quota: Habit) -> None:
    assert current_streak(broken_weekly_quota, TODAY) == 2


def test_best_quota_streak_ignores_an_unfinished_current_period(make_habit: HabitFactory) -> None:
    habit = make_habit(frequency=Quota(times=2), start=date(2026, 6, 1), done=june(1, 2, 8))
    assert best_streak(habit, TODAY) == 1


def test_best_quota_streak_of_an_ended_habit_stops_at_its_end(make_habit: HabitFactory) -> None:
    habit = make_habit(
        frequency=Quota(times=1), start=date(2026, 6, 1), end=date(2026, 6, 14), done=june(1, 8)
    )
    assert best_streak(habit, date(2027, 1, 1)) == 2


def test_best_quota_streak_ignores_completions_made_after_the_habit_ended(
    make_habit: HabitFactory,
) -> None:
    habit = make_habit(
        frequency=Quota(times=1),
        start=date(2026, 6, 1),
        end=date(2026, 6, 14),
        done=june(1, 8, 15, 22),
    )
    assert best_streak(habit, date(2026, 7, 1)) == 2


def test_best_monthly_quota_streak_counts_consecutive_months(make_habit: HabitFactory) -> None:
    done = [
        date(2026, 3, 2),
        date(2026, 3, 9),
        date(2026, 4, 5),
        date(2026, 4, 6),
        date(2026, 5, 3),  # May has only 1 of 2
    ]
    habit = make_habit(
        frequency=Quota(times=2, period=Period.MONTH), start=date(2026, 3, 1), done=done
    )
    assert best_streak(habit, TODAY) == 2


# ---------- Completions on days the habit is not due ----------


def test_best_streak_ignores_completions_made_on_days_the_habit_is_not_due(
    make_habit: HabitFactory,
) -> None:
    saturday = date(2026, 5, 30)
    habit = make_habit(frequency=FRIDAYS, done=[saturday])
    assert current_streak(habit, TODAY) == 0
    assert best_streak(habit, TODAY) == 0
