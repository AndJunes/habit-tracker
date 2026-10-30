"""A repository that keeps everything in a SQLite file, using only the standard library.

Rules every operation follows:

* One public method is one transaction. It commits when it finishes and rolls
  everything back when anything fails, so a failed operation never leaves data
  half written. Reads are transactions too: a read transaction that stayed open
  would keep other programs from writing to the file.
* Values are always passed as ``?`` parameters, never formatted into the SQL.
* Habits are written with an upsert, never ``INSERT OR REPLACE``: a replace deletes
  the row first, and the foreign key would delete the habit's completions with it.
* Every ``sqlite3.Error`` leaves as a :class:`~habit_tracker.ports.StorageError`.

Upserts need SQLite 3.24 or newer.
"""

import math
import os
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from ..domain.errors import ErrorCode, ValidationError
from ..domain.models import Area, Habit, ImportantDate, PriorityNote, Snapshot
from ..ports import StorageError
from . import schema
from .serialization import (
    MeasurementColumns,
    ReminderColumns,
    format_day,
    frequency_from_columns,
    frequency_to_columns,
    measurement_from_columns,
    measurement_to_columns,
    reminder_from_columns,
    reminder_to_columns,
    stored_date,
)

MINIMUM_SQLITE_VERSION = (3, 24, 0)

_FILE_MODE = 0o600

_SELECT_AREAS = "SELECT id, name, color, soft_color FROM areas ORDER BY position"
_SELECT_HABITS = """
    SELECT id, name, area_id, frequency_kind, frequency_params, start_date, end_date,
           description, notes, measurement_kind, measurement_goal, measurement_unit,
           measurement_minimum, measurement_ideal, reminder_time, reminder_weekdays
    FROM habits ORDER BY id
"""
_SELECT_COMPLETIONS = "SELECT habit_id, day, value FROM completions ORDER BY habit_id, day"
_SELECT_IMPORTANT_DATES = "SELECT day, title FROM important_dates ORDER BY day, title"
_SELECT_PRIORITY = "SELECT for_day, text FROM priority_note"

_INSERT_AREA = """
    INSERT INTO areas (id, name, color, soft_color, position) VALUES (?, ?, ?, ?, ?)
"""
# A new area goes last; updating one keeps its place.
_UPSERT_AREA = """
    INSERT INTO areas (id, name, color, soft_color, position)
    VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(position), -1) + 1 FROM areas))
    ON CONFLICT (id) DO UPDATE SET
        name = excluded.name, color = excluded.color, soft_color = excluded.soft_color
"""
_INSERT_HABIT = """
    INSERT INTO habits (
        id, name, area_id, frequency_kind, frequency_params, start_date, end_date,
        description, notes, measurement_kind, measurement_goal, measurement_unit,
        measurement_minimum, measurement_ideal, reminder_time, reminder_weekdays
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_UPSERT_HABIT = (
    _INSERT_HABIT
    + """
    ON CONFLICT (id) DO UPDATE SET
        name = excluded.name,
        area_id = excluded.area_id,
        frequency_kind = excluded.frequency_kind,
        frequency_params = excluded.frequency_params,
        start_date = excluded.start_date,
        end_date = excluded.end_date,
        description = excluded.description,
        notes = excluded.notes,
        measurement_kind = excluded.measurement_kind,
        measurement_goal = excluded.measurement_goal,
        measurement_unit = excluded.measurement_unit,
        measurement_minimum = excluded.measurement_minimum,
        measurement_ideal = excluded.measurement_ideal,
        reminder_time = excluded.reminder_time,
        reminder_weekdays = excluded.reminder_weekdays
