"""The schema, its version bookkeeping and the migration chain."""

import sqlite3
import struct
from collections.abc import Callable
from pathlib import Path

import pytest

from habit_tracker.ports import StorageError
from habit_tracker.storage import schema

RawConnect = Callable[[Path], sqlite3.Connection]
Migration = Callable[[sqlite3.Connection], None]

APPLICATION_ID_OFFSET = 68
USER_VERSION_OFFSET = 60


def create_table(name: str) -> Migration:
    def migration(con: sqlite3.Connection) -> None:
        con.execute(f"CREATE TABLE {name} (x)")

    return migration


def fail_after_creating(name: str) -> Migration:
    def migration(con: sqlite3.Connection) -> None:
        con.execute(f"CREATE TABLE {name} (x)")
        raise RuntimeError("the migration is broken")

    return migration


def fail_with_sql_error(con: sqlite3.Connection) -> None:
    con.execute("CREATE TABLE half_done (x)")
    con.execute("SELECT * FROM table_that_does_not_exist")


def tables(con: sqlite3.Connection) -> set[str]:
    rows = con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


def versions(con: sqlite3.Connection) -> tuple[int, int]:
    return schema.read_user_version(con), schema.read_application_id(con)


@pytest.fixture
def con(db_path: Path, raw_connect: RawConnect) -> sqlite3.Connection:
    return raw_connect(db_path)


# ---------- The first version ----------


def test_migrating_an_empty_database_builds_the_current_schema(con: sqlite3.Connection) -> None:
    schema.migrate(con)
    assert tables(con) >= {"areas", "habits", "completions", "important_dates", "priority_note"}
    assert versions(con) == (schema.SCHEMA_VERSION, schema.APPLICATION_ID)
    assert schema.SCHEMA_VERSION == len(schema.MIGRATIONS) == 1


def test_the_versions_are_written_where_sqlite_documents_them(
    con: sqlite3.Connection, db_path: Path
) -> None:
    schema.migrate(con)
    header = db_path.read_bytes()[:100]
    (user_version,) = struct.unpack_from(">I", header, USER_VERSION_OFFSET)
    (application_id,) = struct.unpack_from(">i", header, APPLICATION_ID_OFFSET)
    assert user_version == schema.SCHEMA_VERSION
    assert application_id == schema.APPLICATION_ID


def test_the_application_id_is_a_signed_32_bit_integer() -> None:
    assert 0 < schema.APPLICATION_ID < 2**31
    assert schema.APPLICATION_ID.to_bytes(4, "big") == b"HABT"


def test_migrating_twice_changes_nothing(con: sqlite3.Connection, db_path: Path) -> None:
    schema.migrate(con)
    before = db_path.read_bytes()
    schema.migrate(con)
    assert db_path.read_bytes() == before


def test_migrate_needs_a_connection_with_autocommit_off(db_path: Path) -> None:
    legacy = sqlite3.connect(db_path)
    with pytest.raises(ValueError, match="autocommit=False"):
        schema.migrate(legacy)
    legacy.close()
    assert db_path.read_bytes() == b""


# ---------- Constraints that protect the data ----------


def insert_habit(con: sqlite3.Connection, **overrides: object) -> None:
    row: dict[str, object] = {
        "id": 1,
        "name": "Walk",
        "area_id": "a",
        "frequency_kind": "daily",
        "frequency_params": "{}",
        "start_date": "2026-09-01",
        "end_date": None,
        "measurement_kind": None,
        "measurement_goal": None,
        "measurement_unit": None,
        "reminder_time": None,
        "reminder_weekdays": None,
    }
    row.update(overrides)
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    con.execute(f"INSERT INTO habits ({columns}) VALUES ({marks})", tuple(row.values()))


@pytest.mark.parametrize(
    "overrides",
    [
        {"frequency_kind": "yearly"},
        {"start_date": "tomorrow"},
        {"start_date": "2026-9-1"},
        {"end_date": "soon"},
        {"end_date": "2026-08-31"},
        {"measurement_kind": "weight", "measurement_goal": 1.0, "measurement_unit": "kg"},
        {"measurement_kind": "quantity"},
        {"measurement_goal": 1.0},
        {"reminder_time": "9:00", "reminder_weekdays": "[]"},
        {"reminder_time": "09:00"},
        {"reminder_weekdays": "[]"},
    ],
    ids=repr,
)
def test_the_schema_rejects_malformed_habit_rows(
    con: sqlite3.Connection, overrides: dict[str, object]
) -> None:
    schema.migrate(con)
    with pytest.raises(sqlite3.IntegrityError):
        insert_habit(con, **overrides)


