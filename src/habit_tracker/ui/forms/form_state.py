"""Everything the habit form knows and decides, with no window involved.

The form is a view over :class:`FormState`: the person's choices live here, not in the
widgets, so changing an option never loses what was picked for another one (the dates picked
for "times per month" are still there after a visit to "specific days"). The state also turns
those choices into domain objects, whose constructors enforce the rules of the domain; it only
adds the rules that belong to a form (the text format of dates and times, a selection that is
still missing) and leaves the rest to the service.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import TypedDict

from ...domain.enums import IntervalUnit, MeasurementKind, Period, Weekday
from ...domain.errors import ErrorCode, ValidationError
from ...domain.frequency import Daily, FixedDates, Frequency, Interval, Quota, Weekdays
from ...domain.models import Area, Habit, Measurement, Reminder
from ...service import HabitService
from ..strings import error_message
from . import preview_text, texts
from .choices import (
    DayGroup,
    FrequencyChoice,
    HintTone,
    IntervalChoice,
    MeasurementChoice,
    TextField,
)
from .numbers import format_number, parse_number
from .units import CUSTOM_UNIT, DURATION_UNITS, GENERIC_UNITS, UNITS_BY_AREA

DEFAULT_TIMES = {Period.WEEK: 3, Period.MONTH: 4}
MIN_TIMES = 1
MAX_TIMES = {Period.WEEK: len(Weekday), Period.MONTH: 31}
DEFAULT_INTERVAL = 2
MIN_INTERVAL = 1
MAX_INTERVAL = 365
DEFAULT_REMINDER_TIME = "20:00"
NO_AREA_ID = ""

# ``date.fromisoformat`` accepts other layouts since Python 3.11 ("20261231"), so the shape
# of what was typed is checked first. ASCII digits only: ``\d`` would take any script's.
_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIME_TEXT = re.compile(r"([0-9]{1,2}):([0-9]{2})")

_INTERVAL_UNITS = {
    IntervalChoice.DAYS: IntervalUnit.DAYS,
    IntervalChoice.WEEKS: IntervalUnit.WEEKS,
    IntervalChoice.MONTHS: IntervalUnit.MONTHS,
}
_CHOICE_OF_INTERVAL_UNIT = {unit: choice for choice, unit in _INTERVAL_UNITS.items()}
_PERIOD_CHOICES = {
    Period.WEEK: FrequencyChoice.TIMES_PER_WEEK,
    Period.MONTH: FrequencyChoice.TIMES_PER_MONTH,
}


class FormError(ValueError):
    """Something typed or picked in the form that cannot become a habit.

    The message is already worded for the person.
    """


class HabitFields(TypedDict):
    """What the service asks for to create or edit a habit, with the form's names."""

    name: str
    area_id: str
    frequency: Frequency
    description: str
    notes: str
    start: date
    end: date | None
    measurement: Measurement | None
    reminder: Reminder | None


@dataclass(frozen=True, slots=True)
class Hint:
    """The line under the frequency zone: what is missing or how the choice reads."""

    text: str
    tone: HintTone = HintTone.MUTED


@dataclass(frozen=True, slots=True)
class PreviewRow:
    """What the preview row of the form shows: how the habit will look in a list."""

    title: str
    detail: str
    area: Area | None


def describe_error(error: FormError | ValidationError) -> str:
    """The sentence for a problem found while building the habit."""
    if isinstance(error, ValidationError):
        return error_message(error)
    return str(error)


def parse_typed_date(text: str) -> date | None:
    """A date written as ``YYYY-MM-DD`` and in no other layout; ``None`` if it is not one."""
    candidate = text.strip()
    if not _DATE_TEXT.fullmatch(candidate):
        return None
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None  # right shape, impossible date (month 13, February 30)


