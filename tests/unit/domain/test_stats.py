"""Statistics for the calendar, the consistency map, the month view and the dashboard."""

from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.domain.enums import DayStatus, IntervalUnit, Period, Weekday
from habit_tracker.domain.frequency import FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import Area, Habit, ImportantDate
from habit_tracker.domain.stats import (
    MonthStats,
    completed_areas_by_day,
    consistency_matrix,
    day_progress,
    important_dates_in_month,
    longest_streak,
    month_stats,
)

HabitFactory = Callable[..., Habit]

TODAY = date(2026, 6, 11)  # a Thursday

FRIDAYS = Weekdays(frozenset({Weekday.FRIDAY}))
THREE_A_WEEK = Quota(times=3)
CHOSEN_DATES = FixedDates(
    (date(2026, 5, 20), date(2026, 6, 3), date(2026, 6, 10), date(2026, 6, 20))
)
JUNE_START = date(2026, 6, 1)


def june(*days: int) -> list[date]:
    return [date(2026, 6, number) for number in days]


# ---------- completed_areas_by_day ----------


def test_completed_areas_are_listed_by_day_of_the_month(make_habit: HabitFactory) -> None:
    gym = make_habit(id=1, area_id="gym", start=JUNE_START, done=june(11))
    english = make_habit(
        id=2, name="English 30 minutes", area_id="english", start=JUNE_START, done=june(10, 11)
    )
    summary = completed_areas_by_day([gym, english], 2026, 6)
    assert summary == {11: ["gym", "english"], 10: ["english"]}


def test_an_area_appears_once_per_day_even_if_two_habits_share_it(
    make_habit: HabitFactory,
) -> None:
    first = make_habit(id=1, area_id="gym", done=june(11))
    second = make_habit(id=2, name="Stretching", area_id="gym", done=june(11))
    assert completed_areas_by_day([first, second], 2026, 6) == {11: ["gym"]}


def test_completed_areas_ignore_other_months_and_years(make_habit: HabitFactory) -> None:
    habit = make_habit(done=[date(2026, 5, 31), date(2025, 6, 11), date(2026, 7, 1), TODAY])
    assert completed_areas_by_day([habit], 2026, 6) == {11: ["gym"]}


def test_a_month_without_completions_has_an_empty_summary(make_habit: HabitFactory) -> None:
    assert completed_areas_by_day([make_habit()], 2026, 6) == {}


# ---------- day_progress ----------


def test_progress_ring_counts_done_over_due_habits_of_the_day(make_habit: HabitFactory) -> None:
    # Today is Thursday: the Friday habit is not due, so the ring is 1 of 1.
    daily = make_habit(id=1, start=JUNE_START, done=june(11))
    fridays = make_habit(id=2, name="Finances", frequency=FRIDAYS, start=JUNE_START)
    assert day_progress([daily, fridays], TODAY) == (1, 1)


def test_progress_ring_counts_a_pending_due_habit_as_due_but_not_done(
    make_habit: HabitFactory,
) -> None:
    done = make_habit(id=1, start=JUNE_START, done=june(11))
    pending = make_habit(id=2, name="Read", start=JUNE_START)
    assert day_progress([done, pending], TODAY) == (1, 2)


def test_a_quota_habit_does_not_put_the_ring_in_debt(make_habit: HabitFactory) -> None:
    daily = make_habit(id=1, start=JUNE_START, done=june(11))
    quota = make_habit(id=3, name="Padel", frequency=THREE_A_WEEK)
    assert day_progress([daily, quota], TODAY) == (1, 1)


def test_a_quota_habit_adds_to_the_ring_when_it_is_done(make_habit: HabitFactory) -> None:
    daily = make_habit(id=1, start=JUNE_START, done=june(11))
    quota = make_habit(id=3, name="Padel", frequency=THREE_A_WEEK, done=june(11))
    assert day_progress([daily, quota], TODAY) == (2, 2)


def test_progress_ring_ignores_habits_that_ended_or_have_not_started(
    make_habit: HabitFactory,
) -> None:
    ended = make_habit(id=1, start=JUNE_START, end=date(2026, 6, 10))
    future = make_habit(id=2, name="Later", start=date(2026, 6, 12))
    assert day_progress([ended, future], TODAY) == (0, 0)


