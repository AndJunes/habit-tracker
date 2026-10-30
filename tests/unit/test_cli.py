import json
from datetime import datetime
from pathlib import Path

from habit_tracker.bootstrap import Options, Session, start_session
from habit_tracker.cli import PROGRAM, build_parser, startup_messages
from habit_tracker.clock import FixedClock
from habit_tracker.paths import database_path

NOW = datetime(2026, 10, 30, 9, 30)


def start(tmp_path: Path, options: Options) -> Session:
    return start_session(
        options,
        clock=FixedClock(NOW),
        platform="darwin",
        environ={},
        home=tmp_path / "home",
    )


def test_the_parser_defaults_mean_a_normal_run() -> None:
    args = build_parser().parse_args([])

    assert args.demo is False
    assert args.data_dir is None
    assert args.import_legacy is None
    assert build_parser().prog == PROGRAM


def test_the_parser_reads_every_option() -> None:
    args = build_parser().parse_args(
        ["--demo", "--data-dir", "/tmp/data", "--import-legacy", "/tmp/habitos.json"]
    )

    assert args.demo is True
    assert args.data_dir == Path("/tmp/data")
    assert args.import_legacy == Path("/tmp/habitos.json")


def test_a_normal_start_has_nothing_to_tell(tmp_path: Path) -> None:
    session = start(tmp_path, Options(data_dir=tmp_path / "data"))

    assert startup_messages(session) == ()


def test_a_damaged_database_is_explained_with_where_it_went(tmp_path: Path) -> None:
    directory = tmp_path / "data"
    directory.mkdir()
    database_path(directory).write_bytes(b"this is not a database " * 20)

    session = start(tmp_path, Options(data_dir=directory))

    (message,) = startup_messages(session)
    assert session.recovery is not None
    assert str(session.recovery.quarantined_to) in message
    assert "dañado" in message


def test_an_import_reports_how_many_habits_came_in_and_where_the_backup_is(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "habitos.json"
    legacy.write_text(
        json.dumps(
            {
                "version": 3,
                "areas": [{"id": "salud", "nombre": "Salud", "color": "#65a882"}],
                "habitos": [
                    {
                        "id": 1,
                        "nombre": "Caminar",
                        "area": "salud",
                        "frecuencia": "diario",
                        "creado": "2026-10-01",
                        "completados": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    session = start(tmp_path, Options(data_dir=tmp_path / "data", import_legacy=legacy))

    (message,) = startup_messages(session)
    assert session.imported is not None
    assert "1 hábito " in message
    assert str(session.imported.backup) in message
    assert "no se pudieron importar" not in message
