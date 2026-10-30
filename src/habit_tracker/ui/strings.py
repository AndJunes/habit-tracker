"""Every user-facing sentence the domain would otherwise have to know about.

The interface speaks Spanish. Keeping its text here, apart from the domain
rules, means a translation would not touch the logic.
"""

from pathlib import Path

from ..domain.enums import IntervalUnit, Period, Weekday
from ..domain.errors import ErrorCode, ValidationError
from ..domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays

APP_TITLE = "Registro de hábitos"

WEEKDAY_NAMES = {
    Weekday.MONDAY: "lunes",
    Weekday.TUESDAY: "martes",
    Weekday.WEDNESDAY: "miércoles",
    Weekday.THURSDAY: "jueves",
    Weekday.FRIDAY: "viernes",
    Weekday.SATURDAY: "sábado",
    Weekday.SUNDAY: "domingo",
}

_INTERVAL_UNITS = {
    IntervalUnit.DAYS: ("día", "días"),
    IntervalUnit.WEEKS: ("semana", "semanas"),
    IntervalUnit.MONTHS: ("mes", "meses"),
}

# From this many weekdays on, it reads better to say which days are skipped.
_ALMOST_EVERY_DAY = 5


def describe_frequency(frequency: Frequency) -> str:
    """A short phrase for the interface; empty when the habit is simply daily."""
    match frequency:
        case Daily():
            return ""
        case Weekdays(days=days):
            if len(days) == len(Weekday):
                return ""
            if len(days) >= _ALMOST_EVERY_DAY:
                skipped = [WEEKDAY_NAMES[day] for day in Weekday if day not in days]
                return "descansa " + " y ".join(skipped)
            return "solo " + " y ".join(WEEKDAY_NAMES[day] for day in sorted(days))
        case Quota(times=times, period=period):
            unit = "mes" if period is Period.MONTH else "semana"
            return f"{times} {'vez' if times == 1 else 'veces'} por {unit}"
        case FixedDates(dates=dates):
            count = len(dates)
            return f"{count} {'fecha elegida' if count == 1 else 'fechas elegidas'}"
        case Interval(every=every, unit=unit):
            singular, plural = _INTERVAL_UNITS[unit]
            return f"cada {singular}" if every == 1 else f"cada {every} {plural}"
    raise TypeError(f"unknown frequency: {frequency!r}")


_MESSAGES = {
    ErrorCode.NAME_REQUIRED: "El hábito necesita un nombre.",
    ErrorCode.NAME_TOO_LONG: "El nombre es demasiado largo (máximo {limit} caracteres).",
    ErrorCode.NAME_DUPLICATE: "Ese hábito ya existe.",
    ErrorCode.TITLE_REQUIRED: "El evento necesita un título.",
    ErrorCode.AREA_UNKNOWN: "Elige un área de la lista.",
    ErrorCode.END_BEFORE_START: "La fecha de fin no puede ser anterior a la de inicio.",
    ErrorCode.WEEKDAYS_REQUIRED: "Elige al menos un día de la semana.",
    ErrorCode.QUOTA_OUT_OF_RANGE: "Las veces por {period} deben ir de 1 a {maximum}.",
    ErrorCode.DATES_REQUIRED: "Elige al menos una fecha.",
    ErrorCode.DATE_INVALID: "Hay una fecha elegida que no es válida.",
    ErrorCode.DATE_OUT_OF_RANGE: (
        "El {day} queda fuera del período del hábito (entre la fecha de inicio y la de fin)."
    ),
    ErrorCode.INTERVAL_INVALID: (
        "El intervalo debe ser un número mayor que cero de días, semanas o meses."
    ),
    ErrorCode.GOAL_INVALID: "La meta debe ser un número mayor que cero.",
    ErrorCode.UNIT_REQUIRED: "Escribe la unidad de medida.",
    ErrorCode.BOUNDS_INVALID: (
        "La meta mínima y la ideal deben ser números positivos, y la mínima no puede superar a "
        "la ideal."
    ),
    ErrorCode.VALUE_INVALID: "El valor debe ser un número positivo.",
    ErrorCode.HABIT_NOT_FOUND: "Ese hábito ya no existe.",
}

_PERIOD_NAMES = {Period.WEEK.value: ("semana", 7), Period.MONTH.value: ("mes", 31)}


def error_message(error: ValidationError) -> str:
    """The sentence shown to the person for a domain error."""
    values = {key: str(value) for key, value in error.context.items()}
    if error.code is ErrorCode.QUOTA_OUT_OF_RANGE:
        name, maximum = _PERIOD_NAMES.get(values.get("period", ""), ("período", 31))
        values.update(period=name, maximum=str(maximum))
    return _MESSAGES[error.code].format(**values)


def recovery_message(quarantined_to: Path) -> str:
    """Told to the person when the data file was damaged and has been set aside."""
    return (
        "El archivo de datos parecía dañado y no se pudo leer. No se borró: quedó guardado "
        f"aparte en\n{quarantined_to}\n\n"
        "Se creó un archivo nuevo y vacío para que puedas seguir usando la app."
    )


def import_message(habits: int, skipped: int, backup: Path) -> str:
    """Told to the person after data from an older version was imported."""
    noun = "hábito" if habits == 1 else "hábitos"
    text = (
        f"Se importaron {habits} {noun} del archivo anterior. El original quedó intacto y hay "
        f"una copia de respaldo en\n{backup}"
    )
    if skipped:
        text += (
            f"\n\nAlgunos datos no se pudieron importar ({skipped}); "
            "el detalle quedó en el registro de la aplicación."
        )
    return text


def fatal_message(reason: str) -> str:
    """Shown when the data cannot be opened at all."""
    return f"No se pudieron abrir los datos.\n\n{reason}\n\nNo se modificó nada."
