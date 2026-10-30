"""Validation: habit fields against each other, and the Measurement and Reminder constructors."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import FrozenInstanceError
from datetime import UTC, date, time
from decimal import Decimal
from typing import Any

import pytest

from habit_tracker.domain.enums import MeasurementKind, Weekday
from habit_tracker.domain.errors import ErrorCode, ValidationError
from habit_tracker.domain.frequency import Daily, FixedDates, Quota
from habit_tracker.domain.models import (
    MAX_NAME_LENGTH,
    Area,
    Habit,
    Measurement,
    Reminder,
    is_finite_number,
)
from habit_tracker.domain.validation import validate_habit_fields

HabitFactory = Callable[..., Habit]
RaisesCode = Callable[[ErrorCode], AbstractContextManager[None]]
Validate = Callable[..., str]

START = date(2026, 6, 1)
NAN = float("nan")
INF = float("inf")


@pytest.fixture
def validate(areas: list[Area]) -> Validate:
    """Run ``validate_habit_fields`` on a valid form; keyword arguments override fields."""

    def run(**overrides: Any) -> str:
        fields: dict[str, Any] = {
            "name": "Read",
            "area_id": "gym",
            "areas": areas,
            "start": START,
            "end": None,
            "frequency": Daily(),
            "habits": [],
        }
        fields.update(overrides)
        return validate_habit_fields(**fields)

    return run


# ---------- Name ----------


@pytest.mark.parametrize(
    ("typed", "cleaned"),
    [
        pytest.param("Read", "Read", id="already-clean"),
        pytest.param("  Read  ", "Read", id="outer-spaces"),
        pytest.param("Read   a   lot", "Read a lot", id="repeated-spaces"),
        pytest.param("Read\ta\nlot", "Read a lot", id="tabs-and-newlines"),
    ],
)
def test_name_is_cleaned_to_single_spaces(validate: Validate, typed: str, cleaned: str) -> None:
    assert validate(name=typed) == cleaned


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param("\t\n ", id="whitespace"),
    ],
)
def test_blank_name_is_rejected(validate: Validate, raises_code: RaisesCode, name: str) -> None:
    with raises_code(ErrorCode.NAME_REQUIRED):
        validate(name=name)


def test_name_of_the_maximum_length_is_accepted(validate: Validate) -> None:
    name = "a" * MAX_NAME_LENGTH
    assert validate(name=name) == name


def test_name_longer_than_the_maximum_is_rejected(
    validate: Validate, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.NAME_TOO_LONG):
        validate(name="a" * (MAX_NAME_LENGTH + 1))


def test_the_maximum_name_length_is_eighty() -> None:
    assert MAX_NAME_LENGTH == 80


def test_name_too_long_reports_the_limit(validate: Validate) -> None:
    with pytest.raises(ValidationError) as caught:
        validate(name="a" * 81)
    assert caught.value.context == {"limit": 80}


def test_name_length_is_measured_after_cleaning_the_spaces(validate: Validate) -> None:
    padded = "  " + "a" * MAX_NAME_LENGTH + "   "
    assert validate(name=padded) == "a" * MAX_NAME_LENGTH


def test_name_made_of_short_words_counts_single_spaces_only(validate: Validate) -> None:
    spaced = "a" + "   a" * 39  # 40 letters separated by wide gaps; 79 characters once cleaned
    assert validate(name=spaced) == " ".join("a" * 40)


# ---------- Duplicate names ----------


@pytest.mark.parametrize(
    "typed",
    [
        pytest.param("Read", id="same"),
        pytest.param("read", id="lowercase"),
        pytest.param("READ", id="uppercase"),
        pytest.param(" read ", id="spaces-and-case"),
        pytest.param("Read   ", id="trailing-spaces"),
    ],
)
def test_a_name_already_in_use_is_rejected_ignoring_case_and_spaces(
    validate: Validate, make_habit: HabitFactory, raises_code: RaisesCode, typed: str
) -> None:
    with raises_code(ErrorCode.NAME_DUPLICATE):
        validate(name=typed, habits=[make_habit(name="Read")])


def test_names_are_compared_with_full_case_folding(
    validate: Validate, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    existing = make_habit(name="Straße")
    with raises_code(ErrorCode.NAME_DUPLICATE):
        validate(name="STRASSE", habits=[existing])


def test_inner_spaces_are_ignored_when_comparing_names(
    validate: Validate, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.NAME_DUPLICATE):
        validate(name="Read   a lot", habits=[make_habit(name="Read a lot")])


def test_a_stored_name_with_extra_spaces_still_counts_as_a_duplicate(
    validate: Validate, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.NAME_DUPLICATE):
        validate(name="Read a lot", habits=[make_habit(name="  Read   A  Lot ")])


@pytest.mark.parametrize("typed", ["Reading", "Read more", "Rea"])
def test_a_different_name_is_not_a_duplicate(
    validate: Validate, make_habit: HabitFactory, typed: str
) -> None:
    assert validate(name=typed, habits=[make_habit(name="Read")]) == typed


def test_a_name_in_use_is_a_duplicate_even_in_another_area(
    validate: Validate, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    existing = make_habit(name="Read", area_id="english")
    with raises_code(ErrorCode.NAME_DUPLICATE):
        validate(name="Read", area_id="gym", habits=[existing])


def test_a_habit_being_edited_may_keep_its_own_name(
    validate: Validate, make_habit: HabitFactory
) -> None:
    habit = make_habit(id=4, name="Read")
    assert validate(name="Read", habits=[habit], own_id=4) == "Read"


def test_a_habit_being_edited_may_change_the_case_of_its_own_name(
    validate: Validate, make_habit: HabitFactory
) -> None:
    habit = make_habit(id=4, name="Read")
    assert validate(name=" READ ", habits=[habit], own_id=4) == "READ"


def test_a_habit_being_edited_cannot_take_the_name_of_another(
    validate: Validate, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    mine = make_habit(id=4, name="Read")
    other = make_habit(id=5, name="Run")
    with raises_code(ErrorCode.NAME_DUPLICATE):
        validate(name=" run", habits=[mine, other], own_id=4)


def test_a_new_habit_cannot_take_a_name_even_if_an_edit_id_is_unrelated(
    validate: Validate, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.NAME_DUPLICATE):
        validate(name="Read", habits=[make_habit(id=4, name="Read")], own_id=9)


# ---------- Area, dates ----------


def test_an_unknown_area_is_rejected(validate: Validate, raises_code: RaisesCode) -> None:
    with raises_code(ErrorCode.AREA_UNKNOWN):
        validate(area_id="nowhere")


def test_an_unknown_area_reports_the_offending_id(validate: Validate) -> None:
    with pytest.raises(ValidationError) as caught:
        validate(area_id="nowhere")
    assert caught.value.context == {"area_id": "nowhere"}


def test_a_known_area_is_accepted(validate: Validate) -> None:
    assert validate(area_id="english") == "Read"


def test_an_end_before_the_start_is_rejected(validate: Validate, raises_code: RaisesCode) -> None:
    with raises_code(ErrorCode.END_BEFORE_START):
        validate(start=date(2026, 6, 10), end=date(2026, 6, 1))


def test_an_end_on_the_start_day_is_accepted(validate: Validate) -> None:
    assert validate(start=START, end=START) == "Read"


def test_no_end_is_accepted(validate: Validate) -> None:
    assert validate(end=None) == "Read"


@pytest.mark.parametrize(
    ("chosen", "end"),
    [
        pytest.param(date(2026, 7, 1), date(2026, 6, 30), id="after-the-end"),
        pytest.param(date(2026, 5, 31), None, id="before-the-start"),
        pytest.param(date(2026, 5, 1), None, id="long-before-the-start"),
    ],
)
def test_fixed_dates_outside_the_habit_period_are_rejected(
    validate: Validate, raises_code: RaisesCode, chosen: date, end: date | None
) -> None:
    with raises_code(ErrorCode.DATE_OUT_OF_RANGE):
        validate(frequency=FixedDates((chosen,)), end=end)


def test_the_out_of_range_fixed_date_is_reported(validate: Validate) -> None:
    with pytest.raises(ValidationError) as caught:
        validate(frequency=FixedDates((date(2026, 6, 5), date(2026, 8, 1))), end=date(2026, 6, 30))
    assert caught.value.context == {"day": date(2026, 8, 1)}


def test_fixed_dates_on_the_first_and_last_day_of_the_period_are_accepted(
    validate: Validate,
) -> None:
    end = date(2026, 6, 30)
    assert validate(frequency=FixedDates((START, end)), end=end) == "Read"


def test_fixed_dates_without_an_end_may_be_far_in_the_future(validate: Validate) -> None:
    assert validate(frequency=FixedDates((date(2031, 1, 1),)), end=None) == "Read"


def test_other_frequencies_are_not_checked_against_the_period(validate: Validate) -> None:
    assert validate(frequency=Quota(times=3), end=date(2026, 6, 2)) == "Read"


# ---------- Measurement ----------


def test_a_measurement_keeps_its_goal_unit_and_kind() -> None:
    measurement = Measurement(MeasurementKind.QUANTITY, goal=10, unit="pages")
    assert (measurement.kind, measurement.goal, measurement.unit) == (
        MeasurementKind.QUANTITY,
        10,
        "pages",
    )
    assert measurement.minimum is None
    assert measurement.ideal is None


def test_a_measurement_accepts_a_fractional_goal() -> None:
    assert Measurement(MeasurementKind.QUANTITY, goal=0.5, unit="liters").goal == 0.5


@pytest.mark.parametrize(
    "goal",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(NAN, id="nan"),
        pytest.param(INF, id="infinity"),
        pytest.param(-INF, id="negative-infinity"),
        pytest.param(True, id="bool"),
        pytest.param("10", id="text"),
    ],
)
def test_a_measurement_goal_must_be_a_positive_finite_number(
    raises_code: RaisesCode, goal: Any
) -> None:
    with raises_code(ErrorCode.GOAL_INVALID):
        Measurement(MeasurementKind.QUANTITY, goal=goal, unit="glasses")


@pytest.mark.parametrize("unit", ["", "   ", "\t"])
def test_a_measurement_needs_a_unit(raises_code: RaisesCode, unit: str) -> None:
    with raises_code(ErrorCode.UNIT_REQUIRED):
        Measurement(MeasurementKind.QUANTITY, goal=5, unit=unit)


def test_a_measurement_unit_is_stripped() -> None:
    assert Measurement(MeasurementKind.QUANTITY, goal=5, unit="  glasses ").unit == "glasses"


@pytest.mark.parametrize(
    ("minimum", "ideal"),
    [
        pytest.param(-1, None, id="negative-minimum"),
        pytest.param(None, -1, id="negative-ideal"),
        pytest.param(NAN, None, id="nan-minimum"),
        pytest.param(None, NAN, id="nan-ideal"),
        pytest.param(INF, None, id="infinite-minimum"),
        pytest.param(None, INF, id="infinite-ideal"),
        pytest.param(True, None, id="bool-minimum"),
        pytest.param(None, True, id="bool-ideal"),
        pytest.param(9, 6, id="minimum-above-ideal"),
    ],
)
def test_measurement_bounds_must_be_finite_non_negative_and_ordered(
    raises_code: RaisesCode, minimum: Any, ideal: Any
) -> None:
    with raises_code(ErrorCode.BOUNDS_INVALID):
        Measurement(MeasurementKind.QUANTITY, goal=5, unit="glasses", minimum=minimum, ideal=ideal)


@pytest.mark.parametrize(
    ("minimum", "ideal"),
    [
        pytest.param(5, 5, id="equal"),
        pytest.param(0, 8, id="zero-minimum"),
        pytest.param(3, None, id="only-minimum"),
        pytest.param(None, 8, id="only-ideal"),
        pytest.param(2.5, 7.5, id="fractions"),
    ],
)
def test_measurement_bounds_that_are_ordered_are_accepted(
    minimum: float | None, ideal: float | None
) -> None:
    measurement = Measurement(
        MeasurementKind.DURATION, goal=5, unit="minutes", minimum=minimum, ideal=ideal
    )
    assert (measurement.minimum, measurement.ideal) == (minimum, ideal)


def test_a_measurement_kind_given_as_text_becomes_a_kind() -> None:
    measurement = Measurement("duration", goal=15, unit="minutes")  # type: ignore[arg-type]
    assert measurement.kind is MeasurementKind.DURATION


def test_a_measurement_rejects_an_unknown_kind() -> None:
    with pytest.raises(ValueError, match="weight"):
        Measurement("weight", goal=15, unit="kg")  # type: ignore[arg-type]


def test_a_measurement_cannot_be_modified() -> None:
    measurement = Measurement(MeasurementKind.QUANTITY, goal=5, unit="glasses")
    with pytest.raises(FrozenInstanceError):
        measurement.goal = 6  # type: ignore[misc]


def test_a_measurement_goal_too_large_for_a_float_is_rejected_with_a_code(
    raises_code: RaisesCode,
) -> None:
    with raises_code(ErrorCode.GOAL_INVALID):
        Measurement(MeasurementKind.QUANTITY, goal=10**400, unit="glasses")


# ---------- Reminder ----------


def test_a_reminder_keeps_the_time_to_the_minute() -> None:
    assert Reminder(at=time(7, 30)).at == time(7, 30)


def test_a_reminder_drops_seconds_and_microseconds() -> None:
    assert Reminder(at=time(20, 0, 45, 123456)).at == time(20, 0)


def test_a_reminder_drops_the_time_zone() -> None:
    assert Reminder(at=time(20, 0, tzinfo=UTC)).at.tzinfo is None


def test_a_reminder_without_weekdays_means_the_days_the_habit_is_due() -> None:
    assert Reminder(at=time(20, 0)).weekdays == frozenset()


def test_reminder_weekdays_given_as_numbers_become_weekdays() -> None:
    reminder = Reminder(at=time(20, 0), weekdays=frozenset({0, 4}))  # type: ignore[arg-type]
    assert reminder.weekdays == frozenset({Weekday.MONDAY, Weekday.FRIDAY})
    assert {type(day) for day in reminder.weekdays} == {Weekday}


def test_a_reminder_rejects_a_number_that_is_not_a_weekday() -> None:
    with pytest.raises(ValueError, match="9"):
        Reminder(at=time(20, 0), weekdays=frozenset({9}))  # type: ignore[arg-type]


# ---------- is_finite_number ----------


@pytest.mark.parametrize("value", [0, 1, -1, 2.5, -0.5, 1e308, 10**30])
def test_real_numbers_are_finite_numbers(value: float) -> None:
    assert is_finite_number(value) is True


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(NAN, id="nan"),
        pytest.param(INF, id="infinity"),
        pytest.param(-INF, id="negative-infinity"),
        pytest.param("1", id="text"),
        pytest.param(None, id="none"),
        pytest.param(Decimal("1"), id="decimal"),
        pytest.param(1 + 2j, id="complex"),
    ],
)
def test_booleans_nan_infinities_and_non_numbers_are_not_finite_numbers(value: object) -> None:
    assert is_finite_number(value) is False
