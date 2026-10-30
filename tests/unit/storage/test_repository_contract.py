"""Behaviour every ``Repository`` implementation must share."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import Area, Habit, ImportantDate, PriorityNote, Snapshot
from habit_tracker.ports import Repository, StorageError
from habit_tracker.storage.memory import MemoryRepository
from habit_tracker.storage.sqlite import SqliteRepository

DAY = date(2026, 10, 29)
HEALTH = Area("health", "Health", "#65a882", "#e3efe8")
CAREER = Area("career", "Career", "#6488d8", "#e3eaf8")


@pytest.fixture(params=["memory", "sqlite"])
def repository(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Repository]:
    if request.param == "memory":
        yield MemoryRepository()
        return
    with SqliteRepository(tmp_path / "habits.sqlite3") as sqlite_repository:
        yield sqlite_repository


def make_habit(habit_id: int = 1, name: str = "Read", area_id: str = "health") -> Habit:
    return Habit(
        id=habit_id, name=name, area_id=area_id, frequency=Daily(), start=date(2026, 1, 1)
    )


def seed(repository: Repository, *habits: Habit) -> None:
    repository.save_area(HEALTH)
    repository.save_area(CAREER)
    for habit in habits:
        repository.save_habit(habit)


def test_an_empty_repository_loads_an_empty_snapshot(repository: Repository) -> None:
    assert repository.load() == Snapshot()


def test_everything_written_comes_back_as_it_was(repository: Repository) -> None:
    demo = build_demo_snapshot(DAY)
    for area in demo.areas:
        repository.save_area(area)
    for habit in demo.habits:
        repository.save_habit(habit)
        for day, value in habit.completions.items():
            repository.set_completion(habit.id, day, done=True, value=value)
    for item in demo.important_dates:
        repository.add_important_date(item)
    repository.save_priority(demo.priority)

    assert repository.load() == demo


def test_habits_are_loaded_in_id_order(repository: Repository) -> None:
    seed(repository, make_habit(3, "Third"), make_habit(1, "First"), make_habit(2, "Second"))

    assert [habit.id for habit in repository.load().habits] == [1, 2, 3]


def test_updating_an_area_keeps_its_place(repository: Repository) -> None:
    seed(repository)
    repository.save_area(Area("health", "Wellbeing", "#65a882"))

    areas = repository.load().areas

    assert [area.id for area in areas] == ["health", "career"]
    assert areas[0].name == "Wellbeing"


def test_saving_a_habit_again_updates_it_and_keeps_its_completions(
    repository: Repository,
) -> None:
    seed(repository, make_habit())
    repository.set_completion(1, DAY, done=True)

    repository.save_habit(make_habit(name="Read more"))

    (habit,) = repository.load().habits
    assert habit.name == "Read more"
    assert habit.completions == {DAY: None}


def test_a_completion_can_be_replaced_and_cleared(repository: Repository) -> None:
    seed(repository, make_habit())

    repository.set_completion(1, DAY, done=True, value=10)
    repository.set_completion(1, DAY, done=True, value=25)
    assert repository.load().habits[0].completions == {DAY: 25}

    repository.set_completion(1, DAY, done=False)
    assert repository.load().habits[0].completions == {}


def test_clearing_a_day_that_was_not_done_is_harmless(repository: Repository) -> None:
    seed(repository, make_habit())

    repository.set_completion(1, DAY, done=False)

    assert repository.load().habits[0].completions == {}


def test_deleting_a_habit_deletes_its_history_too(repository: Repository) -> None:
    seed(repository, make_habit())
    repository.set_completion(1, DAY, done=True)

    repository.delete_habit(1)
    repository.save_habit(make_habit())

    assert repository.load().habits[0].completions == {}


def test_deleting_a_habit_that_does_not_exist_is_harmless(repository: Repository) -> None:
    seed(repository, make_habit())

    repository.delete_habit(99)

    assert len(repository.load().habits) == 1


def test_completing_a_habit_that_does_not_exist_is_a_storage_error(
    repository: Repository,
) -> None:
    seed(repository)

    with pytest.raises(StorageError):
        repository.set_completion(99, DAY, done=True)


def test_a_habit_in_an_unknown_area_is_a_storage_error(repository: Repository) -> None:
    seed(repository)

    with pytest.raises(StorageError):
        repository.save_habit(make_habit(area_id="missing"))

    assert repository.load().habits == []


def test_the_priority_note_is_replaced_and_cleared(repository: Repository) -> None:
    repository.save_priority(PriorityNote(DAY, "First"))
    repository.save_priority(PriorityNote(DAY, "Second"))
    assert repository.load().priority == PriorityNote(DAY, "Second")

    repository.save_priority(None)
    assert repository.load().priority is None


def test_important_dates_can_be_added_twice_and_removed(repository: Repository) -> None:
    item = ImportantDate(DAY, "Exam")

    repository.add_important_date(item)
    repository.add_important_date(item)
    assert repository.load().important_dates == [item]

    repository.remove_important_date(item)
    repository.remove_important_date(item)
    assert repository.load().important_dates == []
