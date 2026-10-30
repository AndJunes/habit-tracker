"""Every sentence the habit form and the value dialog show.

The interface speaks Spanish; the rest of the code does not. Menu entries are keyed by the
choice they stand for, so a choice without a label fails when this module is imported.
"""

from ...domain.enums import Period
from .choices import FrequencyChoice, IntervalChoice, MeasurementChoice

# ---------- Window ----------

TITLE_NEW = "Nuevo hábito"
TITLE_EDIT = "Editar hábito"
SAVE_NEW = "Crear hábito"
SAVE_EDIT = "Guardar cambios"
CANCEL = "Cancelar"
EYEBROW = "SEGUIMIENTO PERSONAL"
TAGLINE = "Pequeñas acciones, grandes cambios."


# ---------- Name, motivation and area ----------

NAME_PROMPT = "¿Qué hábito quieres registrar?"
NAME_EXAMPLE = "Ej. Leer 10 páginas, caminar 20 minutos…"
MOTIVATION_PROMPT = "¿Por qué quieres incorporarlo? (opcional)"
AREA_PROMPT = "Área (define el color)"

# ---------- Frequency ----------

# The buttons of the counters (the minus is U+2212, wider than a hyphen).
STEP_DOWN = "\N{MINUS SIGN}"
STEP_UP = "+"

FREQUENCY_PROMPT = "¿Cada cuánto?"

_FREQUENCY_LABELS = {
    FrequencyChoice.DAILY: "Todos los días",
    FrequencyChoice.WEEKDAYS: "Días específicos",
    FrequencyChoice.TIMES_PER_WEEK: "Veces por semana",
    FrequencyChoice.TIMES_PER_MONTH: "Veces por mes",
    FrequencyChoice.FIXED_DATES: "Fechas específicas",
    FrequencyChoice.CUSTOM: "Personalizada",
}
FREQUENCY_OPTIONS = tuple(_FREQUENCY_LABELS[choice] for choice in FrequencyChoice)

_INTERVAL_LABELS = {
    IntervalChoice.DAYS: "días",
    IntervalChoice.WEEKS: "semanas",
    IntervalChoice.MONTHS: "meses",
    IntervalChoice.PICKED_DATES: "fechas elegidas a mano",
}
INTERVAL_OPTIONS = tuple(_INTERVAL_LABELS[choice] for choice in IntervalChoice)

PICK_WEEKDAYS = "Elige los días"
PICK_PREFERRED_DAYS = "Días preferidos (opcional)"
PICK_MONTH_DATES = "Fechas concretas (opcional)"
PICK_DATES = "Elige las fechas"
EVERY = "Cada"
INTERVAL_FROM_START = "Cuenta desde la fecha de inicio del hábito."

_PERIOD_NAMES = {Period.WEEK: "semana", Period.MONTH: "mes"}


def times_per(period: Period) -> str:
    """The caption beside the counter."""
    return f"veces por {_PERIOD_NAMES[period]}"


# Hint line under the frequency zone.
DATES_OUT_OF_RANGE = (
    "Hay fechas fuera del período del hábito (en rosa): quítalas "
    "o cambia la fecha de inicio o de fin."
)
FLEXIBLE_GOAL = "Meta flexible: tú decides cuándo, sin fechas fijas."
NO_DATES_YET = "Aún no elegiste ninguna fecha."


def preferred_fewer(preferred: int) -> str:
    return (
        f"Prefieres {preferred} {'día' if preferred == 1 else 'días'}; los otros los decides tú."
    )


def preferred_more(preferred: int, times: int) -> str:
    return f"Prefieres {preferred} días para {times} veces: elegirás {times} de ellos."


def dates_complete(count: int, times: int) -> str:
    return f"✓ {count} de {times} fechas elegidas"


def dates_incomplete(count: int, times: int) -> str:
    return (
        f"{count} de {times} fechas elegidas: completa las que faltan, quita las que sobran "
        "o bórralas todas para dejarla flexible."
    )


def dates_count(count: int) -> str:
    return f"{count} {'fecha elegida' if count == 1 else 'fechas elegidas'}"


# ---------- Measurement ----------

MEASUREMENT_PROMPT = "Forma de medir"

_MEASUREMENT_LABELS = {
    MeasurementChoice.YES_NO: "Sí / No",
    MeasurementChoice.QUANTITY: "Por cantidad",
    MeasurementChoice.DURATION: "Por duración",
}
MEASUREMENT_OPTIONS = tuple(_MEASUREMENT_LABELS[choice] for choice in MeasurementChoice)

