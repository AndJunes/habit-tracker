"""Spanish names of months and weekdays: the single source for every date label.

The same names are shown in several shapes (full, abbreviated, uppercase), so each
shape has its own constant. Months are indexed from 0 (``MONTHS[date.month - 1]``)
and weekdays from Monday (``WEEKDAYS_LONG[date.weekday()]``).
"""

from datetime import date

from ..domain.enums import Weekday
from .strings import WEEKDAY_NAMES

# "Hoy es 29 de octubre", "octubre 2026" in the calendar headers.
MONTHS: tuple[str, ...] = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

# Lowercase abbreviation, as on the date picker's buttons ("29 oct").
MONTHS_SHORT: tuple[str, ...] = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)

# Uppercase abbreviation, as on the dashboard's date chips ("12 JUN").
MONTHS_SHORT_UPPER: tuple[str, ...] = tuple(month.upper() for month in MONTHS_SHORT)

# "lunes 29 de octubre" in the page headers. Taken from the domain's weekday names so
# the two cannot drift apart.
WEEKDAYS_LONG: tuple[str, ...] = tuple(WEEKDAY_NAMES[day] for day in Weekday)

# Three letters: calendar column headers and the weekday chips of the habit form.
WEEKDAYS_SHORT: tuple[str, ...] = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def short_date_text(day: date) -> str:
    """``date(2026, 11, 5)`` becomes ``"5 nov"``: for chips, previews and subtitles."""
    return f"{day.day} {MONTHS_SHORT[day.month - 1]}"
