"""Opening the database file, including the case where it is damaged.

A file that SQLite cannot read as a database is never deleted or overwritten. It
is moved next to where it was, under a name that says when it was set aside, and
a fresh database takes its place; the person is told through a
:class:`RecoveryNotice`.

SQLite's own guidance (atomic commit, section 9) is that a journal belongs to its
database file and must not be deleted by hand. Nothing here deletes one: looking at
the file lets SQLite itself roll back a hot journal, which is how an interrupted
write is repaired, and a journal still there afterwards moves together with its
database (journal first: SQLite discards a journal it finds next to a missing one).

Files that are healthy but not usable here (another program's database, or one
from a newer version of this application) are left exactly as they are.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..clock import Clock
from ..paths import ensure_private_directory
from ..ports import StorageError
from . import schema
from .sqlite import SqliteRepository

# No database is smaller than its 100-byte header, but SQLite itself accepts a
# one-byte file as an empty database and would write over it.
_HEADER_SIZE = 100
_JOURNAL_SUFFIX = "-journal"
_DAMAGE_CODES = frozenset({sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB})
_PRIMARY_CODE_MASK = 0xFF


@dataclass(frozen=True, slots=True)
class RecoveryNotice:
    """What happened to a damaged database, for the interface to tell the person."""

    quarantined_to: Path
    reason: str


@dataclass(frozen=True, slots=True)
class OpenResult:
    repository: SqliteRepository
    notice: RecoveryNotice | None


def open_repository(path: Path, *, clock: Clock) -> OpenResult:
    """Open the database at ``path``, creating it, or replacing it if it is damaged.

    Raises ``StorageError`` when the file cannot be used and must not be touched:
    it is another program's database, it comes from a newer version of the
    application, or SQLite failed for a reason other than damage (a lock, a
    permission, an I/O error).
    """
    if not path.exists():
        try:
            ensure_private_directory(path.parent)
        except OSError as error:
            raise StorageError(f"could not create the directory {path.parent}: {error}") from error
        return OpenResult(SqliteRepository(path), None)
    reason = _find_damage(path)
    if reason is None:
        return OpenResult(SqliteRepository(path), None)
    quarantined_to = _quarantine(path, clock.now())
    return OpenResult(SqliteRepository(path), RecoveryNotice(quarantined_to, reason))


def _find_damage(path: Path) -> str | None:
    """Why the file is not a valid database, or ``None`` when it is one."""
    if not path.is_file():
        raise StorageError(f"{path} exists but is not a file")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise StorageError(f"could not read {path}: {error}") from error
    if 0 < size < _HEADER_SIZE:
        return f"the file has only {size} bytes, less than a database header"
    try:
        con = sqlite3.connect(path, autocommit=False)
    except sqlite3.Error as error:
        raise StorageError(f"could not open the database {path}: {error}") from error
    try:
        schema.ensure_supported(con)
        results = [row[0] for row in con.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as error:
        if _is_damage(error):
            return str(error)
        raise StorageError(f"could not read the database {path}: {error}") from error
    finally:
        con.close()
    if results == ["ok"]:
        return None
    return "the integrity check failed: " + "; ".join(results[:3])


def _is_damage(error: sqlite3.Error) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    return code is not None and code & _PRIMARY_CODE_MASK in _DAMAGE_CODES


def _quarantine(path: Path, moment: datetime) -> Path:
    """Move the file, and its journal if it has one, to ``<name>.corrupt-YYYYMMDD-HHMMSS``."""
    base = f"{path.name}.corrupt-{moment:%Y%m%d-%H%M%S}"
    destination = path.with_name(base)
    attempt = 1
    while os.path.lexists(destination) or os.path.lexists(_journal(destination)):
        attempt += 1
        destination = path.with_name(f"{base}-{attempt}")
    try:
        if _journal(path).exists():
            os.replace(_journal(path), _journal(destination))
        os.replace(path, destination)
    except OSError as error:
        raise StorageError(f"could not move the damaged database aside: {error}") from error
    return destination


def _journal(path: Path) -> Path:
    return path.with_name(path.name + _JOURNAL_SUFFIX)
