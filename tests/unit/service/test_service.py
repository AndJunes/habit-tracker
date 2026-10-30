"""The application service: queries on the injected clock, marking, editing and validation."""

import copy
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.enums import DayStatus, MeasurementKind, Period, Weekday
from habit_tracker.domain.errors import ErrorCode, ValidationError
from habit_tracker.domain.frequency import Daily, FixedDates, Quota, Weekdays
from habit_tracker.domain.models import (
    Area,
    Habit,
    ImportantDate,
    Measurement,
    PriorityNote,
    Reminder,
)
from habit_tracker.service import HabitService

HabitFactory = Callable[..., Habit]
RepositoryFactory = Callable[..., Any]
ServiceFactory = Callable[..., HabitService]
RaisesCode = Callable[[ErrorCode], AbstractContextManager[None]]

TODAY = date(2026, 6, 11)  # a Thursday
TOMORROW = date(2026, 6, 12)
NAN = float("nan")
INF = float("inf")
PAGES = Measurement(MeasurementKind.QUANTITY, goal=10, unit="pages")


def june(*days: int) -> list[date]:
    return [date(2026, 6, number) for number in days]


def at(hour: int, minute: int, *, day: int = 11) -> datetime:
    return datetime(2026, 6, day, hour, minute)


# ---------- The clock governs every "today" ----------


def test_today_is_the_day_of_the_injected_clock(
    make_service: ServiceFactory, clock: FixedClock
) -> None:
    service = make_service()
    assert service.today() == TODAY
    clock.current = datetime(2026, 12, 31, 23, 59)
    assert service.today() == date(2026, 12, 31)


def test_day_progress_defaults_to_the_day_of_the_clock(
    make_service: ServiceFactory, make_habit: HabitFactory, clock: FixedClock
) -> None:
    first = make_habit(id=1, done=june(10, 11))
    second = make_habit(id=2, name="Run", done=june(10))
    service = make_service(first, second)
    assert service.day_progress() == (1, 2)
    clock.current = datetime(2026, 6, 10, 9, 0)
    assert service.day_progress() == (2, 2)


