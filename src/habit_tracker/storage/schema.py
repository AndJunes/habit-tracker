"""The database schema and the migrations that build it.

Schema version 1::

    areas(id PK, name, color, soft_color, position)
    habits(id PK, name, area_id -> areas, frequency_kind, frequency_params,
           start_date, end_date, description, notes,
           measurement_kind/goal/unit/minimum/ideal, reminder_time, reminder_weekdays)
    completions(habit_id -> habits ON DELETE CASCADE, day, value)  PK (habit_id, day)
    important_dates(day, title)                                    PK (day, title)
    priority_note(id = 1, for_day, text)

Why it looks like this:

* Dates are ``YYYY-MM-DD`` text and times ``HH:MM`` text. SQLite has no date type,
  and ISO text sorts and compares chronologically, so ``ORDER BY day`` and range
  queries work without conversions.
* A frequency has a different shape for each kind, so it is stored as a ``kind``
  plus a JSON object of parameters. A measurement and a reminder are optional and
  always whole, so they are nullable columns with a ``CHECK`` that they are either
  all present or all absent.
* ``completions`` and ``important_dates`` are ``WITHOUT ROWID`` tables: their
  natural key is the primary key and nothing else needs a row id. Deleting a
  habit removes its completions through the foreign key.
* ``areas.position`` keeps the order the person arranged. Habits are listed by id,
  which is their creation order. The implicit rowid is not used for ordering
  because ``VACUUM`` may renumber it.
* ``priority_note`` has a single row (``id = 1`` is enforced) because there is
  only ever one note.
* Tables are not ``STRICT``: that needs SQLite 3.37 and Python 3.12 may be linked
  against an older library. ``CHECK`` constraints cover what matters and the domain
  constructors validate everything that is read back.

The schema version lives in ``PRAGMA user_version``, which SQLite itself never
uses (header offset 60). ``PRAGMA application_id`` (offset 68) marks the file as
ours so that another program's database is never "migrated".
"""

import sqlite3
from collections.abc import Callable, Sequence
from contextlib import suppress

from ..ports import StorageError

# The ASCII bytes "HABT" as a signed 32-bit integer. SQLite does not register or
# interpret application ids; this value is simply ours.
APPLICATION_ID = 0x48414254

Migration = Callable[[sqlite3.Connection], None]

_DATE = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
_TIME = "'[0-2][0-9]:[0-5][0-9]'"

_SCHEMA_V1 = (
    """
    CREATE TABLE areas (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        color       TEXT NOT NULL,
        soft_color  TEXT NOT NULL DEFAULT '',
        position    INTEGER NOT NULL
    )
    """,
    f"""
    CREATE TABLE habits (
        id                   INTEGER PRIMARY KEY,
        name                 TEXT NOT NULL,
        area_id              TEXT NOT NULL REFERENCES areas (id),
        frequency_kind       TEXT NOT NULL
            CHECK (frequency_kind IN ('daily', 'weekdays', 'quota', 'fixed_dates', 'interval')),
        frequency_params     TEXT NOT NULL,
        start_date           TEXT NOT NULL CHECK (start_date GLOB {_DATE}),
        end_date             TEXT CHECK (end_date IS NULL OR end_date GLOB {_DATE}),
        description          TEXT NOT NULL DEFAULT '',
        notes                TEXT NOT NULL DEFAULT '',
        measurement_kind     TEXT CHECK (measurement_kind IN ('quantity', 'duration')),
        measurement_goal     REAL,
        measurement_unit     TEXT,
        measurement_minimum  REAL,
        measurement_ideal    REAL,
        reminder_time        TEXT CHECK (reminder_time IS NULL OR reminder_time GLOB {_TIME}),
        reminder_weekdays    TEXT,
        CHECK (end_date IS NULL OR end_date >= start_date),
        CHECK ((measurement_kind IS NULL) = (measurement_goal IS NULL)
               AND (measurement_kind IS NULL) = (measurement_unit IS NULL)),
        CHECK ((reminder_time IS NULL) = (reminder_weekdays IS NULL))
    )
    """,
    "CREATE INDEX habits_by_area ON habits (area_id)",
    f"""
    CREATE TABLE completions (
        habit_id  INTEGER NOT NULL REFERENCES habits (id) ON DELETE CASCADE,
        day       TEXT NOT NULL CHECK (day GLOB {_DATE}),
        value     REAL,
        PRIMARY KEY (habit_id, day)
    ) WITHOUT ROWID
    """,
    f"""
    CREATE TABLE important_dates (
        day    TEXT NOT NULL CHECK (day GLOB {_DATE}),
        title  TEXT NOT NULL,
        PRIMARY KEY (day, title)
    ) WITHOUT ROWID
    """,
    f"""
    CREATE TABLE priority_note (
        id       INTEGER PRIMARY KEY CHECK (id = 1),
        for_day  TEXT NOT NULL CHECK (for_day GLOB {_DATE}),
        text     TEXT NOT NULL
    )
    """,
)


