"""The texts of a habit row: subtitle, dimmed subtitle and the pill. No window is needed."""

from datetime import date

from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import Habit, Measurement
from habit_tracker.service import HabitService
from habit_tracker.ui.views import habit_labels

TODAY = date(2026, 10, 29)


def by_name(service: HabitService, name: str) -> Habit:
    return next(habit for habit in service.habits() if habit.name == name)


class TestPill:
    def test_a_weekly_quota_shows_its_progress(self, service: HabitService, today: date) -> None:
        train = by_name(service, "Entrenar 3 veces por semana")

        text = habit_labels.pill_text(service, train, today)

        assert text is not None
        assert text.endswith("/3 esta semana")

    def test_a_monthly_quota_says_this_month(self, service: HabitService, today: date) -> None:
        habit = service.add_habit(
            name="Cine", area_id="experiencias", frequency=Quota(2, Period.MONTH), start=today
        )

        assert habit_labels.pill_text(service, habit, today) == "0/2 este mes"

        service.mark(habit.id, True)
        assert habit_labels.pill_text(service, habit, today) == "1/2 este mes"

    def test_a_habit_due_on_few_weekdays_is_weekly(
        self, service: HabitService, today: date
    ) -> None:
        finances = by_name(service, "Viernes de finanzas (1 h)")

        assert habit_labels.pill_text(service, finances, today) == "semanal"

    def test_a_daily_habit_shows_its_streak_in_days(
        self, service: HabitService, today: date
    ) -> None:
        study = by_name(service, "Bloque de estudio")
        streak = service.current_streak(study)

        assert streak > 1
        assert habit_labels.pill_text(service, study, today) == f"🔥 {streak} días"

    def test_a_streak_of_one_is_singular(self, empty_service: HabitService, today: date) -> None:
        habit = empty_service.add_habit(
            name="Leer", area_id="carrera", frequency=Daily(), start=date(2026, 10, 28)
        )
        empty_service.mark(habit.id, True, day=date(2026, 10, 28))

        assert habit_labels.pill_text(empty_service, habit, today) == "🔥 1 día"

    def test_a_daily_habit_without_a_streak_has_no_pill(
        self, empty_service: HabitService, today: date
    ) -> None:
        habit = empty_service.add_habit(
            name="Leer", area_id="carrera", frequency=Daily(), start=today
        )

        assert habit_labels.pill_text(empty_service, habit, today) is None

    def test_a_habit_due_on_most_weekdays_shows_its_streak_not_weekly(
        self, empty_service: HabitService, today: date
    ) -> None:
        weekdays = frozenset(Weekday) - {Weekday.SUNDAY, Weekday.SATURDAY}
        habit = empty_service.add_habit(
            name="Oficina",
            area_id="carrera",
            frequency=Weekdays(weekdays),
            start=date(2026, 10, 26),
        )
        empty_service.mark(habit.id, True, day=date(2026, 10, 28))
        empty_service.mark(habit.id, True, day=date(2026, 10, 29))

        assert habit_labels.pill_text(empty_service, habit, today) == "🔥 2 días"

    def test_fixed_dates_count_occasions_in_a_row(
        self, empty_service: HabitService, today: date
    ) -> None:
        dates = (date(2026, 10, 15), date(2026, 10, 22), date(2026, 10, 29))
        habit = empty_service.add_habit(
            name="Cena", area_id="relaciones", frequency=FixedDates(dates), start=dates[0]
        )
        for day in dates[:2]:
            empty_service.mark(habit.id, True, day=day)

        assert habit_labels.pill_text(empty_service, habit, today) == "🔥 2 seguidas"

    def test_without_a_streak_fixed_dates_and_intervals_describe_their_frequency(
        self, empty_service: HabitService, today: date
    ) -> None:
        dinner = empty_service.add_habit(
            name="Cena",
            area_id="relaciones",
            frequency=FixedDates((date(2026, 11, 5), date(2026, 11, 12))),
            start=today,
        )
        cleaning = empty_service.add_habit(
            name="Limpieza",
            area_id="estilo_vida",
            frequency=Interval(2, IntervalUnit.WEEKS),
            start=today,
        )

        assert habit_labels.pill_text(empty_service, dinner, today) == "2 fechas elegidas"
        assert habit_labels.pill_text(empty_service, cleaning, today) == "cada 2 semanas"

    def test_a_missed_occasion_does_not_break_the_streak_of_the_ones_before(
        self, service: HabitService, today: date
    ) -> None:
        dinner = by_name(service, "Cena con amigas")  # three done, one missed, two to come

        assert habit_labels.pill_text(service, dinner, today) == "🔥 3 seguidas"

    def test_a_single_occasion_in_a_row_is_singular(
        self, empty_service: HabitService, today: date
    ) -> None:
        habit = empty_service.add_habit(
            name="Podar",
            area_id="estilo_vida",
            frequency=Interval(1, IntervalUnit.DAYS),
            start=date(2026, 10, 28),
        )
        empty_service.mark(habit.id, True, day=date(2026, 10, 28))

        assert habit_labels.pill_text(empty_service, habit, today) == "🔥 1 seguida"