"""
)
_INSERT_COMPLETION = "INSERT INTO completions (habit_id, day, value) VALUES (?, ?, ?)"
_UPSERT_COMPLETION = (
    _INSERT_COMPLETION + " ON CONFLICT (habit_id, day) DO UPDATE SET value = excluded.value"
)
_INSERT_IMPORTANT_DATE = "INSERT INTO important_dates (day, title) VALUES (?, ?)"
_INSERT_PRIORITY = "INSERT INTO priority_note (id, for_day, text) VALUES (1, ?, ?)"
_UPSERT_PRIORITY = (
    _INSERT_PRIORITY
    + " ON CONFLICT (id) DO UPDATE SET for_day = excluded.for_day, text = excluded.text"
)


class SqliteRepository:
    """Implements :class:`~habit_tracker.ports.Repository` on a SQLite file.

    Opening creates the file when it is missing (readable only by its owner) and
    brings its schema up to date. Use :func:`~habit_tracker.storage.recovery.open_repository`
    to also deal with files that are damaged.
    """

    def __init__(self, path: Path) -> None:
        self._con = _connect(path)
        try:
            schema.migrate(self._con)
        except BaseException:
            self._con.close()
            raise

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def load(self) -> Snapshot:
        with self._transaction("load the data") as con:
            areas = [
                Area(id=row[0], name=row[1], color=row[2], soft_color=row[3])
                for row in con.execute(_SELECT_AREAS)
            ]
            completions = _load_completions(con)
            habits = [
                _habit_from_row(row, completions.get(row[0], {}))
                for row in con.execute(_SELECT_HABITS)
            ]
            important_dates = [
                ImportantDate(day=stored_date(row[0], where="important date"), title=row[1])
                for row in con.execute(_SELECT_IMPORTANT_DATES)
            ]
            row = con.execute(_SELECT_PRIORITY).fetchone()
            priority = (
                None
                if row is None
                else PriorityNote(for_day=stored_date(row[0], where="priority note"), text=row[1])
            )
        return Snapshot(
            areas=areas, habits=habits, important_dates=important_dates, priority=priority
        )

    def save_area(self, area: Area) -> None:
        with self._transaction("save the area") as con:
            con.execute(_UPSERT_AREA, (area.id, area.name, area.color, area.soft_color))

    def save_habit(self, habit: Habit) -> None:
        with self._transaction("save the habit") as con:
            con.execute(_UPSERT_HABIT, _habit_parameters(habit))

    def delete_habit(self, habit_id: int) -> None:
        with self._transaction("delete the habit") as con:
            con.execute("DELETE FROM habits WHERE id = ?", (habit_id,))

    def set_completion(
        self, habit_id: int, day: date, *, done: bool, value: float | None = None
    ) -> None:
        with self._transaction("save the completion") as con:
            if done:
                con.execute(
                    _UPSERT_COMPLETION, (habit_id, format_day(day), _completion_value(value))
                )
            else:
                con.execute(
                    "DELETE FROM completions WHERE habit_id = ? AND day = ?",
                    (habit_id, format_day(day)),
                )

    def save_priority(self, note: PriorityNote | None) -> None:
        with self._transaction("save the priority note") as con:
            if note is None:
                con.execute("DELETE FROM priority_note")
            else:
                con.execute(_UPSERT_PRIORITY, (format_day(note.for_day), note.text))

    def add_important_date(self, item: ImportantDate) -> None:
        """Add the date; adding one that already exists changes nothing."""
        with self._transaction("save the important date") as con:
            con.execute(
                "INSERT OR IGNORE INTO important_dates (day, title) VALUES (?, ?)",
                (format_day(item.day), item.title),
            )

    def remove_important_date(self, item: ImportantDate) -> None:
        with self._transaction("remove the important date") as con:
            con.execute(
                "DELETE FROM important_dates WHERE day = ? AND title = ?",
                (format_day(item.day), item.title),
            )

    def is_empty(self) -> bool:
        """Whether there are no habits and no areas."""
        with self._transaction("check the data") as con:
            return _is_empty(con)

    def import_snapshot(self, snapshot: Snapshot) -> None:
        """Write a whole snapshot in a single transaction.

        Raises ``StorageError`` when the database already has habits or areas, or
        when the snapshot cannot be stored (for example, a habit in an unknown
        area). In either case nothing is written.
        """
        with self._transaction("import the data") as con:
            if not _is_empty(con):
                raise StorageError("cannot import into a database that already has data")
            for position, area in enumerate(snapshot.areas):
                con.execute(
                    _INSERT_AREA, (area.id, area.name, area.color, area.soft_color, position)
                )
            for habit in snapshot.habits:
                con.execute(_INSERT_HABIT, _habit_parameters(habit))
                con.executemany(
                    _INSERT_COMPLETION,
                    [
                        (habit.id, format_day(day), _completion_value(value))
                        for day, value in habit.completions.items()
                    ],
                )
            for item in snapshot.important_dates:
                con.execute(_INSERT_IMPORTANT_DATE, (format_day(item.day), item.title))
            if snapshot.priority is not None:
                con.execute(
                    _INSERT_PRIORITY,
                    (format_day(snapshot.priority.for_day), snapshot.priority.text),
                )

    @contextmanager
    def _transaction(self, action: str) -> Iterator[sqlite3.Connection]:
        """Commit when the block ends, roll back when it fails."""
        con = self._con
        try:
            yield con
            con.commit()
        except (sqlite3.Error, OverflowError) as error:
            _rollback(con)
            raise StorageError(f"could not {action}: {error}") from error
        except BaseException:
            _rollback(con)
            raise


def _connect(path: Path) -> sqlite3.Connection:
    if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
        needed = ".".join(map(str, MINIMUM_SQLITE_VERSION))
        raise StorageError(f"SQLite {needed} or newer is required, found {sqlite3.sqlite_version}")
    created = not path.exists()
    try:
        # autocommit=False follows PEP 249: a transaction is always open, and
        # commit() and rollback() open the next one.
        con = sqlite3.connect(path, autocommit=False)
    except sqlite3.Error as error:
        raise StorageError(f"could not open the database {path}: {error}") from error
    try:
        if created:
            _restrict_permissions(path)
        # "PRAGMA foreign_keys = ON" does nothing inside a transaction, and with
        # autocommit=False one is always open. The connection option is the same
        # switch and works at any time.
        con.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY, True)
        if not con.execute("PRAGMA foreign_keys").fetchone()[0]:
            raise StorageError("could not enable foreign key enforcement")
    except sqlite3.Error as error:
        con.close()
        raise StorageError(f"could not set up the database {path}: {error}") from error
    except BaseException:
        con.close()
        raise
    return con


def _restrict_permissions(path: Path) -> None:
    try:
        os.chmod(path, _FILE_MODE)
    except OSError as error:
        if sys.platform != "win32":
            raise StorageError(f"could not restrict the permissions of {path}: {error}") from error


def _rollback(con: sqlite3.Connection) -> None:
    with suppress(sqlite3.Error):
        con.rollback()


def _is_empty(con: sqlite3.Connection) -> bool:
    row = con.execute(
        "SELECT NOT EXISTS (SELECT 1 FROM habits) AND NOT EXISTS (SELECT 1 FROM areas)"
    ).fetchone()
    return bool(row[0])


def _completion_value(value: float | None) -> float | None:
    """The value as a float; SQLite would turn NaN into NULL, so it is refused."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationError(ErrorCode.VALUE_INVALID, value=value)
    try:
        number = float(value)
    except OverflowError:  # an int beyond the range of a float
        raise ValidationError(ErrorCode.VALUE_INVALID, value=value) from None
    if not math.isfinite(number):
        raise ValidationError(ErrorCode.VALUE_INVALID, value=value)
    return number


