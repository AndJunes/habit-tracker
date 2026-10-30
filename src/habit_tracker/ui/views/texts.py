"""Every sentence the screens and their controllers show (the interface speaks Spanish).

Text that depends on data (names, counts, dates) is assembled where the data is known; what
is fixed lives here, so a translation would not touch the drawing code.
"""

# ---------- Dialog titles ----------

NOTICE_TITLE = "Aviso"
CONFIRM_TITLE = "Confirmar"
DONE_TITLE = "Lista"
SAVE_ERROR_TITLE = "No se pudo guardar"
UNEXPECTED_ERROR_TITLE = "Error inesperado"

SAVE_ERROR_MESSAGE = (
    "No se pudo guardar el cambio. Revisa que el archivo de datos esté disponible "
    "e inténtalo de nuevo."
)
UNEXPECTED_ERROR_MESSAGE = (
    "Ocurrió un error inesperado. Puedes seguir usando la aplicación; el detalle quedó registrado."
)

# ---------- Habit actions ----------

UNMARK_TITLE = "Quitar el registro"
TOO_MANY_HABITS_TITLE = "Un momento"
NO_HABITS_TO_DELETE = "No hay hábitos para eliminar."


def unmark_message(when: str, amount: str) -> str:
    """Warns that unmarking discards the measured value; ``when`` is "de hoy" or "del 5 nov"."""
    return f"Vas a quitar la marca {when} y el valor que registraste ({amount}).\n\n¿Seguro?"


def too_many_habits_message(active: int) -> str:
    return (
        f"Ya tienes {active} hábitos activos.\n\n"
        "Lo recomendable es no pasar de 5 o 6 para no sobrecargarte. "
        "¿Seguro que quieres agregar otro?"
    )


def delete_confirmation(count: int, names: list[str]) -> str:
    bullets = "\n".join(f"• {name}" for name in names)
    return f"¿Eliminar {habit_count(count)} y todo su historial?\n\n{bullets}"


def habit_count(count: int) -> str:
    """``1`` becomes ``"1 hábito"``, ``2`` becomes ``"2 hábitos"``."""
    return f"{count} hábito{'' if count == 1 else 's'}"


# ---------- Buttons and hints shared by Today and the dashboard ----------

ADD_HABIT = "+ Agregar hábito"
DELETE_HABIT = "Eliminar hábito…"
CANCEL = "Cancelar"
DELETE = "Eliminar"
NO_HABITS_YET = "No tienes hábitos todavía.\n¡Agrega el primero!"
NO_HABITS_TO_SHOW = "todavía no hay hábitos que mostrar"


def delete_selected(count: int) -> str:
    """Label of the confirm button of delete mode."""
    return f"Eliminar {habit_count(count)}"


# ---------- Tomorrow's priority ----------

PRIORITY_SAVE = "Guardar"
PRIORITY_EMPTY = "Escribe primero la tarea de mañana."
PRIORITY_SAVED = "Guardada. Mañana te estará esperando destacada."

# ---------- Today ----------

TODAY_DELETE_HINT = "Marca los hábitos que quieras eliminar (se borra también su historial)"
PRIORITY_TODAY_LABEL = "PRIORIDAD DE HOY · UNA SOLA TAREA"
PRIORITY_TOMORROW_LABEL = "PRIORIDAD DE MAÑANA · UNA SOLA TAREA"


def today_title(day: int, month_name: str) -> str:
    return f"Hoy es {day} de {month_name}"


# ---------- Calendar ----------

# Single angle quotation marks, spelled as escapes because they look like "<" and ">".
PREVIOUS_MONTH = "\u2039"
NEXT_MONTH = "\u203a"
CALENDAR_DATES_TITLE = "FECHAS DEL MES"

# ---------- Month figures (My month and the dashboard) ----------

STAT_TODAY = "hoy"
STAT_LONGEST_STREAK = "racha más larga"
STAT_MONTH_CHECKS = "checks del mes"

MONTH_BY_AREA_TITLE = "Tu mes por área"
MONTH_BALANCE_TITLE = "Balance del mes"
MONTH_BALANCE_NOTE = "qué áreas estás alimentando"
MONTH_PACE_TITLE = "Ritmo del mes"
MONTH_PACE_NOTE = "hábitos cumplidos por día"
MONTH_CONSISTENCY_TITLE = "Constancia del mes"
MONTH_CONSISTENCY_NOTE = "cada fila es un área · de un vistazo, qué estás alimentando"

GREETING_MORNING = "Buenos días ✿"
GREETING_AFTERNOON = "Buenas tardes ✿"
GREETING_EVENING = "Buenas noches ✿"

# ---------- Dashboard ----------

DASHBOARD_BRAND = "jardín suave · tu app de hábitos"
DASHBOARD_TITLE = "Registro de hábitos"
DASHBOARD_TODAY_TITLE = "Hoy"
DASHBOARD_DELETE_HINT = "Marca los hábitos a eliminar (se borra su historial)"
DASHBOARD_PRIORITY_LABEL = "PRIORIDAD DE MAÑANA"
DASHBOARD_PRIORITY_NOTE = "lo escribes esta noche · una sola tarea"
DASHBOARD_CALENDAR_NOTE = "un buen mes se ve como un arcoíris"
DASHBOARD_DATES_TITLE = "Fechas del mes"
DASHBOARD_NO_DATES = "este mes no tiene fechas anotadas"

# ---------- Main window ----------

WINDOW_TITLE = "Registro de hábitos"
WINDOW_TITLE_DEMO = "Registro de hábitos · modo demo"
TAB_TODAY = "Hoy"
TAB_CALENDAR = "Calendario"
TAB_MONTH = "Mi mes"
REMINDER_MESSAGE = "Es tu hora. Márcalo cuando lo hagas."


def reminder_with_goal(goal: str, unit: str) -> str:
    return f"Es tu hora. Meta: {goal} {unit}."