GOAL_LABEL = "Meta por ocasión"
UNIT_LABEL = "Unidad de medida"
CUSTOM_UNIT_LABEL = "Escribe la unidad"

# ---------- Validity ----------

VALIDITY_PROMPT = "Duración del hábito"
START_LABEL = "Empieza el (AAAA-MM-DD)"
END_LABEL = "Termina el (AAAA-MM-DD)"
OPEN_CALENDAR = "Elegir en el calendario"
WITH_END = "Con fecha de finalización"

# ---------- Notes and advanced options ----------

NOTES_PROMPT = "Notas adicionales (opcional)"
SHOW_ADVANCED = "\N{FULLWIDTH PLUS SIGN} Mostrar opciones avanzadas"
HIDE_ADVANCED = "\N{MINUS SIGN} Ocultar opciones avanzadas"
REFERENCE_GOALS = "Metas de referencia (opcional)"
MINIMUM_LABEL = "Mínima"
IDEAL_LABEL = "Ideal"
REFERENCE_GOALS_NOTE = "Son una guía: cualquier registro cuenta como cumplido."
REST_DAYS = "Días de descanso (opcional)"
REST_DAYS_NOTE = "Los días marcados no cuentan, ni como cumplido ni como fallo."
REMINDER_HEADING = "Recordatorio"
WANT_REMINDER = "Quiero un recordatorio"
REMINDER_TIME_LABEL = "Hora (HH:MM)"
REMINDER_DAYS = "Días en que suena (vacío = los días en que toca)"
REMINDER_NOTE = "Suena como notificación de macOS mientras la app esté abierta."

# ---------- Preview ----------

PREVIEW_PROMPT = "Vista previa"
PREVIEW_PLACEHOLDER_NAME = "Nombre del hábito"
PREVIEW_DEFAULT_NAME = "Tu hábito"
NO_AREA = "Sin área"


def preview_row_goal(goal: str, unit: str) -> str:
    """The goal appended to the area name on the preview row."""
    return f" · meta {goal} {unit}"


def preview_goal(goal: str, unit: str) -> str:
    """The goal as a clause of the preview sentence."""
    return f"meta por ocasión: {goal} {unit}"


def preview_period(start: str, end: str | None) -> str:
    return f"desde el {start}" + (f" hasta el {end}" if end else "")


def preview_reminder(time_text: str) -> str:
    return f"recordatorio a las {time_text}"


# ---------- Problems with what was typed or picked ----------
# The rules of the domain have their sentences in ``ui.strings``; these belong to the form.

NAME_FIRST = "Escribe primero el nombre del hábito."
WEEKDAYS_REQUIRED = "Elige al menos un día de la semana."
EVERY_DAY_RESTED = "Marcaste descanso todos los días de la semana."
DATES_REQUIRED = "Elige al menos una fecha en el calendario."
MINIMUM_NOT_A_NUMBER = "La meta mínima debe ser un número."
IDEAL_NOT_A_NUMBER = "La meta ideal debe ser un número."
START_FORMAT = "La fecha de inicio debe tener el formato AAAA-MM-DD."
END_FORMAT = "La fecha de fin debe tener el formato AAAA-MM-DD."
REMINDER_TIME_FORMAT = "La hora del recordatorio debe tener el formato HH:MM."
SAVE_FAILED = "No se pudo guardar el hábito. Inténtalo de nuevo."


def dates_mismatch(count: int, times: int) -> str:
    return (
        f"Elegiste {count} de {times} fechas: completa las que faltan, quita las que sobran "
        "o bórralas todas para dejar la meta flexible."
    )


# ---------- Value dialog ----------

VALUE_QUESTION = "¿Cuánto hiciste hoy?"
VALUE_SUBMIT = "Registrar"
VALUE_INVALID = "Escribe un número mayor que cero."


def value_references(goal: str, minimum: str | None, ideal: str | None) -> str:
    """The goal and the optional reference goals, as a hint under the field."""
    parts = [f"meta {goal}"]
    if minimum is not None:
        parts.append(f"mínimo {minimum}")
    if ideal is not None:
        parts.append(f"ideal {ideal}")
    return " · ".join(parts) + ". Cualquier cantidad cuenta."