def parse_typed_time(text: str) -> time | None:
    """A time written as ``HH:MM`` (``8:30`` is fine too); ``None`` if it is not one."""
    found = _TIME_TEXT.fullmatch(text.strip())
    if found is None:
        return None
    hour, minute = int(found.group(1)), int(found.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


class FormState:
    """The state of the habit form, filled from ``habit`` when it edits one."""

    def __init__(
        self,
        areas: Sequence[Area],
        today: date,
        *,
        habit: Habit | None = None,
    ) -> None:
        self.areas = tuple(areas)
        self.today = today
        self.habit_id = habit.id if habit is not None else None

        self._texts = dict.fromkeys(TextField, "")
        self._texts[TextField.START] = today.isoformat()
        self._texts[TextField.REMINDER_TIME] = DEFAULT_REMINDER_TIME
        self._days: dict[DayGroup, set[Weekday]] = {group: set() for group in DayGroup}
        self._times = dict(DEFAULT_TIMES)
        self._dates: set[date] = set()

        self.area_index = 0 if self.areas else -1
        self.frequency_choice = FrequencyChoice.DAILY
        self.interval_every = DEFAULT_INTERVAL
        self.interval_choice = IntervalChoice.WEEKS
        self.measurement_choice = MeasurementChoice.YES_NO
        self.unit_choice = ""
        self.has_end = False
        self.has_reminder = False
        self.advanced_visible = False

        if habit is not None:
            self._load(habit)

    # ---------- Reading and writing the simple fields ----------

    def text(self, field: TextField) -> str:
        return self._texts[field]

    def set_text(self, field: TextField, value: str) -> None:
        self._texts[field] = value

    def typed_date(self, field: TextField) -> date | None:
        """What a date field holds, as a date; ``None`` while it is not a complete one."""
        return parse_typed_date(self.text(field))

    def days(self, group: DayGroup) -> frozenset[Weekday]:
        return frozenset(self._days[group])

    def toggle_day(self, group: DayGroup, day: Weekday) -> None:
        self._days[group].symmetric_difference_update({day})

    def times(self, period: Period) -> int:
        """How many times per ``period`` the counter shows."""
        return self._times[period]

    def adjust_times(self, period: Period, step: int) -> int:
        """Moves the counter by ``step`` within its limits and returns the new value."""
        self._times[period] = min(MAX_TIMES[period], max(MIN_TIMES, self._times[period] + step))
        return self._times[period]

    def adjust_interval(self, step: int) -> int:
        """Moves the "every N" counter by ``step`` within its limits and returns the new value."""
        self.interval_every = min(MAX_INTERVAL, max(MIN_INTERVAL, self.interval_every + step))
        return self.interval_every

    @property
    def chosen_dates(self) -> frozenset[date]:
        """The dates picked in the calendar, kept when the frequency changes."""
        return frozenset(self._dates)

    def set_dates(self, days: Iterable[date]) -> None:
        self._dates = set(days)

    @property
    def is_editing(self) -> bool:
        return self.habit_id is not None

    def toggle_end(self) -> None:
        self.has_end = not self.has_end

    def toggle_reminder(self) -> None:
        self.has_reminder = not self.has_reminder

    def toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible

    # ---------- Area and measurement ----------

    @property
    def selected_area(self) -> Area | None:
        return self.areas[self.area_index] if self.area_index >= 0 else None

    def select_area(self, index: int) -> None:
        self.area_index = index
        self._keep_unit_valid()  # the suggested units depend on the area

    def select_measurement(self, choice: MeasurementChoice) -> None:
        self.measurement_choice = choice
        self._keep_unit_valid()

    def unit_options(self) -> tuple[str, ...]:
        """The units the menu offers: minutes or hours for durations, the area's otherwise."""
        if self.measurement_choice is MeasurementChoice.DURATION:
            return DURATION_UNITS
        area = self.selected_area
        suggested = UNITS_BY_AREA.get(area.id, GENERIC_UNITS) if area else GENERIC_UNITS
        return (*suggested, CUSTOM_UNIT)

    def choose_unit(self, index: int) -> None:
        self.unit_choice = self.unit_options()[index]

    def unit_value(self) -> str:
        """The unit the habit would be saved with: the menu's, or the one written by hand."""
        if self.unit_choice == CUSTOM_UNIT:
            return self.text(TextField.CUSTOM_UNIT).strip()
        return self.unit_choice

    def _keep_unit_valid(self) -> None:
        if self.measurement_choice is MeasurementChoice.YES_NO:
            return
        options = self.unit_options()
        if self.unit_choice not in options:
            self.unit_choice = options[0]

    # ---------- Frequency zone ----------

    def choose_frequency(self, choice: FrequencyChoice) -> None:
        self.frequency_choice = choice

    @property
    def uses_date_picker(self) -> bool:
        """Whether the frequency zone shows a calendar to pick dates."""
        choice = self.frequency_choice
        if choice in (FrequencyChoice.TIMES_PER_MONTH, FrequencyChoice.FIXED_DATES):
            return True
        return choice is FrequencyChoice.CUSTOM and self._picks_dates_by_hand

    @property
    def _picks_dates_by_hand(self) -> bool:
        return self.interval_choice is IntervalChoice.PICKED_DATES

    def validity_limits(self) -> tuple[date | None, date | None]:
        """``(start, end)`` as far as the fields hold a date: ``None`` where they do not yet."""
        end = self.typed_date(TextField.END) if self.has_end else None
        return self.typed_date(TextField.START), end

    def out_of_range_dates(self) -> list[date]:
        """The picked dates that fall outside the habit's period, oldest first."""
        start, end = self.validity_limits()
        return sorted(
            day
            for day in self._dates
            if (start is not None and day < start) or (end is not None and day > end)
        )

    def frequency_hint(self) -> Hint | None:
        """The line under the frequency zone, or ``None`` when that zone has no such line.

        It reports what does not add up (a pink warning) but never changes the picked dates.
        """
        choice = self.frequency_choice
        if choice is FrequencyChoice.TIMES_PER_WEEK:
            preferred = len(self._days[DayGroup.PREFERRED])
            times = self.times(Period.WEEK)
            if preferred and preferred < times:
                return Hint(texts.preferred_fewer(preferred))
            if preferred > times:
                return Hint(texts.preferred_more(preferred, times))
            return Hint("")
        if not self.uses_date_picker:
            return None
        count = len(self._dates)
        if self.out_of_range_dates():
            return Hint(texts.DATES_OUT_OF_RANGE, HintTone.WARNING)
        if choice is FrequencyChoice.TIMES_PER_MONTH:
            times = self.times(Period.MONTH)
            if count == 0:
                return Hint(texts.FLEXIBLE_GOAL)
            if count == times:
                return Hint(texts.dates_complete(count, times), HintTone.SUCCESS)
            return Hint(texts.dates_incomplete(count, times), HintTone.WARNING)
        return Hint(texts.NO_DATES_YET if count == 0 else texts.dates_count(count))

    # ---------- Building the habit ----------

    def build_frequency(self) -> Frequency:
        """The chosen frequency as a domain value, or the reason it cannot be built yet."""
        choice = self.frequency_choice
        if choice is FrequencyChoice.DAILY:
            rested = self._days[DayGroup.REST]
            if not rested:
                return Daily()
            remaining = frozenset(Weekday) - rested
            if not remaining:
                raise FormError(texts.EVERY_DAY_RESTED)
            return Weekdays(remaining)  # "every day except…" is, underneath, a list of days
        if choice is FrequencyChoice.WEEKDAYS:
            if not self._days[DayGroup.WEEKDAYS]:
                raise FormError(texts.WEEKDAYS_REQUIRED)
            return Weekdays(frozenset(self._days[DayGroup.WEEKDAYS]))
        if choice is FrequencyChoice.TIMES_PER_WEEK:
            return Quota(
                self.times(Period.WEEK), Period.WEEK, frozenset(self._days[DayGroup.PREFERRED])
            )
        if choice is FrequencyChoice.TIMES_PER_MONTH:
            times = self.times(Period.MONTH)
            if not self._dates:
                return Quota(times, Period.MONTH)
            if len(self._dates) != times:
                raise FormError(texts.dates_mismatch(len(self._dates), times))
            return FixedDates(tuple(sorted(self._dates)))
        if choice is FrequencyChoice.CUSTOM and not self._picks_dates_by_hand:
            return Interval(self.interval_every, _INTERVAL_UNITS[self.interval_choice])
        if not self._dates:  # specific dates, or custom with hand-picked dates
            raise FormError(texts.DATES_REQUIRED)
        return FixedDates(tuple(sorted(self._dates)))

    def build_measurement(self) -> Measurement | None:
        """The measurement, ``None`` for a yes/no habit; raises if the fields cannot build one."""
        core = self._measurement_core()
        if core is None:
            return None
        minimum = self._reference_goal(TextField.MINIMUM, texts.MINIMUM_NOT_A_NUMBER)
        ideal = self._reference_goal(TextField.IDEAL, texts.IDEAL_NOT_A_NUMBER)
        return Measurement(core.kind, core.goal, core.unit, minimum, ideal)

    def build_reminder(self) -> Reminder | None:
        if not self.has_reminder:
            return None
        at = parse_typed_time(self.text(TextField.REMINDER_TIME))
        if at is None:
            raise FormError(texts.REMINDER_TIME_FORMAT)
        return Reminder(at, self.days(DayGroup.REMINDER))

    def build_fields(self) -> HabitFields:
        """Everything the service asks for, or the first thing that is wrong.

        The name comes first because it is what the person writes first. Whatever the
        domain rules reject (a duplicate name, dates outside the period) is left to the
        service, which checks them against the rest of the habits.
        """
        name = self.text(TextField.NAME).strip()
        if not name:
            raise FormError(texts.NAME_FIRST)
        frequency = self.build_frequency()
        measurement = self.build_measurement()
        start = self._require_date(TextField.START, texts.START_FORMAT)
        end_text = self.text(TextField.END).strip()
        end = (
            self._require_date(TextField.END, texts.END_FORMAT)
            if self.has_end and end_text
            else None
        )
        area = self.selected_area
        return HabitFields(
            name=name,
            area_id=area.id if area else NO_AREA_ID,
            frequency=frequency,
            description=self.text(TextField.DESCRIPTION),
            notes=self.text(TextField.NOTES),
            start=start,
            end=end,
            measurement=measurement,
            reminder=self.build_reminder(),
        )

    def save(self, service: HabitService) -> Habit:
        """Creates the habit, or changes the one being edited, and returns it.

        Raises :class:`FormError` or :class:`ValidationError` when something is wrong, and
        ``StorageError`` when the store cannot write; nothing is saved in either case.
        """
        fields = self.build_fields()
        if self.habit_id is None:
            return service.add_habit(**fields)
        return service.edit_habit(self.habit_id, **fields)

    def _measurement_core(self) -> Measurement | None:
        """Kind, goal and unit alone: what the preview needs and the first things to check."""
        if self.measurement_choice is MeasurementChoice.YES_NO:
            return None
        goal_text = self.text(TextField.GOAL)
        goal = parse_number(goal_text)
        if goal is None:
            # The domain only takes numbers; text that is not one breaks the same rule.
            raise ValidationError(ErrorCode.GOAL_INVALID, goal=goal_text)
        kind = (
            MeasurementKind.DURATION
            if self.measurement_choice is MeasurementChoice.DURATION
            else MeasurementKind.QUANTITY
        )
        return Measurement(kind, goal, self.unit_value())

    def _reference_goal(self, field: TextField, message: str) -> int | float | None:
        text = self.text(field).strip()
        if not text:
            return None
        value = parse_number(text)
        if value is None:
            raise FormError(message)
        return value

    def _require_date(self, field: TextField, message: str) -> date:
        found = self.typed_date(field)
        if found is None:
            raise FormError(message)
        return found

    # ---------- Preview ----------

    def preview_row(self) -> PreviewRow:
        """The habit as a list row would show it, from whatever is filled in so far."""
        area = self.selected_area
        detail = area.name if area else texts.NO_AREA
        core = self._try_measurement_core()
        if core is not None:
            detail += texts.preview_row_goal(format_number(core.goal), core.unit)
        title = self.text(TextField.NAME).strip() or texts.PREVIEW_PLACEHOLDER_NAME
        return PreviewRow(title, detail, area)

    def preview_sentence(self) -> str:
        """The habit in a sentence; when the frequency is not complete, what is missing."""
        name = self.text(TextField.NAME).strip() or texts.PREVIEW_DEFAULT_NAME
        try:
            schedule = preview_text.frequency_in_words(self.build_frequency())
        except (FormError, ValidationError) as error:
            schedule = describe_error(error)
        core = self._try_measurement_core()
        start, end = self.validity_limits()
        reminder_time = self.text(TextField.REMINDER_TIME).strip() if self.has_reminder else ""
        return preview_text.preview_sentence(
            name=name,
            schedule=schedule,
            goal=(core.goal, core.unit) if core is not None else None,
            start=start,
            end=end,
            reminder_time=reminder_time,
        )

    def _try_measurement_core(self) -> Measurement | None:
        try:
            return self._measurement_core()
        except ValidationError:
            return None

    # ---------- Editing: filling the state from a habit ----------

    def _load(self, habit: Habit) -> None:
        self.set_text(TextField.NAME, habit.name)
        self.set_text(TextField.DESCRIPTION, habit.description)
        self.set_text(TextField.NOTES, habit.notes)
        self.set_text(TextField.START, habit.start.isoformat())
        if habit.end is not None:
            self.has_end = True
            self.set_text(TextField.END, habit.end.isoformat())
        for index, area in enumerate(self.areas):
            if area.id == habit.area_id:
                self.area_index = index
        self._load_frequency(habit.frequency)
        if habit.measurement is not None:
            self._load_measurement(habit.measurement)
        if habit.reminder is not None:
            self.has_reminder = True
            self.set_text(TextField.REMINDER_TIME, habit.reminder.at.strftime("%H:%M"))
            self._days[DayGroup.REMINDER] = set(habit.reminder.weekdays)
            self.advanced_visible = True

    def _load_frequency(self, frequency: Frequency) -> None:
        match frequency:
            case Daily():
                self.frequency_choice = FrequencyChoice.DAILY
            case Weekdays(days=days):
                self.frequency_choice = FrequencyChoice.WEEKDAYS
                self._days[DayGroup.WEEKDAYS] = set(days)
            case Quota(times=times, period=period, preferred=preferred):
                self.frequency_choice = _PERIOD_CHOICES[period]
                self._times[period] = times
                self._days[DayGroup.PREFERRED] = set(preferred)
            case FixedDates(dates=dates):
                self.frequency_choice = FrequencyChoice.FIXED_DATES
                self._dates = set(dates)
            case Interval(every=every, unit=unit):
                self.frequency_choice = FrequencyChoice.CUSTOM
                self.interval_every = every
                self.interval_choice = _CHOICE_OF_INTERVAL_UNIT[unit]
            case _:
                raise TypeError(f"unknown frequency: {frequency!r}")

    def _load_measurement(self, measurement: Measurement) -> None:
        self.measurement_choice = (
            MeasurementChoice.DURATION
            if measurement.kind is MeasurementKind.DURATION
            else MeasurementChoice.QUANTITY
        )
        self.set_text(TextField.GOAL, format_number(measurement.goal))
        for field, bound in (
            (TextField.MINIMUM, measurement.minimum),
            (TextField.IDEAL, measurement.ideal),
        ):
            self.set_text(field, format_number(bound) if bound is not None else "")
        if measurement.unit in self.unit_options() and measurement.unit != CUSTOM_UNIT:
            self.unit_choice = measurement.unit
        else:
            self.unit_choice = CUSTOM_UNIT
            self.set_text(TextField.CUSTOM_UNIT, measurement.unit)
        self._keep_unit_valid()
        if self.text(TextField.MINIMUM) or self.text(TextField.IDEAL):
            self.advanced_visible = True