class TestMutedSubtitle:
    def test_fixed_dates_say_when_the_next_one_is(self, service: HabitService) -> None:
        dinner = by_name(service, "Cena con amigas")

        assert habit_labels.muted_subtitle(service, dinner, date(2026, 11, 1)) == "próxima: 7 nov"

    def test_fixed_dates_with_none_left_say_so(self, service: HabitService) -> None:
        dinner = by_name(service, "Cena con amigas")

        assert habit_labels.muted_subtitle(service, dinner, date(2026, 11, 22)) == "sin más fechas"

    def test_an_interval_says_when_the_next_one_is(self, service: HabitService) -> None:
        cleaning = by_name(service, "Limpieza profunda")

        text = habit_labels.muted_subtitle(service, cleaning, date(2026, 10, 29))

        assert text.startswith("próxima: ")

    def test_a_finished_habit_says_when_it_ended(self, service: HabitService) -> None:
        english = by_name(service, "Inglés 30 minutos")

        assert (
            habit_labels.muted_subtitle(service, english, date(2026, 11, 20))
            == "terminó el 10 nov"
        )

    def test_a_habit_that_has_not_started_says_when_it_will(self, service: HabitService) -> None:
        dinner = by_name(service, "Cena con amigas")

        assert habit_labels.muted_subtitle(service, dinner, date(2026, 8, 1)) == "empieza el 1 sep"

    def test_other_habits_say_how_often_they_are_due(self, service: HabitService) -> None:
        finances = by_name(service, "Viernes de finanzas (1 h)")

        assert habit_labels.muted_subtitle(service, finances, TODAY) == "solo viernes"


class TestSubtitle:
    def test_a_plain_habit_shows_only_its_area(self, service: HabitService, today: date) -> None:
        train = by_name(service, "Entrenar 3 veces por semana")

        assert habit_labels.subtitle(train, "Salud", today) == "Salud"

    def test_a_measured_habit_shows_its_goal(self, service: HabitService) -> None:
        study = by_name(service, "Bloque de estudio")

        assert (
            habit_labels.subtitle(study, "Carrera", date(2026, 7, 1))
            == "Carrera · meta 90 minutos"
        )

    def test_a_measured_habit_done_shows_what_was_recorded(
        self, service: HabitService, today: date
    ) -> None:
        study = by_name(service, "Bloque de estudio")
        recorded = study.completions[today]

        text = habit_labels.subtitle(study, "Carrera", today)

        assert text == f"Carrera · {recorded:g} minutos (meta 90 minutos)"

    def test_a_goal_stored_as_a_float_is_written_without_a_decimal_point(self) -> None:
        habit = Habit(
            id=1,
            name="Leer",
            area_id="carrera",
            frequency=Daily(),
            start=TODAY,
            measurement=Measurement(MeasurementKind.QUANTITY, 10.0, "páginas"),
        )

        assert habit_labels.subtitle(habit, "Carrera", TODAY) == "Carrera · meta 10 páginas"
