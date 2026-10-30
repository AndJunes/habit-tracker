"""Closed sets of values used across the domain."""

from enum import IntEnum, StrEnum


class Weekday(IntEnum):
    """Days of the week; the values match :meth:`datetime.date.weekday`."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class Period(StrEnum):
    """The span over which a quota is counted."""

    WEEK = "week"
    MONTH = "month"


class IntervalUnit(StrEnum):
    """The unit of an "every N" frequency."""

    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class MeasurementKind(StrEnum):
    """What a measured habit records each time it is done."""

    QUANTITY = "quantity"
    DURATION = "duration"


class DayStatus(StrEnum):
    """How one day looks on the consistency map of an area."""

    DONE = "done"
    MISSED = "missed"
    PENDING = "pending"
    NOT_DUE = "not_due"
    FUTURE = "future"