def _habit_parameters(habit: Habit) -> tuple[object, ...]:
    kind, params = frequency_to_columns(habit.frequency)
    return (
        habit.id,
        habit.name,
        habit.area_id,
        kind,
        params,
        format_day(habit.start),
        None if habit.end is None else format_day(habit.end),
        habit.description,
        habit.notes,
        *measurement_to_columns(habit.measurement),
        *reminder_to_columns(habit.reminder),
    )


def _load_completions(con: sqlite3.Connection) -> dict[int, dict[date, float | None]]:
    completions: dict[int, dict[date, float | None]] = {}
    for habit_id, day, value in con.execute(_SELECT_COMPLETIONS):
        where = f"completion of habit {habit_id}"
        if value is not None and type(value) is not float:
            raise StorageError(f"{where}: invalid stored value {value!r}")
        completions.setdefault(habit_id, {})[stored_date(day, where=where)] = value
    return completions


def _habit_from_row(row: Sequence[Any], completions: dict[date, float | None]) -> Habit:
    habit_id, name, area_id, kind, params, start, end, description, notes = row[:9]
    where = f"habit {habit_id}"
    measurement = measurement_from_columns(MeasurementColumns(*row[9:14]), where=where)
    reminder = reminder_from_columns(ReminderColumns(*row[14:16]), where=where)
    try:
        return Habit(
            id=habit_id,
            name=name,
            area_id=area_id,
            frequency=frequency_from_columns(kind, params, where=where),
            start=stored_date(start, where=where),
            end=None if end is None else stored_date(end, where=where),
            description=description,
            notes=notes,
            measurement=measurement,
            reminder=reminder,
            completions=dict(completions),
        )
    except ValueError as error:
        raise StorageError(f"{where}: invalid habit ({error})") from error
