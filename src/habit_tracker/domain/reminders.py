"""When a habit's reminder is due."""

from datetime import datetime

from .enums import Weekday
from .frequency import Quota
from .models import Habit
from .streaks import count_in_period

# A reminder may fire up to an hour late (for example if the computer was
# asleep at the exact time); after that, notifying no longer makes sense.
GRACE_MINUTES = 60


def is_reminder_due(habit: Habit, now: datetime) -> bool:
    """Whether the habit's reminder should be shown at ``now``.

    It is due from its time until the grace period ends, only on a day the
    habit is in force, and only while the habit is still not done: for a quota
    habit, while the week or month is not already complete.
    """
    reminder = habit.reminder
    if reminder is None:
        return False
    minutes_late = (now.hour * 60 + now.minute) - (reminder.at.hour * 60 + reminder.at.minute)
    if not 0 <= minutes_late < GRACE_MINUTES:
        return False
    today = now.date()
    if today < habit.start or (habit.end is not None and today > habit.end):
        return False
    if habit.is_done(today):
        return False
    if (
        isinstance(habit.frequency, Quota)
        and count_in_period(habit, habit.frequency, today) >= habit.frequency.times
    ):
        return False
    if reminder.weekdays:
        return Weekday(today.weekday()) in reminder.weekdays
    return habit.applies_on(today)
