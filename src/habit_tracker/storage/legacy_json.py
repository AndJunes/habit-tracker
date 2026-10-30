"""Importer for the JSON files written by versions 1, 2 and 3 of the application.

* v1 has no ``version`` key: ``{"habit name": ["2026-10-01", ...]}``. Every habit
  becomes a daily habit in a ``general`` area.
* v2 and v3 are ``{"version", "areas", "habitos", "fechas_importantes",
  "prioridad_manana"}``. v3 added a description, notes, an end date, a measurement,
  recorded values and a reminder to each habit; a v2 file simply lacks them. A
  frequency given as an object without ``tipo`` is a quota (the v2 form).

The keys and the weekday names are Spanish, as the old versions wrote them. A day
is done when it is in ``completados`` or a key of ``registros``; the recorded
value, when there is one, becomes the completion's value. The habit icon is
dropped: the new version has none.

One bad entity never stops the import. A habit, area or date that cannot be read
is left out and described in ``LegacyImport.skipped``; so is every habit that had
to be adjusted. The original file is only ever read: :func:`backup_legacy_file`
copies it first.

The snapshot lists habits by id and important dates by day, the order the
repository returns them in; areas keep the order of the file.
"""

import json
import math
import os
import shutil
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Any

from ..domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from ..domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from ..domain.models import (
    Area,
    Habit,
    ImportantDate,
    Measurement,
    PriorityNote,
    Reminder,
    Snapshot,
)
from ..ports import StorageError
from .serialization import parse_iso_date, parse_iso_time

LATEST_VERSION = 3

GENERAL_AREA_ID = "general"

_INT64_LIMIT = 2**63

_WEEKDAYS = {
    "lunes": Weekday.MONDAY,
    "martes": Weekday.TUESDAY,
    "miercoles": Weekday.WEDNESDAY,
    "jueves": Weekday.THURSDAY,
    "viernes": Weekday.FRIDAY,
    "sabado": Weekday.SATURDAY,
    "domingo": Weekday.SUNDAY,
}
_PERIODS = {"semana": Period.WEEK, "mes": Period.MONTH}
_INTERVAL_UNITS = {
    "dias": IntervalUnit.DAYS,
    "semanas": IntervalUnit.WEEKS,
    "meses": IntervalUnit.MONTHS,
}
_MEASUREMENT_KINDS = {
    "cantidad": MeasurementKind.QUANTITY,
    "duracion": MeasurementKind.DURATION,
}


@dataclass(frozen=True, slots=True)
class LegacyImport:
    """The result of reading an old file.

    ``skipped`` describes, in English, everything that was left out or changed to
    keep a habit (its history is never dropped because of its area).
    """

    snapshot: Snapshot
    source_version: int
    skipped: tuple[str, ...]


class _InvalidEntityError(ValueError):
    """An entity of the old file that cannot be imported as it is."""


def load_legacy(path: Path, *, today: date) -> LegacyImport:
    """Read an old JSON file and convert it; ``today`` dates v1 habits with no history."""
    raw = _read_object(path)
    if "version" not in raw:
        return _import_v1(raw, today)
    version = raw["version"]
    if type(version) is not int or version < 2:
        raise StorageError(f"{path} has an unknown format version: {version!r}")
    if version > LATEST_VERSION:
        raise StorageError(
            f"{path} uses format version {version}, newer than the last one this "
            f"application can import ({LATEST_VERSION})"
        )
    return _import_current(raw, version)


def backup_legacy_file(path: Path, *, source_version: int, today: date) -> Path:
    """Copy ``path`` to ``<name>.bak-v<version>-<YYYYMMDD>`` next to it.

    An existing backup is never overwritten: a number is added to the name
    instead. The original is not modified.
    """
    base = f"{path.name}.bak-v{source_version}-{today:%Y%m%d}"
    destination = path.with_name(base)
    attempt = 1
    while os.path.lexists(destination):
        attempt += 1
        destination = path.with_name(f"{base}-{attempt}")
    try:
        shutil.copy2(path, destination)
    except OSError as error:
        raise StorageError(f"could not back up {path}: {error}") from error
    return destination


def _read_object(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError, RecursionError) as error:
        raise StorageError(f"could not read {path} as JSON: {error}") from error
    if not isinstance(raw, dict):
        raise StorageError(f"{path} does not hold a JSON object")
    return raw


def _import_v1(raw: dict[str, Any], today: date) -> LegacyImport:
    habits: list[Habit] = []
    skipped: list[str] = []
    for number, (name, days) in enumerate(raw.items(), start=1):
        label = f"habit {name!r}"
        if not name.strip() or not isinstance(days, list):
            skipped.append(f"{label}: expected a name and a list of dates")
            continue
        completions, dropped = _parse_days(days)
        _report_dropped(skipped, label, dropped, 0)
        habits.append(
            Habit(
                id=number,
                name=name,
                area_id=GENERAL_AREA_ID,
                frequency=Daily(),
                start=min(completions, default=today),
                completions=completions,
            )
        )
    snapshot = Snapshot(areas=[_general_area()], habits=habits)
    return LegacyImport(snapshot, 1, tuple(skipped))


