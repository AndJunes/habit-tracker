"""Pure conversions between domain values and what the database stores.

Frequencies become a ``kind`` and a JSON object of parameters; measurements and
reminders become nullable columns; dates and times become ISO text. Reading goes
through the domain constructors, so a stored value that breaks a domain rule is
reported as a :class:`~habit_tracker.ports.StorageError` naming the row.
"""

import json
from collections.abc import Iterable
from datetime import date, time
from typing import Any, NamedTuple

from ..domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from ..domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from ..domain.models import Measurement, Reminder
from ..ports import StorageError

_WEEKDAYS_BY_NAME = {day.name.lower(): day for day in Weekday}


class MeasurementColumns(NamedTuple):
    kind: str | None
    goal: float | None
    unit: str | None
    minimum: float | None
    ideal: float | None


class ReminderColumns(NamedTuple):
    at: str | None
    weekdays: str | None


def format_day(day: date) -> str:
    return day.isoformat()


def format_time(at: time) -> str:
    return at.isoformat(timespec="minutes")


def parse_iso_date(value: object) -> date:
    """Parse ``YYYY-MM-DD`` and nothing else.

    ``date.fromisoformat`` also accepts other layouts (``20261001``, ``2026-W40-4``),
    which would not sort or compare as text.
    """
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.isoformat() == value:
                return parsed
    raise ValueError(f"not a YYYY-MM-DD date: {value!r}")


def parse_iso_time(value: object) -> time:
    """Parse ``HH:MM`` and nothing else."""
    if isinstance(value, str):
        try:
            parsed = time.fromisoformat(value)
        except ValueError:
            pass
        else:
            if format_time(parsed) == value:
                return parsed
    raise ValueError(f"not an HH:MM time: {value!r}")


def stored_date(value: object, *, where: str) -> date:
    """A date read from a column, or a ``StorageError`` that names the row."""
    try:
        return parse_iso_date(value)
    except ValueError as error:
        raise StorageError(f"{where}: invalid stored date ({error})") from error


def frequency_to_columns(frequency: Frequency) -> tuple[str, str]:
    """The ``(kind, JSON parameters)`` pair that stores ``frequency``."""
    params: dict[str, object]
    match frequency:
        case Daily():
            kind, params = "daily", {}
        case Weekdays(days=days):
            kind, params = "weekdays", {"days": _weekday_names(days)}
        case Quota(times=times, period=period, preferred=preferred):
            kind = "quota"
            params = {
                "times": times,
                "period": period.value,
                "preferred": _weekday_names(preferred),
            }
        case FixedDates(dates=dates):
            kind, params = "fixed_dates", {"dates": [format_day(day) for day in dates]}
        case Interval(every=every, unit=unit):
            kind, params = "interval", {"every": every, "unit": unit.value}
        case _:
            raise StorageError(f"cannot store a frequency of type {type(frequency).__name__}")
    return kind, json.dumps(params, separators=(",", ":"), sort_keys=True)


def frequency_from_columns(kind: str, params: str, *, where: str) -> Frequency:
    """Rebuild a frequency from its stored columns."""
    try:
        data = json.loads(params)
        if not isinstance(data, dict):
            raise ValueError("the parameters are not a JSON object")
        return _build_frequency(kind, data)
    except (ValueError, KeyError, TypeError) as error:
        raise StorageError(f"{where}: invalid {kind!r} frequency ({error})") from error


def measurement_to_columns(measurement: Measurement | None) -> MeasurementColumns:
    if measurement is None:
        return MeasurementColumns(None, None, None, None, None)
    return MeasurementColumns(
        measurement.kind.value,
        measurement.goal,
        measurement.unit,
        measurement.minimum,
        measurement.ideal,
    )


def measurement_from_columns(columns: MeasurementColumns, *, where: str) -> Measurement | None:
    if columns.kind is None:
        return None
    if columns.goal is None or columns.unit is None:
        raise StorageError(f"{where}: the measurement has no goal or unit")
    try:
        return Measurement(
            kind=MeasurementKind(columns.kind),
            goal=columns.goal,
            unit=columns.unit,
            minimum=columns.minimum,
            ideal=columns.ideal,
        )
    except ValueError as error:
        raise StorageError(f"{where}: invalid measurement ({error})") from error


def reminder_to_columns(reminder: Reminder | None) -> ReminderColumns:
    if reminder is None:
        return ReminderColumns(None, None)
    weekdays = json.dumps(_weekday_names(reminder.weekdays), separators=(",", ":"))
    return ReminderColumns(format_time(reminder.at), weekdays)


def reminder_from_columns(columns: ReminderColumns, *, where: str) -> Reminder | None:
    if columns.at is None:
        return None
    try:
        weekdays = json.loads(columns.weekdays) if columns.weekdays is not None else None
        return Reminder(at=parse_iso_time(columns.at), weekdays=_weekday_set(weekdays))
    except (ValueError, TypeError) as error:
        raise StorageError(f"{where}: invalid reminder ({error})") from error


def _build_frequency(kind: str, data: dict[str, Any]) -> Frequency:
    match kind:
        case "daily":
            return Daily()
        case "weekdays":
            return Weekdays(days=_weekday_set(data["days"]))
        case "quota":
            return Quota(
                times=data["times"],
                period=Period(data["period"]),
                preferred=_weekday_set(data["preferred"]),
            )
        case "fixed_dates":
            dates = data["dates"]
            if not isinstance(dates, list):
                raise ValueError("the dates are not a JSON array")
            return FixedDates(dates=tuple(parse_iso_date(item) for item in dates))
        case "interval":
            return Interval(every=data["every"], unit=IntervalUnit(data["unit"]))
        case _:
            raise ValueError("unknown kind")


def _weekday_names(days: Iterable[Weekday]) -> list[str]:
    return [day.name.lower() for day in sorted(days)]


def _weekday_set(value: object) -> frozenset[Weekday]:
    if not isinstance(value, list):
        raise ValueError("the weekdays are not a JSON array")
    days: set[Weekday] = set()
    for name in value:
        if not isinstance(name, str) or name not in _WEEKDAYS_BY_NAME:
            raise ValueError(f"unknown weekday {name!r}")
        days.add(_WEEKDAYS_BY_NAME[name])
    return frozenset(days)
