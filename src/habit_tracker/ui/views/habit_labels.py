"""The small texts of a habit row: its subtitle and the pill next to the checkbox.

They are plain functions of the habit and the service, so they can be tested without a screen.
"""

from datetime import date

from ...domain.enums import Period
from ...domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from ...domain.models import Habit
from ...service import HabitService
from ..calendar_es import short_date_text
from ..controllers.habit_actions import format_number
from ..strings import describe_frequency

# A habit due on fewer weekdays than this is called "weekly" in its pill.
_WEEKLY_BELOW_DAYS = 5


def subtitle(habit: Habit, area_name: str, day: date) -> str:
    """Under the name: the area and, for a measured habit, its goal (or what was recorded)."""
    measurement = habit.measurement
    if measurement is None:
        return area_name
    goal = f"{format_number(measurement.goal)} {measurement.unit}"
    value = habit.completions.get(day)
    if habit.is_done(day) and value is not None:
        return f"{area_name} · {format_number(value)} {measurement.unit} (meta {goal})"
    return f"{area_name} · meta {goal}"


def muted_subtitle(service: HabitService, habit: Habit, day: date) -> str:
    """Why the habit is not due on ``day``: it ended, has not started, or when it comes next."""
    if habit.end is not None and habit.end < day:
        return f"terminó el {short_date_text(habit.end)}"
    if day < habit.start:
        return f"empieza el {short_date_text(habit.start)}"
    if isinstance(habit.frequency, FixedDates | Interval):
        upcoming = service.next_due(habit, day)
        return f"próxima: {short_date_text(upcoming)}" if upcoming else "sin más fechas"
    return describe_frequency(habit.frequency)


def pill_text(service: HabitService, habit: Habit, day: date) -> str | None:
    """What the pill says: progress of a quota, "semanal", or the streak.

    Daily and weekday habits show their streak in days, fixed-date and interval habits in
    occasions in a row (and, while they have none, how often they happen).
    """
    frequency = habit.frequency
    if isinstance(frequency, Quota):
        done = service.done_in_period(habit, day)
        period = "este mes" if frequency.period is Period.MONTH else "esta semana"
        return f"{done}/{frequency.times} {period}"
    if isinstance(frequency, Weekdays) and len(frequency.days) < _WEEKLY_BELOW_DAYS:
        return "semanal"
    streak = service.current_streak(habit)
    plural = "" if streak == 1 else "s"
    if isinstance(frequency, Daily | Weekdays):
        return f"🔥 {streak} día{plural}" if streak > 0 else None
    if streak > 0:
        return f"🔥 {streak} seguida{plural}"
    return describe_frequency(frequency)
