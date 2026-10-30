"""Opening the database file: creating it, quarantining damaged files and refusing foreign ones."""

import os
import shutil
import sqlite3
import stat
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.models import Area, Snapshot
from habit_tracker.ports import StorageError
from habit_tracker.storage import schema
from habit_tracker.storage.recovery import RecoveryNotice, open_repository
from habit_tracker.storage.sqlite import SqliteRepository

RawConnect = Callable[[Path], sqlite3.Connection]

# FixedClock in conftest.py reads 2026-10-30 01:40:05.
QUARANTINE = ".corrupt-20261030-014005"


def directory_listing(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def make_database(path: Path, rows: int = 0) -> bytes:
    """A real database of ours, with some padding so that it spans several pages."""
    with SqliteRepository(path) as repository:
        repository.save_area(Area("health", "Health", "#65a882"))
    if rows:
        con = sqlite3.connect(path, autocommit=False)
        con.executemany(
            "INSERT INTO important_dates VALUES (?, ?)",
            [(f"2026-01-{(n % 28) + 1:02d}", f"Event number {n} " * 8) for n in range(rows)],
        )
        con.commit()
        con.close()
    return path.read_bytes()


def foreign_database(path: Path, application_id: int = 0x12345678, rows: int = 1) -> bytes:
    con = sqlite3.connect(path, autocommit=False)
    con.execute(f"PRAGMA application_id = {application_id}")
    con.execute("CREATE TABLE songs (title TEXT)")
    con.executemany("INSERT INTO songs VALUES (?)", [(f"Not ours {n}" * 20,) for n in range(rows)])
    con.commit()
    con.close()
    return path.read_bytes()


def assert_usable(repository: SqliteRepository) -> None:
    """A repository that is empty, accepts writes and reads them back."""
    assert repository.is_empty()
    area = Area("new", "New", "#000000")
    repository.save_area(area)
    assert repository.load().areas == [area]


# ---------- Files that are fine ----------


def test_a_missing_file_is_created_with_its_directory(tmp_path: Path, clock: FixedClock) -> None:
    path = tmp_path / "data" / "habit-tracker" / "habits.sqlite3"
    result = open_repository(path, clock=clock)
    assert result.notice is None
    assert path.is_file()
    assert_usable(result.repository)
    result.repository.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_new_directory_and_file_are_private(tmp_path: Path, clock: FixedClock) -> None:
    path = tmp_path / "data" / "habits.sqlite3"
    result = open_repository(path, clock=clock)
    result.repository.close()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_an_empty_file_is_an_empty_database(db_path: Path, clock: FixedClock) -> None:
    db_path.touch()
    result = open_repository(db_path, clock=clock)
    assert result.notice is None
    assert_usable(result.repository)
    result.repository.close()
    assert directory_listing(db_path.parent) == [db_path.name]


def test_a_valid_database_opens_without_a_notice_and_keeps_its_data(
    db_path: Path, clock: FixedClock
) -> None:
    make_database(db_path)
    result = open_repository(db_path, clock=clock)
    assert result.notice is None
    assert result.repository.load() == Snapshot(areas=[Area("health", "Health", "#65a882")])
    result.repository.close()
    assert directory_listing(db_path.parent) == [db_path.name]


# ---------- Damaged files go to quarantine ----------


def damaged_files() -> dict[str, Callable[[Path], bytes]]:
    def write(content: bytes) -> Callable[[Path], bytes]:
        def build(path: Path) -> bytes:
            path.write_bytes(content)
            return content

        return build

    def corrupt_page(path: Path) -> bytes:
        data = bytearray(make_database(path, rows=400))
        data[8192 : 8192 + 300] = b"\xff" * 300
        path.write_bytes(bytes(data))
        return bytes(data)

    def truncated(path: Path) -> bytes:
        data = make_database(path, rows=400)[:6000]
        path.write_bytes(data)
        return data

    def broken_header(path: Path) -> bytes:
        data = bytearray(make_database(path, rows=50))
        data[:16] = b"NotSQLiteFormat\0"
        path.write_bytes(bytes(data))
        return bytes(data)

    def check_constraint_violated(path: Path) -> bytes:
        make_database(path)
        con = sqlite3.connect(path, autocommit=False)
        con.execute("PRAGMA ignore_check_constraints = ON")
        con.execute("INSERT INTO important_dates VALUES ('not-a-date', 'Bad row')")
        con.commit()
        con.close()
        return path.read_bytes()

    return {
        "text": write(b"This was supposed to be my database. " * 100),
        "zeros": write(b"\0" * 8192),
        "one byte": write(b"x"),
        "short": write(b"{}"),
        "random-looking": write(bytes(range(256)) * 20),
        "corrupt page": corrupt_page,
        "truncated": truncated,
        "broken header": broken_header,
        "failed integrity check": check_constraint_violated,
    }


@pytest.mark.parametrize("build", damaged_files().values(), ids=damaged_files().keys())
def test_a_damaged_file_is_quarantined_byte_for_byte_and_replaced(
    db_path: Path, clock: FixedClock, build: Callable[[Path], bytes]
) -> None:
    original = build(db_path)
    result = open_repository(db_path, clock=clock)
    quarantined = db_path.with_name(db_path.name + QUARANTINE)
    assert result.notice is not None
    assert result.notice.quarantined_to == quarantined
    assert result.notice.reason
    assert quarantined.read_bytes() == original
    assert directory_listing(db_path.parent) == sorted([db_path.name, quarantined.name])
    assert_usable(result.repository)
    result.repository.close()


def test_the_reason_says_what_was_wrong(db_path: Path, clock: FixedClock) -> None:
    db_path.write_bytes(b"not a database at all " * 30)
    result = open_repository(db_path, clock=clock)
    assert result.notice is not None
    assert "not a database" in result.notice.reason
    result.repository.close()


def test_a_failed_integrity_check_is_reported_with_its_messages(
    db_path: Path, clock: FixedClock
) -> None:
    damaged_files()["failed integrity check"](db_path)
    result = open_repository(db_path, clock=clock)
    assert result.notice is not None
    assert "integrity check failed" in result.notice.reason
    assert "CHECK constraint failed in important_dates" in result.notice.reason
    result.repository.close()


def test_the_replacement_database_is_private(db_path: Path, clock: FixedClock) -> None:
    db_path.write_bytes(b"garbage" * 50)
    result = open_repository(db_path, clock=clock)
    result.repository.close()
    if sys.platform != "win32":
        assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_quarantine_names_never_collide(db_path: Path, clock: FixedClock) -> None:
    contents = [b"first garbage" * 20, b"second garbage" * 20, b"third garbage" * 20]
    for content in contents:
        db_path.write_bytes(content)  # overwrites the empty replacement left by the last round
        open_repository(db_path, clock=clock).repository.close()
    names = [db_path.name + QUARANTINE + suffix for suffix in ("", "-2", "-3")]
    assert directory_listing(db_path.parent) == sorted([db_path.name, *names])
    for name, content in zip(names, contents, strict=True):
        assert (db_path.parent / name).read_bytes() == content


def test_quarantine_never_overwrites_an_existing_file(db_path: Path, clock: FixedClock) -> None:
    earlier = db_path.with_name(db_path.name + QUARANTINE)
    earlier.write_bytes(b"an earlier quarantine")
    db_path.write_bytes(b"garbage" * 50)
    result = open_repository(db_path, clock=clock)
    result.repository.close()
    assert earlier.read_bytes() == b"an earlier quarantine"
    assert result.notice is not None
    assert result.notice.quarantined_to == earlier.with_name(earlier.name + "-2")


def test_a_journal_left_beside_the_database_moves_with_it(
    db_path: Path, clock: FixedClock
) -> None:
    # A journal with a zeroed header (journal_mode=PERSIST leaves these) is inert:
    # SQLite does not discard it, so it is still there when the file is set aside.
    journal = db_path.with_name(db_path.name + "-journal")
    db_path.write_bytes(b"garbage" * 50)
    journal.write_bytes(b"\0" * 512)
    result = open_repository(db_path, clock=clock)
    result.repository.close()
    quarantined = db_path.with_name(db_path.name + QUARANTINE)
    assert quarantined.with_name(quarantined.name + "-journal").read_bytes() == b"\0" * 512
    assert quarantined.read_bytes() == b"garbage" * 50
    assert not journal.exists()
    assert_usable(SqliteRepository(db_path))


def test_a_write_interrupted_by_a_crash_is_rolled_back_not_quarantined(
    tmp_path: Path, clock: FixedClock
) -> None:
    source = tmp_path / "running" / "habits.sqlite3"
    source.parent.mkdir()
    make_database(source, rows=300)
    committed = source.read_bytes()
    con = sqlite3.connect(source, autocommit=False)
    con.execute("PRAGMA cache_size = 5")  # a tiny cache pushes dirty pages to the file early
    con.executemany(
        "INSERT INTO important_dates VALUES (?, ?)",
        [(f"2027-02-{(n % 28) + 1:02d}", f"never committed {n}" * 10) for n in range(3000)],
    )
    # What a crash would leave behind: the database already changed, plus its journal.
    crashed = tmp_path / "crashed" / "habits.sqlite3"
    crashed.parent.mkdir()
    journal = source.with_name(source.name + "-journal")
    shutil.copy2(source, crashed)
    shutil.copy2(journal, crashed.with_name(crashed.name + "-journal"))
    con.rollback()
    con.close()
    assert crashed.read_bytes() != committed

    result = open_repository(crashed, clock=clock)

    assert result.notice is None
    assert len(result.repository.load().important_dates) == 300
    result.repository.close()
    assert crashed.read_bytes() == committed
    assert directory_listing(crashed.parent) == [crashed.name]


def test_the_quarantine_time_comes_from_the_clock(db_path: Path) -> None:
    db_path.write_bytes(b"garbage" * 50)
    clock = FixedClock(datetime(2027, 1, 2, 3, 4, 5))
    result = open_repository(db_path, clock=clock)
    result.repository.close()
    assert result.notice is not None
    assert result.notice.quarantined_to.name == "habits.sqlite3.corrupt-20270102-030405"


def test_a_failed_move_is_a_storage_error_and_nothing_is_lost(
    db_path: Path, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path.write_bytes(b"garbage" * 50)

    def refuse(source: object, destination: object) -> None:
        raise PermissionError("read-only directory")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(StorageError, match="could not move the damaged database aside"):
        open_repository(db_path, clock=clock)
    assert db_path.read_bytes() == b"garbage" * 50


# ---------- Files that are not ours to touch ----------


@pytest.mark.parametrize("application_id", [1, 0x12345678, -5])
def test_a_database_of_another_program_is_refused_and_left_alone(
    db_path: Path, clock: FixedClock, application_id: int
) -> None:
    original = foreign_database(db_path, application_id)
    with pytest.raises(StorageError, match="another application"):
        open_repository(db_path, clock=clock)
    assert db_path.read_bytes() == original
    assert directory_listing(db_path.parent) == [db_path.name]


def test_a_database_with_tables_and_no_application_id_is_refused_and_left_alone(
    db_path: Path, clock: FixedClock
) -> None:
    original = foreign_database(db_path, application_id=0)
    with pytest.raises(StorageError, match="another application"):
        open_repository(db_path, clock=clock)
    assert db_path.read_bytes() == original
    assert directory_listing(db_path.parent) == [db_path.name]


def test_a_foreign_database_that_is_also_damaged_is_still_left_alone(
    db_path: Path, clock: FixedClock
) -> None:
    data = bytearray(foreign_database(db_path, rows=400))
    data[8192 : 8192 + 300] = b"\xff" * 300  # trash a page, keep the header
    db_path.write_bytes(bytes(data))
    before = db_path.read_bytes()
    with pytest.raises(StorageError, match="another application"):
        open_repository(db_path, clock=clock)
    assert db_path.read_bytes() == before
    assert directory_listing(db_path.parent) == [db_path.name]


def test_a_database_from_a_newer_version_is_refused_and_left_alone(
    db_path: Path, clock: FixedClock, raw_connect: RawConnect
) -> None:
    make_database(db_path)
    con = raw_connect(db_path)
    con.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION + 1}")
    con.commit()
    con.close()
    original = db_path.read_bytes()
    with pytest.raises(StorageError, match="update the application"):
        open_repository(db_path, clock=clock)
    assert db_path.read_bytes() == original
    assert directory_listing(db_path.parent) == [db_path.name]


def test_a_directory_in_place_of_the_file_is_refused(tmp_path: Path, clock: FixedClock) -> None:
    path = tmp_path / "habits.sqlite3"
    path.mkdir()
    (path / "inside").write_text("keep me")
    with pytest.raises(StorageError, match="not a file"):
        open_repository(path, clock=clock)
    assert (path / "inside").read_text() == "keep me"


def fail_to_read(monkeypatch: pytest.MonkeyPatch, message: str, code: int | None) -> None:
    error = sqlite3.DatabaseError(message)
    if code is not None:
        error.sqlite_errorcode = code

    real = schema.ensure_supported
    failed = False

    def fail(
        con: sqlite3.Connection, migrations: Sequence[schema.Migration] = schema.MIGRATIONS
    ) -> None:
        nonlocal failed
        if failed:  # the replacement database goes through the real check
            real(con, migrations)
            return
        failed = True
        raise error

    monkeypatch.setattr(schema, "ensure_supported", fail)


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("database is locked", sqlite3.SQLITE_BUSY),
        ("disk I/O error", sqlite3.SQLITE_IOERR),
        ("unable to open database file", sqlite3.SQLITE_CANTOPEN),
        ("attempt to write a readonly database", sqlite3.SQLITE_READONLY),
        ("an error without a code", None),
    ],
)
def test_an_error_that_is_not_damage_never_moves_the_file(
    db_path: Path,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    code: int | None,
) -> None:
    original = make_database(db_path)
    fail_to_read(monkeypatch, message, code)
    with pytest.raises(StorageError, match="could not read the database"):
        open_repository(db_path, clock=clock)
    assert db_path.read_bytes() == original
    assert directory_listing(db_path.parent) == [db_path.name]


@pytest.mark.parametrize("code", [sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB, 267, 282])
def test_damage_is_recognised_by_the_primary_part_of_the_error_code(
    db_path: Path, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    # 267 is SQLITE_CORRUPT_VTAB and 282 is SQLITE_NOTADB with an extra bit: extended codes.
    original = make_database(db_path)
    fail_to_read(monkeypatch, "damaged in some way", code)
    result = open_repository(db_path, clock=clock)
    result.repository.close()
    assert result.notice is not None
    assert result.notice.reason == "damaged in some way"
    assert result.notice.quarantined_to.read_bytes() == original


def test_a_notice_is_a_plain_value(db_path: Path) -> None:
    notice = RecoveryNotice(db_path, "because")
    assert (notice.quarantined_to, notice.reason) == (db_path, "because")
