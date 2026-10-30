"""Rules that involve more than one field or the rest of the habits."""

from collections.abc import Iterable
from datetime import date

from .errors import ErrorCode, ValidationError
from .frequency import FixedDates, Frequency
from .models import MAX_NAME_LENGTH, Area, Habit


def _fold(name: str) -> str:
    """The form in which two names are compared: single spaces, case ignored."""
    return " ".join(name.split()).casefold()


def validate_habit_fields(
    *,
    name: str,
    area_id: str,
    areas: Iterable[Area],
    start: date,
    end: date | None,
    frequency: Frequency,
    habits: Iterable[Habit],
    own_id: int | None = None,
) -> str:
    """Check a habit's fields against each other and the existing habits.

    Returns the cleaned name or raises :class:`ValidationError`. ``own_id`` is
    the id of the habit being edited, which may keep its own name.
    """
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValidationError(ErrorCode.NAME_REQUIRED)
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationError(ErrorCode.NAME_TOO_LONG, limit=MAX_NAME_LENGTH)
    folded = cleaned.casefold()
    if any(_fold(habit.name) == folded and habit.id != own_id for habit in habits):
        raise ValidationError(ErrorCode.NAME_DUPLICATE, name=cleaned)
    if not any(area.id == area_id for area in areas):
        raise ValidationError(ErrorCode.AREA_UNKNOWN, area_id=area_id)
    if end is not None and end < start:
        raise ValidationError(ErrorCode.END_BEFORE_START, start=start, end=end)
    if isinstance(frequency, FixedDates):
        for chosen in frequency.dates:
            if chosen < start or (end is not None and chosen > end):
                raise ValidationError(ErrorCode.DATE_OUT_OF_RANGE, day=chosen)
    return cleaned
