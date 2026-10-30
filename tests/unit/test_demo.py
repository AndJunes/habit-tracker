from datetime import date

import pytest

from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.streaks import current_streak
from habit_tracker.domain.validation import validate_habit_fields

TODAY = date(2026, 10, 29)


def test_demo_is_deterministic_for_a_given_day() -> None:
    assert build_demo_snapshot(TODAY) == build_demo_snapshot(TODAY)


def test_demo_changes_with_the_seed() -> None:
    assert build_demo_snapshot(TODAY, seed=1) != build_demo_snapshot(TODAY, seed=2)


def test_demo_has_one_habit_of_each_kind_of_schedule() -> None:
    kinds = {type(habit.frequency) for habit in build_demo_snapshot(TODAY).habits}
    assert kinds == {Quota, Daily, FixedDates, Interval, Weekdays}


def test_demo_habits_pass_the_same_rules_as_user_input() -> None:
    snapshot = build_demo_snapshot(TODAY)
    for habit in snapshot.habits:
        others = [other for other in snapshot.habits if other.id != habit.id]
        cleaned = validate_habit_fields(
            name=habit.name,
            area_id=habit.area_id,
            areas=snapshot.areas,
            start=habit.start,
            end=habit.end,
            frequency=habit.frequency,
            habits=others,
        )
        assert cleaned == habit.name


def test_demo_only_has_history_up_to_today() -> None:
    for habit in build_demo_snapshot(TODAY).habits:
        assert all(habit.start <= day <= TODAY for day in habit.completions)


@pytest.mark.parametrize("today", [date(2026, 1, 31), date(2026, 10, 29), date(2028, 2, 29)])
def test_demo_keeps_streaks_alive_whenever_it_is_opened(today: date) -> None:
    snapshot = build_demo_snapshot(today)
    by_name = {habit.name: habit for habit in snapshot.habits}
    assert current_streak(by_name["Bloque de estudio"], today) >= 4
    assert current_streak(by_name["Entrenar 3 veces por semana"], today) >= 2


def test_demo_priority_is_for_tomorrow() -> None:
    priority = build_demo_snapshot(TODAY).priority
    assert priority is not None
    assert (priority.for_day - TODAY).days == 1
