"""Every action reaches the repository, and a failed write never changes the service."""

import copy
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, time
from typing import Any

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from habit_tracker.domain.models import Habit, ImportantDate, Measurement, PriorityNote, Reminder
from habit_tracker.ports import StorageError
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository

HabitFactory = Callable[..., Habit]
RepositoryFactory = Callable[..., MemoryRepository]
ServiceFactory = Callable[..., HabitService]
Reload = Callable[[], HabitService]

TODAY = date(2026, 6, 11)  # a Thursday
PAGES = Measurement(MeasurementKind.QUANTITY, goal=10, unit="pages")
MEDITATION = Measurement(MeasurementKind.DURATION, goal=15, unit="minutes", minimum=5, ideal=30)


@pytest.fixture
def repository(make_repository: RepositoryFactory) -> MemoryRepository:
    return make_repository()


@pytest.fixture
def service(make_service: ServiceFactory, repository: MemoryRepository) -> HabitService:
    return make_service(repository=repository)


@pytest.fixture
def reload(repository: MemoryRepository, clock: FixedClock) -> Reload:
    """Open a brand-new service on the same repository, like closing and reopening the app."""

    def open_again() -> HabitService:
        return HabitService(repository, clock)

    return open_again


# ---------- Every action reaches the repository ----------


def test_an_added_habit_survives_reopening(service: HabitService, reload: Reload) -> None:
    added = service.add_habit(name="Read", area_id="english", frequency=Daily(), notes="a note")
    assert reload().habits() == (added,)


def test_a_marked_day_survives_reopening(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_habit: HabitFactory,
    clock: FixedClock,
) -> None:
    repository = make_repository(make_habit())
    make_service(repository=repository).mark(1, True, day=TODAY)
    assert HabitService(repository, clock).get_habit(1).completions == {TODAY: None}


def test_an_unmarked_day_stays_unmarked_after_reopening(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_habit: HabitFactory,
    clock: FixedClock,
) -> None:
    repository = make_repository(make_habit(done=[TODAY]))
    make_service(repository=repository).mark(1, False, day=TODAY)
    assert HabitService(repository, clock).get_habit(1).completions == {}


def test_marking_and_unmarking_each_write_one_completion(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    make_habit: HabitFactory,
) -> None:
    repository = make_flaky(make_repository(make_habit()))
    service = make_service(repository=repository)
    service.mark(1, True, day=TODAY)
    service.mark(1, False, day=TODAY)
    assert repository.writes == ["set_completion", "set_completion"]


def test_a_recorded_value_survives_reopening(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_habit: HabitFactory,
    clock: FixedClock,
) -> None:
    repository = make_repository(make_habit(measurement=PAGES))
    make_service(repository=repository).mark(1, True, day=TODAY, value=12)
    assert HabitService(repository, clock).get_habit(1).completions == {TODAY: 12}


def test_marking_again_without_a_value_keeps_the_value_in_the_store_too(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_habit: HabitFactory,
    clock: FixedClock,
) -> None:
    repository = make_repository(make_habit(measurement=PAGES, completions={TODAY: 12.0}))
    make_service(repository=repository).mark(1, True, day=TODAY)
    assert HabitService(repository, clock).get_habit(1).completions == {TODAY: 12.0}


def test_a_value_given_to_a_habit_without_measurement_is_not_stored(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_habit: HabitFactory,
    clock: FixedClock,
) -> None:
    repository = make_repository(make_habit(measurement=None))
    make_service(repository=repository).mark(1, True, day=TODAY, value=5)
    assert HabitService(repository, clock).get_habit(1).completions == {TODAY: None}


def test_a_measurement_and_its_recorded_values_survive_reopening(
    service: HabitService, reload: Reload
) -> None:
    habit = service.add_habit(
        name="Meditate",
        area_id="gym",
        frequency=Daily(),
        start=date(2026, 6, 1),
        measurement=MEDITATION,
    )
    service.mark(habit.id, True, day=TODAY, value=20)
    reopened = reload().get_habit(habit.id)
    assert reopened.measurement == MEDITATION
    assert reopened.completions == {TODAY: 20}


