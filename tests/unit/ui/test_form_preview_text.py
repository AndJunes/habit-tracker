"""The habit described in words, and the small tables the form is built from."""

from datetime import date

import pytest

from habit_tracker.domain.enums import IntervalUnit, Period, Weekday
from habit_tracker.domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from habit_tracker.seed import default_areas
from habit_tracker.ui.forms import texts
from habit_tracker.ui.forms.choices import FrequencyChoice, IntervalChoice, MeasurementChoice
from habit_tracker.ui.forms.numbers import format_number, parse_number
from habit_tracker.ui.forms.preview_text import (
    dates_in_words,
    frequency_in_words,
    join_words,
    preview_sentence,
)
from habit_tracker.ui.forms.units import (
    CUSTOM_UNIT,
    DURATION_UNITS,
    GENERIC_UNITS,
    UNITS_BY_AREA,
)

MON, TUE, WED, THU, FRI, SAT, SUN = Weekday


def nov(day: int) -> date:
    return date(2026, 11, day)


class TestJoinWords:
    @pytest.mark.parametrize(
        ("items", "expected"),
        [
            ([], ""),
            (["a"], "a"),
            (["a", "b"], "a y b"),
            (["a", "b", "c"], "a, b y c"),
            (["a", "b", "c", "d"], "a, b, c y d"),
        ],
    )
    def test_the_last_item_gets_the_y(self, items: list[str], expected: str) -> None:
        assert join_words(items) == expected

    def test_it_accepts_any_iterable(self) -> None:
        assert join_words(str(number) for number in (5, 12, 27)) == "5, 12 y 27"


class TestDatesInWords:
    def test_a_single_date_says_the_day(self) -> None:
        assert dates_in_words([nov(5)]) == "el día 5 de noviembre"

    def test_dates_of_one_month_share_the_month(self) -> None:
        assert dates_in_words([nov(27), nov(5), nov(12)]) == "los días 5, 12 y 27 de noviembre"

    def test_dates_of_several_months_are_grouped_by_month(self) -> None:
        assert dates_in_words([date(2026, 12, 3), nov(5), nov(12)]) == (
            "los días 5 y 12 de noviembre y 3 de diciembre"
        )

    def test_dates_that_span_years_carry_their_year(self) -> None:
        assert dates_in_words([date(2026, 12, 30), date(2027, 1, 2)]) == (
            "los días 30 de diciembre de 2026 y 2 de enero de 2027"
        )

    def test_no_dates(self) -> None:
        assert dates_in_words([]) == "sin fechas"


class TestFrequencyInWords:
    @pytest.mark.parametrize(
        ("frequency", "expected"),
        [
            (Daily(), "todos los días"),
            (Weekdays(frozenset(Weekday)), "todos los días"),
            (Weekdays(frozenset(Weekday) - {SUN}), "todos los días, excepto domingo"),
            (
                Weekdays(frozenset({MON, TUE, WED, THU, FRI})),
                "todos los días, excepto sábado y domingo",
            ),
            (Weekdays(frozenset({MON, WED, FRI})), "los lunes, miércoles y viernes"),
            (Weekdays(frozenset({FRI})), "los viernes"),
            (Weekdays(frozenset({SAT, SUN})), "los sábados y domingos"),
            (Quota(1, Period.MONTH), "1 vez por mes"),
            (Quota(3), "3 veces por semana"),
            (
                Quota(3, Period.WEEK, frozenset({FRI, MON, WED})),
                "3 veces por semana, preferentemente lunes, miércoles y viernes",
            ),
            (FixedDates((nov(5),)), "el día 5 de noviembre"),
            (Interval(1, IntervalUnit.MONTHS), "cada mes"),
            (Interval(2, IntervalUnit.WEEKS), "cada 2 semanas"),
        ],
    )
    def test_the_wording(self, frequency: Frequency, expected: str) -> None:
        assert frequency_in_words(frequency) == expected

    def test_a_quota_with_no_preferred_days_never_names_days(self) -> None:
        text = frequency_in_words(Quota(2, Period.WEEK))
        assert text == "2 veces por semana"
        assert "lunes" not in text

    def test_an_unknown_frequency_is_rejected(self) -> None:
        class Odd(Frequency):
            def occurs_on(self, day: date, start: date) -> bool:
                return False

            def last_on_or_before(self, day: date, start: date) -> date | None:
                return None

            def first_after(self, day: date, start: date) -> date | None:
                return None

        with pytest.raises(TypeError):
            frequency_in_words(Odd())


