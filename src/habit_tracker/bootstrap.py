"""Builds the service for a run of the application, without touching any GUI.

This is the composition root: it decides which repository to use, recovers or
creates the data file, optionally imports data saved by an older version, and
returns what the interface needs to start.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .clock import Clock
from .demo import build_demo_snapshot
from .paths import data_dir, database_path
from .seed import default_areas
from .service import HabitService
from .storage.legacy_json import backup_legacy_file, load_legacy
from .storage.memory import MemoryRepository
from .storage.recovery import RecoveryNotice, open_repository


@dataclass(frozen=True, slots=True)
class Options:
    """What the person asked for on the command line."""

    demo: bool = False
    data_dir: Path | None = None
    import_legacy: Path | None = None


@dataclass(frozen=True, slots=True)
class ImportSummary:
    """What was brought in from a file saved by an older version."""

    habits: int
    skipped: tuple[str, ...]
    backup: Path


@dataclass(frozen=True, slots=True)
class Session:
    """A ready-to-run application: the service plus what happened while preparing it."""

    service: HabitService
    demo: bool
    directory: Path | None
    recovery: RecoveryNotice | None
    imported: ImportSummary | None


def start_session(
    options: Options,
    *,
    clock: Clock,
    platform: str,
    environ: Mapping[str, str],
    home: Path,
) -> Session:
    """Open (or create) the data and build the service.

    Demo mode keeps everything in memory, so nothing is read from or written to disk.
    Raises ``StorageError`` when the data cannot be used and must be left alone.
    """
    if options.demo:
        demo_repository = MemoryRepository(build_demo_snapshot(clock.now().date()))
        return Session(HabitService(demo_repository, clock), True, None, None, None)

    directory = options.data_dir or data_dir(platform=platform, environ=environ, home=home)
    opened = open_repository(database_path(directory), clock=clock)
    repository = opened.repository
    imported = None
    if options.import_legacy is not None:
        today = clock.now().date()
        legacy = load_legacy(options.import_legacy, today=today)
        repository.import_snapshot(legacy.snapshot)
        backup = backup_legacy_file(
            options.import_legacy, source_version=legacy.source_version, today=today
        )
        imported = ImportSummary(len(legacy.snapshot.habits), legacy.skipped, backup)
    if not repository.load().areas:
        for area in default_areas():
            repository.save_area(area)
    return Session(HabitService(repository, clock), False, directory, opened.notice, imported)
