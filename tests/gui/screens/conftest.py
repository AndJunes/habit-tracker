"""Fixtures for the screen tests: demo data on a fixed clock, and doubles for what needs a person.

The forms (new habit, edit habit, ask for a value) belong to another module and need a
human to answer, so they are replaced by recorders. The message boxes are injected too.
"""

import tkinter as tk
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import Habit, Snapshot
from habit_tracker.ports import StorageError
from habit_tracker.seed import default_areas
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository
from habit_tracker.ui.controllers import habit_actions
from habit_tracker.ui.theme.tkutil import widget_exists
from habit_tracker.ui.widgets.soft_button import SoftButton, TrashButton

TODAY = date(2026, 10, 29)  # a Thursday
NOW = datetime(2026, 10, 29, 9, 30)


class FlakyRepository(MemoryRepository):
    """A memory store whose writes can be made to fail, as a full disk would."""

    def __init__(self, snapshot: Snapshot) -> None:
        super().__init__(snapshot)
        self.failing = False
        self.writes_allowed: int | None = None  # fail every write after this many succeed

    def _check(self) -> None:
        if self.failing:
            raise StorageError("write failed")
        if self.writes_allowed is not None:
            if self.writes_allowed == 0:
                raise StorageError("write failed")
            self.writes_allowed -= 1

    def delete_habit(self, habit_id: int) -> None:
        self._check()
        super().delete_habit(habit_id)

    def set_completion(
        self, habit_id: int, day: date, *, done: bool, value: float | None = None
    ) -> None:
        self._check()
        super().set_completion(habit_id, day, done=done, value=value)

    def save_priority(self, note: Any) -> None:
        self._check()
        super().save_priority(note)


@dataclass
class RecordingDialogs:
    """Answers the yes/no questions from ``answers`` (then ``default``) and records everything."""

    default: bool = True
    answers: list[bool] = field(default_factory=list)
    asked: list[tuple[str, str]] = field(default_factory=list)
    shown: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, title, message)

    def ask_yes_no(self, title: str, message: str) -> bool:
        self.asked.append((title, message))
        return self.answers.pop(0) if self.answers else self.default

    def show_info(self, title: str, message: str) -> None:
        self.shown.append(("info", title, message))

    def show_warning(self, title: str, message: str) -> None:
        self.shown.append(("warning", title, message))

    def show_error(self, title: str, message: str) -> None:
        self.shown.append(("error", title, message))

    def kinds(self) -> list[str]:
        return [kind for kind, _, _ in self.shown]


@dataclass
class FormCall:
    master: tk.Misc
    service: HabitService
    habit: Habit | None
    on_saved: Callable[[Habit], None]


class FormRecorder:
    """Stands in for ``HabitFormDialog``: remembers how it was opened, opens nothing."""

    def __init__(self) -> None:
        self.calls: list[FormCall] = []

    def __call__(
        self,
        master: tk.Misc,
        service: HabitService,
        *,
        habit: Habit | None = None,
        on_saved: Callable[[Habit], None],
    ) -> None:
        self.calls.append(FormCall(master, service, habit, on_saved))

    def save(self, habit: Habit) -> None:
        """Play the person pressing "save" in the most recent form."""
        self.calls[-1].on_saved(habit)


class ValuePrompt:
    """Stands in for ``ask_value``: answers with ``answer`` (``None`` is a cancel)."""

    def __init__(self) -> None:
        self.answer: float | None = None
        self.calls: list[tuple[Habit, date]] = []

    def __call__(self, master: tk.Misc, habit: Habit, day: date) -> float | None:
        self.calls.append((habit, day))
        return self.answer


class Tree:
    """Finds things in a widget tree."""

    @staticmethod
    def descendants(widget: tk.Misc) -> Iterator[tk.Misc]:
        for child in widget.winfo_children():
            yield child
            yield from Tree.descendants(child)

    @staticmethod
    def buttons(widget: tk.Misc) -> dict[str, SoftButton]:
        """The soft buttons under ``widget`` by their text, including those hung from canvases."""
        found: dict[str, SoftButton] = {}
        for item in Tree.descendants(widget):
            if isinstance(item, SoftButton):
                found[item.text] = item
        return found

    @staticmethod
    def trash_buttons(widget: tk.Misc) -> list[TrashButton]:
        return [item for item in Tree.descendants(widget) if isinstance(item, TrashButton)]

    @staticmethod
    def texts(canvas: tk.Canvas) -> list[str]:
        return [
            str(canvas.itemcget(item, "text"))
            for item in canvas.find_all()
            if canvas.type(item) == "text"
        ]

    @staticmethod
    def all_texts(widget: tk.Misc) -> list[str]:
        """Every text drawn in the canvases and written in the labels under ``widget``."""
        found: list[str] = []
        for item in Tree.descendants(widget):
            if isinstance(item, tk.Canvas):
                found.extend(Tree.texts(item))
            elif isinstance(item, tk.Label):
                found.append(str(item.cget("text")))
        return found

    @staticmethod
    def enabled(button: tk.Canvas) -> bool:
        """A button that is drawn but off has no click bound."""
        return bool(button.bind("<Button-1>"))


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def repository() -> FlakyRepository:
    return FlakyRepository(build_demo_snapshot(TODAY))


@pytest.fixture
def service(repository: FlakyRepository, clock: FixedClock) -> HabitService:
    """The demo data: six habits, one of each kind of schedule."""
    return HabitService(repository, clock)


@pytest.fixture
def empty_service(clock: FixedClock) -> HabitService:
    """The default areas and no habits at all."""
    return HabitService(FlakyRepository(Snapshot(areas=default_areas())), clock)


@pytest.fixture
def add_daily_habit() -> Callable[[HabitService, str], Habit]:
    """Adds a plain daily habit to the service, starting 30 days before the demo's today."""

    def add(service: HabitService, name: str) -> Habit:
        return service.add_habit(
            name=name, area_id="salud", frequency=Daily(), start=date(2026, 9, 29)
        )

    return add


@pytest.fixture
def dialogs() -> RecordingDialogs:
    return RecordingDialogs()


@pytest.fixture
def forms(monkeypatch: pytest.MonkeyPatch) -> FormRecorder:
    recorder = FormRecorder()
    monkeypatch.setattr(habit_actions, "HabitFormDialog", recorder)
    return recorder


@pytest.fixture
def value_prompt(monkeypatch: pytest.MonkeyPatch) -> ValuePrompt:
    prompt = ValuePrompt()
    monkeypatch.setattr(habit_actions, "ask_value", prompt)
    return prompt


@pytest.fixture
def tree() -> type[Tree]:
    return Tree


@pytest.fixture
def private_root(tk_root: tk.Tk) -> Iterator[tk.Tk]:
    """A root of its own (its own Tcl interpreter), for tests that change what a root does.

    ``tk_root`` is requested only for the skip logic and the ``gui`` marker.
    """
    root = tk.Tk()
    root.withdraw()
    try:
        yield root
    finally:
        if widget_exists(root):
            root.destroy()
