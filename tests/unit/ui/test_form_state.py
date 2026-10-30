"""The habit form's state and rules, without a window."""

from datetime import date, datetime, time
from typing import Any

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.errors import ErrorCode, ValidationError
from habit_tracker.domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from habit_tracker.domain.models import (
    RECOMMENDED_MAX_HABITS,
    Area,
    Habit,
    Measurement,
    Reminder,
    Snapshot,
)
from habit_tracker.ports import StorageError
from habit_tracker.seed import default_areas
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository
from habit_tracker.ui.forms import texts
from habit_tracker.ui.forms.choices import (
    DayGroup,
    FrequencyChoice,
    HintTone,
    IntervalChoice,
    MeasurementChoice,
    TextField,
)
from habit_tracker.ui.forms.form_state import (
    FormError,
    FormState,
    describe_error,
    parse_typed_date,
    parse_typed_time,
)
from habit_tracker.ui.forms.units import CUSTOM_UNIT

MON, TUE, WED, THU, FRI, SAT, SUN = Weekday
TODAY = date(2026, 11, 1)


def nov(day: int) -> date:
    return date(2026, 11, day)


def make_state(name: str = "Leer") -> FormState:
    state = FormState(default_areas(), TODAY)
    state.set_text(TextField.NAME, name)
    return state


def make_service(*habits: Habit, repository: MemoryRepository | None = None) -> HabitService:
    snapshot = Snapshot(areas=default_areas(), habits=list(habits))
    clock = FixedClock(datetime(2026, 11, 1, 9, 0))
    return HabitService(repository or MemoryRepository(snapshot), clock)


class FailingRepository(MemoryRepository):
    """A store that cannot write, as when the disk is full."""

    def save_habit(self, habit: Habit) -> None:
        raise StorageError("disk full")


def pick_days(state: FormState, group: DayGroup, *days: Weekday) -> None:
    for day in days:
        state.toggle_day(group, day)


# ---------- Typed dates and times ----------


class TestTypedDates:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("2026-11-05", date(2026, 11, 5)),
            ("  2026-11-05  ", date(2026, 11, 5)),
            ("2028-02-29", date(2028, 2, 29)),
        ],
    )
    def test_the_iso_layout_is_read(self, text: str, expected: date) -> None:
        assert parse_typed_date(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "mañana",
            "20261231",  # fromisoformat takes it since Python 3.11
            "2026-1-5",
            "2026/11/05",
            "05-11-2026",
            "2026-W44-4",  # an ISO week date
            "2026-11-05T10:00",
            "2026-13-01",
            "2026-02-30",
            "2026-02-29",  # 2026 is not a leap year
            "0000-01-01",
            "\uff12\uff10\uff12\uff16-\uff11\uff11-\uff10\uff15",  # full-width digits
        ],
    )
    def test_any_other_layout_is_rejected(self, text: str) -> None:
        assert parse_typed_date(text) is None

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("20:00", time(20, 0)),
            ("8:30", time(8, 30)),
            ("08:30", time(8, 30)),
            ("00:00", time(0)),
        ],
    )
    def test_a_time_is_read_with_one_or_two_digits_of_hour(
        self, text: str, expected: time
    ) -> None:
        assert parse_typed_time(text) == expected

    @pytest.mark.parametrize(
        "text", ["", "25:99", "24:00", "12:60", "8:5", "830", "8h30", "12:30:00", "a:bc", "-1:30"]
    )
    def test_a_malformed_or_impossible_time_is_rejected(self, text: str) -> None:
        assert parse_typed_time(text) is None


# ---------- The starting state ----------


class TestStartingState:
    def test_a_new_habit_starts_daily_today_and_not_measured(self) -> None:
        state = make_state()
        assert state.build_frequency() == Daily()
        assert state.text(TextField.START) == "2026-11-01"
        assert state.selected_area == default_areas()[0]
        assert state.measurement_choice is MeasurementChoice.YES_NO
        assert state.build_measurement() is None
        assert state.build_reminder() is None
        assert not state.is_editing
        assert not state.advanced_visible

    def test_a_state_without_areas_has_none_selected(self) -> None:
        state = FormState([], TODAY)
        assert state.area_index == -1
        assert state.selected_area is None
        assert state.preview_row().detail == texts.NO_AREA

    def test_the_counters_start_at_three_a_week_and_four_a_month(self) -> None:
        state = make_state()
        assert (state.times(Period.WEEK), state.times(Period.MONTH)) == (3, 4)
        assert (state.interval_every, state.interval_choice) == (2, IntervalChoice.WEEKS)

    def test_the_counters_stay_inside_their_limits(self) -> None:
        state = make_state()
        assert state.adjust_times(Period.WEEK, -10) == 1
        assert state.adjust_times(Period.WEEK, 10) == 7
        assert state.adjust_times(Period.MONTH, 100) == 31
        assert state.adjust_interval(-5) == 1
        assert state.adjust_interval(1000) == 365


