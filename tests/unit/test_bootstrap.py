import json
from datetime import datetime
from pathlib import Path

import pytest

from habit_tracker.bootstrap import Options, Session, start_session
from habit_tracker.clock import FixedClock
from habit_tracker.domain.frequency import Daily
from habit_tracker.paths import database_path
from habit_tracker.ports import StorageError
from habit_tracker.seed import default_areas

NOW = datetime(2026, 10, 30, 9, 30)


def start(
    tmp_path: Path,
    *,
    demo: bool = False,
    data_dir: Path | None = None,
    import_legacy: Path | None = None,
) -> Session:
    return start_session(
        Options(demo=demo, data_dir=data_dir, import_legacy=import_legacy),
        clock=FixedClock(NOW),
        platform="darwin",
        environ={},
        home=tmp_path / "home",
    )


def write_legacy_file(path: Path) -> bytes:
    data = {
        "version": 3,
        "areas": [{"id": "salud", "nombre": "Salud", "color": "#65a882", "color_suave": ""}],
        "habitos": [
            {
                "id": 1,
                "nombre": "Caminar",
                "area": "salud",
                "frecuencia": "diario",
                "creado": "2026-10-01",
                "completados": ["2026-10-02", "2026-10-03"],
            },
            {
                "id": 2,
                "nombre": "Roto",
                "area": "salud",
                "frecuencia": "cada tanto",
                "creado": "2026-10-01",
                "completados": [],
            },
        ],
        "fechas_importantes": [],
        "prioridad_manana": None,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path.read_bytes()


def test_demo_mode_works_in_memory_and_writes_nothing(tmp_path: Path) -> None:
    session = start(tmp_path, demo=True, data_dir=tmp_path / "data")

    assert session.demo
    assert len(session.service.habits()) == 6
    assert session.service.today() == NOW.date()
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "home").exists()


def test_a_first_run_creates_the_database_with_the_default_areas(tmp_path: Path) -> None:
    directory = tmp_path / "data"

    session = start(tmp_path, data_dir=directory)

    assert database_path(directory).is_file()
    assert session.directory == directory
    assert session.service.areas() == tuple(default_areas())
    assert session.service.habits() == ()
    assert session.recovery is None
    assert session.imported is None


def test_without_a_data_dir_the_platform_directory_is_used(tmp_path: Path) -> None:
    session = start(tmp_path)

    expected = tmp_path / "home" / "Library" / "Application Support" / "com.habittracker.app"
    assert session.directory == expected
    assert database_path(expected).is_file()


def test_data_saved_in_one_run_is_there_in_the_next(tmp_path: Path) -> None:
    first = start(tmp_path, data_dir=tmp_path / "data")
    first.service.add_habit(name="Read", area_id="salud", frequency=Daily())

    second = start(tmp_path, data_dir=tmp_path / "data")

    assert [habit.name for habit in second.service.habits()] == ["Read"]
    assert len(second.service.areas()) == len(default_areas())


def test_a_damaged_database_is_set_aside_and_reported(tmp_path: Path) -> None:
    directory = tmp_path / "data"
    directory.mkdir()
    damaged = b"this is not a database " * 20
    database_path(directory).write_bytes(damaged)

    session = start(tmp_path, data_dir=directory)

    assert session.recovery is not None
    assert session.recovery.quarantined_to.read_bytes() == damaged
    assert session.service.habits() == ()
    assert len(session.service.areas()) == len(default_areas())


def test_importing_an_old_file_brings_its_data_and_keeps_the_original(tmp_path: Path) -> None:
    legacy = tmp_path / "habitos.json"
    original = write_legacy_file(legacy)

    session = start(tmp_path, data_dir=tmp_path / "data", import_legacy=legacy)

    assert session.imported is not None
    assert session.imported.habits == 1
    assert session.imported.skipped
    assert session.imported.backup.read_bytes() == original
    assert legacy.read_bytes() == original
    (habit,) = session.service.habits()
    assert habit.name == "Caminar"
    assert len(habit.completions) == 2
    assert [area.id for area in session.service.areas()] == ["salud"]


def test_importing_into_a_database_that_already_has_data_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "data"
    start(tmp_path, data_dir=directory).service.add_habit(
        name="Read", area_id="salud", frequency=Daily()
    )
    legacy = tmp_path / "habitos.json"
    write_legacy_file(legacy)

    with pytest.raises(StorageError):
        start(tmp_path, data_dir=directory, import_legacy=legacy)

    assert [habit.name for habit in start(tmp_path, data_dir=directory).service.habits()] == [
        "Read"
    ]


def test_a_file_that_is_not_json_cannot_be_imported(tmp_path: Path) -> None:
    legacy = tmp_path / "habitos.json"
    legacy.write_text("not json", encoding="utf-8")

    with pytest.raises(StorageError):
        start(tmp_path, data_dir=tmp_path / "data", import_legacy=legacy)