def _create_initial_schema(con: sqlite3.Connection) -> None:
    for statement in _SCHEMA_V1:
        con.execute(statement)


# Each entry upgrades the schema by exactly one version: MIGRATIONS[0] takes an
# empty database to version 1, MIGRATIONS[1] takes version 1 to 2, and so on.
# Entries are never edited or reordered once released.
MIGRATIONS: tuple[Migration, ...] = (_create_initial_schema,)

SCHEMA_VERSION = len(MIGRATIONS)


def read_application_id(con: sqlite3.Connection) -> int:
    return int(con.execute("PRAGMA application_id").fetchone()[0])


def read_user_version(con: sqlite3.Connection) -> int:
    return int(con.execute("PRAGMA user_version").fetchone()[0])


def ensure_supported(
    con: sqlite3.Connection, migrations: Sequence[Migration] = MIGRATIONS
) -> None:
    """Raise ``StorageError`` unless the database is blank or ours at a known version.

    Reads only. A file that SQLite cannot read raises ``sqlite3.DatabaseError``
    untouched, because only the caller knows whether that means corruption.
    """
    application_id = read_application_id(con)
    if application_id == APPLICATION_ID:
        version = read_user_version(con)
        if version > len(migrations):
            raise StorageError(
                f"the database uses schema version {version}, but this version of the "
                f"application only understands up to {len(migrations)}; "
                "update the application to open it"
            )
        return
    # Without our id the file is acceptable only when nothing is in it yet.
    if application_id != 0 or read_user_version(con) != 0 or _has_objects(con):
        raise StorageError(
            "the file is a database that belongs to another application "
            f"(application_id={application_id})"
        )


def migrate(con: sqlite3.Connection, migrations: Sequence[Migration] = MIGRATIONS) -> None:
    """Bring the database up to the last version in ``migrations``.

    Each missing step runs in its own transaction together with the update of
    ``user_version``, so a failed step leaves the database at the previous
    version. A database from a newer version, or another program's, is rejected
    before anything is written.

    The connection must have been opened with ``autocommit=False``: in the legacy
    transaction mode DDL statements would not be part of a transaction.
    """
    if con.autocommit is not False:
        raise ValueError("migrate() needs a connection opened with autocommit=False")
    try:
        ensure_supported(con, migrations)
        current = read_user_version(con)
    except StorageError:
        _rollback(con)
        raise
    except sqlite3.Error as error:
        _rollback(con)
        raise StorageError(f"could not read the schema version: {error}") from error
    for target in range(current + 1, len(migrations) + 1):
        _apply(con, migrations[target - 1], target)
    # Nothing to apply still leaves the reads above in an open transaction.
    _rollback(con)


def _apply(con: sqlite3.Connection, migration: Migration, target: int) -> None:
    try:
        migration(con)
        # PRAGMA arguments cannot be bound; both values are integers built here.
        con.execute(f"PRAGMA application_id = {int(APPLICATION_ID)}")
        con.execute(f"PRAGMA user_version = {int(target)}")
        con.commit()
    except sqlite3.Error as error:
        _rollback(con)
        raise StorageError(
            f"could not upgrade the database to schema version {target}: {error}"
        ) from error
    except BaseException:
        _rollback(con)
        raise


def _has_objects(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None


def _rollback(con: sqlite3.Connection) -> None:
    with suppress(sqlite3.Error):
        con.rollback()