def test_progress_ring_of_no_habits_is_empty() -> None:
    assert day_progress([], TODAY) == (0, 0)


# ---------- consistency_matrix: day statuses ----------


def test_daily_habit_statuses_done_missed_pending_and_future(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=JUNE_START, done=june(9, 11))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert row[9] is DayStatus.DONE
    assert row[10] is DayStatus.MISSED
    assert row[11] is DayStatus.DONE
    assert row[12] is DayStatus.FUTURE


def test_today_without_a_completion_is_pending_not_missed(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=JUNE_START, done=june(10))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert row[11] is DayStatus.PENDING


def test_days_before_the_habit_started_are_not_due(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=date(2026, 6, 5))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert [row[number] for number in range(1, 5)] == [DayStatus.NOT_DUE] * 4
    assert row[5] is DayStatus.MISSED


def test_weekday_habit_is_not_due_between_its_days(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(frequency=FRIDAYS, area_id="english", start=JUNE_START, done=june(5))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["english"]
    assert row[4] is DayStatus.NOT_DUE  # Thursday
    assert row[5] is DayStatus.DONE  # Friday, done
    assert row[11] is DayStatus.NOT_DUE  # Thursday again
    assert row[12] is DayStatus.FUTURE  # next Friday


def test_a_quota_habit_paints_the_days_done_and_never_a_missed_day(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(frequency=THREE_A_WEEK, done=june(9))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert row[9] is DayStatus.DONE
    assert row[8] is DayStatus.NOT_DUE
    assert row[10] is DayStatus.NOT_DUE
    assert DayStatus.MISSED not in row.values()


def test_a_quota_habit_never_makes_today_pending(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(frequency=THREE_A_WEEK, done=june(9))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert row[11] is DayStatus.NOT_DUE


def test_a_done_quota_habit_paints_its_day_even_if_a_scheduled_habit_was_missed(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    daily = make_habit(id=1, start=JUNE_START, done=june(5, 6, 7, 8, 9, 10))
    quota = make_habit(id=2, name="Padel", frequency=THREE_A_WEEK, done=june(3))
    row = consistency_matrix(areas, [daily, quota], 2026, 6, TODAY)["gym"]
    assert row[3] is DayStatus.DONE  # the quota was done although the daily habit was missed
    assert row[4] is DayStatus.MISSED  # only the daily habit was due


def test_a_day_is_done_when_any_habit_of_the_area_was_done(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    done = make_habit(id=1, start=JUNE_START, done=june(9))
    missed = make_habit(id=2, name="Stretching", start=JUNE_START)
    row = consistency_matrix(areas, [done, missed], 2026, 6, TODAY)["gym"]
    assert row[9] is DayStatus.DONE
    assert row[10] is DayStatus.MISSED


def test_days_after_the_end_of_a_habit_are_not_due(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=JUNE_START, end=date(2026, 6, 3), done=june(2))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert row[2] is DayStatus.DONE
    assert row[3] is DayStatus.MISSED
    assert all(row[number] is DayStatus.NOT_DUE for number in range(4, 31))


def test_fixed_date_that_passed_without_being_done_is_missed(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(frequency=CHOSEN_DATES, done=june(3))
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert row[3] is DayStatus.DONE
    assert row[10] is DayStatus.MISSED
    assert row[20] is DayStatus.FUTURE
    assert row[4] is DayStatus.NOT_DUE


def test_interval_occurrence_that_passed_without_being_done_is_missed(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(
        frequency=Interval(3, IntervalUnit.DAYS), start=date(2026, 5, 30), done=june(2, 8)
    )
    row = consistency_matrix(areas, [habit], 2026, 6, TODAY)["gym"]
    assert row[2] is DayStatus.DONE
    assert row[5] is DayStatus.MISSED
    assert row[8] is DayStatus.DONE
    assert row[11] is DayStatus.PENDING
    assert row[14] is DayStatus.FUTURE
    assert row[6] is DayStatus.NOT_DUE


def test_quota_preferred_days_do_not_change_the_matrix(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    done = june(1, 2, 3, 8)
    plain = make_habit(frequency=THREE_A_WEEK, done=done)
    hinted = make_habit(
        frequency=Quota(
            times=3, preferred=frozenset({Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY})
        ),
        done=done,
    )
    assert consistency_matrix(areas, [hinted], 2026, 6, TODAY) == consistency_matrix(
        areas, [plain], 2026, 6, TODAY
    )


# ---------- consistency_matrix: shape ----------


def test_only_areas_with_habits_have_a_row(make_habit: HabitFactory, areas: list[Area]) -> None:
    matrix = consistency_matrix(areas, [make_habit(area_id="english")], 2026, 6, TODAY)
    assert list(matrix) == ["english"]


@pytest.mark.parametrize(
    ("year", "month", "days"),
    [
        pytest.param(2026, 6, 30, id="thirty-days"),
        pytest.param(2026, 7, 31, id="thirty-one-days"),
        pytest.param(2026, 2, 28, id="february"),
        pytest.param(2028, 2, 29, id="leap-february"),
    ],
)
def test_each_row_has_one_status_per_day_of_the_month(
    make_habit: HabitFactory, areas: list[Area], year: int, month: int, days: int
) -> None:
    row = consistency_matrix(areas, [make_habit()], year, month, TODAY)["gym"]
    assert list(row) == list(range(1, days + 1))


def test_every_day_of_a_month_before_the_habit_is_not_due(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=date(2026, 6, 1))
    row = consistency_matrix(areas, [habit], 2026, 5, TODAY)["gym"]
    assert set(row.values()) == {DayStatus.NOT_DUE}


# ---------- month_stats ----------


def test_area_percentage_is_done_days_over_due_days_without_today_or_the_future(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    # Days 1-10 were due (the 11th is pending): 5 done of 10 is 50%.
    habit = make_habit(start=JUNE_START, done=june(1, 2, 3, 4, 5))
    stats = month_stats(areas, [habit], 2026, 6, TODAY)
    assert stats.percentages == [(areas[0], 50)]


def test_area_percentage_is_rounded_to_a_whole_number(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    # 2 done of 3 due days: 66.67% rounds to 67.
    habit = make_habit(start=date(2026, 6, 8), done=june(8, 9))
    stats = month_stats(areas, [habit], 2026, 6, TODAY)
    assert stats.percentages == [(areas[0], 67)]


def test_area_percentage_is_zero_when_no_day_has_closed_yet(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=TODAY)
    stats = month_stats(areas, [habit], 2026, 6, TODAY)
    assert stats.percentages == [(areas[0], 0)]


def test_percentages_and_counts_follow_the_order_of_the_areas(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    gym = make_habit(id=1, area_id="gym", start=JUNE_START, done=june(9))
    english = make_habit(id=2, name="English", area_id="english", start=JUNE_START, done=june(9))
    stats = month_stats([areas[1], areas[0]], [gym, english], 2026, 6, TODAY)
    assert [area.id for area, _ in stats.percentages] == ["english", "gym"]
    assert [area.id for area, _ in stats.counts_by_area] == ["english", "gym"]


def test_areas_without_habits_are_left_out_of_percentages_and_counts(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    stats = month_stats(areas, [make_habit(area_id="english")], 2026, 6, TODAY)
    assert [area.id for area, _ in stats.percentages] == ["english"]
    assert [area.id for area, _ in stats.counts_by_area] == ["english"]


def test_counts_by_area_and_total_add_up_the_done_days(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=JUNE_START, done=june(9, 10))
    stats = month_stats(areas, [habit], 2026, 6, TODAY)
    assert {area.id: count for area, count in stats.counts_by_area} == {"gym": 2}
    assert stats.total == 2


def test_total_sums_the_done_days_of_every_area(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    gym = make_habit(id=1, area_id="gym", start=JUNE_START, done=june(8, 9, 10))
    english = make_habit(id=2, name="English", area_id="english", start=JUNE_START, done=june(9))
    stats = month_stats(areas, [gym, english], 2026, 6, TODAY)
    assert stats.total == 4


def test_counts_by_day_run_from_the_first_of_the_month_until_today(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=JUNE_START, done=june(9, 10))
    by_day = dict(month_stats(areas, [habit], 2026, 6, TODAY).counts_by_day)
    assert by_day[9] == 1
    assert by_day[10] == 1
    assert by_day[8] == 0
    assert len(by_day) == 11


def test_counts_by_day_count_each_area_once_even_with_two_habits(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    first = make_habit(id=1, area_id="gym", start=JUNE_START, done=june(9))
    second = make_habit(id=2, name="Stretching", area_id="gym", start=JUNE_START, done=june(9))
    english = make_habit(id=3, name="English", area_id="english", start=JUNE_START, done=june(9))
    by_day = dict(month_stats(areas, [first, second, english], 2026, 6, TODAY).counts_by_day)
    assert by_day[9] == 2


def test_counts_by_day_cover_the_whole_of_a_past_month(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(done=[date(2026, 5, 31)])
    by_day = month_stats(areas, [habit], 2026, 5, TODAY).counts_by_day
    assert len(by_day) == 31
    assert by_day[-1] == (31, 1)


def test_counts_by_day_of_a_future_month_are_empty(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    assert month_stats(areas, [make_habit()], 2026, 7, TODAY).counts_by_day == []


def test_counts_by_day_of_a_past_year_cover_the_whole_month(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    by_day = month_stats(areas, [make_habit()], 2025, 12, TODAY).counts_by_day
    assert len(by_day) == 31


def test_month_stats_embeds_the_consistency_matrix(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(start=JUNE_START, done=june(9))
    stats = month_stats(areas, [habit], 2026, 6, TODAY)
    assert stats.matrix == consistency_matrix(areas, [habit], 2026, 6, TODAY)


def test_month_stats_of_no_habits_is_empty(areas: list[Area]) -> None:
    stats = month_stats(areas, [], 2026, 6, TODAY)
    assert stats == MonthStats(
        matrix={},
        percentages=[],
        counts_by_area=[],
        counts_by_day=[(number, 0) for number in range(1, 12)],
        total=0,
    )


def test_quota_done_days_count_in_the_month_but_never_as_missed(
    make_habit: HabitFactory, areas: list[Area]
) -> None:
    habit = make_habit(frequency=Quota(times=2, period=Period.MONTH), done=june(3, 9))
    stats = month_stats(areas, [habit], 2026, 6, TODAY)
    assert stats.total == 2
    assert stats.percentages == [(areas[0], 100)]


# ---------- longest_streak ----------


def test_longest_streak_is_the_best_run_among_all_the_habits(make_habit: HabitFactory) -> None:
    # A run of 3 that already ended, and a current run of 1.
    broken = make_habit(id=1, start=JUNE_START, done=june(2, 3, 4, 11))
    short = make_habit(id=2, name="Read", start=JUNE_START, done=june(10, 11))
    assert longest_streak([broken, short], TODAY) == 3


def test_longest_streak_of_no_habits_is_zero() -> None:
    assert longest_streak([], TODAY) == 0


def test_longest_streak_takes_it_from_whichever_habit_has_it(make_habit: HabitFactory) -> None:
    short = make_habit(id=1, start=JUNE_START, done=june(10, 11))
    long = make_habit(id=2, name="Read", start=JUNE_START, done=june(5, 6, 7, 8, 9, 10))
    assert longest_streak([short, long], TODAY) == 6


# ---------- important_dates_in_month ----------


def test_important_dates_of_the_month_are_sorted_by_day() -> None:
    items = [
        ImportantDate(date(2026, 6, 25), "Delivery"),
        ImportantDate(date(2026, 6, 3), "Exam"),
        ImportantDate(date(2026, 6, 25), "Birthday"),
    ]
    assert important_dates_in_month(items, 2026, 6) == [
        (3, "Exam"),
        (25, "Birthday"),
        (25, "Delivery"),
    ]


def test_important_dates_of_other_months_and_years_are_left_out() -> None:
    items = [
        ImportantDate(date(2026, 5, 31), "Last month"),
        ImportantDate(date(2025, 6, 10), "Last year"),
        ImportantDate(date(2026, 6, 10), "This month"),
    ]
    assert important_dates_in_month(items, 2026, 6) == [(10, "This month")]


def test_a_month_without_important_dates_has_an_empty_list() -> None:
    assert important_dates_in_month([], 2026, 6) == []