# ---------- The six frequencies ----------


class TestFrequency:
    def test_daily_is_the_default(self) -> None:
        assert make_state().build_frequency() == Daily()

    def test_rest_days_turn_daily_into_the_remaining_weekdays(self) -> None:
        state = make_state()
        pick_days(state, DayGroup.REST, SUN)
        assert state.build_frequency() == Weekdays(frozenset(Weekday) - {SUN})

    def test_resting_every_day_of_the_week_is_a_problem_of_the_form(self) -> None:
        state = make_state()
        pick_days(state, DayGroup.REST, *Weekday)
        with pytest.raises(FormError, match="descanso todos los días"):
            state.build_frequency()

    def test_specific_days_are_kept_in_week_order_not_click_order(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.WEEKDAYS)
        pick_days(state, DayGroup.WEEKDAYS, FRI, MON, WED)
        assert state.build_frequency() == Weekdays(frozenset({MON, WED, FRI}))

    def test_specific_days_need_at_least_one_day(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.WEEKDAYS)
        with pytest.raises(FormError, match="al menos un día"):
            state.build_frequency()

    def test_times_per_week_keeps_the_count_and_only_hints_at_days(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_WEEK)
        assert state.build_frequency() == Quota(3, Period.WEEK)
        pick_days(state, DayGroup.PREFERRED, WED, MON, FRI)
        assert state.build_frequency() == Quota(3, Period.WEEK, frozenset({MON, WED, FRI}))

    def test_times_per_month_without_dates_is_a_flexible_quota(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_MONTH)
        state.adjust_times(Period.MONTH, -1)
        assert state.build_frequency() == Quota(3, Period.MONTH)

    def test_times_per_month_with_as_many_dates_as_times_becomes_those_dates(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_MONTH)
        state.adjust_times(Period.MONTH, -2)
        state.set_dates([nov(20), nov(5)])
        assert state.build_frequency() == FixedDates((nov(5), nov(20)))

    def test_times_per_month_with_the_wrong_number_of_dates_is_reported_not_trimmed(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_MONTH)
        state.adjust_times(Period.MONTH, -1)
        state.set_dates([nov(4), nov(18)])
        with pytest.raises(FormError, match="2 de 3"):
            state.build_frequency()
        assert state.chosen_dates == {nov(4), nov(18)}

    def test_specific_dates_are_sorted_and_need_at_least_one(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        with pytest.raises(FormError, match="al menos una fecha"):
            state.build_frequency()
        state.set_dates([nov(27), nov(5), nov(12)])
        assert state.build_frequency() == FixedDates((nov(5), nov(12), nov(27)))

    @pytest.mark.parametrize(
        ("choice", "unit"),
        [
            (IntervalChoice.DAYS, IntervalUnit.DAYS),
            (IntervalChoice.WEEKS, IntervalUnit.WEEKS),
            (IntervalChoice.MONTHS, IntervalUnit.MONTHS),
        ],
    )
    def test_custom_is_an_interval_in_the_chosen_unit(
        self, choice: IntervalChoice, unit: IntervalUnit
    ) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.CUSTOM)
        state.interval_choice = choice
        state.adjust_interval(1)
        assert state.build_frequency() == Interval(3, unit)

    def test_custom_with_hand_picked_dates_is_a_set_of_dates(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.CUSTOM)
        state.interval_choice = IntervalChoice.PICKED_DATES
        with pytest.raises(FormError, match="al menos una fecha"):
            state.build_frequency()
        state.set_dates([nov(9)])
        assert state.build_frequency() == FixedDates((nov(9),))

    def test_what_was_picked_survives_a_visit_to_another_option(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        state.set_dates([nov(3), nov(30)])
        pick_days(state, DayGroup.PREFERRED, TUE)
        state.choose_frequency(FrequencyChoice.WEEKDAYS)
        state.choose_frequency(FrequencyChoice.TIMES_PER_MONTH)
        assert state.chosen_dates == {nov(3), nov(30)}
        state.choose_frequency(FrequencyChoice.TIMES_PER_WEEK)
        assert state.build_frequency() == Quota(3, Period.WEEK, frozenset({TUE}))

    def test_the_date_picker_belongs_to_three_of_the_zones(self) -> None:
        state = make_state()
        shown = {}
        for choice in FrequencyChoice:
            state.choose_frequency(choice)
            shown[choice] = state.uses_date_picker
        assert shown == {
            FrequencyChoice.DAILY: False,
            FrequencyChoice.WEEKDAYS: False,
            FrequencyChoice.TIMES_PER_WEEK: False,
            FrequencyChoice.TIMES_PER_MONTH: True,
            FrequencyChoice.FIXED_DATES: True,
            FrequencyChoice.CUSTOM: False,
        }
        state.interval_choice = IntervalChoice.PICKED_DATES
        assert state.uses_date_picker  # custom, with hand-picked dates


# ---------- The line under the frequency zone ----------


class TestFrequencyHint:
    def test_zones_without_a_line_have_no_hint(self) -> None:
        state = make_state()
        assert state.frequency_hint() is None
        state.choose_frequency(FrequencyChoice.WEEKDAYS)
        assert state.frequency_hint() is None

    def test_times_per_week_is_silent_when_the_preferred_days_match_the_count(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_WEEK)
        pick_days(state, DayGroup.PREFERRED, MON, WED, FRI)
        hint = state.frequency_hint()
        assert hint is not None
        assert (hint.text, hint.tone) == ("", HintTone.MUTED)

    def test_fewer_preferred_days_than_times_leaves_the_rest_to_the_person(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_WEEK)
        pick_days(state, DayGroup.PREFERRED, MON)
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.text == "Prefieres 1 día; los otros los decides tú."
        pick_days(state, DayGroup.PREFERRED, TUE)
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.text == "Prefieres 2 días; los otros los decides tú."

    def test_more_preferred_days_than_times_says_how_many_will_be_chosen(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_WEEK)
        pick_days(state, DayGroup.PREFERRED, MON, TUE, WED, THU)
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.text == "Prefieres 4 días para 3 veces: elegirás 3 de ellos."
        assert state.build_frequency() == Quota(3, Period.WEEK, frozenset({MON, TUE, WED, THU}))

    def test_times_per_month_without_dates_is_called_flexible(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_MONTH)
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.text == "Meta flexible: tú decides cuándo, sin fechas fijas."

    def test_times_per_month_counts_the_dates_and_warns_when_they_do_not_add_up(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_MONTH)
        state.adjust_times(Period.MONTH, -1)
        state.set_dates([nov(4), nov(18)])
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.tone is HintTone.WARNING
        assert hint.text.startswith("2 de 3 fechas elegidas")
        state.set_dates([nov(4), nov(18), nov(25)])
        hint = state.frequency_hint()
        assert hint is not None
        assert (hint.text, hint.tone) == ("✓ 3 de 3 fechas elegidas", HintTone.SUCCESS)

    def test_specific_dates_are_counted(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.text == "Aún no elegiste ninguna fecha."
        state.set_dates([nov(5)])
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.text == "1 fecha elegida"
        state.set_dates([nov(5), nov(6)])
        hint = state.frequency_hint()
        assert hint is not None
        assert hint.text == "2 fechas elegidas"

    def test_dates_outside_the_period_are_flagged_and_kept(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        state.set_dates([nov(5), nov(27)])
        state.toggle_end()
        state.set_text(TextField.END, "2026-11-20")
        assert state.out_of_range_dates() == [nov(27)]
        hint = state.frequency_hint()
        assert hint is not None
        assert (hint.text, hint.tone) == (texts.DATES_OUT_OF_RANGE, HintTone.WARNING)
        assert state.chosen_dates == {nov(5), nov(27)}

    def test_dates_before_the_start_are_outside_the_period_too(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        state.set_dates([date(2026, 10, 31)])
        assert state.out_of_range_dates() == [date(2026, 10, 31)]

    def test_nothing_is_outside_while_the_period_is_not_a_complete_date(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        state.set_dates([nov(5)])
        state.set_text(TextField.START, "mañana")
        assert state.validity_limits() == (None, None)
        assert state.out_of_range_dates() == []

    def test_an_end_that_is_switched_off_no_longer_limits(self) -> None:
        state = make_state()
        state.toggle_end()
        state.set_text(TextField.END, "2026-11-20")
        assert state.validity_limits() == (TODAY, date(2026, 11, 20))
        state.toggle_end()
        assert state.validity_limits() == (TODAY, None)


# ---------- Measurement ----------


class TestMeasurement:
    def test_yes_no_has_no_measurement(self) -> None:
        assert make_state().build_measurement() is None

    def test_units_are_suggested_by_area(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        assert state.unit_options()[:3] == ("vasos", "litros", "minutos")
        assert state.unit_options()[-1] == CUSTOM_UNIT
        state.select_area(1)  # career
        assert state.unit_options()[:2] == ("minutos", "horas")
        assert "páginas" in state.unit_options()

    def test_an_area_without_its_own_list_gets_the_generic_units(self) -> None:
        state = FormState([Area("otra", "Otra", "#112233")], TODAY)
        state.select_measurement(MeasurementChoice.QUANTITY)
        assert state.unit_options() == ("veces", "unidades", CUSTOM_UNIT)

    def test_a_duration_is_counted_in_minutes_or_hours(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.DURATION)
        assert state.unit_options() == ("minutos", "horas")

    def test_the_unit_follows_the_options_when_the_area_or_the_kind_changes(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        assert state.unit_choice == "vasos"
        state.select_area(2)  # finances has neither "vasos" nor "minutos"
        assert state.unit_choice == "pesos"
        state.choose_unit(len(state.unit_options()) - 1)
        assert state.unit_choice == CUSTOM_UNIT
        state.select_area(1)  # a custom unit is valid in every area
        assert state.unit_choice == CUSTOM_UNIT
        state.select_measurement(MeasurementChoice.DURATION)  # but not for a duration
        assert state.unit_choice == "minutos"

    def test_a_quantity_is_built_with_the_goal_and_unit(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        state.set_text(TextField.GOAL, "10")
        assert state.build_measurement() == Measurement(MeasurementKind.QUANTITY, 10, "vasos")

    def test_a_duration_accepts_a_comma_as_the_decimal_separator(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.DURATION)
        state.set_text(TextField.GOAL, "15,5")
        state.choose_unit(1)
        assert state.build_measurement() == Measurement(MeasurementKind.DURATION, 15.5, "horas")

    @pytest.mark.parametrize("goal", ["", "abc", "0", "-3", "nan", "inf", "1e999"])
    def test_a_goal_that_is_not_a_positive_number_breaks_the_goal_rule(self, goal: str) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        state.set_text(TextField.GOAL, goal)
        with pytest.raises(ValidationError) as caught:
            state.build_measurement()
        assert caught.value.code is ErrorCode.GOAL_INVALID
        assert describe_error(caught.value) == "La meta debe ser un número mayor que cero."

    def test_a_custom_unit_must_be_written(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        state.set_text(TextField.GOAL, "2")
        state.choose_unit(len(state.unit_options()) - 1)
        with pytest.raises(ValidationError) as caught:
            state.build_measurement()
        assert caught.value.code is ErrorCode.UNIT_REQUIRED
        state.set_text(TextField.CUSTOM_UNIT, "  capítulos ")
        assert state.build_measurement() == Measurement(MeasurementKind.QUANTITY, 2, "capítulos")

    def test_reference_goals_are_optional_numbers(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.DURATION)
        state.set_text(TextField.GOAL, "30")
        state.set_text(TextField.MINIMUM, "10")
        state.set_text(TextField.IDEAL, "45")
        assert state.build_measurement() == Measurement(
            MeasurementKind.DURATION, 30, "minutos", minimum=10, ideal=45
        )

    @pytest.mark.parametrize(
        ("field", "message"),
        [
            (TextField.MINIMUM, "La meta mínima debe ser un número."),
            (TextField.IDEAL, "La meta ideal debe ser un número."),
        ],
    )
    def test_a_reference_goal_that_is_not_a_number_is_a_problem_of_the_form(
        self, field: TextField, message: str
    ) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        state.set_text(TextField.GOAL, "5")
        state.set_text(field, "mucho")
        with pytest.raises(FormError) as caught:
            state.build_measurement()
        assert describe_error(caught.value) == message

    def test_a_minimum_above_the_ideal_breaks_the_bounds_rule(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        state.set_text(TextField.GOAL, "5")
        state.set_text(TextField.MINIMUM, "9")
        state.set_text(TextField.IDEAL, "3")
        with pytest.raises(ValidationError) as caught:
            state.build_measurement()
        assert caught.value.code is ErrorCode.BOUNDS_INVALID

    def test_going_back_to_yes_no_drops_the_measurement_but_keeps_the_typing(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.QUANTITY)
        state.set_text(TextField.GOAL, "7")
        state.select_measurement(MeasurementChoice.YES_NO)
        assert state.build_measurement() is None
        state.select_measurement(MeasurementChoice.QUANTITY)
        assert state.text(TextField.GOAL) == "7"


# ---------- Reminder ----------


class TestReminder:
    def test_without_the_reminder_switched_on_there_is_none(self) -> None:
        state = make_state()
        state.set_text(TextField.REMINDER_TIME, "garbage")
        assert state.build_reminder() is None

    def test_the_time_is_normalized_and_the_days_are_kept(self) -> None:
        state = make_state()
        state.toggle_reminder()
        assert state.build_reminder() == Reminder(time(20, 0))
        state.set_text(TextField.REMINDER_TIME, "8:30")
        pick_days(state, DayGroup.REMINDER, MON)
        assert state.build_reminder() == Reminder(time(8, 30), frozenset({MON}))

    @pytest.mark.parametrize("text", ["25:99", "", "ocho", "8:5"])
    def test_a_bad_time_is_reported(self, text: str) -> None:
        state = make_state()
        state.toggle_reminder()
        state.set_text(TextField.REMINDER_TIME, text)
        with pytest.raises(FormError, match="HH:MM"):
            state.build_reminder()


# ---------- What is handed to the service ----------


class TestBuildFields:
    def test_the_fields_carry_domain_values_and_dates_not_text(self) -> None:
        state = make_state("  Leer 10 páginas  ")
        state.set_text(TextField.DESCRIPTION, "Por gusto")
        state.set_text(TextField.NOTES, "Antes de dormir")
        state.set_text(TextField.START, "2026-11-03")
        state.toggle_end()
        state.set_text(TextField.END, "2026-12-31")
        fields = state.build_fields()
        assert fields == {
            "name": "Leer 10 páginas",
            "area_id": "salud",
            "frequency": Daily(),
            "description": "Por gusto",
            "notes": "Antes de dormir",
            "start": date(2026, 11, 3),
            "end": date(2026, 12, 31),
            "measurement": None,
            "reminder": None,
        }
        assert type(fields["start"]) is date

    def test_the_name_is_asked_for_before_anything_else(self) -> None:
        state = make_state("   ")
        state.choose_frequency(FrequencyChoice.WEEKDAYS)  # also incomplete
        with pytest.raises(FormError, match="nombre"):
            state.build_fields()

    def test_the_frequency_is_checked_before_the_measurement(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.WEEKDAYS)
        state.select_measurement(MeasurementChoice.QUANTITY)
        with pytest.raises(FormError, match="al menos un día"):
            state.build_fields()

    @pytest.mark.parametrize("start", ["mañana", "", "20261231", "2026-1-5", "2026-02-30"])
    def test_a_start_that_is_not_a_strict_date_is_rejected_with_its_own_message(
        self, start: str
    ) -> None:
        state = make_state()
        state.set_text(TextField.START, start)
        with pytest.raises(FormError, match=r"fecha de inicio.*AAAA-MM-DD"):
            state.build_fields()

    @pytest.mark.parametrize("end", ["pronto", "20261231", "2026-1-5"])
    def test_an_end_that_is_not_a_strict_date_is_rejected_with_its_own_message(
        self, end: str
    ) -> None:
        state = make_state()
        state.toggle_end()
        state.set_text(TextField.END, end)
        with pytest.raises(FormError, match=r"fecha de fin.*AAAA-MM-DD"):
            state.build_fields()

    def test_an_end_switched_on_but_left_blank_means_no_end(self) -> None:
        state = make_state()
        state.toggle_end()
        assert state.build_fields()["end"] is None

    def test_an_end_that_was_typed_and_then_switched_off_is_ignored(self) -> None:
        state = make_state()
        state.toggle_end()
        state.set_text(TextField.END, "garbage")
        state.toggle_end()
        assert state.build_fields()["end"] is None

    def test_a_state_without_areas_hands_over_no_area(self) -> None:
        state = FormState([], TODAY)
        state.set_text(TextField.NAME, "Leer")
        assert state.build_fields()["area_id"] == ""


# ---------- Saving through the service ----------


class TestSave:
    def test_a_new_habit_is_created(self) -> None:
        service = make_service()
        state = make_state("Leer")
        habit = state.save(service)
        assert habit.name == "Leer"
        assert service.habits() == (habit,)
        assert habit.start == TODAY

    def test_the_rules_of_the_domain_come_back_as_validation_errors(self) -> None:
        service = make_service()
        make_state("Leer").save(service)
        with pytest.raises(ValidationError) as caught:
            make_state("leer").save(service)
        assert caught.value.code is ErrorCode.NAME_DUPLICATE
        assert describe_error(caught.value) == "Ese hábito ya existe."
        assert len(service.habits()) == 1

    def test_an_end_before_the_start_is_left_to_the_domain(self) -> None:
        state = make_state()
        state.toggle_end()
        state.set_text(TextField.END, "2026-10-01")
        with pytest.raises(ValidationError) as caught:
            state.save(make_service())
        assert caught.value.code is ErrorCode.END_BEFORE_START
        assert "anterior" in describe_error(caught.value)

    def test_dates_outside_the_period_are_left_to_the_service(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        state.set_dates([nov(5), nov(27)])
        state.toggle_end()
        state.set_text(TextField.END, "2026-11-20")
        with pytest.raises(ValidationError) as caught:
            state.save(make_service())
        assert caught.value.code is ErrorCode.DATE_OUT_OF_RANGE
        assert "2026-11-27" in describe_error(caught.value)

    def test_a_store_that_fails_leaves_the_error_to_the_caller_and_stores_nothing(self) -> None:
        service = make_service(repository=FailingRepository(Snapshot(areas=default_areas())))
        with pytest.raises(StorageError):
            make_state("Leer").save(service)
        assert service.habits() == ()

    def test_editing_changes_the_habit_in_place_and_keeps_its_history(self) -> None:
        service = make_service()
        original_state = make_state()
        original_state.choose_frequency(FrequencyChoice.FIXED_DATES)
        original_state.set_text(TextField.NAME, "Visitar a la abuela")
        original_state.set_dates([nov(5), nov(12), nov(27)])
        original = original_state.save(service)
        service.mark(original.id, True, day=nov(5))

        editing = FormState(service.areas(), service.today(), habit=original)
        assert editing.chosen_dates == {nov(5), nov(12), nov(27)}
        editing.set_dates([nov(5), nov(27)])
        editing.set_text(TextField.NAME, "Visitar a Rosa")
        edited = editing.save(service)

        assert edited.id == original.id
        assert edited.name == "Visitar a Rosa"
        assert edited.frequency == FixedDates((nov(5), nov(27)))
        assert list(edited.completions) == [nov(5)]
        assert len(service.habits()) == 1

    def test_the_form_never_refuses_a_habit_for_going_past_the_recommended_maximum(self) -> None:
        # Warning about the maximum is the job of whoever opens the form, not of the form.
        habits = [
            Habit(id=n, name=f"Hábito {n}", area_id="salud", frequency=Daily(), start=nov(1))
            for n in range(1, RECOMMENDED_MAX_HABITS + 2)
        ]
        service = make_service(*habits)
        assert len(service.active_habits()) > RECOMMENDED_MAX_HABITS
        assert make_state("Uno más").save(service).name == "Uno más"
        assert len(service.habits()) == RECOMMENDED_MAX_HABITS + 2


# ---------- Editing: filling the state from a habit ----------


def a_habit(**overrides: Any) -> Habit:
    fields: dict[str, Any] = {
        "id": 7,
        "name": "Editar esto",
        "area_id": "carrera",
        "frequency": Daily(),
        "start": nov(1),
    }
    fields.update(overrides)
    return Habit(**fields)


class TestEditing:
    @pytest.mark.parametrize(
        ("frequency", "choice"),
        [
            (Daily(), FrequencyChoice.DAILY),
            (Weekdays(frozenset({MON, WED, FRI})), FrequencyChoice.WEEKDAYS),
            # "every day except Sunday" comes back as the days that remain
            (Weekdays(frozenset(Weekday) - {SUN}), FrequencyChoice.WEEKDAYS),
            (Quota(3, Period.WEEK), FrequencyChoice.TIMES_PER_WEEK),
            (Quota(2, Period.WEEK, frozenset({MON, THU})), FrequencyChoice.TIMES_PER_WEEK),
            (Quota(5, Period.MONTH), FrequencyChoice.TIMES_PER_MONTH),
            # "times per month" with dates was stored as the dates: it comes back as such
            (FixedDates((nov(5), nov(12))), FrequencyChoice.FIXED_DATES),
            (Interval(3, IntervalUnit.MONTHS), FrequencyChoice.CUSTOM),
            (Interval(10, IntervalUnit.DAYS), FrequencyChoice.CUSTOM),
        ],
    )
    def test_every_frequency_comes_back_as_it_was_saved(
        self, frequency: Frequency, choice: FrequencyChoice
    ) -> None:
        state = FormState(default_areas(), TODAY, habit=a_habit(frequency=frequency))
        assert state.frequency_choice is choice
        assert state.build_frequency() == frequency

    def test_the_dates_days_and_counts_are_recovered_exactly(self) -> None:
        state = FormState(
            default_areas(),
            TODAY,
            habit=a_habit(frequency=Quota(2, Period.WEEK, frozenset({MON, THU}))),
        )
        assert state.times(Period.WEEK) == 2
        assert state.days(DayGroup.PREFERRED) == {MON, THU}
        dated = FormState(
            default_areas(), TODAY, habit=a_habit(frequency=FixedDates((nov(5), nov(12))))
        )
        assert dated.chosen_dates == {nov(5), nov(12)}
        interval = FormState(
            default_areas(), TODAY, habit=a_habit(frequency=Interval(3, IntervalUnit.MONTHS))
        )
        assert (interval.interval_every, interval.interval_choice) == (3, IntervalChoice.MONTHS)

    def test_the_text_fields_the_area_and_the_period_are_recovered(self) -> None:
        habit = a_habit(
            description="Motivo", notes="Una nota", end=date(2026, 12, 31), area_id="finanzas"
        )
        state = FormState(default_areas(), TODAY, habit=habit)
        assert state.is_editing
        assert state.text(TextField.NAME) == "Editar esto"
        assert state.text(TextField.DESCRIPTION) == "Motivo"
        assert state.text(TextField.NOTES) == "Una nota"
        assert state.text(TextField.START) == "2026-11-01"
        assert state.has_end
        assert state.text(TextField.END) == "2026-12-31"
        assert state.selected_area == default_areas()[2]

    def test_a_measured_habit_recovers_goal_unit_and_reference_goals(self) -> None:
        habit = a_habit(
            measurement=Measurement(MeasurementKind.DURATION, 90, "horas", minimum=45, ideal=120)
        )
        state = FormState(default_areas(), TODAY, habit=habit)
        assert state.measurement_choice is MeasurementChoice.DURATION
        assert state.text(TextField.GOAL) == "90"
        assert state.unit_choice == "horas"
        assert (state.text(TextField.MINIMUM), state.text(TextField.IDEAL)) == ("45", "120")
        assert state.advanced_visible  # it has reference goals, so the advanced options open
        assert state.build_measurement() == habit.measurement

    def test_a_goal_stored_as_a_float_is_shown_without_a_trailing_zero(self) -> None:
        habit = a_habit(measurement=Measurement(MeasurementKind.QUANTITY, 90.0, "minutos"))
        assert FormState(default_areas(), TODAY, habit=habit).text(TextField.GOAL) == "90"
        decimal = a_habit(measurement=Measurement(MeasurementKind.QUANTITY, 2.5, "litros"))
        assert FormState(default_areas(), TODAY, habit=decimal).text(TextField.GOAL) == "2.5"

    def test_a_unit_outside_the_suggestions_comes_back_as_the_custom_one(self) -> None:
        habit = a_habit(measurement=Measurement(MeasurementKind.QUANTITY, 2, "capítulos"))
        state = FormState(default_areas(), TODAY, habit=habit)
        assert state.unit_choice == CUSTOM_UNIT
        assert state.text(TextField.CUSTOM_UNIT) == "capítulos"
        assert state.build_measurement() == habit.measurement

    def test_a_unit_in_the_list_of_the_area_is_not_a_custom_one(self) -> None:
        habit = a_habit(measurement=Measurement(MeasurementKind.QUANTITY, 5, "páginas"))
        state = FormState(default_areas(), TODAY, habit=habit)  # career suggests "páginas"
        assert state.unit_choice == "páginas"

    def test_a_reminder_recovers_its_time_days_and_opens_the_advanced_options(self) -> None:
        habit = a_habit(reminder=Reminder(time(8, 30), frozenset({MON})))
        state = FormState(default_areas(), TODAY, habit=habit)
        assert state.has_reminder
        assert state.text(TextField.REMINDER_TIME) == "08:30"
        assert state.days(DayGroup.REMINDER) == {MON}
        assert state.advanced_visible
        assert state.build_reminder() == habit.reminder

    def test_a_plain_habit_leaves_the_advanced_options_folded(self) -> None:
        assert not FormState(default_areas(), TODAY, habit=a_habit()).advanced_visible

    def test_saving_an_unchanged_form_gives_back_the_same_configuration(self) -> None:
        habit = a_habit(
            frequency=Quota(2, Period.WEEK, frozenset({MON, THU})),
            measurement=Measurement(MeasurementKind.QUANTITY, 10, "páginas", minimum=5),
            reminder=Reminder(time(7, 0), frozenset({TUE})),
            description="Motivo",
            notes="Nota",
            end=date(2026, 12, 31),
        )
        fields = FormState(default_areas(), TODAY, habit=habit).build_fields()
        assert fields["name"] == habit.name
        assert fields["area_id"] == habit.area_id
        assert fields["frequency"] == habit.frequency
        assert fields["start"] == habit.start
        assert fields["end"] == habit.end
        assert fields["measurement"] == habit.measurement
        assert fields["reminder"] == habit.reminder
        assert fields["description"] == "Motivo"
        assert fields["notes"] == "Nota"


# ---------- The preview ----------


class TestPreview:
    def test_a_daily_habit_reads_as_every_day_from_its_start(self) -> None:
        assert make_state("Leer 10 páginas").preview_sentence() == (
            "Leer 10 páginas — todos los días; desde el 1 nov."
        )

    def test_without_a_name_the_sentence_and_the_row_use_placeholders(self) -> None:
        state = make_state("")
        assert state.preview_sentence().startswith("Tu hábito — ")
        assert state.preview_row().title == "Nombre del hábito"

    def test_specific_days_are_named(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.WEEKDAYS)
        pick_days(state, DayGroup.WEEKDAYS, FRI, MON, WED)
        assert "los lunes, miércoles y viernes" in state.preview_sentence()

    def test_a_quota_never_claims_fixed_days(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_WEEK)
        sentence = state.preview_sentence()
        assert "3 veces por semana" in sentence
        assert "preferentemente" not in sentence
        assert "los lunes" not in sentence

    def test_preferred_days_are_only_a_preference(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_WEEK)
        pick_days(state, DayGroup.PREFERRED, MON, WED, FRI)
        assert "3 veces por semana, preferentemente lunes, miércoles y viernes" in (
            state.preview_sentence()
        )

    def test_picked_dates_are_written_out(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.TIMES_PER_MONTH)
        state.adjust_times(Period.MONTH, -2)
        state.set_dates([nov(5), nov(20)])
        assert "los días 5 y 20 de noviembre" in state.preview_sentence()

    def test_an_interval_is_written_out(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.CUSTOM)
        assert "cada 2 semanas" in state.preview_sentence()

    def test_rest_days_are_named_as_the_exception(self) -> None:
        state = make_state()
        pick_days(state, DayGroup.REST, SUN)
        assert "todos los días, excepto domingo" in state.preview_sentence()

    def test_an_incomplete_frequency_says_what_is_missing(self) -> None:
        state = make_state()
        state.choose_frequency(FrequencyChoice.FIXED_DATES)
        assert state.preview_sentence().startswith(
            "Leer — Elige al menos una fecha en el calendario."
        )

    def test_the_goal_appears_once_it_is_valid_whatever_the_reference_goals_say(self) -> None:
        state = make_state()
        state.select_measurement(MeasurementChoice.DURATION)
        assert "meta por ocasión" not in state.preview_sentence()
        state.set_text(TextField.GOAL, "15,5")
        state.choose_unit(1)
        assert "meta por ocasión: 15.5 horas" in state.preview_sentence()
        state.set_text(TextField.MINIMUM, "9")
        state.set_text(TextField.IDEAL, "3")  # the bounds rule is broken, the goal is not
        assert "meta por ocasión: 15.5 horas" in state.preview_sentence()
        assert state.preview_row().detail == "Salud · meta 15.5 horas"

    def test_the_period_and_the_reminder_are_mentioned(self) -> None:
        state = make_state()
        state.toggle_end()
        state.set_text(TextField.END, "2026-12-31")
        state.toggle_reminder()
        state.set_text(TextField.REMINDER_TIME, " 8:30 ")
        sentence = state.preview_sentence()
        assert "desde el 1 nov hasta el 31 dic" in sentence
        assert sentence.endswith("recordatorio a las 8:30.")

    def test_the_period_is_left_out_while_the_start_is_not_a_date(self) -> None:
        state = make_state()
        state.set_text(TextField.START, "mañana")
        assert "desde" not in state.preview_sentence()

    def test_the_row_shows_the_area_and_its_color_source(self) -> None:
        state = make_state("Leer")
        state.select_area(1)
        row = state.preview_row()
        assert (row.title, row.detail) == ("Leer", "Carrera")
        assert row.area == default_areas()[1]
