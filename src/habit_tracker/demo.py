"""Demo data: six habits, one of each kind of schedule, with almost two months of history.

The dates are relative to the day the demo is built, so it always looks alive
(streaks running, the calendar painted) whenever it is opened. For a given day
the result is always the same: the random choices use a fixed seed.
"""

import random
from datetime import date, time, timedelta

from .domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from .domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from .domain.models import (
    Habit,
    ImportantDate,
    Measurement,
    PriorityNote,
    Reminder,
    Snapshot,
)
from .seed import default_areas

HISTORY_DAYS = 58


def build_demo_snapshot(today: date, *, seed: int = 7) -> Snapshot:
    """The demo data, taking ``today`` as the current day."""
    rng = random.Random(seed)
    start = today - timedelta(days=HISTORY_DAYS)

    def offset(days: int) -> date:
        """The date ``days`` away from today: negative is the past, positive the future."""
        return today + timedelta(days=days)

    def days_until_today(first: date) -> list[date]:
        return [first + timedelta(days=n) for n in range((today - first).days + 1)]

    def mark(habit: Habit, day: date, value: float | None = None) -> None:
        habit.completions[day] = value

    # 1. A weekly quota with preferred days (a preference, not an obligation).
    train = Habit(
        id=1,
        name="Entrenar 3 veces por semana",
        area_id="salud",
        frequency=Quota(
            3, Period.WEEK, frozenset({Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY})
        ),
        start=start,
        description="Mover el cuerpo sin obsesionarme con el calendario.",
    )
    this_monday = today - timedelta(days=today.weekday())
    for day in days_until_today(start):
        if day.weekday() in (0, 2, 4):
            two_weeks_ago = this_monday - timedelta(days=14) <= day < this_monday
            if two_weeks_ago or rng.random() < 0.8:  # the last two weeks: a streak is guaranteed
                mark(train, day)

    # 2. Daily, measured by duration, with reference goals.
    study = Habit(
        id=2,
        name="Bloque de estudio",
        area_id="carrera",
        frequency=Daily(),
        start=start,
        description="Una sola tarea importante, sin distracciones.",
        measurement=Measurement(MeasurementKind.DURATION, 90, "minutos", minimum=45, ideal=120),
    )
    for day in days_until_today(start):
        if day > today - timedelta(days=4) or rng.random() < 0.7:  # the last 4 days, always
            mark(study, day, rng.randint(60, 110))

    # 3. Daily, measured, with an end date (the day of the exam).
    english = Habit(
        id=3,
        name="Inglés 30 minutos",
        area_id="crecimiento",
        frequency=Daily(),
        start=start,
        end=offset(12),
        measurement=Measurement(MeasurementKind.DURATION, 30, "minutos"),
    )
    for day in days_until_today(start):
        if day > today - timedelta(days=6) or rng.random() < 0.75:
            mark(english, day, rng.randint(20, 45))

    # 4. Fixed dates: some have passed (three done, one missed), others are coming.
    dinner = Habit(
        id=4,
        name="Cena con amigas",
        area_id="relaciones",
        frequency=FixedDates(tuple(offset(n) for n in (-47, -33, -19, -5, 9, 23))),
        start=start,
    )
    for n in (-47, -33, -19):
        mark(dinner, offset(n))

    # 5. An interval: every two weeks since it began.
    cleaning = Habit(
        id=5,
        name="Limpieza profunda",
        area_id="estilo_vida",
        frequency=Interval(2, IntervalUnit.WEEKS),
        start=offset(-54),
    )
    for n in (-54, -40, -26, -12):
        mark(cleaning, offset(n))

    # 6. A fixed weekday, with a reminder.
    finances = Habit(
        id=6,
        name="Viernes de finanzas (1 h)",
        area_id="finanzas",
        frequency=Weekdays(frozenset({Weekday.FRIDAY})),
        start=start,
        reminder=Reminder(time(18, 0)),
    )
    for day in days_until_today(start):
        if day.weekday() == 4 and rng.random() < 0.9:
            mark(finances, day)

    return Snapshot(
        areas=default_areas(),
        habits=[train, study, english, dinner, cleaning, finances],
        important_dates=[
            ImportantDate(offset(5), "Entrega del informe"),
            ImportantDate(offset(12), "Examen de inglés"),
            ImportantDate(offset(22), "Viaje de fin de semana"),
        ],
        priority=PriorityNote(offset(1), "Preparar la presentación"),
    )
