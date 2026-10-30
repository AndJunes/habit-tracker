"""Statistics for the calendar, the monthly view and the dashboard.

No one is in debt to a quota: a quota habit can paint a day as done but never
as missed, and a day that has not finished yet is "pending", not "missed".
"""

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from .enums import DayStatus
from .frequency import Quota
from .models import Area, Habit, ImportantDate
from .streaks import best_streak


def completed_areas_by_day(habits: Iterable[Habit], year: int, month: int) -> dict[int, list[str]]:
    """For the calendar grid: ``{day of month: [ids of the areas done that day]}``.

    Each area appears once per day, even if two habits share it.
    """
    summary: dict[int, list[str]] = {}
    for habit in habits:
        for day in habit.completions:
            if day.year == year and day.month == month:
                areas = summary.setdefault(day.day, [])
                if habit.area_id not in areas:
                    areas.append(habit.area_id)
    return summary


def day_progress(habits: Iterable[Habit], day: date) -> tuple[int, int]:
    """For the progress ring: ``(habits done, habits due)`` on ``day``.

    Quota habits count only when they were done: they add to the ring but never
    put it in debt, because their goal belongs to a week or a month.
    """
    done = due = 0
    for habit in habits:
        if not habit.applies_on(day):
            continue
        if isinstance(habit.frequency, Quota) and not habit.is_done(day):
            continue
        due += 1
        if habit.is_done(day):
            done += 1
    return done, due


def consistency_matrix(
    areas: Iterable[Area], habits: Sequence[Habit], year: int, month: int, today: date
) -> dict[str, dict[int, DayStatus]]:
    """``{area id: {day of month: status}}`` for the areas that have at least one habit."""
    days_in_month = calendar.monthrange(year, month)[1]
    matrix: dict[str, dict[int, DayStatus]] = {}
    for area in areas:
        area_habits = [habit for habit in habits if habit.area_id == area.id]
        if not area_habits:
            continue
        row: dict[int, DayStatus] = {}
        for number in range(1, days_in_month + 1):
            row[number] = _day_status(area_habits, date(year, month, number), today)
        matrix[area.id] = row
    return matrix


def _day_status(area_habits: Sequence[Habit], day: date, today: date) -> DayStatus:
    scheduled = [
        habit
        for habit in area_habits
        if habit.applies_on(day) and not isinstance(habit.frequency, Quota)
    ]
    quota_done = any(
        isinstance(habit.frequency, Quota) and habit.applies_on(day) and habit.is_done(day)
        for habit in area_habits
    )
    if quota_done or any(habit.is_done(day) for habit in scheduled):
        return DayStatus.DONE
    if not scheduled:
        return DayStatus.NOT_DUE
    if day > today:
        return DayStatus.FUTURE
    if day == today:
        return DayStatus.PENDING
    return DayStatus.MISSED


@dataclass(frozen=True, slots=True)
class MonthStats:
    """Every figure the monthly view and the dashboard need, computed once."""

    matrix: dict[str, dict[int, DayStatus]]
    percentages: list[tuple[Area, int]]
    counts_by_area: list[tuple[Area, int]]
    counts_by_day: list[tuple[int, int]]
    total: int


def month_stats(
    areas: Sequence[Area], habits: Sequence[Habit], year: int, month: int, today: date
) -> MonthStats:
    """Build the month's figures from a single pass over the consistency matrix.

    The percentage of an area is done days over due days; today (pending) and
    the future are left out so that nothing counts against what has not happened.
    """
    matrix = consistency_matrix(areas, habits, year, month, today)
    percentages: list[tuple[Area, int]] = []
    counts_by_area: list[tuple[Area, int]] = []
    for area in areas:
        row = matrix.get(area.id)
        if row is None:
            continue
        done = sum(1 for status in row.values() if status is DayStatus.DONE)
        missed = sum(1 for status in row.values() if status is DayStatus.MISSED)
        percentages.append((area, round(100 * done / (done + missed)) if done + missed else 0))
        counts_by_area.append((area, done))
    return MonthStats(
        matrix=matrix,
        percentages=percentages,
        counts_by_area=counts_by_area,
        counts_by_day=_counts_by_day(matrix, year, month, today),
        total=sum(count for _, count in counts_by_area),
    )


def _counts_by_day(
    matrix: dict[str, dict[int, DayStatus]], year: int, month: int, today: date
) -> list[tuple[int, int]]:
    """``(day, areas done)`` from the 1st until today, or the whole month if it is over."""
    if (year, month) > (today.year, today.month):
        return []
    if (year, month) == (today.year, today.month):
        last = today.day
    else:
        last = calendar.monthrange(year, month)[1]
    return [
        (day, sum(1 for row in matrix.values() if row.get(day) is DayStatus.DONE))
        for day in range(1, last + 1)
    ]


def longest_streak(habits: Iterable[Habit], today: date) -> int:
    """The best streak ever reached across all habits."""
    return max((best_streak(habit, today) for habit in habits), default=0)


def important_dates_in_month(
    items: Iterable[ImportantDate], year: int, month: int
) -> list[tuple[int, str]]:
    """``(day of month, title)`` for the month, sorted."""
    return sorted(
        (item.day.day, item.title)
        for item in items
        if item.day.year == year and item.day.month == month
    )
