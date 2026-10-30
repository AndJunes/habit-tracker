"""Domain errors: a stable code plus the offending values."""

import pytest

from habit_tracker.domain.errors import ErrorCode, ValidationError


def test_a_validation_error_is_a_value_error() -> None:
    assert issubclass(ValidationError, ValueError)


def test_a_validation_error_carries_its_code_and_context() -> None:
    error = ValidationError(ErrorCode.HABIT_NOT_FOUND, habit_id=99)
    assert error.code is ErrorCode.HABIT_NOT_FOUND
    assert error.context == {"habit_id": 99}


def test_the_message_of_an_error_without_context_is_its_code() -> None:
    assert str(ValidationError(ErrorCode.NAME_REQUIRED)) == "name_required"


def test_the_message_lists_the_context_values() -> None:
    error = ValidationError(ErrorCode.NAME_TOO_LONG, limit=80)
    assert str(error) == "name_too_long (limit=80)"


def test_a_validation_error_without_context_has_an_empty_one() -> None:
    assert ValidationError(ErrorCode.DATES_REQUIRED).context == {}


def test_a_validation_error_can_be_caught_by_its_code() -> None:
    with pytest.raises(ValidationError, match="quota_out_of_range"):
        raise ValidationError(ErrorCode.QUOTA_OUT_OF_RANGE, times=0)


def test_error_codes_are_unique_lowercase_names() -> None:
    values = [code.value for code in ErrorCode]
    assert values == [code.name.lower() for code in ErrorCode]
    assert len(set(values)) == len(values)