class TestPreviewSentence:
    def test_the_clauses_are_joined_with_semicolons(self) -> None:
        sentence = preview_sentence(
            name="Leer",
            schedule="todos los días",
            goal=(10, "páginas"),
            start=nov(1),
            end=date(2026, 12, 31),
            reminder_time="8:30",
        )
        assert sentence == (
            "Leer — todos los días; meta por ocasión: 10 páginas; desde el 1 nov hasta el 31 dic; "
            "recordatorio a las 8:30."
        )

    def test_missing_pieces_are_left_out(self) -> None:
        sentence = preview_sentence(
            name="Leer", schedule="3 veces por semana", goal=None, start=None, end=None,
            reminder_time=None,
        )  # fmt: skip
        assert sentence == "Leer — 3 veces por semana."

    def test_a_whole_goal_is_written_without_decimals(self) -> None:
        sentence = preview_sentence(
            name="x", schedule="s", goal=(30.0, "minutos"), start=None, end=None,
            reminder_time=None,
        )  # fmt: skip
        assert "meta por ocasión: 30 minutos" in sentence


class TestNumbers:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("12", 12),
            (" 12 ", 12),
            ("12,5", 12.5),
            ("12.5", 12.5),
            ("0", 0),
            ("-3", -3),
            ("2.0", 2),
        ],
    )
    def test_numbers_are_read_with_either_decimal_separator(
        self, text: str, expected: float
    ) -> None:
        assert parse_number(text) == expected

    def test_a_whole_number_comes_back_as_an_int(self) -> None:
        assert type(parse_number("2.0")) is int
        assert type(parse_number("2.5")) is float

    @pytest.mark.parametrize("text", ["", "  ", "abc", "1,2,3", "nan", "inf", "-inf", "1e999"])
    def test_anything_that_is_not_a_finite_number_is_none(self, text: str) -> None:
        assert parse_number(text) is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(10, "10"), (10.0, "10"), (2.5, "2.5"), (0.1, "0.1"), (90.0, "90")],
    )
    def test_numbers_are_written_without_a_trailing_zero(
        self, value: float, expected: str
    ) -> None:
        assert format_number(value) == expected


class TestTables:
    def test_every_menu_entry_has_a_label_in_the_order_of_its_choice(self) -> None:
        assert len(texts.FREQUENCY_OPTIONS) == len(FrequencyChoice)
        assert texts.FREQUENCY_OPTIONS[FrequencyChoice.TIMES_PER_MONTH] == "Veces por mes"
        assert texts.INTERVAL_OPTIONS[IntervalChoice.PICKED_DATES] == "fechas elegidas a mano"
        assert texts.MEASUREMENT_OPTIONS[MeasurementChoice.DURATION] == "Por duración"
        assert texts.INTERVAL_OPTIONS == ("días", "semanas", "meses", "fechas elegidas a mano")

    def test_the_unit_suggestions_are_keyed_by_the_ids_the_data_stores(self) -> None:
        area_ids = {area.id for area in default_areas()}
        assert set(UNITS_BY_AREA) == area_ids

    def test_no_list_offers_the_custom_option_by_itself(self) -> None:
        for units in (*UNITS_BY_AREA.values(), GENERIC_UNITS, DURATION_UNITS):
            assert CUSTOM_UNIT not in units
