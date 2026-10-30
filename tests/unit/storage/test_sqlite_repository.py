"""The SQLite repository: round trips, atomic operations, permissions and bad stored rows."""

import os
import sqlite3
import stat
import sys
from collections.abc import Callable
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest

from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.errors import ErrorCode, ValidationError
from habit_tracker.domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from habit_tracker.domain.models import (
    Area,
    Habit,
    ImportantDate,
    Measurement,
    PriorityNote,
    Reminder,
    Snapshot,
)
from habit_tracker.ports import Repository, StorageError
from habit_tracker.storage import sqlite as sqlite_module
from habit_tracker.storage.sqlite import SqliteRepository

RawConnect = Callable[[Path], sqlite3.Connection]

DAY = date(2026, 10, 1)


def make_habit(habit_id: int = 1, **overrides: object) -> Habit:
    fields: dict[str, Any] = {
        "id": habit_id,
        "name": f"Habit {habit_id}",
        "area_id": "health",
        "frequency": Daily(),
        "start": date(2026, 9, 1),
    }
    fields.update(overrides)
    return Habit(**fields)


@pytest.fixture
def health(repository: SqliteRepository) -> SqliteRepository:
    """A repository that already has the ``health`` area."""
    repository.save_area(Area("health", "Health", "#65a882", "#e3efe8"))
    return repository


def integrity_check(path: Path, raw_connect: RawConnect) -> list[str]:
    return [row[0] for row in raw_connect(path).execute("PRAGMA integrity_check")]


def count(path: Path, raw_connect: RawConnect, table: str) -> int:
    row = raw_connect(path).execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0])


# ---------- Round trips ----------


def test_a_new_repository_is_empty(repository: SqliteRepository) -> None:
    assert repository.load() == Snapshot()
    assert repository.is_empty()


def test_it_satisfies_the_repository_port(repository: SqliteRepository) -> None:
    port: Repository = repository
    assert port.load() == Snapshot()


def test_a_snapshot_survives_a_round_trip(
    repository: SqliteRepository, snapshot: Snapshot
) -> None:
    repository.import_snapshot(snapshot)
    assert repository.load() == snapshot


def test_the_same_data_written_one_entity_at_a_time_loads_identically(
    repository: SqliteRepository, snapshot: Snapshot
) -> None:
    for area in snapshot.areas:
        repository.save_area(area)
    for habit in snapshot.habits:
        repository.save_habit(habit)
        for day, value in habit.completions.items():
            repository.set_completion(habit.id, day, done=True, value=value)
    for item in snapshot.important_dates:
        repository.add_important_date(item)
    repository.save_priority(snapshot.priority)
    assert repository.load() == snapshot


def test_data_is_still_there_after_reopening_the_file(
    repository: SqliteRepository, snapshot: Snapshot, db_path: Path
) -> None:
    repository.import_snapshot(snapshot)
    repository.close()
    with SqliteRepository(db_path) as reopened:
        assert reopened.load() == snapshot


@pytest.mark.parametrize(
    "frequency",
    [
        Daily(),
        Weekdays(frozenset({Weekday.TUESDAY})),
        Weekdays(frozenset(Weekday)),
        Quota(1, Period.WEEK),
        Quota(7, Period.WEEK, frozenset({Weekday.MONDAY, Weekday.FRIDAY})),
        Quota(31, Period.MONTH),
        FixedDates((date(2026, 12, 25),)),
        FixedDates((date(2026, 11, 5), date(2026, 10, 2), date(2026, 12, 1))),
        Interval(1, IntervalUnit.DAYS),
        Interval(3, IntervalUnit.WEEKS),
        Interval(2, IntervalUnit.MONTHS),
    ],
    ids=repr,
)
def test_every_kind_of_frequency_survives_a_round_trip(
    health: SqliteRepository, frequency: Frequency
) -> None:
    habit = make_habit(frequency=frequency)
    health.save_habit(habit)
    assert health.load().habits == [habit]


@pytest.mark.parametrize(
    "measurement",
    [
        None,
        Measurement(MeasurementKind.QUANTITY, 10, "pages"),
        Measurement(MeasurementKind.QUANTITY, 2.5, "liters", 1, 3),
        Measurement(MeasurementKind.DURATION, 30, "min", minimum=10),
        Measurement(MeasurementKind.DURATION, 30, "min", ideal=45),
    ],
    ids=repr,
)
def test_a_measurement_survives_a_round_trip(
    health: SqliteRepository, measurement: Measurement | None
) -> None:
    habit = make_habit(measurement=measurement)
    health.save_habit(habit)
    assert health.load().habits == [habit]


