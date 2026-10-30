"""The habit described in words, for the form's live preview. Pure functions, no window.

``ui.strings.describe_frequency`` gives the short phrase the lists use ("solo viernes");
the preview needs the full one, and it must never claim fixed days when the habit only has
a quota ("3 veces por semana" says so, and names days only as a preference).
"""

from collections.abc import Iterable
from datetime import date

from ...domain.enums import Weekday
from ...domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from ..calendar_es import MONTHS, short_date_text
from ..strings import WEEKDAY_NAMES, describe_frequency
from . import texts
from .numbers import format_number

_EVERY_DAY = len(Weekday)
# From this many weekdays on it reads better to say which days are skipped.
_MOSTLY_EVERY_DAY = 5
# Weekday names that do not already end in "s" when pluralized ("los sábados").
_NEEDS_PLURAL_S = frozenset({Weekday.SATURDAY, Weekday.SUNDAY})


def join_words(items: Iterable[str]) -> str:
    """``["a", "b", "c"]`` becomes ``"a, b y c"``."""
    parts = list(items)
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " y " + parts[-1]


def dates_in_words(days: Iterable[date]) -> str:
    """``[5 nov, 12 nov, 27 nov]`` becomes ``"los días 5, 12 y 27 de noviembre"``.

    Dates in different months are grouped ("5 y 12 de noviembre y 3 de diciembre") and,
    when they span years, every group carries its year.
    """
    ordered = sorted(days)
    if not ordered:
        return "sin fechas"
    with_year = len({day.year for day in ordered}) > 1
    groups: dict[tuple[int, int], list[int]] = {}
    for day in ordered:
        groups.setdefault((day.year, day.month), []).append(day.day)
    parts = []
    for (year, month), numbers in groups.items():
        part = f"{join_words(str(number) for number in numbers)} de {MONTHS[month - 1]}"
        parts.append(part + (f" de {year}" if with_year else ""))
    return ("el día " if len(ordered) == 1 else "los días ") + join_words(parts)


def _plural_name(day: Weekday) -> str:
    return WEEKDAY_NAMES[day] + ("s" if day in _NEEDS_PLURAL_S else "")


def frequency_in_words(frequency: Frequency) -> str:
    """The frequency as a clause: ``"los lunes, miércoles y viernes"``, ``"cada 2 semanas"``."""
    match frequency:
        case Daily():
            return "todos los días"
        case Weekdays(days=days):
            if len(days) >= _EVERY_DAY:
                return "todos los días"
            if len(days) >= _MOSTLY_EVERY_DAY:
                rested = join_words(WEEKDAY_NAMES[day] for day in Weekday if day not in days)
                return "todos los días, excepto " + rested
            return "los " + join_words(_plural_name(day) for day in sorted(days))
        case Quota(preferred=preferred):
            text = describe_frequency(frequency)
            if preferred:
                text += ", preferentemente " + join_words(
                    WEEKDAY_NAMES[day] for day in sorted(preferred)
                )
            return text
        case FixedDates(dates=dates):
            return dates_in_words(dates)
        case Interval():
            return describe_frequency(frequency)
    raise TypeError(f"unknown frequency: {frequency!r}")


def preview_sentence(
    *,
    name: str,
    schedule: str,
    goal: tuple[float, str] | None,
    start: date | None,
    end: date | None,
    reminder_time: str | None,
) -> str:
    """``"Leer — todos los días; meta por ocasión: 10 páginas; desde el 1 nov."``.

    ``schedule`` is the frequency clause, or what is missing for one to exist. ``goal`` is the
    amount and unit, ``start`` and ``end`` are what could be read from the validity fields and
    ``reminder_time`` is the text typed for the reminder (``None`` when there is no reminder).
    """
    parts = [schedule]
    if goal is not None:
        parts.append(texts.preview_goal(format_number(goal[0]), goal[1]))
    if start is not None:
        parts.append(
            texts.preview_period(
                short_date_text(start), short_date_text(end) if end is not None else None
            )
        )
    if reminder_time:
        parts.append(texts.preview_reminder(reminder_time))
    return f"{name} — " + "; ".join(parts) + "."
