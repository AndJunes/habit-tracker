"""The habit form's window: the wiring between its widgets, the state and the service.

The rules live in ``FormState`` and are tested without a window (``tests/unit/ui``). These
tests drive the real widgets and check that what the person does reaches the service, and that
what the service says reaches the person.
"""

import logging
import tkinter as tk
from collections.abc import Callable, Iterator
from datetime import date, datetime, time
from pathlib import Path

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from habit_tracker.domain.frequency import Daily, FixedDates, Interval, Quota, Weekdays
from habit_tracker.domain.models import RECOMMENDED_MAX_HABITS, Habit, Measurement, Reminder
from habit_tracker.ports import StorageError
from habit_tracker.seed import default_areas
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository
from habit_tracker.storage.sqlite import SqliteRepository
from habit_tracker.ui.forms import modal
from habit_tracker.ui.forms.choices import TextField
from habit_tracker.ui.forms.habit_form import (
    MAX_WINDOW_HEIGHT,
    MIN_WINDOW_HEIGHT,
    WINDOW_WIDTH,
    HabitFormDialog,
)
from habit_tracker.ui.forms.parts import WeekdayChipRow
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.tkutil import widget_exists
from habit_tracker.ui.widgets.chips import SelectionChip
from habit_tracker.ui.widgets.date_picker import DatePicker
from habit_tracker.ui.widgets.soft_button import SoftButton
from habit_tracker.ui.widgets.soft_menu import SoftMenu

MON, TUE, WED, THU, FRI, SAT, SUN = Weekday
FREQUENCY_MENU = "Todos los días"  # the first entry of the frequency menu
MEASUREMENT_MENU = "Sí / No"  # the first entry of the measurement menu
INTERVAL_MENU = "días"  # the first entry of the "every" menu
SHOW_ADVANCED = "\N{FULLWIDTH PLUS SIGN} Mostrar opciones avanzadas"
MINUS = "\N{MINUS SIGN}"


def nov(day: int) -> date:
    return date(2026, 11, day)


class FailingRepository(MemoryRepository):
    """A store that can be switched to fail every write, as when the disk is full."""

    def __init__(self) -> None:
        super().__init__()
        self.failing = False
        for area in default_areas():
            self.save_area(area)

    def save_habit(self, habit: Habit) -> None:
        if self.failing:
            raise StorageError("disk full")
        super().save_habit(habit)


class FormDriver:
    """Operates a form the way a person would: through its widgets."""

    def __init__(self, dialog: HabitFormDialog) -> None:
        self.dialog = dialog
        self.saved: list[Habit] = []

    # ----- finding widgets -----

    def descendants(self, widget: tk.Misc | None = None) -> Iterator[tk.Misc]:
        for child in (widget or self.dialog).winfo_children():
            yield child
            yield from self.descendants(child)

    def named(self, name: str) -> tk.Misc:
        return next(w for w in self.descendants() if w.winfo_name() == name)

    def entry(self, field: TextField) -> tk.Entry:
        found = self.named(field.value)
        assert isinstance(found, tk.Entry)
        return found

    def chip(self, text: str, nth: int = 0) -> SelectionChip:
        chips = [w for w in self.descendants() if isinstance(w, SelectionChip) and w.text == text]
        assert chips, f"there is no chip {text!r}"
        return chips[nth]

    def button(self, text: str, nth: int = 0) -> SoftButton:
        buttons = [w for w in self.descendants() if isinstance(w, SoftButton) and w.text == text]
        assert buttons, f"there is no button {text!r}"
        return buttons[nth]

    def menu(self, first_option: str) -> SoftMenu:
        menus = [
            w
            for w in self.descendants()
            if isinstance(w, SoftMenu) and w.options and w.options[0] == first_option
        ]
        assert menus, f"there is no menu starting with {first_option!r}"
        return menus[0]

    def picker(self, nth: int = 0) -> DatePicker:
        return [w for w in self.descendants() if isinstance(w, DatePicker)][nth]

    def pickers(self) -> list[DatePicker]:
        return [w for w in self.descendants() if isinstance(w, DatePicker)]

    def day_rows(self) -> list[WeekdayChipRow]:
        return [w for w in self.descendants() if isinstance(w, WeekdayChipRow)]

    # ----- doing things -----

    def type_into(self, field: TextField, text: str) -> None:
        entry = self.entry(field)
        entry.delete(0, "end")
        entry.insert(0, text)

    def press_chip(self, text: str, nth: int = 0) -> None:
        self.chip(text, nth).command()

    def press(self, text: str, nth: int = 0) -> None:
        self.button(text, nth).command()

    def choose(self, first_option: str, index: int) -> None:
        self.menu(first_option).select(index)

    def pick(self, *days: date, nth: int = 0) -> None:
        for day in days:
            self.picker(nth).toggle(day)

    def submit(self) -> None:
        self.press("Crear hábito" if not self.dialog.form_state.is_editing else "Guardar cambios")

    def save(self) -> Habit:
        """Presses the save button and returns what was saved; fails if the form said no."""
        error = self.dialog.error_text
        self.submit()
        assert self.saved, f"the form did not save: {self.dialog.error_text or error!r}"
        return self.saved[-1]

    # ----- reading -----

    def label(self, name: str) -> tk.Label:
        found = self.named(name)
        assert isinstance(found, tk.Label)
        return found

    def text_of(self, name: str) -> str:
        return str(self.label(name).cget("text"))

    def labels(self) -> list[str]:
        return [str(w.cget("text")) for w in self.descendants() if isinstance(w, tk.Label)]

    @property
    def sentence(self) -> str:
        return self.text_of("preview_sentence")

    @property
    def hint(self) -> str:
        return self.text_of("frequency_hint")

    @property
    def is_open(self) -> bool:
        return widget_exists(self.dialog)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 1, 9, 0))