@pytest.mark.parametrize(
    "reminder",
    [
        None,
        Reminder(time(8, 5)),
        Reminder(time(0, 0), frozenset({Weekday.SUNDAY})),
        Reminder(time(23, 59), frozenset(Weekday)),
    ],
    ids=repr,
)
def test_a_reminder_survives_a_round_trip(
    health: SqliteRepository, reminder: Reminder | None
) -> None:
    habit = make_habit(reminder=reminder)
    health.save_habit(habit)
    assert health.load().habits == [habit]


def test_text_fields_and_dates_survive_a_round_trip(health: SqliteRepository) -> None:
    habit = make_habit(
        name="Café ☕ \"quoted\" 'name'; DROP TABLE habits;--",
        description="line one\nline two",
        notes="  spaced  ",
        end=date(2027, 1, 31),
    )
    health.save_habit(habit)
    assert health.load().habits == [habit]


def test_habits_are_listed_in_id_order(health: SqliteRepository) -> None:
    for habit_id in (7, 2, 5):
        health.save_habit(make_habit(habit_id))
    assert [habit.id for habit in health.load().habits] == [2, 5, 7]


# ---------- Areas ----------


def test_areas_keep_the_order_they_were_added_in(repository: SqliteRepository) -> None:
    for area_id in ("zeta", "alpha", "mid"):
        repository.save_area(Area(area_id, area_id.title(), "#000000"))
    assert [area.id for area in repository.load().areas] == ["zeta", "alpha", "mid"]


def test_saving_an_existing_area_updates_it_in_place(repository: SqliteRepository) -> None:
    repository.save_area(Area("a", "A", "#111111"))
    repository.save_area(Area("b", "B", "#222222"))
    repository.save_area(Area("a", "Renamed", "#333333", "#444444"))
    assert repository.load().areas == [
        Area("a", "Renamed", "#333333", "#444444"),
        Area("b", "B", "#222222"),
    ]


# ---------- Habits and completions ----------


def test_saving_an_existing_habit_updates_it(health: SqliteRepository) -> None:
    health.save_habit(make_habit(name="Before", frequency=Daily()))
    health.save_habit(make_habit(name="After", frequency=Interval(2, IntervalUnit.DAYS)))
    habits = health.load().habits
    assert len(habits) == 1
    assert habits[0].name == "After"
    assert habits[0].frequency == Interval(2, IntervalUnit.DAYS)


def test_saving_a_habit_never_touches_its_completions(health: SqliteRepository) -> None:
    health.save_habit(make_habit())
    health.set_completion(1, DAY, done=True, value=3.5)
    stale = make_habit(name="Renamed", completions={date(2000, 1, 1): None})
    health.save_habit(stale)
    saved = health.load().habits[0]
    assert saved.name == "Renamed"
    assert saved.completions == {DAY: 3.5}


def test_a_completion_may_have_a_value_or_not(health: SqliteRepository) -> None:
    health.save_habit(make_habit())
    health.set_completion(1, DAY, done=True)
    health.set_completion(1, date(2026, 10, 2), done=True, value=0.0)
    health.set_completion(1, date(2026, 10, 3), done=True, value=12)
    assert health.load().habits[0].completions == {
        DAY: None,
        date(2026, 10, 2): 0.0,
        date(2026, 10, 3): 12.0,
    }


def test_marking_a_day_again_replaces_its_value(health: SqliteRepository) -> None:
    health.save_habit(make_habit())
    health.set_completion(1, DAY, done=True, value=1.0)
    health.set_completion(1, DAY, done=True, value=2.0)
    health.set_completion(1, DAY, done=True)
    assert health.load().habits[0].completions == {DAY: None}


def test_a_completion_can_be_cleared(health: SqliteRepository) -> None:
    health.save_habit(make_habit())
    health.set_completion(1, DAY, done=True, value=4.0)
    health.set_completion(1, DAY, done=False)
    health.set_completion(1, date(2030, 1, 1), done=False)  # never done: nothing to clear
    assert health.load().habits[0].completions == {}


