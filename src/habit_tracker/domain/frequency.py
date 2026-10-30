"""How often a habit is due: five value types and their calendar rules.

Every frequency answers three questions for a habit that starts on ``start``:
is it due on a day, which due day is the latest one on or before a day, and
which is the first one after a day. A habit's end date is applied by
:class:`~habit_tracker.domain.models.Habit`, not here.
"""

import calendar
from abc import ABC, abstractmethod
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta

from .enums import IntervalUnit, Period, Weekday
from .errors import ErrorCode, ValidationError

_ONE_DAY = timedelta(days=1)
_DAYS_IN_WEEK = 7
_MAX_QUOTA = {Period.WEEK: 7, Period.MONTH: 31}


def _is_plain_int(value: object) -> bool:
    return type(value) is int


def _months_between(first: date, second: date) -> int:
    return (second.year - first.year) * 12 + second.month - first.month


def _month_occurrence(start: date, months_after: int) -> date:
    """The date ``months_after`` months past ``start``, always counted from its day.

    A habit that starts on the 31st is due on January 31, February 28 and
    March 31: the day never drifts after a short month.
    """
    total = start.month - 1 + months_after
    year, month = start.year + total // 12, total % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


class Frequency(ABC):
    """Base class of the frequency value types."""

    @abstractmethod
    def occurs_on(self, day: date, start: date) -> bool:
        """Whether a habit starting on ``start`` is due on ``day``."""

    @abstractmethod
    def last_on_or_before(self, day: date, start: date) -> date | None:
        """The latest due day that is on or before ``day``, if there is one."""

    @abstractmethod
    def first_after(self, day: date, start: date) -> date | None:
        """The first due day strictly after ``day``, if there is one."""


class _Repeating(Frequency):
    """Frequencies whose pattern repeats at least every seven days."""

    def last_on_or_before(self, day: date, start: date) -> date | None:
        for offset in range(_DAYS_IN_WEEK):
            candidate = day - timedelta(days=offset)
            if candidate < start:
                return None
            if self.occurs_on(candidate, start):
                return candidate
        return None

    def first_after(self, day: date, start: date) -> date | None:
        first = max(day + _ONE_DAY, start)
        for offset in range(_DAYS_IN_WEEK):
            candidate = first + timedelta(days=offset)
            if self.occurs_on(candidate, start):
                return candidate
        return None


@dataclass(frozen=True, slots=True)
class Daily(_Repeating):
    """Every day."""

    def occurs_on(self, day: date, start: date) -> bool:
        return day >= start


@dataclass(frozen=True, slots=True)
class Weekdays(_Repeating):
    """On the chosen days of the week."""

    days: frozenset[Weekday]

    def __post_init__(self) -> None:
        days = frozenset(Weekday(day) for day in self.days)
        if not days:
            raise ValidationError(ErrorCode.WEEKDAYS_REQUIRED)
        object.__setattr__(self, "days", days)

    def occurs_on(self, day: date, start: date) -> bool:
        return day >= start and Weekday(day.weekday()) in self.days


@dataclass(frozen=True, slots=True)
class Quota(_Repeating):
    """N times per week or per month, on whichever days the person chooses.

    A quota does not schedule particular days, so it never counts as a
    missed day: ``preferred`` is only a hint for the interface.
    """

    times: int
    period: Period = Period.WEEK
    preferred: frozenset[Weekday] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        period = Period(self.period)
        if not _is_plain_int(self.times) or not 1 <= self.times <= _MAX_QUOTA[period]:
            raise ValidationError(
                ErrorCode.QUOTA_OUT_OF_RANGE, times=self.times, period=period.value
            )
        object.__setattr__(self, "period", period)
        object.__setattr__(self, "preferred", frozenset(Weekday(day) for day in self.preferred))

    def occurs_on(self, day: date, start: date) -> bool:
        return day >= start

    def period_bounds(self, day: date) -> tuple[date, date]:
        """First and last day of the week (Monday to Sunday) or month containing ``day``."""
        if self.period is Period.MONTH:
            last_day = calendar.monthrange(day.year, day.month)[1]
            return day.replace(day=1), day.replace(day=last_day)
        first = day - timedelta(days=day.weekday())
        return first, first + timedelta(days=_DAYS_IN_WEEK - 1)


@dataclass(frozen=True, slots=True)
class FixedDates(Frequency):
    """Only on specific dates; the dates are kept sorted and without repeats."""

    dates: tuple[date, ...]

    def __post_init__(self) -> None:
        if any(type(item) is not date for item in self.dates):
            raise ValidationError(ErrorCode.DATE_INVALID)
        if not self.dates:
            raise ValidationError(ErrorCode.DATES_REQUIRED)
        object.__setattr__(self, "dates", tuple(sorted(set(self.dates))))

    def occurs_on(self, day: date, start: date) -> bool:
        index = bisect_left(self.dates, day)
        return day >= start and index < len(self.dates) and self.dates[index] == day

    def last_on_or_before(self, day: date, start: date) -> date | None:
        index = bisect_right(self.dates, day)
        if index == 0:
            return None
        candidate = self.dates[index - 1]
        return candidate if candidate >= start else None

    def first_after(self, day: date, start: date) -> date | None:
        index = bisect_right(self.dates, max(day, start - _ONE_DAY))
        return self.dates[index] if index < len(self.dates) else None


@dataclass(frozen=True, slots=True)
class Interval(Frequency):
    """Every N days, weeks or months, counted from the habit's start date."""

    every: int
    unit: IntervalUnit

    def __post_init__(self) -> None:
        if not _is_plain_int(self.every) or self.every < 1:
            raise ValidationError(ErrorCode.INTERVAL_INVALID, every=self.every)
        object.__setattr__(self, "unit", IntervalUnit(self.unit))

    @property
    def _step_days(self) -> int:
        return self.every * (_DAYS_IN_WEEK if self.unit is IntervalUnit.WEEKS else 1)

    def occurs_on(self, day: date, start: date) -> bool:
        if day < start:
            return False
        if self.unit is IntervalUnit.MONTHS:
            months = _months_between(start, day)
            return months % self.every == 0 and day == _month_occurrence(start, months)
        return (day - start).days % self._step_days == 0

    def last_on_or_before(self, day: date, start: date) -> date | None:
        if day < start:
            return None
        if self.unit is IntervalUnit.MONTHS:
            index = _months_between(start, day)
            index -= index % self.every
            while index >= 0:
                candidate = _month_occurrence(start, index)
                if candidate <= day:
                    return candidate
                index -= self.every
            return None
        step = self._step_days
        return start + timedelta(days=(day - start).days // step * step)

    def first_after(self, day: date, start: date) -> date | None:
        if day < start:
            return start
        if self.unit is IntervalUnit.MONTHS:
            index = _months_between(start, day)
            index -= index % self.every
            candidate = _month_occurrence(start, index)
            while candidate <= day:
                index += self.every
                candidate = _month_occurrence(start, index)
            return candidate
        step = self._step_days
        return start + timedelta(days=((day - start).days // step + 1) * step)