@pytest.fixture
def make_service(clock: FixedClock) -> Callable[..., HabitService]:
    """A service on the demo data of the fixed day, with no habits unless asked for."""

    def build(*, habits: bool = False, repository: MemoryRepository | None = None) -> HabitService:
        if repository is None:
            snapshot = build_demo_snapshot(clock.now().date())
            if not habits:
                snapshot.habits = []
            repository = MemoryRepository(snapshot)
        return HabitService(repository, clock)

    return build


@pytest.fixture
def service(make_service: Callable[..., HabitService]) -> HabitService:
    return make_service()


@pytest.fixture
def open_form(tk_root: tk.Tk) -> Callable[..., FormDriver]:
    """Opens the form hidden (new, or editing ``habit``) and returns the driver."""

    def open_(service: HabitService, *, name: str = "", habit: Habit | None = None) -> FormDriver:
        holder: list[FormDriver] = []
        dialog = HabitFormDialog(
            tk_root, service, habit=habit, on_saved=lambda saved: holder[0].saved.append(saved)
        )
        driver = FormDriver(dialog)
        holder.append(driver)
        dialog.withdraw()
        tk_root.update_idletasks()
        if habit is None and name:
            driver.type_into(TextField.NAME, name)
        return driver

    return open_


# ================= The six frequencies =================


def test_daily(service: HabitService, open_form: Callable[..., FormDriver]) -> None:
    form = open_form(service, name="Leer 10 páginas")
    assert len(form.dialog.winfo_children()) > 0
    areas = [w for w in form.descendants() if isinstance(w, SelectionChip) and w.color]
    assert len(areas) == 8
    assert areas[0].selected
    assert "Leer 10 páginas — todos los días" in form.sentence
    habit = form.save()
    assert habit.frequency == Daily()
    assert habit.start == nov(1)
    assert habit.end is None
    assert habit.measurement is None
    assert habit.reminder is None
    assert service.habits() == (habit,)
    assert not form.is_open


def test_specific_weekdays(service: HabitService, open_form: Callable[..., FormDriver]) -> None:
    form = open_form(service, name="Gimnasio")
    form.choose(FREQUENCY_MENU, 1)
    form.submit()
    assert "al menos un día" in form.dialog.error_text
    assert form.is_open
    for day in ("vie", "lun", "mié"):
        form.press_chip(day)
    assert "los lunes, miércoles y viernes" in form.sentence
    assert form.save().frequency == Weekdays(frozenset({MON, WED, FRI}))  # week order, not clicks