def test_clearing_a_completion_ignores_the_value(health: SqliteRepository) -> None:
    health.save_habit(make_habit())
    health.set_completion(1, DAY, done=True)
    health.set_completion(1, DAY, done=False, value=float("nan"))
    assert health.load().habits[0].completions == {}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 10**400, True, "5"])
def test_a_value_that_is_not_a_finite_number_is_refused_and_nothing_is_written(
    health: SqliteRepository, value: Any
) -> None:
    health.save_habit(make_habit())
    with pytest.raises(ValidationError) as caught:
        health.set_completion(1, DAY, done=True, value=value)
    assert caught.value.code is ErrorCode.VALUE_INVALID
    assert health.load().habits[0].completions == {}


def test_deleting_a_habit_deletes_its_completions(
    health: SqliteRepository, db_path: Path, raw_connect: RawConnect
) -> None:
    health.save_habit(make_habit(1))
    health.save_habit(make_habit(2))
    health.set_completion(1, DAY, done=True, value=1.0)
    health.set_completion(1, date(2026, 10, 2), done=True)
    health.set_completion(2, DAY, done=True)
    health.delete_habit(1)
    assert [habit.id for habit in health.load().habits] == [2]
    assert count(db_path, raw_connect, "completions") == 1


def test_deleting_an_unknown_habit_changes_nothing(health: SqliteRepository) -> None:
    health.save_habit(make_habit())
    health.delete_habit(99)
    assert [habit.id for habit in health.load().habits] == [1]


# ---------- Priority note and important dates ----------


def test_the_priority_note_can_be_set_replaced_and_cleared(health: SqliteRepository) -> None:
    assert health.load().priority is None
    health.save_priority(PriorityNote(date(2026, 10, 2), "First"))
    health.save_priority(PriorityNote(date(2026, 10, 3), "Second"))
    assert health.load().priority == PriorityNote(date(2026, 10, 3), "Second")
    health.save_priority(None)
    health.save_priority(None)
    assert health.load().priority is None


def test_important_dates_are_added_once_removed_and_listed_by_day(
    repository: SqliteRepository,
) -> None:
    later = ImportantDate(date(2026, 12, 1), "Later")
    sooner = ImportantDate(date(2026, 11, 1), "Sooner")
    same_day = ImportantDate(date(2026, 11, 1), "Another")
    for item in (later, sooner, sooner, same_day):
        repository.add_important_date(item)
    assert repository.load().important_dates == [same_day, sooner, later]
    repository.remove_important_date(sooner)
    repository.remove_important_date(sooner)
    assert repository.load().important_dates == [same_day, later]


# ---------- is_empty and import_snapshot ----------


def test_the_repository_is_empty_only_without_habits_and_areas(
    repository: SqliteRepository,
) -> None:
    repository.add_important_date(ImportantDate(DAY, "Note"))
    repository.save_priority(PriorityNote(DAY, "Note"))
    assert repository.is_empty()
    repository.save_area(Area("health", "Health", "#65a882"))
    assert not repository.is_empty()


def test_import_snapshot_refuses_a_database_that_is_not_empty(
    health: SqliteRepository, snapshot: Snapshot
) -> None:
    before = health.load()
    with pytest.raises(StorageError, match="already has data"):
        health.import_snapshot(snapshot)
    assert health.load() == before


def test_import_snapshot_of_nothing_leaves_the_database_empty(
    repository: SqliteRepository,
) -> None:
    repository.import_snapshot(Snapshot())
    assert repository.is_empty()


# ---------- Failures never leave partial changes ----------


def test_a_failed_import_writes_nothing(
    repository: SqliteRepository, snapshot: Snapshot, db_path: Path, raw_connect: RawConnect
) -> None:
    snapshot.habits.append(make_habit(99, area_id="nowhere"))  # the last statement to fail
    with pytest.raises(StorageError, match="FOREIGN KEY"):
        repository.import_snapshot(snapshot)
    assert repository.is_empty()
    assert repository.load() == Snapshot()
    assert integrity_check(db_path, raw_connect) == ["ok"]
    for table in ("areas", "habits", "completions", "important_dates", "priority_note"):
        assert count(db_path, raw_connect, table) == 0