def test_an_edited_habit_survives_reopening_with_its_history(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_habit: HabitFactory,
    clock: FixedClock,
) -> None:
    repository = make_repository(make_habit(measurement=PAGES, completions={TODAY: 8.0}))
    service = make_service(repository=repository)
    service.edit_habit(
        1, name="Read more", area_id="english", frequency=Quota(times=4), measurement=PAGES
    )
    reopened = HabitService(repository, clock).get_habit(1)
    assert (reopened.name, reopened.area_id, reopened.frequency) == (
        "Read more",
        "english",
        Quota(times=4),
    )
    assert reopened.completions == {TODAY: 8.0}


def test_adding_a_habit_writes_only_its_configuration(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
) -> None:
    repository = make_flaky(make_repository())
    make_service(repository=repository).add_habit(name="Read", area_id="gym", frequency=Daily())
    assert repository.writes == ["save_habit"]


def test_editing_a_habit_writes_only_its_configuration(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    make_habit: HabitFactory,
) -> None:
    repository = make_flaky(make_repository(make_habit(done=[TODAY])))
    make_service(repository=repository).edit_habit(
        1, name="Gym 2", area_id="gym", frequency=Daily()
    )
    assert repository.writes == ["save_habit"]


def test_a_deleted_habit_stays_deleted_after_reopening(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_habit: HabitFactory,
    clock: FixedClock,
) -> None:
    repository = make_repository(make_habit(id=1), make_habit(id=2, name="Run"))
    make_service(repository=repository).delete_habit(1)
    assert [habit.id for habit in HabitService(repository, clock).habits()] == [2]


def test_deleting_a_habit_writes_one_deletion(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    make_habit: HabitFactory,
) -> None:
    repository = make_flaky(make_repository(make_habit()))
    make_service(repository=repository).delete_habit(1)
    assert repository.writes == ["delete_habit"]


def test_the_priority_for_tomorrow_survives_reopening(
    service: HabitService, repository: MemoryRepository, reload: Reload
) -> None:
    service.set_priority_for_tomorrow("Submit the report")
    assert repository.load().priority == PriorityNote(date(2026, 6, 12), "Submit the report")
    assert reload().priority_for_tomorrow() == "Submit the report"


def test_clearing_the_priority_clears_it_in_the_repository(
    make_service: ServiceFactory, make_repository: RepositoryFactory
) -> None:
    repository = make_repository(priority=PriorityNote(date(2026, 6, 12), "Old"))
    make_service(repository=repository).set_priority_for_tomorrow("  ")
    assert repository.load().priority is None


def test_important_dates_survive_reopening(service: HabitService, reload: Reload) -> None:
    exam = service.add_important_date(date(2026, 6, 3), "Exam")
    service.add_important_date(date(2026, 6, 25), "Delivery")
    service.remove_important_date(exam)
    assert reload().important_dates(2026, 6) == [(25, "Delivery")]


def test_important_dates_write_one_operation_each(
    make_service: ServiceFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
) -> None:
    repository = make_flaky(make_repository())
    service = make_service(repository=repository)
    exam = service.add_important_date(date(2026, 6, 3), "Exam")
    service.remove_important_date(exam)
    assert repository.writes == ["add_important_date", "remove_important_date"]


FREQUENCIES = [
    pytest.param(Daily(), id="daily"),
    pytest.param(
        Weekdays(frozenset({Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY})),
        id="monday-wednesday-friday",
    ),
    pytest.param(Quota(times=3), id="three-a-week"),
    pytest.param(
        Quota(times=3, preferred=frozenset({Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY})),
        id="three-a-week-preferring-days",
    ),
    pytest.param(Quota(times=3, period=Period.MONTH), id="three-a-month"),
    pytest.param(FixedDates((date(2026, 11, 5), date(2026, 11, 20))), id="two-chosen-dates"),
    pytest.param(
        FixedDates((date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 27))),
        id="three-chosen-dates",
    ),
    pytest.param(Interval(2, IntervalUnit.WEEKS), id="every-two-weeks"),
    pytest.param(Interval(1, IntervalUnit.MONTHS), id="every-month"),
]