def test_times_per_week_claims_no_fixed_days(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Entrenar")
    form.choose(FREQUENCY_MENU, 2)
    sentence = form.sentence
    assert "3 veces por semana" in sentence
    assert "preferentemente" not in sentence
    assert "los lunes" not in sentence
    assert form.save().frequency == Quota(3, Period.WEEK)


def test_times_per_week_with_preferred_days(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Pádel")
    form.choose(FREQUENCY_MENU, 2)
    for day in ("lun", "mié", "vie"):
        form.press_chip(day)
    assert "3 veces por semana, preferentemente lunes, miércoles y viernes" in form.sentence
    habit = form.save()
    assert habit.frequency == Quota(3, Period.WEEK, frozenset({MON, WED, FRI}))
    assert isinstance(habit.frequency, Quota)
    assert habit.frequency.times == 3  # the count rules; the days are a preference


def test_more_preferred_days_than_times_is_explained_and_allowed(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Pádel")
    form.choose(FREQUENCY_MENU, 2)
    for day in ("lun", "mar", "mié", "jue"):
        form.press_chip(day)
    assert form.hint == "Prefieres 4 días para 3 veces: elegirás 3 de ellos."
    assert form.save().frequency == Quota(3, Period.WEEK, frozenset({MON, TUE, WED, THU}))


def test_the_counter_moves_within_its_limits(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Entrenar")
    form.choose(FREQUENCY_MENU, 2)
    for _ in range(10):
        form.press("+")
    assert "7 veces por semana" in form.sentence
    for _ in range(10):
        form.press(MINUS)
    assert "1 vez por semana" in form.sentence
    assert form.save().frequency == Quota(1, Period.WEEK)


def test_two_times_per_month_with_picked_dates(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Cita con amigas")
    form.choose(FREQUENCY_MENU, 3)
    form.press(MINUS)
    form.press(MINUS)  # 4 -> 2
    form.pick(nov(5), nov(20))
    assert form.hint.startswith("✓ 2 de 2")
    assert form.label("frequency_hint").cget("fg") == palette.ACCENT_TOTAL
    assert "los días 5 y 20 de noviembre" in form.sentence
    assert form.save().frequency == FixedDates((nov(5), nov(20)))  # the dates become occasions


def test_three_times_per_month_flexible_and_a_warning_for_incomplete_dates(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Salir a caminar")
    form.choose(FREQUENCY_MENU, 3)
    form.press(MINUS)  # 4 -> 3
    assert "sin fechas fijas" in form.hint
    assert form.save().frequency == Quota(3, Period.MONTH)

    form = open_form(service, name="Salir a nadar")
    form.choose(FREQUENCY_MENU, 3)
    form.press(MINUS)
    form.pick(nov(4), nov(18))  # only 2 of 3
    assert "2 de 3 fechas" in form.hint
    assert form.label("frequency_hint").cget("fg") == palette.TRASH_ACTIVE
    form.submit()
    assert "2 de 3" in form.dialog.error_text
    assert form.is_open
    assert form.dialog.form_state.chosen_dates == {nov(4), nov(18)}  # the warning drops nothing
    assert form.picker().dates() == [nov(4), nov(18)]
    form.picker().clear()  # "delete them all" goes back to flexible
    assert form.save().frequency == Quota(3, Period.MONTH)


def test_specific_dates(service: HabitService, open_form: Callable[..., FormDriver]) -> None:
    form = open_form(service, name="Visitar a la abuela")
    form.choose(FREQUENCY_MENU, 4)
    form.submit()
    assert "al menos una fecha" in form.dialog.error_text
    form.pick(nov(27), nov(5), nov(12), nov(12), nov(12))  # the 12th is set, dropped, set again
    assert form.picker().dates() == [nov(5), nov(12), nov(27)]
    assert "los días 5, 12 y 27 de noviembre" in form.sentence
    assert form.save().frequency == FixedDates((nov(5), nov(12), nov(27)))


def test_custom(service: HabitService, open_form: Callable[..., FormDriver]) -> None:
    form = open_form(service, name="Limpieza profunda")
    form.choose(FREQUENCY_MENU, 5)
    assert form.menu(INTERVAL_MENU).options == (
        "días",
        "semanas",
        "meses",
        "fechas elegidas a mano",
    )
    assert "cada 2 semanas" in form.sentence
    form.press("+")  # 2 -> 3
    form.choose(INTERVAL_MENU, 2)  # months
    habit = form.save()
    assert habit.frequency == Interval(3, IntervalUnit.MONTHS)

    editing = open_form(service, habit=habit)  # on editing it comes back as it was
    state = editing.dialog.form_state
    assert editing.menu(FREQUENCY_MENU).current() == 5
    assert state.interval_every == 3
    assert editing.menu(INTERVAL_MENU).current() == 2

    form = open_form(service, name="Fechas a mano")
    form.choose(FREQUENCY_MENU, 5)
    form.choose(INTERVAL_MENU, 3)  # "dates picked by hand"
    form.pick(nov(9))
    assert form.save().frequency == FixedDates((nov(9),))


def test_the_selection_survives_changing_the_option(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Cambio de opción")
    form.choose(FREQUENCY_MENU, 4)
    form.pick(nov(3), nov(30))
    form.choose(FREQUENCY_MENU, 1)  # to specific days…
    assert form.pickers() == []
    form.choose(FREQUENCY_MENU, 3)  # …and to times per month
    assert form.picker().dates() == [nov(3), nov(30)]


# ================= Editing, period, measurement and validations =================


def test_editing_recovers_the_dates_and_keeps_the_history(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Visitar a la abuela")
    form.choose(FREQUENCY_MENU, 4)
    form.pick(nov(5), nov(12), nov(27))
    habit = form.save()
    service.mark(habit.id, True, day=nov(5))

    form = open_form(service, habit=habit)
    assert form.dialog.title() == "Editar hábito"
    assert form.entry(TextField.NAME).get() == "Visitar a la abuela"
    assert form.entry(TextField.START).get() == "2026-11-01"
    assert form.menu(FREQUENCY_MENU).current() == 4
    assert form.picker().dates() == [nov(5), nov(12), nov(27)]  # the dates come back
    form.picker().remove(nov(12))
    form.type_into(TextField.NAME, "Visitar a la abuela Rosa")
    edited = form.save()
    assert edited.id == habit.id
    assert edited.frequency == FixedDates((nov(5), nov(27)))
    assert edited.name == "Visitar a la abuela Rosa"
    assert list(edited.completions) == [nov(5)]  # the history, untouched
    assert service.get_habit(habit.id) is edited
    assert len(service.habits()) == 1


def test_editing_recovers_preferred_days_measurement_and_advanced_options(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Pádel")
    form.choose(FREQUENCY_MENU, 2)
    for day in ("lun", "mié", "vie"):
        form.press_chip(day)
    form.choose(MEASUREMENT_MENU, 2)
    form.type_into(TextField.GOAL, "90")
    form.press(SHOW_ADVANCED)
    form.type_into(TextField.MINIMUM, "45")
    form.type_into(TextField.IDEAL, "120")
    form.press_chip("Quiero un recordatorio")
    form.type_into(TextField.REMINDER_TIME, "8:30")  # normalized to 08:30
    habit = form.save()
    assert habit.reminder == Reminder(time(8, 30))

    form = open_form(service, habit=habit)
    state = form.dialog.form_state
    assert form.menu(FREQUENCY_MENU).current() == 2
    chosen = {chip.text for chip in form.day_rows()[0].chips.values() if chip.selected}
    assert chosen == {"lun", "mié", "vie"}
    assert form.menu(MEASUREMENT_MENU).current() == 2
    assert form.entry(TextField.GOAL).get() == "90"
    assert state.advanced_visible  # it has reference goals and a reminder
    assert form.entry(TextField.MINIMUM).get() == "45"
    assert form.entry(TextField.IDEAL).get() == "120"
    assert form.entry(TextField.REMINDER_TIME).get() == "08:30"
    assert form.button("\N{MINUS SIGN} Ocultar opciones avanzadas")


def test_editing_a_measured_habit_with_a_custom_unit_brings_the_unit_back(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Leer")
    form.choose(MEASUREMENT_MENU, 1)
    form.choose("vasos", 6)  # "personalizada"
    form.type_into(TextField.CUSTOM_UNIT, "capítulos")
    form.type_into(TextField.GOAL, "2")
    habit = form.save()
    assert habit.measurement == Measurement(MeasurementKind.QUANTITY, 2, "capítulos")

    form = open_form(service, habit=habit)
    assert form.menu(MEASUREMENT_MENU).current() == 1
    assert form.entry(TextField.GOAL).get() == "2"
    assert form.entry(TextField.CUSTOM_UNIT).get() == "capítulos"
    assert form.menu("vasos").options[form.menu("vasos").current()] == "personalizada"


def test_dates_outside_the_validity_period(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Taller")
    form.choose(FREQUENCY_MENU, 4)
    form.pick(nov(5), nov(27))
    form.press_chip("Con fecha de finalización")
    form.type_into(TextField.END, "2026-11-20")  # the 27th is now outside
    assert form.picker().out_of_range_dates() == [nov(27)]
    assert "fuera del período" in form.hint
    form.pick(nov(25))  # nor can another one be picked outside
    assert nov(25) not in form.picker().dates()
    form.submit()
    assert "fuera del período" in form.dialog.error_text
    assert form.picker().dates() == [nov(5), nov(27)]  # nothing was dropped
    form.picker().remove(nov(27))
    habit = form.save()
    assert habit.end == nov(20)
    assert habit.frequency == FixedDates((nov(5),))

    before_the_start = open_form(service, name="Taller B")
    before_the_start.choose(FREQUENCY_MENU, 4)
    before_the_start.pick(date(2026, 10, 31))  # before the start
    assert before_the_start.picker().dates() == []


def test_changing_the_measurement_changes_the_fields(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Meditar")
    assert not [w for w in form.descendants() if w.winfo_name() == "goal"]  # yes/no: no fields
    form.choose(MEASUREMENT_MENU, 1)
    assert form.entry(TextField.GOAL)
    assert form.menu("vasos").options[:3] == ("vasos", "litros", "minutos")  # the Health units
    assert form.menu("vasos").options[-1] == "personalizada"
    form.submit()
    assert "meta" in form.dialog.error_text  # no goal, no saving
    form.type_into(TextField.GOAL, "0")
    form.submit()
    assert "mayor que cero" in form.dialog.error_text
    form.chip("Carrera").command()  # Career: other units
    assert form.menu("minutos").options[:2] == ("minutos", "horas")
    assert "páginas" in form.menu("minutos").options
    form.choose(MEASUREMENT_MENU, 2)  # duration
    assert form.menu("minutos").options == ("minutos", "horas")
    form.type_into(TextField.GOAL, "15,5")  # decimal comma
    form.choose("minutos", 1)
    assert "meta por ocasión: 15.5 horas" in form.sentence
    form.choose(MEASUREMENT_MENU, 1)
    form.choose("minutos", len(form.menu("minutos").options) - 1)  # "personalizada"
    form.submit()
    assert "unidad" in form.dialog.error_text
    form.type_into(TextField.CUSTOM_UNIT, "capítulos")
    form.type_into(TextField.GOAL, "2")
    habit = form.save()
    assert habit.measurement == Measurement(MeasurementKind.QUANTITY, 2, "capítulos")

    plain = open_form(service, name="Sin medir")
    plain.choose(MEASUREMENT_MENU, 1)
    plain.choose(MEASUREMENT_MENU, 0)  # back to yes/no
    assert not [w for w in plain.descendants() if w.winfo_name() == "goal"]
    assert plain.save().measurement is None


def test_invalid_input_is_not_saved_and_nothing_typed_is_lost(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    def fails(form: FormDriver, fragment: str) -> None:
        before = len(service.habits())
        form.submit()
        assert fragment in form.dialog.error_text, form.dialog.error_text
        assert form.is_open
        assert form.saved == []
        assert len(service.habits()) == before
        assert not form.dialog.is_saving  # it can be tried again

    fails(open_form(service, name=""), "nombre")

    open_form(service, name="Nombre repetido").save()
    duplicate = open_form(service, name="Nombre repetido")
    fails(duplicate, "ya existe")
    assert duplicate.entry(TextField.NAME).get() == "Nombre repetido"  # what was typed stays

    broken_start = open_form(service, name="Inicio roto")
    broken_start.type_into(TextField.START, "mañana")
    fails(broken_start, "formato AAAA-MM-DD")
    broken_start.type_into(TextField.START, "2026-11-10")
    broken_start.press_chip("Con fecha de finalización")
    broken_start.type_into(TextField.END, "2026-11-01")
    fails(broken_start, "anterior")
    assert broken_start.entry(TextField.END).get() == "2026-11-01"

    resting = open_form(service, name="Descanso total")
    resting.press(SHOW_ADVANCED)
    for day in ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"):
        resting.press_chip(day)
    fails(resting, "descanso")

    reminder = open_form(service, name="Recordar mal")
    reminder.press(SHOW_ADVANCED)
    reminder.press_chip("Quiero un recordatorio")
    reminder.type_into(TextField.REMINDER_TIME, "25:99")
    fails(reminder, "HH:MM")


@pytest.mark.parametrize("typed", ["20261231", "2026-1-5", "2026/11/05", "05-11-2026"])
def test_a_start_date_must_be_written_exactly_as_year_month_day(
    service: HabitService, open_form: Callable[..., FormDriver], typed: str
) -> None:
    form = open_form(service, name="Estricto")
    form.type_into(TextField.START, typed)
    form.submit()
    assert "formato AAAA-MM-DD" in form.dialog.error_text
    assert form.is_open
    assert service.habits() == ()


def test_advanced_options_rest_days_reminder_and_reference_goals(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Con todo")
    assert form.day_rows() == []  # folded by default
    form.press(SHOW_ADVANCED)
    assert len(form.day_rows()) == 1
    form.press_chip("dom")  # rests on Sunday
    assert "todos los días, excepto domingo" in form.sentence
    form.press_chip("Quiero un recordatorio")
    form.press_chip("lun", nth=1)  # it only sounds on Mondays
    form.choose(MEASUREMENT_MENU, 2)  # measuring brings up the minimum and the ideal
    form.type_into(TextField.GOAL, "30")
    form.type_into(TextField.MINIMUM, "10")
    form.type_into(TextField.IDEAL, "45")
    habit = form.save()
    assert habit.frequency == Weekdays(frozenset(Weekday) - {SUN})
    assert habit.reminder == Reminder(time(20, 0), frozenset({MON}))
    assert habit.measurement == Measurement(MeasurementKind.DURATION, 30, "minutos", 10, 45)


def test_the_advanced_options_follow_the_rest_of_the_form(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    rest_days = "Días de descanso (opcional)"
    form = open_form(service, name="Sigue al formulario")
    form.press(SHOW_ADVANCED)
    assert rest_days in form.labels()  # rest days: only with "every day"
    form.choose(FREQUENCY_MENU, 1)
    assert rest_days not in form.labels()
    form.choose(FREQUENCY_MENU, 0)
    assert rest_days in form.labels()
    assert "Metas de referencia (opcional)" not in form.labels()  # yes/no: nothing to refer to
    form.choose(MEASUREMENT_MENU, 1)
    assert "Metas de referencia (opcional)" in form.labels()
    assert form.entry(TextField.MINIMUM)
    assert form.entry(TextField.IDEAL)


def test_a_double_click_does_not_duplicate_the_habit(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Un solo hábito")
    button = form.button("Crear hábito")
    button.command()
    button.command()  # the second click arrives after the first one closed the dialog
    assert len(service.habits()) == 1
    assert len(form.saved) == 1


def test_everything_persists_after_closing_and_reopening(
    tk_root: tk.Tk, tmp_path: Path, clock: FixedClock, open_form: Callable[..., FormDriver]
) -> None:
    path = tmp_path / "habits.sqlite3"
    repository = SqliteRepository(path)
    for area in default_areas():
        repository.save_area(area)
    service = HabitService(repository, clock)

    open_form(service, name="Diario").save()
    form = open_form(service, name="Por días")
    form.choose(FREQUENCY_MENU, 1)
    form.press_chip("mar")
    form.save()
    form = open_form(service, name="Cupo")
    form.choose(FREQUENCY_MENU, 2)
    form.press_chip("jue")
    form.save()
    form = open_form(service, name="Fechas")
    form.choose(FREQUENCY_MENU, 4)
    form.pick(nov(6))
    form.choose(MEASUREMENT_MENU, 1)
    form.type_into(TextField.GOAL, "5")
    measured = form.save()
    service.mark(measured.id, True, day=nov(6), value=7)
    repository.close()

    reopened_repository = SqliteRepository(path)
    try:
        reopened = HabitService(reopened_repository, clock)
        assert [habit.frequency for habit in reopened.habits()] == [
            Daily(),
            Weekdays(frozenset({TUE})),
            Quota(3, Period.WEEK, frozenset({THU})),
            FixedDates((nov(6),)),
        ]
        persisted = reopened.habits()[3]
        assert persisted.measurement == Measurement(MeasurementKind.QUANTITY, 5, "vasos")
        assert persisted.completions == {nov(6): 7}
        assert persisted.start == nov(1)
    finally:
        reopened_repository.close()


# ================= Saving: what happens when it goes wrong =================


def test_a_failing_store_shows_an_error_keeps_the_form_open_and_can_be_retried(
    make_service: Callable[..., HabitService],
    open_form: Callable[..., FormDriver],
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = FailingRepository()
    service = make_service(repository=repository)
    form = open_form(service, name="Leer 10 páginas")
    form.type_into(TextField.DESCRIPTION, "Por gusto")
    repository.failing = True
    with caplog.at_level(logging.ERROR):
        form.submit()
    assert "No se pudo guardar" in form.dialog.error_text
    assert form.is_open
    assert form.saved == []
    assert not form.dialog.is_saving  # the button works again
    assert service.habits() == ()
    assert form.entry(TextField.NAME).get() == "Leer 10 páginas"  # what was typed stays
    assert form.entry(TextField.DESCRIPTION).get() == "Por gusto"
    assert "could not be saved" in caplog.text

    repository.failing = False
    form.submit()  # the same button, the same form
    assert form.dialog.is_saving is False
    assert [habit.name for habit in form.saved] == ["Leer 10 páginas"]
    assert not form.is_open
    assert len(service.habits()) == 1


def test_a_failing_store_leaves_the_flag_reset_even_when_it_fails_again(
    make_service: Callable[..., HabitService], open_form: Callable[..., FormDriver]
) -> None:
    repository = FailingRepository()
    repository.failing = True
    form = open_form(make_service(repository=repository), name="Leer")
    for _ in range(3):
        form.submit()
        assert not form.dialog.is_saving
        assert "No se pudo guardar" in form.dialog.error_text
    assert form.is_open


def test_an_unexpected_error_does_not_leave_the_form_stuck(
    service: HabitService,
    open_form: Callable[..., FormDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(**_: object) -> Habit:
        raise RuntimeError("bug")

    form = open_form(service, name="Leer")
    monkeypatch.setattr(service, "add_habit", explode)
    with pytest.raises(RuntimeError, match="bug"):
        form.dialog.submit()
    assert not form.dialog.is_saving
    assert form.is_open
    monkeypatch.undo()
    form.submit()
    assert len(form.saved) == 1


def test_a_domain_error_shows_its_message_and_keeps_the_form_open(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    open_form(service, name="Leer").save()
    form = open_form(service, name="LEER")
    form.submit()
    assert form.dialog.error_text == "Ese hábito ya existe."
    assert form.is_open
    form.type_into(TextField.NAME, "")
    form.submit()
    assert form.dialog.error_text == "Escribe primero el nombre del hábito."  # not appended
    form.type_into(TextField.NAME, "Escribir")
    form.save()


def test_the_form_closes_before_telling_who_opened_it(
    tk_root: tk.Tk, service: HabitService
) -> None:
    seen: list[bool] = []
    holder: list[HabitFormDialog] = []

    def on_saved(saved: Habit) -> None:
        seen.append(widget_exists(holder[0]))

    dialog = HabitFormDialog(tk_root, service, on_saved=on_saved)
    holder.append(dialog)
    dialog.withdraw()
    driver = FormDriver(dialog)
    driver.type_into(TextField.NAME, "Leer")
    driver.submit()
    assert seen == [False]
    assert len(service.habits()) == 1


def test_cancel_closes_without_saving(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="No lo guardes")
    form.press("Cancelar")
    assert not form.is_open
    assert form.saved == []
    assert service.habits() == ()


# ================= Chrome: titles, labels, notice, preview =================


def test_the_window_title_and_the_save_button_follow_the_mode(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    new = open_form(service, name="Leer")
    assert new.dialog.title() == "Nuevo hábito"
    assert new.button("Crear hábito")
    habit = new.save()
    editing = open_form(service, habit=habit)
    assert editing.dialog.title() == "Editar hábito"
    assert editing.button("Guardar cambios")
    heading = [
        w
        for w in editing.descendants()
        if isinstance(w, tk.Label) and w.cget("text") == "Editar hábito"
    ]
    assert heading


def test_the_window_is_a_fixed_width_resizable_in_height(
    tk_root: tk.Tk, service: HabitService
) -> None:
    dialog = HabitFormDialog(tk_root, service, on_saved=lambda saved: None)
    dialog.attributes("-alpha", 0.0)
    dialog.update_idletasks()  # Tk applies the geometry when the window is mapped
    size = dialog.geometry().split("+")[0]
    dialog.withdraw()
    assert dialog.resizable() == (False, True)
    width, height = (int(part) for part in size.split("x"))
    assert width == WINDOW_WIDTH
    assert MIN_WINDOW_HEIGHT <= height <= MAX_WINDOW_HEIGHT


def test_the_form_leaves_the_warning_about_many_habits_to_whoever_opens_it(
    make_service: Callable[..., HabitService], open_form: Callable[..., FormDriver]
) -> None:
    service = make_service(habits=True)
    assert len(service.active_habits()) >= RECOMMENDED_MAX_HABITS
    creating = open_form(service, name="Un séptimo")
    editing = open_form(service, habit=service.habits()[0])
    for form in (creating, editing):
        assert not [text for text in form.labels() if text.startswith("Ya tienes")]
    habit = creating.save()  # nothing in the form stands in the way
    assert habit.name == "Un séptimo"
    assert len(service.habits()) == RECOMMENDED_MAX_HABITS + 1


def test_the_preview_row_follows_the_name_and_the_area(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Leer 10 páginas")
    preview = [w for w in form.descendants() if isinstance(w, tk.Canvas) and w.find_all()][-1]

    def shown(canvas: tk.Canvas) -> list[str]:
        return [
            str(canvas.itemcget(item, "text"))
            for item in canvas.find_all()
            if canvas.type(item) == "text"
        ]

    assert shown(preview) == ["Leer 10 páginas", "Salud"]
    form.press_chip("Finanzas")
    assert shown(preview) == ["Leer 10 páginas", "Finanzas"]
    background = preview.find_all()[0]
    assert preview.itemcget(background, "fill") == default_areas()[2].soft_color
    form.choose(MEASUREMENT_MENU, 1)
    form.type_into(TextField.GOAL, "10")
    assert shown(preview)[1] == "Finanzas · meta 10 pesos"


def test_choosing_an_area_selects_only_its_chip(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Leer")
    form.press_chip("Relaciones")
    selected = [
        w.text
        for w in form.descendants()
        if isinstance(w, SelectionChip) and w.color and w.selected
    ]
    assert selected == ["Relaciones"]
    assert form.save().area_id == "relaciones"


def test_picking_a_date_in_the_calendar_fills_the_field_and_folds_the_calendar(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Calendario")
    form.press("Elegir en el calendario")
    assert len(form.pickers()) == 1
    assert form.picker().mode == "single"
    form.pick(nov(9))
    assert form.entry(TextField.START).get() == "2026-11-09"
    assert form.pickers() == []  # a date was chosen: the calendar folds away
    assert form.save().start == nov(9)


def test_the_calendar_of_the_end_cannot_pick_a_day_before_the_start(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Con fin")
    form.press_chip("Con fecha de finalización")
    form.press("Elegir en el calendario", nth=1)
    assert form.picker().minimum == nov(1)
    form.pick(date(2026, 10, 15))
    assert form.entry(TextField.END).get() == ""
    form.pick(nov(20))
    assert form.entry(TextField.END).get() == "2026-11-20"
    assert form.save().end == nov(20)


def test_the_calendar_button_toggles_and_the_end_can_be_switched_off(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Alterna")
    form.press("Elegir en el calendario")
    form.press("Elegir en el calendario")
    assert form.pickers() == []
    form.press_chip("Con fecha de finalización")
    form.type_into(TextField.END, "2026-12-01")
    form.press_chip("Con fecha de finalización")
    assert not [w for w in form.descendants() if w.winfo_name() == "end"]
    assert form.save().end is None


def test_changing_the_start_moves_the_limits_of_the_calendar_of_dates(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    form = open_form(service, name="Límites")
    form.choose(FREQUENCY_MENU, 4)
    form.pick(nov(5))
    assert form.picker().minimum == nov(1)
    form.type_into(TextField.START, "2026-11-10")
    assert form.picker().minimum == nov(10)
    assert form.picker().out_of_range_dates() == [nov(5)]
    assert "fuera del período" in form.hint
    form.type_into(TextField.START, "garbage")  # not a date yet: no limit at all
    assert form.picker().minimum is None
    assert form.picker().out_of_range_dates() == []


def test_return_in_the_name_field_is_bound_to_saving(
    service: HabitService, open_form: Callable[..., FormDriver]
) -> None:
    # A real key event needs the window system to give the window the focus, which makes the
    # test depend on (and disturb) the desktop: the binding is checked instead.
    form = open_form(service, name="Con Enter")
    assert form.entry(TextField.NAME).bind("<Return>")
    assert not form.entry(TextField.DESCRIPTION).bind("<Return>")


# ================= Making the dialog modal =================


def test_make_modal_grabs_a_window_that_is_on_screen(window: tk.Toplevel) -> None:
    modal.make_modal(window)
    assert window.grab_current() == window
    window.grab_release()


class UngrabbableWindow(tk.Toplevel):
    """A window that Tk refuses to grab, as one that is not on screen yet on some platforms."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.grab_attempts = 0
        self.retries: list[int] = []

    def grab_set(self) -> None:
        self.grab_attempts += 1
        raise tk.TclError("grab failed: window not viewable")

    def after(
        self, ms: int | str, func: Callable[..., object] | None = None, *args: object
    ) -> str:
        self.retries.append(int(ms))  # recorded, not scheduled: the test does not wait
        return ""


def test_make_modal_retries_while_the_window_cannot_be_grabbed_yet(tk_root: tk.Tk) -> None:
    top = UngrabbableWindow(tk_root)
    modal.make_modal(top)
    assert top.grab_attempts == 1
    assert top.retries == [modal.MODAL_RETRY_MS]


def test_make_modal_logs_when_it_gives_up(
    tk_root: tk.Tk, caplog: pytest.LogCaptureFixture
) -> None:
    top = UngrabbableWindow(tk_root)
    with caplog.at_level(logging.WARNING, logger=modal.__name__):
        modal.make_modal(top, attempt=modal.MAX_MODAL_ATTEMPTS)
    assert top.retries == []  # it does not try again
    assert "gave up making" in caplog.text
    assert str(modal.MAX_MODAL_ATTEMPTS) in caplog.text
    assert "not viewable" in caplog.text


def test_make_modal_keeps_trying_until_the_limit(tk_root: tk.Tk) -> None:
    top = UngrabbableWindow(tk_root)
    for attempt in range(modal.MAX_MODAL_ATTEMPTS + 1):
        modal.make_modal(top, attempt)
    assert len(top.retries) == modal.MAX_MODAL_ATTEMPTS


def test_make_modal_does_nothing_for_a_window_that_was_closed(tk_root: tk.Tk) -> None:
    top = tk.Toplevel(tk_root)
    top.destroy()
    modal.make_modal(top)  # no error, no retry
