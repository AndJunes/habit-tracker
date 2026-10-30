"""Importing the JSON files of versions 1, 2 and 3, and backing the original up."""

import json
import os
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest

from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import (
    Area,
    ImportantDate,
    Measurement,
    PriorityNote,
    Reminder,
)
from habit_tracker.ports import StorageError
from habit_tracker.storage.legacy_json import LegacyImport, backup_legacy_file, load_legacy
from habit_tracker.storage.sqlite import SqliteRepository

TODAY = date(2026, 10, 30)
GENERAL = Area("general", "General", "#b4aabf", "#f1eff4")


def write_json(path: Path, content: object) -> bytes:
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    return path.read_bytes()


def legacy_habit(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": 1,
        "nombre": "Leer",
        "area": "carrera",
        "frecuencia": "diario",
        "creado": "2026-09-01",
        "completados": [],
    }
    fields.update(overrides)
    return fields


def legacy_document(version: int = 3, **sections: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": version,
        "areas": [
            {"id": "carrera", "nombre": "Carrera", "color": "#6488d8", "color_suave": "#e3eaf8"}
        ],
        "habitos": [],
        "fechas_importantes": [],
        "prioridad_manana": None,
    }
    document.update(sections)
    return document


@pytest.fixture
def legacy_file(tmp_path: Path) -> Path:
    return tmp_path / "habitos.json"


def skipped_lines(result: LegacyImport, fragment: str) -> list[str]:
    return [line for line in result.skipped if fragment in line]


# ---------- v1 ----------