def test_the_schema_accepts_a_well_formed_habit_row(con: sqlite3.Connection) -> None:
    schema.migrate(con)
    insert_habit(con, end_date="2026-09-01", reminder_time="09:00", reminder_weekdays="[]")
    insert_habit(
        con,
        id=2,
        measurement_kind="duration",
        measurement_goal=15.0,
        measurement_unit="min",
    )


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO completions VALUES (1, 'not-a-day', NULL)",
        "INSERT INTO important_dates VALUES ('2026-1-1', 'Bad')",
        "INSERT INTO priority_note VALUES (2, '2026-10-01', 'Second row')",
        "INSERT INTO priority_note VALUES (1, 'tomorrow', 'Bad day')",
    ],
)
def test_the_schema_rejects_other_malformed_rows(con: sqlite3.Connection, statement: str) -> None:
    schema.migrate(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(statement)


# ---------- The migration chain ----------


def test_migrations_run_in_order_and_each_one_sets_the_version(con: sqlite3.Connection) -> None:
    seen: list[int] = []

    def recording(name: str) -> Migration:
        def migration(connection: sqlite3.Connection) -> None:
            seen.append(schema.read_user_version(connection))
            connection.execute(f"CREATE TABLE {name} (x)")

        return migration

    schema.migrate(con, (recording("one"), recording("two"), recording("three")))
    assert seen == [0, 1, 2]
    assert tables(con) == {"one", "two", "three"}
    assert versions(con) == (3, schema.APPLICATION_ID)


def test_only_the_missing_migrations_run(con: sqlite3.Connection) -> None:
    schema.migrate(con, (create_table("one"),))
    schema.migrate(con, (create_table("one"), create_table("two"), create_table("three")))
    assert tables(con) == {"one", "two", "three"}
    assert schema.read_user_version(con) == 3


def test_a_failing_step_is_undone_and_the_earlier_steps_stay(con: sqlite3.Connection) -> None:
    with pytest.raises(StorageError, match="schema version 2") as caught:
        schema.migrate(con, (create_table("one"), fail_with_sql_error, create_table("three")))
    assert isinstance(caught.value.__cause__, sqlite3.Error)
    assert tables(con) == {"one"}
    assert versions(con) == (1, schema.APPLICATION_ID)


def test_a_step_that_raises_something_else_is_undone_too(con: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError, match="broken"):
        schema.migrate(con, (fail_after_creating("half_done"),))
    assert tables(con) == set()
    assert versions(con) == (0, 0)


def test_after_a_failed_step_the_next_run_resumes_from_it(con: sqlite3.Connection) -> None:
    with pytest.raises(StorageError):
        schema.migrate(con, (create_table("one"), fail_with_sql_error))
    schema.migrate(con, (create_table("one"), create_table("two")))
    assert tables(con) == {"one", "two"}
    assert schema.read_user_version(con) == 2


# ---------- Databases that must not be touched ----------


def test_a_newer_schema_is_refused_before_anything_is_written(
    db_path: Path, raw_connect: RawConnect
) -> None:
    setup = raw_connect(db_path)
    schema.migrate(setup, (create_table("one"), create_table("two"), create_table("three")))
    setup.close()
    before = db_path.read_bytes()
    con = raw_connect(db_path)
    with pytest.raises(StorageError, match=r"schema version 3.*only understands up to 1"):
        schema.migrate(con)
    con.close()
    assert db_path.read_bytes() == before
    assert [path.name for path in db_path.parent.iterdir()] == [db_path.name]


def test_a_database_with_another_application_id_is_refused(
    db_path: Path, raw_connect: RawConnect
) -> None:
    setup = raw_connect(db_path)
    setup.execute("PRAGMA application_id = 1234")
    setup.execute("CREATE TABLE theirs (x)")
    setup.commit()
    setup.close()
    before = db_path.read_bytes()
    con = raw_connect(db_path)
    with pytest.raises(StorageError, match=r"another application.*1234"):
        schema.migrate(con)
    con.close()
    assert db_path.read_bytes() == before


@pytest.mark.parametrize(
    "setup_sql",
    ["CREATE TABLE areas (x)", "PRAGMA user_version = 3", "CREATE VIEW v AS SELECT 1"],
)
def test_a_database_without_our_id_is_accepted_only_if_it_is_blank(
    db_path: Path, raw_connect: RawConnect, setup_sql: str
) -> None:
    setup = raw_connect(db_path)
    setup.execute(setup_sql)
    setup.commit()
    setup.close()
    before = db_path.read_bytes()
    con = raw_connect(db_path)
    with pytest.raises(StorageError, match="another application"):
        schema.migrate(con)
    con.close()
    assert db_path.read_bytes() == before


def test_a_garbage_file_surfaces_the_sqlite_error_to_the_caller(
    db_path: Path, raw_connect: RawConnect
) -> None:
    db_path.write_bytes(b"this is not a database " * 20)
    con = raw_connect(db_path)
    with pytest.raises(sqlite3.DatabaseError):
        schema.ensure_supported(con)
    with pytest.raises(StorageError, match="could not read the schema version"):
        schema.migrate(con)
