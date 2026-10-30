"""Streaks: consecutive due days, or consecutive periods for quotas.

Only days on which a habit is due count, so a habit due on Fridays does not
lose its streak on Monday. The most recent due day that is still pending
never breaks a streak: if today is not done yet, yesterday's streak is alive.
"""

from datetime import date, timedelta

from .frequency import Quota
from .models import Habit


def count_in_period(habit: Habit, quota: Quota, day: date) -> int:
    """How many completions fall in the quota period (week or month) containing ``day``."""
    first, last = quota.period_bounds(day)
    return sum(1 for done in habit.completions if first <= done <= last)


def current_streak(habit: Habit, today: date) -> int:
    """The streak that is alive on ``today``."""
    if isinstance(habit.frequency, Quota):
        return _current_quota_streak(habit, habit.frequency, today)
    day = habit.previous_scheduled(today)
    if day is None:
        return 0
    if not habit.is_done(day):
        day = habit.previous_scheduled(day, inclusive=False)
    streak = 0
    while day is not None and habit.is_done(day):
        streak += 1
        day = habit.previous_scheduled(day, inclusive=False)
    return streak


def best_streak(habit: Habit, today: date) -> int:
    """The longest streak the habit ever reached, even if it was broken afterwards."""
    if isinstance(habit.frequency, Quota):
        return _best_quota_streak(habit, habit.frequency, today)
    best = 0
    for first in habit.completions:
        if not habit.applies_on(first):
            continue  # a completion on a day the habit is not due is not part of a streak
        previous = habit.previous_scheduled(first, inclusive=False)
        if previous is not None and habit.is_done(previous):
            continue  # not the first day of its streak
        length = 0
        cursor: date | None = first
        while cursor is not None and habit.is_done(cursor):
            length += 1
            cursor = habit.next_scheduled(cursor)
        best = max(best, length)
    return best


def _current_quota_streak(habit: Habit, quota: Quota, today: date) -> int:
    """Consecutive periods with the whole quota done.

    The current period counts when it is already complete and, when it is
    not, it does not break the streak. Once a habit has ended, the streak is
    measured from its last period: that period is left open unless it closed
    inside the habit's lifetime without meeting the quota.
    """
    reference = min(today, habit.end) if habit.end is not None else today
    streak = 0
    if count_in_period(habit, quota, reference) >= quota.times:
        streak += 1
    elif (
        habit.end is not None
        and today > habit.end
        and quota.period_bounds(reference)[1] <= habit.end
    ):
        return 0
    day = quota.period_bounds(reference)[0] - timedelta(days=1)
    while (
        quota.period_bounds(day)[1] >= habit.start
        and count_in_period(habit, quota, day) >= quota.times
    ):
        streak += 1
        day = quota.period_bounds(day)[0] - timedelta(days=1)
    return streak


def _best_quota_streak(habit: Habit, quota: Quota, today: date) -> int:
    limit = min(today, habit.end) if habit.end is not None else today
    best = current = 0
    day = habit.start
    while day <= limit:
        if count_in_period(habit, quota, day) >= quota.times:
            current += 1
            best = max(best, current)
        else:
            current = 0
        day = quota.period_bounds(day)[1] + timedelta(days=1)
    return best