def test_v1_habits_become_daily_habits_of_the_general_area(legacy_file: Path) -> None:
    write_json(
        legacy_file,
        {"Read": ["2026-10-02", "2026-10-01"], "Run": [], "Café ☕": ["2026-09-20"]},
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert result.source_version == 1
    assert result.skipped == ()
    assert result.snapshot.areas == [GENERAL]
    habits = result.snapshot.habits
    assert [(h.id, h.name, h.area_id, h.frequency) for h in habits] == [
        (1, "Read", "general", Daily()),
        (2, "Run", "general", Daily()),
        (3, "Café ☕", "general", Daily()),
    ]
    assert habits[0].completions == {date(2026, 10, 1): None, date(2026, 10, 2): None}
    assert [h.start for h in habits] == [date(2026, 10, 1), TODAY, date(2026, 9, 20)]
    assert result.snapshot.important_dates == []
    assert result.snapshot.priority is None


def test_v1_ids_follow_the_position_in_the_file_even_when_a_habit_is_skipped(
    legacy_file: Path,
) -> None:
    write_json(legacy_file, {"Read": ["2026-10-01"], "Broken": "not a list", "Run": []})
    result = load_legacy(legacy_file, today=TODAY)
    assert [(h.id, h.name) for h in result.snapshot.habits] == [(1, "Read"), (3, "Run")]
    assert skipped_lines(result, "Broken")


def test_v1_invalid_days_are_dropped_and_counted(legacy_file: Path) -> None:
    write_json(legacy_file, {"Read": ["2026-10-01", "yesterday", "2026-02-30", 5]})
    result = load_legacy(legacy_file, today=TODAY)
    assert list(result.snapshot.habits[0].completions) == [date(2026, 10, 1)]
    assert len(skipped_lines(result, "ignored 3 completion date(s)")) == 1


def test_an_empty_v1_file_still_gets_the_general_area(legacy_file: Path) -> None:
    write_json(legacy_file, {})
    result = load_legacy(legacy_file, today=TODAY)
    assert result.source_version == 1
    assert result.snapshot.areas == [GENERAL]
    assert result.snapshot.habits == []


# ---------- v2 ----------


def test_v2_quota_without_a_type_is_still_a_quota(legacy_file: Path) -> None:
    write_json(
        legacy_file,
        legacy_document(
            2,
            habitos=[
                legacy_habit(
                    frecuencia={"veces": 3, "por": "semana", "preferidos": ["lunes", "viernes"]},
                    completados=["2026-09-01", "2026-09-03"],
                ),
                legacy_habit(id=2, nombre="Pagar", frecuencia={"veces": 1, "por": "mes"}),
            ],
            fechas_importantes=[{"fecha": "2026-11-03", "titulo": "Parcial"}],
            prioridad_manana={"fecha": "2026-10-31", "texto": "Entregar el informe"},
        ),
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert result.source_version == 2
    assert result.skipped == ()
    first, second = result.snapshot.habits
    assert first.frequency == Quota(3, Period.WEEK, frozenset({Weekday.MONDAY, Weekday.FRIDAY}))
    assert first.completions == {date(2026, 9, 1): None, date(2026, 9, 3): None}
    assert second.frequency == Quota(1, Period.MONTH)
    assert (first.description, first.notes, first.end) == ("", "", None)
    assert (first.measurement, first.reminder) == (None, None)
    assert result.snapshot.important_dates == [ImportantDate(date(2026, 11, 3), "Parcial")]
    assert result.snapshot.priority == PriorityNote(date(2026, 10, 31), "Entregar el informe")


# ---------- v3 ----------


def full_v3_document() -> dict[str, Any]:
    return legacy_document(
        3,
        areas=[
            {"id": "carrera", "nombre": "Carrera", "color": "#6488d8", "color_suave": "#e3eaf8"},
            {"id": "salud", "nombre": "Salud", "color": "#65a882"},
        ],
        habitos=[
            legacy_habit(
                id=1,
                nombre="Leer",
                frecuencia="diario",
                descripcion="Para desconectar",
                notas="Antes de dormir",
                fin="2026-12-31",
                icono="libro",
                medicion={
                    "tipo": "cantidad",
                    "meta": 10,
                    "unidad": "páginas",
                    "minima": 5,
                    "ideal": 15.5,
                },
                completados=["2026-09-01", "2026-09-02"],
                registros={"2026-09-02": 12, "2026-09-03": 8.5},
            ),
            legacy_habit(
                id=2,
                nombre="Gimnasio",
                area="salud",
                frecuencia=["lunes", "miercoles", "sabado"],
            ),
            legacy_habit(
                id=3,
                nombre="Correr",
                area="salud",
                frecuencia={
                    "tipo": "cupo",
                    "veces": 10,
                    "por": "mes",
                    "preferidos": ["domingo"],
                },
            ),
            legacy_habit(
                id=4,
                nombre="Pagar la renta",
                frecuencia={"tipo": "fechas", "fechas": ["2026-11-05", "2026-10-05"]},
            ),
            legacy_habit(
                id=5,
                nombre="Meditar",
                area="salud",
                frecuencia={"tipo": "intervalo", "cada": 2, "unidad": "semanas"},
                medicion={"tipo": "duracion", "meta": 15, "unidad": "min", "minima": None},
                recordatorio={"hora": "07:30", "dias": ["lunes", "jueves"]},
            ),
            legacy_habit(
                id=6,
                nombre="Revisar presupuesto",
                frecuencia={"tipo": "intervalo", "cada": 1, "unidad": "meses"},
                recordatorio={"hora": "20:00", "dias": []},
            ),
            legacy_habit(
                id=7,
                nombre="Estirar",
                frecuencia={"tipo": "intervalo", "cada": 3, "unidad": "dias"},
                medicion=None,
                recordatorio=None,
            ),
        ],
        fechas_importantes=[
            {"fecha": "2026-11-20", "titulo": "Entrega"},
            {"fecha": "2026-11-03", "titulo": "Parcial"},
        ],
        prioridad_manana={"fecha": "2026-10-31", "texto": "Terminar el informe"},
    )


def test_v3_imports_every_kind_of_frequency_and_field(legacy_file: Path) -> None:
    write_json(legacy_file, full_v3_document())
    result = load_legacy(legacy_file, today=TODAY)
    assert result.source_version == 3
    assert result.skipped == ()
    assert result.snapshot.areas == [
        Area("carrera", "Carrera", "#6488d8", "#e3eaf8"),
        Area("salud", "Salud", "#65a882"),
    ]
    by_id = {habit.id: habit for habit in result.snapshot.habits}
    assert len(by_id) == 7

    read = by_id[1]
    assert (read.name, read.area_id, read.start, read.end) == (
        "Leer",
        "carrera",
        date(2026, 9, 1),
        date(2026, 12, 31),
    )
    assert (read.description, read.notes) == ("Para desconectar", "Antes de dormir")
    assert read.frequency == Daily()
    assert read.measurement == Measurement(MeasurementKind.QUANTITY, 10, "páginas", 5, 15.5)
    assert read.completions == {
        date(2026, 9, 1): None,
        date(2026, 9, 2): 12.0,
        date(2026, 9, 3): 8.5,
    }

    assert by_id[2].frequency == Weekdays(
        frozenset({Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.SATURDAY})
    )
    assert by_id[3].frequency == Quota(10, Period.MONTH, frozenset({Weekday.SUNDAY}))
    assert by_id[4].frequency == FixedDates((date(2026, 10, 5), date(2026, 11, 5)))
    assert by_id[5].frequency == Interval(2, IntervalUnit.WEEKS)
    assert by_id[5].measurement == Measurement(MeasurementKind.DURATION, 15, "min")
    assert by_id[5].reminder == Reminder(
        time(7, 30), frozenset({Weekday.MONDAY, Weekday.THURSDAY})
    )
    assert by_id[6].frequency == Interval(1, IntervalUnit.MONTHS)
    assert by_id[6].reminder == Reminder(time(20, 0))
    assert by_id[7].frequency == Interval(3, IntervalUnit.DAYS)
    assert (by_id[7].measurement, by_id[7].reminder) == (None, None)

    assert result.snapshot.important_dates == [
        ImportantDate(date(2026, 11, 3), "Parcial"),
        ImportantDate(date(2026, 11, 20), "Entrega"),
    ]
    assert result.snapshot.priority == PriorityNote(date(2026, 10, 31), "Terminar el informe")


def test_a_recorded_value_wins_over_a_plain_completion_of_the_same_day(
    legacy_file: Path,
) -> None:
    write_json(
        legacy_file,
        legacy_document(
            habitos=[
                legacy_habit(
                    completados=["2026-09-01"],
                    registros={"2026-09-01": 3.5, "2026-09-02": 0, "2026-09-03": None},
                )
            ]
        ),
    )
    habit = load_legacy(legacy_file, today=TODAY).snapshot.habits[0]
    assert habit.completions == {
        date(2026, 9, 1): 3.5,
        date(2026, 9, 2): 0.0,
        date(2026, 9, 3): None,
    }


def test_habits_and_important_dates_come_out_in_the_order_the_repository_returns_them(
    legacy_file: Path,
) -> None:
    write_json(
        legacy_file,
        legacy_document(
            habitos=[legacy_habit(id=9, nombre="Nine"), legacy_habit(id=3, nombre="Three")],
            fechas_importantes=[
                {"fecha": "2026-12-01", "titulo": "B"},
                {"fecha": "2026-11-01", "titulo": "Z"},
                {"fecha": "2026-11-01", "titulo": "A"},
            ],
        ),
    )
    snapshot = load_legacy(legacy_file, today=TODAY).snapshot
    assert [habit.id for habit in snapshot.habits] == [3, 9]
    assert [(item.day.month, item.title) for item in snapshot.important_dates] == [
        (11, "A"),
        (11, "Z"),
        (12, "B"),
    ]


def test_an_empty_end_date_means_no_end(legacy_file: Path) -> None:
    write_json(legacy_file, legacy_document(habitos=[legacy_habit(fin="")]))
    assert load_legacy(legacy_file, today=TODAY).snapshot.habits[0].end is None


def test_a_file_with_only_a_version_is_an_empty_snapshot(legacy_file: Path) -> None:
    write_json(legacy_file, {"version": 3})
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.areas == []
    assert result.snapshot.habits == []
    assert result.skipped == ()


# ---------- Entities that cannot be imported ----------


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"creado": "2026-13-40"}, "'creado' is not a YYYY-MM-DD date"),
        ({"creado": None}, "'creado' is not a YYYY-MM-DD date"),
        ({"nombre": "   "}, "'nombre' is missing or empty"),
        ({"id": "one"}, "'id' is not a usable integer"),
        ({"id": True}, "'id' is not a usable integer"),
        ({"id": 2**70}, "'id' is not a usable integer"),
        ({"fin": "soon"}, "'fin' is not a YYYY-MM-DD date"),
        ({"fin": "2026-08-31"}, "end_before_start"),
        ({"frecuencia": ["lunes", "funday"]}, "unknown weekday"),
        ({"frecuencia": []}, "weekdays_required"),
        ({"frecuencia": "semanal"}, "the frequency is not a JSON object"),
        ({"frecuencia": {"tipo": "anual"}}, "unknown frequency type"),
        ({"frecuencia": {"tipo": "cupo", "veces": 9, "por": "semana"}}, "quota_out_of_range"),
        ({"frecuencia": {"tipo": "cupo", "veces": 3, "por": "dia"}}, "unknown period"),
        ({"frecuencia": {"tipo": "cupo", "veces": "3", "por": "mes"}}, "'veces' is not a usable"),
        (
            {"frecuencia": {"tipo": "fechas", "fechas": ["2026-11-05", "mañana"]}},
            "'fechas' is not a YYYY",
        ),
        ({"frecuencia": {"tipo": "fechas", "fechas": []}}, "dates_required"),
        ({"frecuencia": {"tipo": "intervalo", "cada": 0, "unidad": "dias"}}, "interval_invalid"),
        ({"frecuencia": {"tipo": "intervalo", "cada": 2, "unidad": "anios"}}, "interval unit"),
        ({"medicion": {"tipo": "peso", "meta": 1, "unidad": "kg"}}, "unknown measurement type"),
        ({"medicion": {"tipo": "cantidad", "meta": -1, "unidad": "kg"}}, "goal_invalid"),
        (
            {"medicion": {"tipo": "cantidad", "meta": True, "unidad": "kg"}},
            "'goal' is not a number",
        ),
        ({"medicion": {"tipo": "cantidad", "meta": 1, "unidad": ""}}, "'unidad' is missing"),
        (
            {"medicion": {"tipo": "cantidad", "meta": 1, "unidad": "kg", "minima": 5, "ideal": 2}},
            "bounds_invalid",
        ),
        ({"medicion": "mucho"}, "the measurement is not a JSON object"),
        ({"recordatorio": {"hora": "25:00", "dias": []}}, "'hora' is not an HH:MM time"),
        ({"recordatorio": {"hora": "7:05", "dias": []}}, "'hora' is not an HH:MM time"),
        ({"recordatorio": {"hora": "07:05", "dias": ["pronto"]}}, "unknown weekday"),
        ({"completados": "2026-09-01"}, "'completados' is not a list"),
        ({"registros": ["2026-09-01"]}, "'registros' is not a JSON object"),
        ({"descripcion": 5}, "'descripcion' is not text"),
    ],
    ids=repr,
)
def test_a_habit_with_invalid_data_is_skipped_and_described(
    legacy_file: Path, overrides: dict[str, Any], fragment: str
) -> None:
    write_json(
        legacy_file,
        legacy_document(
            habitos=[
                legacy_habit(id=10, nombre="Healthy one"),
                legacy_habit(**{"id": 11, "nombre": "The broken one", **overrides}),
                legacy_habit(id=12, nombre="Healthy too"),
            ]
        ),
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert [habit.name for habit in result.snapshot.habits] == ["Healthy one", "Healthy too"]
    assert len(result.skipped) == 1
    assert fragment in result.skipped[0]
    assert result.skipped[0].startswith("habit #2")


def test_a_habit_that_is_not_an_object_is_skipped(legacy_file: Path) -> None:
    write_json(legacy_file, legacy_document(habitos=["oops", None, legacy_habit()]))
    result = load_legacy(legacy_file, today=TODAY)
    assert len(result.snapshot.habits) == 1
    assert result.skipped == (
        "habit #1: the habit is not a JSON object",
        "habit #2: the habit is not a JSON object",
    )


def test_a_habit_with_a_repeated_id_is_skipped(legacy_file: Path) -> None:
    write_json(
        legacy_file,
        legacy_document(habitos=[legacy_habit(), legacy_habit(nombre="Same id, other name")]),
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert [habit.name for habit in result.snapshot.habits] == ["Leer"]
    assert skipped_lines(result, "duplicate id 1")


def test_invalid_completions_are_dropped_but_the_habit_is_kept(legacy_file: Path) -> None:
    write_json(
        legacy_file,
        legacy_document(
            habitos=[
                legacy_habit(
                    completados=["2026-09-01", "nope", "2026-02-30", 7],
                    registros={"bad": 1, "2026-09-02": "a lot", "2026-09-03": -4, "2026-09-04": 2},
                )
            ]
        ),
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.habits[0].completions == {
        date(2026, 9, 1): None,
        date(2026, 9, 2): None,
        date(2026, 9, 3): None,
        date(2026, 9, 4): 2.0,
    }
    assert len(result.skipped) == 2
    assert skipped_lines(result, "ignored 4 completion date(s)")
    assert skipped_lines(result, "ignored 2 recorded value(s)")


def test_a_habit_in_an_unknown_area_is_kept_in_the_general_area(legacy_file: Path) -> None:
    write_json(
        legacy_file,
        legacy_document(
            habitos=[
                legacy_habit(id=1, area="carrera"),
                legacy_habit(id=2, nombre="Orphan", area="gimnasio", completados=["2026-09-01"]),
                legacy_habit(id=3, nombre="Another", area="gimnasio"),
            ]
        ),
    )
    result = load_legacy(legacy_file, today=TODAY)
    habits = {habit.id: habit for habit in result.snapshot.habits}
    assert (habits[1].area_id, habits[2].area_id, habits[3].area_id) == (
        "carrera",
        "general",
        "general",
    )
    assert habits[2].completions == {date(2026, 9, 1): None}
    assert [area.id for area in result.snapshot.areas] == ["carrera", "general"]
    assert result.snapshot.areas[1] == GENERAL
    assert len(skipped_lines(result, "unknown area 'gimnasio', moved to 'general'")) == 2


def test_an_existing_general_area_is_not_replaced(legacy_file: Path) -> None:
    mine = {"id": "general", "nombre": "Mi general", "color": "#123456"}
    write_json(
        legacy_file,
        legacy_document(
            areas=[mine],
            habitos=[legacy_habit(area="gimnasio")],
        ),
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.areas == [Area("general", "Mi general", "#123456")]
    assert result.snapshot.habits[0].area_id == "general"


@pytest.mark.parametrize(
    "area",
    [
        {"nombre": "No id", "color": "#000000"},
        {"id": "x", "nombre": "", "color": "#000000"},
        {"id": "x", "nombre": "No color"},
        {"id": "x", "nombre": "Soft color", "color": "#000000", "color_suave": 5},
        "area",
    ],
    ids=repr,
)
def test_an_invalid_area_is_skipped(legacy_file: Path, area: object) -> None:
    good = {"id": "carrera", "nombre": "Carrera", "color": "#6488d8"}
    write_json(legacy_file, legacy_document(areas=[good, area]))
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.areas == [Area("carrera", "Carrera", "#6488d8")]
    assert len(result.skipped) == 1
    assert result.skipped[0].startswith("area #2")


def test_a_repeated_area_id_keeps_the_first_area(legacy_file: Path) -> None:
    first = {"id": "a", "nombre": "First", "color": "#111111"}
    second = {"id": "a", "nombre": "Second", "color": "#222222"}
    write_json(legacy_file, legacy_document(areas=[first, second]))
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.areas == [Area("a", "First", "#111111")]
    assert skipped_lines(result, "duplicate id 'a'")


def test_invalid_important_dates_are_skipped_and_repeated_ones_merged(legacy_file: Path) -> None:
    write_json(
        legacy_file,
        legacy_document(
            fechas_importantes=[
                {"fecha": "2026-11-03", "titulo": "Parcial"},
                {"fecha": "2026-11-03", "titulo": "Parcial"},
                {"fecha": "pronto", "titulo": "Bad day"},
                {"fecha": "2026-11-04", "titulo": ""},
                {"titulo": "No day"},
                7,
            ]
        ),
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.important_dates == [ImportantDate(date(2026, 11, 3), "Parcial")]
    assert len(result.skipped) == 4
    assert all(line.startswith("important date #") for line in result.skipped)


@pytest.mark.parametrize(
    "note",
    [{"fecha": "mañana", "texto": "x"}, {"fecha": "2026-10-31", "texto": 5}, {"texto": "x"}, "x"],
    ids=repr,
)
def test_an_invalid_priority_note_is_skipped(legacy_file: Path, note: object) -> None:
    write_json(legacy_file, legacy_document(prioridad_manana=note))
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.priority is None
    assert len(skipped_lines(result, "priority note")) == 1


def test_a_blank_priority_note_is_no_note_and_not_an_error(legacy_file: Path) -> None:
    write_json(
        legacy_file, legacy_document(prioridad_manana={"fecha": "2026-10-31", "texto": " "})
    )
    result = load_legacy(legacy_file, today=TODAY)
    assert result.snapshot.priority is None
    assert result.skipped == ()


@pytest.mark.parametrize("section", ["areas", "habitos", "fechas_importantes"])
def test_a_section_that_is_not_a_list_is_reported_and_ignored(
    legacy_file: Path, section: str
) -> None:
    document = legacy_document()
    document[section] = {"unexpected": "object"}
    write_json(legacy_file, document)
    result = load_legacy(legacy_file, today=TODAY)
    assert len(result.skipped) == 1
    assert "expected a list" in result.skipped[0]


# ---------- Files that cannot be read at all ----------


def test_a_missing_file_is_a_storage_error(legacy_file: Path) -> None:
    with pytest.raises(StorageError, match="could not read"):
        load_legacy(legacy_file, today=TODAY)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"{not json",
        b'{"version": 3,',
        b"\xff\xfe\x00bad",
        b"nan",
        b"[]",
        b'"text"',
        b"3",
        b"null",
    ],
    ids=repr,
)
def test_a_file_that_is_not_a_json_object_is_a_storage_error(
    legacy_file: Path, content: bytes
) -> None:
    legacy_file.write_bytes(content)
    with pytest.raises(StorageError):
        load_legacy(legacy_file, today=TODAY)
    assert legacy_file.read_bytes() == content


def test_deeply_nested_json_is_a_storage_error(legacy_file: Path) -> None:
    legacy_file.write_text("[" * 100_000 + "]" * 100_000)
    with pytest.raises(StorageError):
        load_legacy(legacy_file, today=TODAY)


@pytest.mark.parametrize("version", [4, 99, 3.5, "3", None, True, 1, 0, -2])
def test_an_unsupported_version_is_a_storage_error(legacy_file: Path, version: object) -> None:
    content = write_json(legacy_file, legacy_document(version=version))  # type: ignore[arg-type]
    with pytest.raises(StorageError, match="version"):
        load_legacy(legacy_file, today=TODAY)
    assert legacy_file.read_bytes() == content


def test_a_newer_version_says_so(legacy_file: Path) -> None:
    write_json(legacy_file, legacy_document(version=4))
    with pytest.raises(StorageError, match="newer than the last one"):
        load_legacy(legacy_file, today=TODAY)


def test_reading_never_modifies_the_original(legacy_file: Path) -> None:
    original = write_json(legacy_file, full_v3_document())
    stat_before = legacy_file.stat()
    load_legacy(legacy_file, today=TODAY)
    assert legacy_file.read_bytes() == original
    assert legacy_file.stat().st_mtime_ns == stat_before.st_mtime_ns
    assert sorted(path.name for path in legacy_file.parent.iterdir()) == [legacy_file.name]


# ---------- Backup ----------


def test_the_backup_is_a_byte_for_byte_copy_with_the_expected_name(legacy_file: Path) -> None:
    original = write_json(legacy_file, full_v3_document())
    os.utime(legacy_file, (1_700_000_000, 1_700_000_000))
    backup = backup_legacy_file(legacy_file, source_version=3, today=TODAY)
    assert backup == legacy_file.with_name("habitos.json.bak-v3-20261030")
    assert backup.read_bytes() == original
    assert legacy_file.read_bytes() == original
    assert int(backup.stat().st_mtime) == 1_700_000_000
    assert sorted(path.name for path in legacy_file.parent.iterdir()) == [
        "habitos.json",
        "habitos.json.bak-v3-20261030",
    ]


def test_the_backup_name_carries_the_version_and_the_date(legacy_file: Path) -> None:
    write_json(legacy_file, {"Read": []})
    backup = backup_legacy_file(legacy_file, source_version=1, today=date(2027, 1, 5))
    assert backup.name == "habitos.json.bak-v1-20270105"


def test_a_backup_never_overwrites_an_earlier_one(legacy_file: Path) -> None:
    write_json(legacy_file, legacy_document())
    earlier = legacy_file.with_name("habitos.json.bak-v3-20261030")
    earlier.write_bytes(b"the first backup")
    second = backup_legacy_file(legacy_file, source_version=3, today=TODAY)
    third = backup_legacy_file(legacy_file, source_version=3, today=TODAY)
    assert second.name == "habitos.json.bak-v3-20261030-2"
    assert third.name == "habitos.json.bak-v3-20261030-3"
    assert earlier.read_bytes() == b"the first backup"
    assert second.read_bytes() == legacy_file.read_bytes() == third.read_bytes()


def test_backing_up_a_missing_file_is_a_storage_error(legacy_file: Path) -> None:
    with pytest.raises(StorageError, match="could not back up"):
        backup_legacy_file(legacy_file, source_version=3, today=TODAY)


# ---------- End to end ----------


@pytest.mark.parametrize("version", [1, 2, 3])
def test_every_version_can_be_imported_into_the_database(
    tmp_path: Path, legacy_file: Path, version: int
) -> None:
    if version == 1:
        write_json(legacy_file, {"Read": ["2026-10-01"], "Run": []})
    elif version == 2:
        write_json(legacy_file, legacy_document(2, habitos=[legacy_habit()]))
    else:
        write_json(legacy_file, full_v3_document())
    result = load_legacy(legacy_file, today=TODAY)
    with SqliteRepository(tmp_path / "habits.sqlite3") as repository:
        repository.import_snapshot(result.snapshot)
        assert repository.load() == result.snapshot


def test_a_snapshot_with_rescued_habits_can_be_stored(tmp_path: Path, legacy_file: Path) -> None:
    write_json(legacy_file, legacy_document(habitos=[legacy_habit(area="gone")]))
    result = load_legacy(legacy_file, today=TODAY)
    with SqliteRepository(tmp_path / "habits.sqlite3") as repository:
        repository.import_snapshot(result.snapshot)
        assert [habit.area_id for habit in repository.load().habits] == ["general"]
