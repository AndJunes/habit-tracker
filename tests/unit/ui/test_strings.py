from datetime import date
from pathlib import Path

import pytest

from habit_tracker.domain.enums import IntervalUnit, Period, Weekday
from habit_tracker.domain.errors import ErrorCode, ValidationError
from habit_tracker.domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from habit_tracker.ui.strings import (
    describe_frequency,
    error_message,
    fatal_message,
    import_message,
    recovery_message,
)

MON, TUE, WED, THU, FRI, SAT, SUN = Weekday


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        (Daily(), ""),
        (Weekdays(frozenset({FRI})), "solo viernes"),
        (Weekdays(frozenset({MON, WED})), "solo lunes y miércoles"),
        (Weekdays(frozenset({MON, TUE, WED, THU, FRI})), "descansa sábado y domingo"),
        (Weekdays(frozenset(Weekday)), ""),
        (Quota(3), "3 veces por semana"),
        (Quota(1, Period.MONTH), "1 vez por mes"),
        (FixedDates((date(2026, 11, 5),)), "1 fecha elegida"),
        (
            FixedDates((date(2026, 11, 5), date(2026, 11, 9), date(2026, 11, 20))),
            "3 fechas elegidas",
        ),
        (Interval(1, IntervalUnit.DAYS), "cada día"),
        (Interval(2, IntervalUnit.WEEKS), "cada 2 semanas"),
        (Interval(1, IntervalUnit.MONTHS), "cada mes"),
    ],
)
def test_describe_frequency(frequency: Frequency, expected: str) -> None:
    assert describe_frequency(frequency) == expected


def test_describe_frequency_rejects_unknown_types() -> None:
    class Odd(Frequency):
        def occurs_on(self, day: date, start: date) -> bool:
            return False

        def last_on_or_before(self, day: date, start: date) -> date | None:
            return None

        def first_after(self, day: date, start: date) -> date | None:
            return None

    with pytest.raises(TypeError):
        describe_frequency(Odd())


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_error_code_has_a_message(code: ErrorCode) -> None:
    error = ValidationError(code, limit=80, period="week", day="2026-11-05")
    assert error_message(error)


def test_quota_message_names_the_period_and_its_maximum() -> None:
    weekly = error_message(ValidationError(ErrorCode.QUOTA_OUT_OF_RANGE, period="week", times=9))
    monthly = error_message(
        ValidationError(ErrorCode.QUOTA_OUT_OF_RANGE, period="month", times=40)
    )
    assert "semana" in weekly
    assert "1 a 7" in weekly
    assert "mes" in monthly
    assert "1 a 31" in monthly


def test_the_import_message_counts_habits_and_mentions_what_was_left_out() -> None:
    backup = Path("/data/habitos.json.bak-v3-20261030")

    one = import_message(1, 0, backup)
    several = import_message(3, 2, backup)

    assert "1 hábito " in one
    assert str(backup) in one
    assert "no se pudieron importar" not in one
    assert "3 hábitos" in several
    assert "no se pudieron importar (2)" in several


def test_the_recovery_and_fatal_messages_say_what_happened() -> None:
    assert "/data/habits.sqlite3.corrupt" in recovery_message(Path("/data/habits.sqlite3.corrupt"))
    assert "disk full" in fatal_message("disk full")