def test_day_progress_of_an_explicit_day_ignores_the_clock(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    first = make_habit(id=1, done=june(10, 11))
    second = make_habit(id=2, name="Run", done=june(10))
    service = make_service(first, second)
    assert service.day_progress(date(2026, 6, 10)) == (2, 2)
    assert service.day_progress(date(2026, 6, 9)) == (0, 2)


def test_priority_for_today_is_the_note_written_for_the_clock_day(
    make_service: ServiceFactory, make_repository: RepositoryFactory
) -> None:
    service = make_service(repository=make_repository(priority=PriorityNote(TODAY, "Send it")))
    assert service.priority_for_today() == "Send it"
    assert service.priority_for_tomorrow() is None


def test_priority_for_tomorrow_is_the_note_written_for_the_day_after_the_clock_day(
    make_service: ServiceFactory, make_repository: RepositoryFactory
) -> None:
    service = make_service(repository=make_repository(priority=PriorityNote(TOMORROW, "Call")))
    assert service.priority_for_tomorrow() == "Call"
    assert service.priority_for_today() is None


@pytest.mark.parametrize(
    "for_day",
    [
        pytest.param(date(2026, 6, 10), id="yesterday"),
        pytest.param(date(2026, 6, 13), id="in-two-days"),
        pytest.param(date(2025, 6, 11), id="a-year-ago"),
    ],
)
def test_a_note_for_any_other_day_is_shown_neither_today_nor_tomorrow(
    make_service: ServiceFactory, make_repository: RepositoryFactory, for_day: date
) -> None:
    service = make_service(repository=make_repository(priority=PriorityNote(for_day, "Old")))
    assert service.priority_for_today() is None
    assert service.priority_for_tomorrow() is None


def test_the_note_written_for_tomorrow_becomes_todays_when_the_clock_moves_on(
    make_service: ServiceFactory, make_repository: RepositoryFactory, clock: FixedClock
) -> None:
    service = make_service(repository=make_repository(priority=PriorityNote(TOMORROW, "Call")))
    assert service.priority_for_today() is None
    clock.current += timedelta(days=1)
    assert service.priority_for_today() == "Call"
    assert service.priority_for_tomorrow() is None


def test_a_note_with_empty_text_is_not_shown(
    make_service: ServiceFactory, make_repository: RepositoryFactory
) -> None:
    service = make_service(repository=make_repository(priority=PriorityNote(TODAY, "")))
    assert service.priority_for_today() is None


def test_active_habits_exclude_the_ones_that_have_ended(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    ended = make_habit(id=10, name="Ended", end=date(2026, 6, 1))
    ending_later = make_habit(id=11, name="Ending later", end=date(2026, 12, 31))
    ending_today = make_habit(id=12, name="Ending today", end=TODAY)
    open_ended = make_habit(id=13, name="Open ended")
    service = make_service(ended, ending_later, ending_today, open_ended)
    assert [habit.id for habit in service.active_habits()] == [11, 12, 13]


def test_active_habits_follow_the_clock(
    make_service: ServiceFactory, make_habit: HabitFactory, clock: FixedClock
) -> None:
    service = make_service(make_habit(id=1, end=TODAY))
    assert [habit.id for habit in service.active_habits()] == [1]
    clock.current += timedelta(days=1)
    assert service.active_habits() == ()


def test_current_streak_is_measured_on_the_clock_day(
    make_service: ServiceFactory, make_habit: HabitFactory, clock: FixedClock
) -> None:
    service = make_service(make_habit(done=june(9, 10)))
    habit = service.get_habit(1)
    assert service.current_streak(habit) == 2
    clock.current = datetime(2026, 6, 13, 9, 0)  # June 11 and 12 were missed
    assert service.current_streak(habit) == 0


def test_longest_streak_is_the_best_run_across_every_habit(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    # A run of 3 that already ended and a current run of 1.
    broken = make_habit(id=1, done=june(2, 3, 4, 11))
    short = make_habit(id=2, name="Run", done=june(10))
    assert make_service(broken, short).longest_streak() == 3


def test_longest_streak_without_habits_is_zero(make_service: ServiceFactory) -> None:
    assert make_service().longest_streak() == 0


def test_longest_streak_of_a_quota_habit_follows_the_clock(
    make_service: ServiceFactory, make_habit: HabitFactory, clock: FixedClock
) -> None:
    weekly = make_habit(frequency=Quota(times=1), done=june(1, 8, 15, 22))
    service = make_service(weekly)
    assert service.longest_streak() == 2  # only the weeks of June 1 and 8 have happened
    clock.current = datetime(2026, 6, 30, 9, 0)
    assert service.longest_streak() == 4


def test_done_in_period_counts_the_week_of_the_clock_day_by_default(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    habit = make_habit(frequency=Quota(3), done=june(5, 8, 10))
    service = make_service(habit)
    assert service.done_in_period(service.get_habit(1)) == 2
    assert service.done_in_period(service.get_habit(1), date(2026, 6, 5)) == 1


def test_done_in_period_of_a_monthly_quota_counts_the_month(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    habit = make_habit(frequency=Quota(4, Period.MONTH), done=[date(2026, 5, 30), *june(2, 10)])
    service = make_service(habit)
    assert service.done_in_period(service.get_habit(1)) == 2


def test_done_in_period_is_only_for_quota_habits(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    with pytest.raises(ValueError, match="quota"):
        service.done_in_period(service.get_habit(1))


def test_next_due_defaults_to_the_day_after_the_clock_day(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    assert service.next_due(service.get_habit(1)) == TOMORROW


def test_next_due_since_a_given_day(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    assert service.next_due(service.get_habit(1), date(2026, 6, 20)) == date(2026, 6, 21)


def test_next_due_is_none_for_a_habit_that_ends_today(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(end=TODAY))
    assert service.next_due(service.get_habit(1)) is None


def test_month_stats_treat_the_clock_day_as_pending_and_later_days_as_missed(
    make_service: ServiceFactory, make_habit: HabitFactory, clock: FixedClock
) -> None:
    service = make_service(make_habit(done=june(10)))
    assert service.month_stats(2026, 6).matrix["gym"][11] is DayStatus.PENDING
    clock.current += timedelta(days=1)
    assert service.month_stats(2026, 6).matrix["gym"][11] is DayStatus.MISSED


def test_month_stats_count_the_days_from_the_first_until_the_clock_day(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(done=june(9, 10)))
    stats = service.month_stats(2026, 6)
    assert len(stats.counts_by_day) == 11
    assert stats.total == 2


def test_completed_areas_by_day_comes_from_the_loaded_habits(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    gym = make_habit(id=1, area_id="gym", done=june(11))
    english = make_habit(id=2, name="English", area_id="english", done=june(10, 11))
    service = make_service(gym, english)
    assert service.completed_areas_by_day(2026, 6) == {11: ["gym", "english"], 10: ["english"]}


# ---------- Loading and lookups ----------


def test_the_service_exposes_the_areas_and_habits_the_repository_holds(
    make_service: ServiceFactory, make_habit: HabitFactory, areas: list[Area]
) -> None:
    service = make_service(make_habit(id=1), make_habit(id=2, name="Run"))
    assert service.areas() == tuple(areas)
    assert [habit.id for habit in service.habits()] == [1, 2]


def test_find_habit_returns_none_for_an_unknown_id(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    assert service.find_habit(99) is None
    assert service.find_habit(1) is not None


def test_get_habit_raises_habit_not_found_for_an_unknown_id(
    make_service: ServiceFactory, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.HABIT_NOT_FOUND):
        make_service().get_habit(99)


def test_habit_not_found_reports_the_id(make_service: ServiceFactory) -> None:
    with pytest.raises(ValidationError) as caught:
        make_service().get_habit(99)
    assert caught.value.context == {"habit_id": 99}


def test_area_of_returns_the_area_of_a_habit(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(area_id="english"))
    area = service.area_of(service.get_habit(1))
    assert area is not None
    assert area.id == "english"


def test_area_of_returns_none_when_the_area_no_longer_exists(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(area_id="vanished"))
    assert service.area_of(service.get_habit(1)) is None


# ---------- Marking and unmarking ----------


def test_marking_a_day_adds_it_to_the_completions(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    service.mark(1, True, day=TODAY)
    habit = service.get_habit(1)
    assert habit.is_done(TODAY)
    assert habit.completions == {TODAY: None}


def test_marking_without_a_day_marks_the_clock_day(
    make_service: ServiceFactory, make_habit: HabitFactory, clock: FixedClock
) -> None:
    service = make_service(make_habit())
    service.mark(1, True)
    clock.current += timedelta(days=1)
    service.mark(1, True)
    assert set(service.get_habit(1).completions) == {TODAY, TOMORROW}


def test_unmarking_a_day_removes_it_from_the_completions(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(done=[TODAY]))
    service.mark(1, False, day=TODAY)
    assert not service.get_habit(1).is_done(TODAY)


def test_unmarking_a_day_that_was_not_done_changes_nothing(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(done=june(10)))
    service.mark(1, False, day=TODAY)
    assert set(service.get_habit(1).completions) == {date(2026, 6, 10)}


def test_marking_a_day_twice_keeps_a_single_completion(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    service.mark(1, True, day=TODAY)
    service.mark(1, True, day=TODAY)
    assert service.get_habit(1).completions == {TODAY: None}


def test_marking_only_touches_the_chosen_habit(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(id=1), make_habit(id=2, name="Run"))
    service.mark(2, True, day=TODAY)
    assert service.get_habit(1).completions == {}
    assert service.get_habit(2).completions == {TODAY: None}


def test_marking_with_a_value_stores_the_value_and_counts_the_day_as_done(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES))
    service.mark(1, True, day=TODAY, value=12)
    habit = service.get_habit(1)
    assert habit.is_done(TODAY)
    assert habit.completions == {TODAY: 12}


def test_unmarking_removes_the_day_and_its_recorded_value(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES, completions={TODAY: 12.0}))
    service.mark(1, False, day=TODAY)
    assert service.get_habit(1).completions == {}


def test_marking_again_after_unmarking_does_not_bring_the_old_value_back(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES))
    service.mark(1, True, day=TODAY, value=12)
    service.mark(1, False, day=TODAY)
    service.mark(1, True, day=TODAY)
    assert service.get_habit(1).completions == {TODAY: None}


def test_marking_again_without_a_value_keeps_the_value_already_recorded(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES, completions={TODAY: 12.0}))
    service.mark(1, True, day=TODAY)
    assert service.get_habit(1).completions == {TODAY: 12.0}


def test_marking_again_with_a_new_value_replaces_the_old_one(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES, completions={TODAY: 12.0}))
    service.mark(1, True, day=TODAY, value=15)
    assert service.get_habit(1).completions == {TODAY: 15}


def test_marking_a_measured_habit_without_a_value_records_a_day_without_value(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES))
    service.mark(1, True, day=TODAY)
    assert service.get_habit(1).completions == {TODAY: None}


def test_a_value_of_zero_is_recorded_and_the_day_counts_as_done(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES))
    service.mark(1, True, day=TODAY, value=0)
    habit = service.get_habit(1)
    assert habit.is_done(TODAY)
    assert habit.completions == {TODAY: 0}


def test_a_value_below_the_goal_still_counts_as_done_and_extends_the_streak(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES))
    service.mark(1, True, day=TODAY, value=2)  # goal 10, did 2: it still counts
    habit = service.get_habit(1)
    assert habit.is_done(TODAY)
    assert service.current_streak(habit) == 1


def test_a_habit_without_measurement_ignores_the_value(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=None))
    service.mark(1, True, day=TODAY, value=5)
    habit = service.get_habit(1)
    assert habit.completions == {TODAY: None}
    assert habit.is_done(TODAY)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(NAN, id="nan"),
        pytest.param(INF, id="infinity"),
        pytest.param(-INF, id="negative-infinity"),
        pytest.param(-1, id="negative"),
        pytest.param(-0.5, id="negative-fraction"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
    ],
)
def test_marking_with_an_invalid_value_is_rejected_and_changes_nothing(
    make_service: ServiceFactory,
    make_habit: HabitFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    raises_code: RaisesCode,
    value: Any,
) -> None:
    repository = make_flaky(make_repository(make_habit(measurement=PAGES)))
    service = make_service(repository=repository)
    with raises_code(ErrorCode.VALUE_INVALID):
        service.mark(1, True, day=TODAY, value=value)
    assert service.get_habit(1).completions == {}
    assert repository.writes == []


def test_an_invalid_value_is_rejected_even_for_a_habit_without_measurement(
    make_service: ServiceFactory, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    service = make_service(make_habit(measurement=None))
    with raises_code(ErrorCode.VALUE_INVALID):
        service.mark(1, True, day=TODAY, value=-3)


def test_the_rejected_value_is_reported(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(measurement=PAGES))
    with pytest.raises(ValidationError) as caught:
        service.mark(1, True, day=TODAY, value=-3)
    assert caught.value.context == {"value": -3}


def test_marking_with_a_value_too_large_for_a_float_is_rejected_with_a_code(
    make_service: ServiceFactory, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    service = make_service(make_habit(measurement=PAGES))
    with raises_code(ErrorCode.VALUE_INVALID):
        service.mark(1, True, day=TODAY, value=10**400)


def test_marking_an_unknown_habit_raises_habit_not_found(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    raises_code: RaisesCode,
) -> None:
    repository = make_flaky(make_repository())
    service = make_service(repository=repository)
    with raises_code(ErrorCode.HABIT_NOT_FOUND):
        service.mark(99, True, day=TODAY)
    assert repository.writes == []


# ---------- Adding habits ----------


def test_adding_a_habit_stores_it_with_a_cleaned_name_and_trimmed_texts(
    make_service: ServiceFactory,
) -> None:
    service = make_service()
    habit = service.add_habit(
        name="  Read   daily ",
        area_id="english",
        frequency=Daily(),
        description="  to relax ",
        notes=" chapter by chapter  ",
    )
    assert habit.name == "Read daily"
    assert habit.description == "to relax"
    assert habit.notes == "chapter by chapter"
    assert habit.area_id == "english"


def test_adding_a_habit_returns_the_habit_the_service_holds(make_service: ServiceFactory) -> None:
    service = make_service()
    habit = service.add_habit(name="Read", area_id="gym", frequency=Daily())
    assert service.get_habit(habit.id) is habit
    assert service.habits() == (habit,)


def test_a_new_habit_starts_on_the_clock_day_unless_told_otherwise(
    make_service: ServiceFactory,
) -> None:
    service = make_service()
    default = service.add_habit(name="Read", area_id="gym", frequency=Daily())
    chosen = service.add_habit(
        name="Run", area_id="gym", frequency=Daily(), start=date(2026, 7, 1)
    )
    assert default.start == TODAY
    assert chosen.start == date(2026, 7, 1)


def test_a_new_habit_has_no_end_and_no_history_by_default(make_service: ServiceFactory) -> None:
    habit = make_service().add_habit(name="Read", area_id="gym", frequency=Daily())
    assert habit.end is None
    assert habit.completions == {}
    assert habit.measurement is None
    assert habit.reminder is None


def test_a_new_habit_keeps_its_end_measurement_and_reminder(make_service: ServiceFactory) -> None:
    reminder = Reminder(at=time(20, 0), weekdays=frozenset({Weekday.MONDAY}))
    habit = make_service().add_habit(
        name="Read",
        area_id="gym",
        frequency=Daily(),
        end=date(2026, 12, 31),
        measurement=PAGES,
        reminder=reminder,
    )
    assert habit.end == date(2026, 12, 31)
    assert habit.measurement == PAGES
    assert habit.reminder == reminder


def test_the_first_habit_gets_id_one(make_service: ServiceFactory) -> None:
    assert make_service().add_habit(name="Read", area_id="gym", frequency=Daily()).id == 1


def test_a_new_habit_id_continues_from_the_highest_existing_id(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(id=4), make_habit(id=7, name="Run"))
    assert service.add_habit(name="Read", area_id="gym", frequency=Daily()).id == 8


@pytest.mark.parametrize(
    "typed",
    [
        pytest.param("Read", id="same"),
        pytest.param(" read ", id="spaces-and-case"),
        pytest.param("READ", id="uppercase"),
        pytest.param("Read  ", id="trailing-spaces"),
    ],
)
def test_adding_a_habit_with_a_name_already_in_use_is_rejected(
    make_service: ServiceFactory,
    make_habit: HabitFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    raises_code: RaisesCode,
    typed: str,
) -> None:
    repository = make_flaky(make_repository(make_habit(name="Read")))
    service = make_service(repository=repository)
    with raises_code(ErrorCode.NAME_DUPLICATE):
        service.add_habit(name=typed, area_id="gym", frequency=Daily())
    assert len(service.habits()) == 1
    assert repository.writes == []


def test_retrying_to_add_the_same_habit_does_not_duplicate_it(
    make_service: ServiceFactory, raises_code: RaisesCode
) -> None:
    service = make_service()
    service.add_habit(name="Read", area_id="gym", frequency=Daily())
    with raises_code(ErrorCode.NAME_DUPLICATE):
        service.add_habit(name="Read", area_id="gym", frequency=Daily())
    assert len(service.habits()) == 1


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        pytest.param({"name": "  "}, ErrorCode.NAME_REQUIRED, id="blank-name"),
        pytest.param({"name": "x" * 81}, ErrorCode.NAME_TOO_LONG, id="name-too-long"),
        pytest.param({"area_id": "nowhere"}, ErrorCode.AREA_UNKNOWN, id="unknown-area"),
        pytest.param(
            {"start": date(2026, 6, 10), "end": date(2026, 6, 1)},
            ErrorCode.END_BEFORE_START,
            id="end-before-start",
        ),
        pytest.param(
            {
                "frequency": FixedDates((date(2026, 7, 1),)),
                "start": date(2026, 6, 1),
                "end": date(2026, 6, 30),
            },
            ErrorCode.DATE_OUT_OF_RANGE,
            id="date-after-the-end",
        ),
        pytest.param(
            {"frequency": FixedDates((date(2026, 5, 1),)), "start": date(2026, 6, 1)},
            ErrorCode.DATE_OUT_OF_RANGE,
            id="date-before-the-start",
        ),
    ],
)
def test_an_invalid_form_is_never_stored(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    raises_code: RaisesCode,
    fields: dict[str, Any],
    code: ErrorCode,
) -> None:
    repository = make_flaky(make_repository())
    service = make_service(repository=repository)
    form: dict[str, Any] = {"name": "X", "area_id": "gym", "frequency": Daily()} | fields
    with raises_code(code):
        service.add_habit(**form)
    assert service.habits() == ()
    assert repository.writes == []


# ---------- Editing habits ----------


def test_editing_changes_the_configuration_and_keeps_the_history(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    history: dict[date, float | None] = {date(2026, 6, 9): None, date(2026, 6, 10): 8.0}
    service = make_service(make_habit(id=10, measurement=PAGES, completions=history))
    service.edit_habit(
        10,
        name="Read more",
        area_id="english",
        frequency=Quota(times=4),
        description="My reason",
        end=date(2026, 12, 31),
        measurement=PAGES,
    )
    edited = service.get_habit(10)
    assert (edited.name, edited.area_id, edited.end) == (
        "Read more",
        "english",
        date(2026, 12, 31),
    )
    assert edited.frequency == Quota(times=4)
    assert edited.description == "My reason"
    assert edited.completions == history
    assert edited.id == 10


def test_editing_trims_the_description_and_the_notes(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    service.edit_habit(
        1,
        name="Gym",
        area_id="gym",
        frequency=Daily(),
        description="  my reason ",
        notes=" a note\n",
    )
    habit = service.get_habit(1)
    assert (habit.description, habit.notes) == ("my reason", "a note")


def test_editing_returns_the_habit_the_service_holds(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    updated = service.edit_habit(1, name="Gym 2", area_id="gym", frequency=Daily())
    assert service.get_habit(1) is updated


def test_editing_keeps_the_habit_in_its_place_among_the_others(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(
        make_habit(id=1, name="One"), make_habit(id=2, name="Two"), make_habit(id=3, name="Three")
    )
    service.edit_habit(2, name="Second", area_id="gym", frequency=Daily())
    assert [habit.name for habit in service.habits()] == ["One", "Second", "Three"]


def test_changing_the_frequency_does_not_lose_any_completion(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(done=june(8, 9, 10)))
    service.edit_habit(1, name="Gym", area_id="gym", frequency=Quota(times=2))
    service.edit_habit(
        1, name="Gym", area_id="gym", frequency=Weekdays(frozenset({Weekday.FRIDAY}))
    )
    assert set(service.get_habit(1).completions) == set(june(8, 9, 10))


def test_an_edited_habit_keeps_its_start_when_none_is_given(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(start=date(2026, 6, 1)))
    service.edit_habit(1, name="Gym", area_id="gym", frequency=Daily())
    assert service.get_habit(1).start == date(2026, 6, 1)


def test_an_edited_habit_can_move_its_start(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(start=date(2026, 6, 1)))
    service.edit_habit(1, name="Gym", area_id="gym", frequency=Daily(), start=date(2026, 6, 5))
    assert service.get_habit(1).start == date(2026, 6, 5)


def test_a_habit_may_keep_its_own_name_when_edited(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(name="Read"))
    service.edit_habit(1, name="Read", area_id="gym", frequency=Daily(), description="new reason")
    assert service.get_habit(1).description == "new reason"


def test_a_habit_may_change_the_case_of_its_own_name(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(name="Read"))
    service.edit_habit(1, name=" READ ", area_id="gym", frequency=Daily())
    assert service.get_habit(1).name == "READ"


def test_a_habit_cannot_take_the_name_of_another_one(
    make_service: ServiceFactory, make_habit: HabitFactory, raises_code: RaisesCode
) -> None:
    service = make_service(make_habit(id=10, name="Test"), make_habit(id=11, name="Another habit"))
    with raises_code(ErrorCode.NAME_DUPLICATE):
        service.edit_habit(10, name="another HABIT", area_id="gym", frequency=Daily())
    assert service.get_habit(10).name == "Test"


def test_chosen_dates_are_recovered_after_adding_and_after_editing(
    make_service: ServiceFactory,
) -> None:
    service = make_service()
    added = FixedDates((date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 27)))
    habit = service.add_habit(
        name="Go running", area_id="gym", frequency=added, start=date(2026, 11, 1)
    )
    assert isinstance(service.get_habit(habit.id).frequency, FixedDates)
    assert service.get_habit(habit.id).frequency == added
    edited = FixedDates((date(2026, 11, 5), date(2026, 11, 19)))
    service.edit_habit(
        habit.id, name="Go running", area_id="gym", frequency=edited, start=date(2026, 11, 1)
    )
    assert service.get_habit(habit.id).frequency == edited


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        pytest.param({"name": " "}, ErrorCode.NAME_REQUIRED, id="blank-name"),
        pytest.param({"area_id": "nowhere"}, ErrorCode.AREA_UNKNOWN, id="unknown-area"),
        pytest.param({"end": date(2026, 5, 1)}, ErrorCode.END_BEFORE_START, id="end-before-start"),
        pytest.param(
            {"frequency": FixedDates((date(2026, 5, 1),))},
            ErrorCode.DATE_OUT_OF_RANGE,
            id="date-before-the-start",
        ),
    ],
)
def test_an_invalid_edit_leaves_the_habit_untouched(
    make_service: ServiceFactory,
    make_habit: HabitFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    raises_code: RaisesCode,
    fields: dict[str, Any],
    code: ErrorCode,
) -> None:
    repository = make_flaky(make_repository(make_habit(done=june(9))))
    service = make_service(repository=repository)
    before = copy.deepcopy(service.get_habit(1))
    form: dict[str, Any] = {"name": "Gym", "area_id": "gym", "frequency": Daily()} | fields
    with raises_code(code):
        service.edit_habit(1, **form)
    assert service.get_habit(1) == before
    assert repository.writes == []


def test_editing_an_unknown_habit_raises_habit_not_found(
    make_service: ServiceFactory, raises_code: RaisesCode
) -> None:
    with raises_code(ErrorCode.HABIT_NOT_FOUND):
        make_service().edit_habit(99, name="X", area_id="gym", frequency=Daily())


def test_an_edited_habit_can_still_be_marked(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit())
    service.edit_habit(1, name="Gym 2", area_id="gym", frequency=Daily())
    service.mark(1, True, day=TODAY)
    assert service.get_habit(1).is_done(TODAY)


# ---------- Deleting habits ----------


def test_deleting_a_habit_removes_it_and_keeps_the_others(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(id=1), make_habit(id=2, name="Run"))
    service.delete_habit(1)
    assert [habit.id for habit in service.habits()] == [2]
    assert service.find_habit(1) is None


def test_deleting_an_unknown_habit_raises_habit_not_found(
    make_service: ServiceFactory,
    make_habit: HabitFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    raises_code: RaisesCode,
) -> None:
    repository = make_flaky(make_repository(make_habit()))
    service = make_service(repository=repository)
    with raises_code(ErrorCode.HABIT_NOT_FOUND):
        service.delete_habit(99)
    assert repository.writes == []
    assert len(service.habits()) == 1


def test_a_deleted_habits_name_can_be_used_again(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    service = make_service(make_habit(name="Read"))
    service.delete_habit(1)
    habit = service.add_habit(name="read", area_id="gym", frequency=Daily())
    assert habit.name == "read"


# ---------- The priority of tomorrow ----------


def test_the_priority_is_saved_for_tomorrow(make_service: ServiceFactory) -> None:
    service = make_service()
    service.set_priority_for_tomorrow("Submit the report")
    assert service.priority_for_tomorrow() == "Submit the report"
    assert service.priority_for_today() is None


def test_the_priority_written_tonight_is_todays_priority_when_the_day_comes(
    make_service: ServiceFactory, clock: FixedClock
) -> None:
    service = make_service()
    service.set_priority_for_tomorrow("Submit the report")
    clock.current = datetime(2026, 6, 12, 7, 30)
    assert service.priority_for_today() == "Submit the report"


def test_the_priority_text_is_trimmed(make_service: ServiceFactory) -> None:
    service = make_service()
    service.set_priority_for_tomorrow("  Submit the report \n")
    assert service.priority_for_tomorrow() == "Submit the report"


def test_a_new_priority_replaces_the_previous_one(make_service: ServiceFactory) -> None:
    service = make_service()
    service.set_priority_for_tomorrow("First idea")
    service.set_priority_for_tomorrow("Second idea")
    assert service.priority_for_tomorrow() == "Second idea"


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_an_empty_priority_clears_the_note(make_service: ServiceFactory, text: str) -> None:
    service = make_service()
    service.set_priority_for_tomorrow("Submit the report")
    service.set_priority_for_tomorrow(text)
    assert service.priority_for_tomorrow() is None


# ---------- Important dates ----------


def test_adding_an_important_date_lists_it_under_its_month(make_service: ServiceFactory) -> None:
    service = make_service()
    item = service.add_important_date(date(2026, 6, 25), "Exam")
    assert item == ImportantDate(date(2026, 6, 25), "Exam")
    assert service.important_dates(2026, 6) == [(25, "Exam")]
    assert service.important_dates(2026, 7) == []


def test_the_title_of_an_important_date_is_trimmed(make_service: ServiceFactory) -> None:
    item = make_service().add_important_date(date(2026, 6, 25), "  Exam \n")
    assert item.title == "Exam"


@pytest.mark.parametrize("title", ["", "   ", "\t"])
def test_an_important_date_needs_a_title(
    make_service: ServiceFactory, raises_code: RaisesCode, title: str
) -> None:
    service = make_service()
    with raises_code(ErrorCode.TITLE_REQUIRED):
        service.add_important_date(date(2026, 6, 25), title)
    assert service.important_dates(2026, 6) == []


def test_adding_the_same_important_date_twice_keeps_one(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
) -> None:
    repository = make_flaky(make_repository())
    service = make_service(repository=repository)
    service.add_important_date(date(2026, 6, 25), "Exam")
    service.add_important_date(date(2026, 6, 25), " Exam ")
    assert service.important_dates(2026, 6) == [(25, "Exam")]
    assert repository.writes == ["add_important_date"]


def test_important_dates_of_a_month_come_sorted_by_day(make_service: ServiceFactory) -> None:
    service = make_service()
    service.add_important_date(date(2026, 6, 25), "Delivery")
    service.add_important_date(date(2026, 6, 3), "Exam")
    assert service.important_dates(2026, 6) == [(3, "Exam"), (25, "Delivery")]


def test_removing_an_important_date_takes_it_off_the_list(make_service: ServiceFactory) -> None:
    service = make_service()
    exam = service.add_important_date(date(2026, 6, 3), "Exam")
    service.add_important_date(date(2026, 6, 25), "Delivery")
    service.remove_important_date(exam)
    assert service.important_dates(2026, 6) == [(25, "Delivery")]


def test_removing_an_important_date_that_is_not_there_changes_nothing(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
) -> None:
    repository = make_flaky(make_repository())
    service = make_service(repository=repository)
    service.remove_important_date(ImportantDate(date(2026, 6, 3), "Exam"))
    assert repository.writes == []


# ---------- Pending reminders ----------


@pytest.fixture
def evening_habit(make_habit: HabitFactory) -> Habit:
    return make_habit(id=1, reminder=Reminder(at=time(20, 0)))


def test_a_reminder_is_reported_when_its_time_comes(
    make_service: ServiceFactory, evening_habit: Habit
) -> None:
    service = make_service(evening_habit)
    assert service.pending_reminders(at(19, 59)) == []
    assert [habit.id for habit in service.pending_reminders(at(20, 0))] == [1]


def test_a_reminder_is_reported_only_once_per_day(
    make_service: ServiceFactory, evening_habit: Habit
) -> None:
    service = make_service(evening_habit)
    assert len(service.pending_reminders(at(20, 0))) == 1
    assert service.pending_reminders(at(20, 1)) == []
    assert service.pending_reminders(at(20, 30)) == []


def test_a_reminder_is_reported_again_the_next_day(
    make_service: ServiceFactory, evening_habit: Habit
) -> None:
    service = make_service(evening_habit)
    assert len(service.pending_reminders(at(20, 0))) == 1
    assert len(service.pending_reminders(at(20, 0, day=12))) == 1


def test_a_reminder_skipped_because_the_habit_was_done_is_not_used_up(
    make_service: ServiceFactory, evening_habit: Habit
) -> None:
    service = make_service(evening_habit)
    service.mark(1, True, day=TODAY)
    assert service.pending_reminders(at(20, 0)) == []
    service.mark(1, False, day=TODAY)
    assert len(service.pending_reminders(at(20, 5))) == 1


def test_each_habit_is_reported_separately_and_in_order(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    first = make_habit(id=1, name="Read", reminder=Reminder(at=time(20, 0)))
    silent = make_habit(id=2, name="Run")
    second = make_habit(id=3, name="Stretch", reminder=Reminder(at=time(20, 30)))
    service = make_service(first, silent, second)
    assert [habit.id for habit in service.pending_reminders(at(20, 0))] == [1]
    assert [habit.id for habit in service.pending_reminders(at(20, 30))] == [3]
    assert service.pending_reminders(at(20, 31)) == []


def test_two_reminders_due_together_are_both_reported(
    make_service: ServiceFactory, make_habit: HabitFactory
) -> None:
    first = make_habit(id=1, name="Read", reminder=Reminder(at=time(20, 0)))
    second = make_habit(id=2, name="Run", reminder=Reminder(at=time(20, 0)))
    service = make_service(first, second)
    assert [habit.id for habit in service.pending_reminders(at(20, 0))] == [1, 2]


def test_pending_reminders_default_to_the_time_of_the_clock(
    make_service: ServiceFactory, evening_habit: Habit, clock: FixedClock
) -> None:
    service = make_service(evening_habit)
    assert service.pending_reminders() == []  # the clock says 09:00
    clock.current = at(20, 0)
    assert [habit.id for habit in service.pending_reminders()] == [1]
    assert service.pending_reminders() == []


def test_the_clock_day_decides_which_day_a_reminder_was_used_up(
    make_service: ServiceFactory, evening_habit: Habit, clock: FixedClock
) -> None:
    service = make_service(evening_habit)
    clock.current = at(20, 0)
    assert len(service.pending_reminders()) == 1
    clock.current = at(20, 0, day=12)
    assert len(service.pending_reminders()) == 1


def test_an_explicit_time_takes_precedence_over_the_clock(
    make_service: ServiceFactory, evening_habit: Habit, clock: FixedClock
) -> None:
    service = make_service(evening_habit)
    assert clock.current == datetime(2026, 6, 11, 9, 0)
    assert len(service.pending_reminders(at(20, 0))) == 1


def test_a_new_habit_that_reuses_a_deleted_habits_id_still_gets_its_reminder(
    make_service: ServiceFactory,
) -> None:
    service = make_service()
    first = service.add_habit(
        name="Read", area_id="gym", frequency=Daily(), reminder=Reminder(at=time(20, 0))
    )
    assert [habit.id for habit in service.pending_reminders(at(20, 0))] == [first.id]
    service.delete_habit(first.id)
    second = service.add_habit(
        name="Run", area_id="gym", frequency=Daily(), reminder=Reminder(at=time(20, 0))
    )
    assert [habit.id for habit in service.pending_reminders(at(20, 5))] == [second.id]