def test_an_error_injected_in_the_middle_of_an_import_rolls_everything_back(
    repository: SqliteRepository, snapshot: Snapshot, db_path: Path, raw_connect: RawConnect
) -> None:
    saboteur = raw_connect(db_path)
    saboteur.execute(
        "CREATE TRIGGER sabotage BEFORE INSERT ON important_dates "
        "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    saboteur.commit()
    with pytest.raises(StorageError, match="injected failure") as caught:
        repository.import_snapshot(snapshot)  # areas, habits and completions go in first
    assert isinstance(caught.value.__cause__, sqlite3.Error)
    assert repository.is_empty()
    assert count(db_path, raw_connect, "completions") == 0
    assert integrity_check(db_path, raw_connect) == ["ok"]


def test_a_failed_update_keeps_the_previous_values(
    health: SqliteRepository, db_path: Path, raw_connect: RawConnect
) -> None:
    health.save_habit(make_habit(name="Original"))
    saboteur = raw_connect(db_path)
    saboteur.execute(
        "CREATE TRIGGER sabotage BEFORE UPDATE ON habits "
        "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    saboteur.commit()
    with pytest.raises(StorageError, match="injected failure"):
        health.save_habit(make_habit(name="Changed"))
    assert health.load().habits[0].name == "Original"
    assert integrity_check(db_path, raw_connect) == ["ok"]


def test_a_habit_in_an_unknown_area_is_refused(
    repository: SqliteRepository, db_path: Path, raw_connect: RawConnect
) -> None:
    with pytest.raises(StorageError, match="FOREIGN KEY"):
        repository.save_habit(make_habit(area_id="nowhere"))
    assert repository.load().habits == []
    assert count(db_path, raw_connect, "habits") == 0


def test_a_completion_of_an_unknown_habit_is_refused(repository: SqliteRepository) -> None:
    with pytest.raises(StorageError, match="FOREIGN KEY"):
        repository.set_completion(404, DAY, done=True)
    assert repository.load() == Snapshot()


def test_an_integer_too_large_for_sqlite_becomes_a_storage_error(
    health: SqliteRepository,
) -> None:
    with pytest.raises(StorageError):
        health.save_habit(make_habit(2**70))
    with pytest.raises(StorageError):
        health.delete_habit(2**70)
    assert health.load().habits == []


def test_a_closed_repository_raises_storage_errors(db_path: Path) -> None:
    repository = SqliteRepository(db_path)
    repository.close()
    with pytest.raises(StorageError):
        repository.load()
    with pytest.raises(StorageError):
        repository.save_area(Area("a", "A", "#000000"))


# ---------- Stored data that no longer satisfies the domain ----------


@pytest.mark.parametrize(
    ("column", "bad_value", "message"),
    [
        ("frequency_params", "{not json", "habit 1: invalid 'daily' frequency"),
        ("frequency_kind", "quota", "habit 1: invalid 'quota' frequency"),
        ("start_date", "2026-02-31", "habit 1: invalid stored date"),
        ("end_date", "2026-08-31", "habit 1: invalid habit"),
        ("measurement_goal", -1.0, "habit 1: invalid measurement"),
        ("reminder_weekdays", '["funday"]', "habit 1: invalid reminder"),
    ],
)
def test_a_stored_habit_that_breaks_a_domain_rule_names_its_row(
    health: SqliteRepository,
    db_path: Path,
    raw_connect: RawConnect,
    column: str,
    bad_value: object,
    message: str,
) -> None:
    health.save_habit(
        make_habit(
            measurement=Measurement(MeasurementKind.QUANTITY, 5, "pages"),
            reminder=Reminder(time(9, 0)),
        )
    )
    tamper = raw_connect(db_path)
    tamper.execute("PRAGMA ignore_check_constraints = ON")
    tamper.execute(f"UPDATE habits SET {column} = ? WHERE id = 1", (bad_value,))
    tamper.commit()
    with pytest.raises(StorageError, match=message):
        health.load()


def test_a_stored_completion_with_a_bad_day_names_its_row(
    health: SqliteRepository, db_path: Path, raw_connect: RawConnect
) -> None:
    health.save_habit(make_habit())
    tamper = raw_connect(db_path)
    tamper.execute("PRAGMA ignore_check_constraints = ON")
    tamper.execute("INSERT INTO completions VALUES (1, '2026-13-01', NULL)")
    tamper.commit()
    with pytest.raises(StorageError, match="completion of habit 1"):
        health.load()


# ---------- Files, locks and permissions ----------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_database_file_is_created_readable_only_by_its_owner(db_path: Path) -> None:
    SqliteRepository(db_path).close()
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_an_existing_file_keeps_its_permissions(db_path: Path) -> None:
    SqliteRepository(db_path).close()
    db_path.chmod(0o640)
    SqliteRepository(db_path).close()
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o640


def test_permission_errors_are_ignored_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(path: object, mode: int) -> None:
        raise PermissionError("no POSIX modes here")

    monkeypatch.setattr(os, "chmod", refuse)
    monkeypatch.setattr(sys, "platform", "win32")
    sqlite_module._restrict_permissions(Path("habits.sqlite3"))


def test_permission_errors_are_reported_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(path: object, mode: int) -> None:
        raise PermissionError("operation not permitted")

    monkeypatch.setattr(os, "chmod", refuse)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(StorageError, match="restrict the permissions"):
        sqlite_module._restrict_permissions(Path("habits.sqlite3"))


def test_every_operation_is_committed_when_it_returns(
    repository: SqliteRepository, db_path: Path, raw_connect: RawConnect
) -> None:
    repository.save_area(Area("health", "Health", "#65a882"))
    other = raw_connect(db_path)
    assert other.execute("SELECT id FROM areas").fetchall() == [("health",)]


def test_reading_does_not_keep_other_writers_out(
    health: SqliteRepository, db_path: Path, raw_connect: RawConnect
) -> None:
    health.load()
    health.is_empty()
    other = raw_connect(db_path)
    other.execute("INSERT INTO important_dates VALUES ('2026-10-01', 'Written meanwhile')")
    other.commit()
    assert health.load().important_dates == [ImportantDate(DAY, "Written meanwhile")]


def test_a_database_that_cannot_be_opened_is_a_storage_error(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="could not open"):
        SqliteRepository(tmp_path / "missing-directory" / "habits.sqlite3")


def test_nothing_is_created_when_sqlite_is_too_old(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 20, 0))
    with pytest.raises(StorageError, match=r"3\.24\.0 or newer"):
        SqliteRepository(db_path)
    assert not db_path.exists()


def test_a_database_from_a_newer_version_is_refused_untouched(
    db_path: Path, raw_connect: RawConnect
) -> None:
    SqliteRepository(db_path).close()
    raw = raw_connect(db_path)
    raw.execute("PRAGMA user_version = 99")
    raw.commit()
    before = db_path.read_bytes()
    with pytest.raises(StorageError, match="schema version 99"):
        SqliteRepository(db_path)
    assert db_path.read_bytes() == before
    assert [path.name for path in db_path.parent.iterdir()] == [db_path.name]


# ---------- What the repository relies on from sqlite3 ----------
# These pin down behaviour found by experiment, so that a different Python or
# SQLite that changed it would fail here and not in someone's data.


def test_pragma_foreign_keys_does_nothing_inside_the_transaction_autocommit_false_keeps_open(
    tmp_path: Path,
) -> None:
    con = sqlite3.connect(tmp_path / "x.db", autocommit=False)
    con.execute("PRAGMA foreign_keys = ON")
    assert con.execute("PRAGMA foreign_keys").fetchone() == (0,)
    con.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY, True)
    assert con.execute("PRAGMA foreign_keys").fetchone() == (1,)
    con.close()


def insert_then_fail(con: sqlite3.Connection) -> None:
    with con:
        con.execute("INSERT INTO t VALUES (2)")
        raise RuntimeError("fail")


def test_the_with_statement_opens_a_new_transaction_when_it_exits(tmp_path: Path) -> None:
    con = sqlite3.connect(tmp_path / "x.db", autocommit=False)
    con.execute("CREATE TABLE t (x)")
    with con:
        con.execute("INSERT INTO t VALUES (1)")
    assert con.in_transaction
    with pytest.raises(RuntimeError):
        insert_then_fail(con)
    assert con.in_transaction
    assert con.execute("SELECT x FROM t").fetchall() == [(1,)]
    con.close()


def test_a_replace_would_delete_the_completions_through_the_foreign_key(
    health: SqliteRepository, db_path: Path, raw_connect: RawConnect
) -> None:
    health.save_habit(make_habit())
    health.set_completion(1, DAY, done=True)
    other = raw_connect(db_path)
    other.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY, True)
    other.execute("INSERT OR REPLACE INTO habits SELECT * FROM habits")
    other.commit()
    assert count(db_path, raw_connect, "completions") == 0