def _import_current(raw: dict[str, Any], version: int) -> LegacyImport:
    skipped: list[str] = []
    areas = _read_areas(raw.get("areas"), skipped)
    habits = _read_habits(raw.get("habitos"), areas, skipped)
    snapshot = Snapshot(
        areas=areas,
        habits=habits,
        important_dates=_read_important_dates(raw.get("fechas_importantes"), skipped),
        priority=_read_priority(raw.get("prioridad_manana"), skipped),
    )
    return LegacyImport(snapshot, version, tuple(skipped))


def _read_areas(value: object, skipped: list[str]) -> list[Area]:
    areas: list[Area] = []
    for index, item in enumerate(_items(value, "areas", skipped), start=1):
        try:
            area = _parse_area(item)
        except ValueError as error:
            skipped.append(f"area #{index}: {error}")
            continue
        if any(existing.id == area.id for existing in areas):
            skipped.append(f"area #{index}: duplicate id {area.id!r}")
            continue
        areas.append(area)
    return areas


def _parse_area(item: object) -> Area:
    data = _mapping(item, "area")
    return Area(
        id=_text(data, "id"),
        name=_text(data, "nombre"),
        color=_text(data, "color"),
        soft_color=_optional_text(data, "color_suave"),
    )


def _read_habits(value: object, areas: list[Area], skipped: list[str]) -> list[Habit]:
    habits: list[Habit] = []
    seen_ids: set[int] = set()
    for index, item in enumerate(_items(value, "habits", skipped), start=1):
        label = _habit_label(item, index)
        try:
            habit, dropped_days, dropped_values = _parse_habit(item)
        except ValueError as error:
            skipped.append(f"{label}: {error}")
            continue
        if habit.id in seen_ids:
            skipped.append(f"{label}: duplicate id {habit.id}")
            continue
        seen_ids.add(habit.id)
        if not any(area.id == habit.area_id for area in areas):
            skipped.append(
                f"{label}: unknown area {habit.area_id!r}, moved to {GENERAL_AREA_ID!r}"
            )
            habit.area_id = GENERAL_AREA_ID
            if not any(area.id == GENERAL_AREA_ID for area in areas):
                areas.append(_general_area())
        _report_dropped(skipped, label, dropped_days, dropped_values)
        habits.append(habit)
    return sorted(habits, key=lambda habit: habit.id)


def _parse_habit(item: object) -> tuple[Habit, int, int]:
    data = _mapping(item, "habit")
    completions, dropped_days = _parse_days(_list(data.get("completados"), "completados"))
    dropped_values = 0
    for text, raw_value in _dict(data.get("registros"), "registros").items():
        try:
            day = parse_iso_date(text)
        except ValueError:
            dropped_days += 1
            continue
        value = _record_value(raw_value)
        if value is None and raw_value is not None:
            dropped_values += 1
        completions[day] = value
    habit = Habit(
        id=_integer(data.get("id"), "id"),
        name=_text(data, "nombre"),
        area_id=_text(data, "area"),
        frequency=_parse_frequency(data.get("frecuencia")),
        start=_day(data.get("creado"), "creado"),
        end=_optional_day(data.get("fin"), "fin"),
        description=_optional_text(data, "descripcion"),
        notes=_optional_text(data, "notas"),
        measurement=_parse_measurement(data.get("medicion")),
        reminder=_parse_reminder(data.get("recordatorio")),
        completions=completions,
    )
    return habit, dropped_days, dropped_values


def _parse_frequency(value: object) -> Frequency:
    if value == "diario":
        return Daily()
    if isinstance(value, list):
        return Weekdays(days=_weekdays(value))
    data = _mapping(value, "frequency")
    kind = data.get("tipo", "cupo")
    if kind == "cupo":
        return Quota(
            times=_integer(data.get("veces"), "veces"),
            period=_lookup(_PERIODS, data.get("por"), "period"),
            preferred=_weekdays(_list(data.get("preferidos"), "preferidos")),
        )
    if kind == "fechas":
        dates = _list(data.get("fechas"), "fechas")
        return FixedDates(dates=tuple(_day(text, "fechas") for text in dates))
    if kind == "intervalo":
        return Interval(
            every=_integer(data.get("cada"), "cada"),
            unit=_lookup(_INTERVAL_UNITS, data.get("unidad"), "interval unit"),
        )
    raise _InvalidEntityError(f"unknown frequency type {kind!r}")


