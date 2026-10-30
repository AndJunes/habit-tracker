"""The closed sets of options the habit form offers, shared by the state and the sections."""

from enum import IntEnum, StrEnum


class FrequencyChoice(IntEnum):
    """The entries of the "how often" menu, in the order they are listed."""

    DAILY = 0
    WEEKDAYS = 1
    TIMES_PER_WEEK = 2
    TIMES_PER_MONTH = 3
    FIXED_DATES = 4
    CUSTOM = 5


class IntervalChoice(IntEnum):
    """The entries of the "every" menu of a custom frequency."""

    DAYS = 0
    WEEKS = 1
    MONTHS = 2
    PICKED_DATES = 3  # not an interval: the person picks the dates by hand


class MeasurementChoice(IntEnum):
    """The entries of the "how to measure" menu."""

    YES_NO = 0
    QUANTITY = 1
    DURATION = 2


class DayGroup(StrEnum):
    """The separate sets of weekdays the form keeps, so that none overwrites another."""

    WEEKDAYS = "weekdays"  # "specific days"
    PREFERRED = "preferred"  # "times per week": a preference, not an obligation
    REST = "rest"  # "every day" except these
    REMINDER = "reminder"  # the days a reminder sounds


class TextField(StrEnum):
    """Every free-text field. The values double as the names of the entry widgets."""

    NAME = "name"
    DESCRIPTION = "description"
    NOTES = "notes"
    START = "start"
    END = "end"
    GOAL = "goal"
    CUSTOM_UNIT = "custom_unit"
    MINIMUM = "minimum"
    IDEAL = "ideal"
    REMINDER_TIME = "reminder_time"


class HintTone(StrEnum):
    """How a hint line under the frequency zone is colored."""

    MUTED = "muted"
    WARNING = "warning"
    SUCCESS = "success"
