"""Domain models: the data every other layer exchanges."""

import math
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from .enums import MeasurementKind, Weekday
from .errors import ErrorCode, ValidationError
from .frequency import Frequency

MAX_NAME_LENGTH = 80

# A soft limit: the interface warns before the person goes past it.
RECOMMENDED_MAX_HABITS = 6


def is_finite_number(value: object) -> bool:
    """True for a real ``int`` or ``float`` that is not NaN or infinite (``bool`` is excluded)."""
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is int:
        try:
            return math.isfinite(float(value))
        except OverflowError:  # an int beyond the range of a float
            return False
    return False


@dataclass(frozen=True, slots=True)
class Area:
    """A life area that groups habits, with the colors that paint it."""

    id: str
    name: str
    color: str
    soft_color: str = ""


@dataclass(frozen=True, slots=True)
class Measurement:
    """What is recorded each time a measured habit is done."""

    kind: MeasurementKind
    goal: float
    unit: str
    minimum: float | None = None
    ideal: float | None = None

    def __post_init__(self) -> None:
        if not is_finite_number(self.goal) or self.goal <= 0:
            raise ValidationError(ErrorCode.GOAL_INVALID, goal=self.goal)
        unit = self.unit.strip()
        if not unit:
            raise ValidationError(ErrorCode.UNIT_REQUIRED)
        for bound in (self.minimum, self.ideal):
            if bound is not None and (not is_finite_number(bound) or bound < 0):
                raise ValidationError(ErrorCode.BOUNDS_INVALID, bound=bound)
        if self.minimum is not None and self.ideal is not None and self.minimum > self.ideal:
            raise ValidationError(ErrorCode.BOUNDS_INVALID, minimum=self.minimum, ideal=self.ideal)
        object.__setattr__(self, "kind", MeasurementKind(self.kind))
        object.__setattr__(self, "unit", unit)


@dataclass(frozen=True, slots=True)
class Reminder:
    """A daily notification time; no weekdays means "the days the habit is due"."""

    at: time
    weekdays: frozenset[Weekday] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", self.at.replace(second=0, microsecond=0, tzinfo=None))
        object.__setattr__(self, "weekdays", frozenset(Weekday(day) for day in self.weekdays))


@dataclass
class Habit:
    """A habit with its schedule and its history.

    ``completions`` is the single source of truth for "done": a day is done
    when it is a key, and the value is what was measured (``None`` for yes/no
    habits). A value below the goal still counts: goals guide, they never judge.
    """

    id: int
    name: str
    area_id: str
    frequency: Frequency
    start: date
    end: date | None = None
    description: str = ""
    notes: str = ""
    measurement: Measurement | None = None
    reminder: Reminder | None = None
    completions: dict[date, float | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise ValidationError(ErrorCode.END_BEFORE_START, start=self.start, end=self.end)

    def applies_on(self, day: date) -> bool:
        """Whether the habit is due on ``day`` (never before it starts or after it ends)."""
        return (self.end is None or day <= self.end) and self.frequency.occurs_on(day, self.start)

    def is_done(self, day: date) -> bool:
        return day in self.completions

    def is_active(self, today: date) -> bool:
        return self.end is None or self.end >= today

    def previous_scheduled(self, day: date, *, inclusive: bool = True) -> date | None:
        """The latest due day on or before ``day`` (strictly before when not ``inclusive``).

        Once a habit has ended the search starts from its last day, so its
        streak stays frozen instead of fading with time.
        """
        limit = day if inclusive else day - timedelta(days=1)
        if self.end is not None:
            limit = min(limit, self.end)
        return self.frequency.last_on_or_before(limit, self.start)

    def next_scheduled(self, day: date) -> date | None:
        """The first due day strictly after ``day``, or ``None`` if the habit has ended."""
        candidate = self.frequency.first_after(day, self.start)
        if candidate is None or (self.end is not None and candidate > self.end):
            return None
        return candidate


@dataclass(frozen=True, slots=True)
class ImportantDate:
    """An event of the month (exam, delivery, meeting) shown on the calendar."""

    day: date
    title: str


@dataclass(frozen=True, slots=True)
class PriorityNote:
    """The single task written the night before for ``for_day``."""

    for_day: date
    text: str


@dataclass
class Snapshot:
    """Everything the application stores, loaded together."""

    areas: list[Area] = field(default_factory=list)
    habits: list[Habit] = field(default_factory=list)
    important_dates: list[ImportantDate] = field(default_factory=list)
    priority: PriorityNote | None = None