def _parse_measurement(value: object) -> Measurement | None:
    if value is None:
        return None
    data = _mapping(value, "measurement")
    return Measurement(
        kind=_lookup(_MEASUREMENT_KINDS, data.get("tipo"), "measurement type"),
        goal=_number(data.get("meta"), "goal"),
        unit=_text(data, "unidad"),
        minimum=_optional_number(data.get("minima"), "minimum"),
        ideal=_optional_number(data.get("ideal"), "ideal"),
    )


def _parse_reminder(value: object) -> Reminder | None:
    if value is None:
        return None
    data = _mapping(value, "reminder")
    return Reminder(
        at=_clock_time(data.get("hora"), "hora"),
        weekdays=_weekdays(_list(data.get("dias"), "dias")),
    )


def _read_important_dates(value: object, skipped: list[str]) -> list[ImportantDate]:
    dates: list[ImportantDate] = []
    for index, item in enumerate(_items(value, "important dates", skipped), start=1):
        try:
            data = _mapping(item, "important date")
            entry = ImportantDate(
                day=_day(data.get("fecha"), "fecha"), title=_text(data, "titulo")
            )
        except ValueError as error:
            skipped.append(f"important date #{index}: {error}")
            continue
        if entry not in dates:
            dates.append(entry)
    return sorted(dates, key=lambda item: (item.day, item.title))


def _read_priority(value: object, skipped: list[str]) -> PriorityNote | None:
    if value is None:
        return None
    try:
        data = _mapping(value, "priority note")
        for_day = _day(data.get("fecha"), "fecha")
        text = data.get("texto")
        if not isinstance(text, str):
            raise _InvalidEntityError("'texto' is not text")
    except ValueError as error:
        skipped.append(f"priority note: {error}")
        return None
    return PriorityNote(for_day=for_day, text=text) if text.strip() else None


def _parse_days(texts: list[Any]) -> tuple[dict[date, float | None], int]:
    """The valid days as done days without a value, and how many were not valid."""
    days: dict[date, float | None] = {}
    dropped = 0
    for text in texts:
        try:
            days[parse_iso_date(text)] = None
        except ValueError:
            dropped += 1
    return days, dropped


def _record_value(value: object) -> float | None:
    """A recorded value, or ``None`` when there is none or it is not a usable number."""
    if type(value) is int or type(value) is float:
        return float(value) if math.isfinite(value) and value >= 0 else None
    return None


def _report_dropped(skipped: list[str], label: str, days: int, values: int) -> None:
    if days:
        skipped.append(f"{label}: ignored {days} completion date(s) that are not valid")
    if values:
        skipped.append(f"{label}: ignored {values} recorded value(s) that are not valid")


def _general_area() -> Area:
    return Area(id=GENERAL_AREA_ID, name="General", color="#b4aabf", soft_color="#f1eff4")


def _habit_label(item: object, index: int) -> str:
    name = item.get("nombre") if isinstance(item, dict) else None
    return f"habit #{index} ({name!r})" if isinstance(name, str) else f"habit #{index}"


def _items(value: object, what: str, skipped: list[str]) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        skipped.append(f"{what}: expected a list")
        return []
    return value


def _mapping(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _InvalidEntityError(f"the {what} is not a JSON object")
    return value


def _dict(value: object, key: str) -> dict[str, Any]:
    return {} if value is None else _mapping(value, repr(key))


def _list(value: object, key: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise _InvalidEntityError(f"{key!r} is not a list")
    return value


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _InvalidEntityError(f"{key!r} is missing or empty")
    return value


def _optional_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _InvalidEntityError(f"{key!r} is not text")
    return value


def _day(value: object, key: str) -> date:
    try:
        return parse_iso_date(value)
    except ValueError:
        raise _InvalidEntityError(f"{key!r} is not a YYYY-MM-DD date: {value!r}") from None


def _optional_day(value: object, key: str) -> date | None:
    return None if value is None or value == "" else _day(value, key)


def _clock_time(value: object, key: str) -> time:
    try:
        return parse_iso_time(value)
    except ValueError:
        raise _InvalidEntityError(f"{key!r} is not an HH:MM time: {value!r}") from None


def _integer(value: object, key: str) -> int:
    if type(value) is not int or not -_INT64_LIMIT <= value < _INT64_LIMIT:
        raise _InvalidEntityError(f"{key!r} is not a usable integer")
    return value


def _number(value: object, key: str) -> float:
    if type(value) is not int and type(value) is not float:
        raise _InvalidEntityError(f"{key!r} is not a number")
    return float(value)


def _optional_number(value: object, key: str) -> float | None:
    return None if value is None else _number(value, key)


def _lookup[T](table: dict[str, T], key: object, what: str) -> T:
    if not isinstance(key, str) or key not in table:
        raise _InvalidEntityError(f"unknown {what}: {key!r}")
    return table[key]


def _weekdays(names: list[Any]) -> frozenset[Weekday]:
    return frozenset(_lookup(_WEEKDAYS, name, "weekday") for name in names)
