"""Domain errors carry a stable code; the UI turns codes into user-facing text."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NAME_REQUIRED = "name_required"
    NAME_TOO_LONG = "name_too_long"
    NAME_DUPLICATE = "name_duplicate"
    TITLE_REQUIRED = "title_required"
    AREA_UNKNOWN = "area_unknown"
    END_BEFORE_START = "end_before_start"
    WEEKDAYS_REQUIRED = "weekdays_required"
    QUOTA_OUT_OF_RANGE = "quota_out_of_range"
    DATES_REQUIRED = "dates_required"
    DATE_INVALID = "date_invalid"
    DATE_OUT_OF_RANGE = "date_out_of_range"
    INTERVAL_INVALID = "interval_invalid"
    GOAL_INVALID = "goal_invalid"
    UNIT_REQUIRED = "unit_required"
    BOUNDS_INVALID = "bounds_invalid"
    VALUE_INVALID = "value_invalid"
    HABIT_NOT_FOUND = "habit_not_found"


class ValidationError(ValueError):
    """Raised when input does not satisfy a domain rule.

    ``code`` identifies the broken rule and ``context`` holds the offending values.
    """

    def __init__(self, code: ErrorCode, **context: object) -> None:
        self.code = code
        self.context = context
        details = ", ".join(f"{key}={value!r}" for key, value in context.items())
        super().__init__(f"{code.value} ({details})" if details else code.value)