@pytest.mark.parametrize("frequency", FREQUENCIES)
def test_every_kind_of_frequency_survives_reopening_with_the_rest_of_the_habit(
    service: HabitService, reload: Reload, frequency: Frequency
) -> None:
    added = service.add_habit(
        name="Habit",
        area_id="gym",
        frequency=frequency,
        description="my reason",
        notes="a note",
        start=date(2026, 11, 1),
        end=date(2026, 12, 31),
        reminder=Reminder(at=time(7, 30), weekdays=frozenset({Weekday.MONDAY})),
    )
    reopened = reload().get_habit(added.id)
    assert reopened.frequency == frequency
    assert reopened == added


# ---------- A failed write never changes the service ----------


@dataclass
class Scenario:
    repository: MemoryRepository
    flaky: Any
    service: HabitService


@pytest.fixture
def scenario(
    make_habit: HabitFactory,
    make_repository: RepositoryFactory,
    make_flaky: Callable[[Any], Any],
    make_service: ServiceFactory,
) -> Scenario:
    """Two habits, one important date and a priority note, behind a repository that can fail."""
    reading = make_habit(
        id=1, name="Read", measurement=PAGES, completions={date(2026, 6, 10): 5.0}
    )
    running = make_habit(id=2, name="Run")
    repository = make_repository(
        reading,
        running,
        important_dates=[ImportantDate(date(2026, 6, 20), "Exam")],
        priority=PriorityNote(date(2026, 6, 12), "Call home"),
    )
    flaky = make_flaky(repository)
    return Scenario(repository, flaky, make_service(repository=flaky))


def observe(service: HabitService) -> tuple[list[Habit], list[tuple[int, str]], str | None]:
    """Everything a screen could show, copied so later changes cannot alter it."""
    return (
        copy.deepcopy(list(service.habits())),
        service.important_dates(2026, 6),
        service.priority_for_tomorrow(),
    )


ACTIONS: dict[str, Callable[[HabitService], object]] = {
    "mark-done": lambda service: service.mark(2, True, day=TODAY),
    "mark-done-with-value": lambda service: service.mark(1, True, day=TODAY, value=7),
    "unmark": lambda service: service.mark(1, False, day=date(2026, 6, 10)),
    "add-habit": lambda service: service.add_habit(
        name="Meditate", area_id="gym", frequency=Daily()
    ),
    "edit-habit": lambda service: service.edit_habit(
        1, name="Read more", area_id="gym", frequency=Daily(), measurement=PAGES
    ),
    "delete-habit": lambda service: service.delete_habit(2),
    "set-priority": lambda service: service.set_priority_for_tomorrow("Something else"),
    "clear-priority": lambda service: service.set_priority_for_tomorrow(""),
    "add-important-date": lambda service: service.add_important_date(date(2026, 6, 25), "Dentist"),
    "remove-important-date": lambda service: service.remove_important_date(
        ImportantDate(date(2026, 6, 20), "Exam")
    ),
}


@pytest.mark.parametrize("action", ACTIONS.values(), ids=list(ACTIONS))
def test_a_failed_write_leaves_the_service_and_the_store_as_they_were(
    scenario: Scenario, action: Callable[[HabitService], object]
) -> None:
    shown_before = observe(scenario.service)
    stored_before = scenario.repository.load()
    scenario.flaky.failing = True
    with pytest.raises(StorageError):
        action(scenario.service)
    assert observe(scenario.service) == shown_before
    assert scenario.repository.load() == stored_before
    assert len(scenario.flaky.writes) == 1  # the one attempt, stopped by the failure


@pytest.mark.parametrize("action", ACTIONS.values(), ids=list(ACTIONS))
def test_the_same_action_works_once_the_store_recovers(
    scenario: Scenario, action: Callable[[HabitService], object]
) -> None:
    shown_before = observe(scenario.service)
    scenario.flaky.failing = True
    with pytest.raises(StorageError):
        action(scenario.service)
    scenario.flaky.failing = False
    action(scenario.service)
    assert observe(scenario.service) != shown_before


@pytest.mark.parametrize("action", ACTIONS.values(), ids=list(ACTIONS))
def test_the_service_and_the_store_agree_after_a_failure_and_a_retry(
    scenario: Scenario, clock: FixedClock, action: Callable[[HabitService], object]
) -> None:
    scenario.flaky.failing = True
    with pytest.raises(StorageError):
        action(scenario.service)
    scenario.flaky.failing = False
    action(scenario.service)
    reopened = HabitService(scenario.repository, clock)
    assert observe(reopened) == observe(scenario.service)
