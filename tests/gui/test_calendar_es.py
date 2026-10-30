from datetime import date, timedelta

from habit_tracker.ui import calendar_es
from habit_tracker.ui.calendar_es import short_date_text

MONDAY = date(2026, 10, 26)


def test_there_are_twelve_distinct_months_from_january() -> None:
    assert len(calendar_es.MONTHS) == 12
    assert len(set(calendar_es.MONTHS)) == 12
    assert calendar_es.MONTHS[0] == "enero"
    assert calendar_es.MONTHS[date(2026, 10, 29).month - 1] == "octubre"
    assert calendar_es.MONTHS[-1] == "diciembre"


def test_short_months_are_the_first_three_letters_of_each_month() -> None:
    assert len(calendar_es.MONTHS_SHORT) == 12
    for month, short in zip(calendar_es.MONTHS, calendar_es.MONTHS_SHORT, strict=True):
        assert month.startswith(short)
        assert len(short) == 3


def test_uppercase_short_months_are_the_dashboard_labels() -> None:
    assert calendar_es.MONTHS_SHORT_UPPER == (
        "ENE",
        "FEB",
        "MAR",
        "ABR",
        "MAY",
        "JUN",
        "JUL",
        "AGO",
        "SEP",
        "OCT",
        "NOV",
        "DIC",
    )


def test_weekdays_run_from_monday_to_sunday() -> None:
    expected = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    assert expected == calendar_es.WEEKDAYS_LONG
    for offset, name in enumerate(expected):
        assert calendar_es.WEEKDAYS_LONG[(MONDAY + timedelta(days=offset)).weekday()] == name


def test_short_weekdays_match_the_long_ones() -> None:
    assert calendar_es.WEEKDAYS_SHORT == ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
    for long, short in zip(calendar_es.WEEKDAYS_LONG, calendar_es.WEEKDAYS_SHORT, strict=True):
        assert long.startswith(short)


def test_short_date_text_is_day_and_lowercase_month() -> None:
    assert short_date_text(date(2026, 11, 5)) == "5 nov"
    assert short_date_text(date(2027, 1, 31)) == "31 ene"
