"""The field for tomorrow's priority: it must never lose what is being typed."""

import tkinter as tk

import pytest

from habit_tracker.service import HabitService
from habit_tracker.ui.controllers.priority import PriorityEditor

from .conftest import FlakyRepository, RecordingDialogs


@pytest.fixture
def editor(tk_root: tk.Tk, service: HabitService, dialogs: RecordingDialogs) -> PriorityEditor:
    return PriorityEditor(service, tk_root, dialogs=dialogs)


def type_into(editor: PriorityEditor, text: str) -> None:
    """What the entry does when the person types: it writes to the variable it is bound to."""
    editor.variable.set(text)


def test_it_starts_with_what_was_saved_for_tomorrow(editor: PriorityEditor) -> None:
    assert editor.variable.get() == "Preparar la presentación"
    assert not editor.edited


def test_it_starts_empty_when_nothing_was_saved(
    tk_root: tk.Tk, empty_service: HabitService, dialogs: RecordingDialogs
) -> None:
    assert PriorityEditor(empty_service, tk_root, dialogs=dialogs).variable.get() == ""


def test_loading_the_saved_text_is_not_an_edit(editor: PriorityEditor) -> None:
    editor.sync()

    assert not editor.edited


def test_syncing_keeps_what_the_person_typed(editor: PriorityEditor) -> None:
    type_into(editor, "Estudiar para el examen")

    editor.sync()
    editor.sync()

    assert editor.variable.get() == "Estudiar para el examen"
    assert editor.edited


def test_a_field_the_person_emptied_stays_empty(editor: PriorityEditor) -> None:
    type_into(editor, "")

    editor.sync()

    assert editor.variable.get() == ""


def test_syncing_picks_up_a_text_saved_elsewhere_while_nothing_is_typed(
    editor: PriorityEditor, service: HabitService
) -> None:
    service.set_priority_for_tomorrow("Otra cosa")

    editor.sync()

    assert editor.variable.get() == "Otra cosa"


def test_saving_stores_the_trimmed_text_and_says_so(
    editor: PriorityEditor, service: HabitService, dialogs: RecordingDialogs
) -> None:
    type_into(editor, "  Llamar al banco  ")

    saved = editor.save()

    assert saved is True
    assert service.priority_for_tomorrow() == "Llamar al banco"
    assert dialogs.shown == [("info", "Lista", "Guardada. Mañana te estará esperando destacada.")]
    assert not editor.edited


def test_after_saving_the_next_sync_shows_the_stored_text(
    editor: PriorityEditor,
) -> None:
    type_into(editor, "  Llamar al banco  ")
    editor.save()

    editor.sync()

    assert editor.variable.get() == "Llamar al banco"


def test_saving_an_empty_field_asks_for_the_task_and_stores_nothing(
    editor: PriorityEditor, service: HabitService, dialogs: RecordingDialogs
) -> None:
    type_into(editor, "   ")

    saved = editor.save()

    assert saved is False
    assert service.priority_for_tomorrow() == "Preparar la presentación"
    assert dialogs.shown == [("info", "Aviso", "Escribe primero la tarea de mañana.")]


def test_a_failed_save_reports_it_and_keeps_the_text_so_it_can_be_retried(
    editor: PriorityEditor,
    service: HabitService,
    repository: FlakyRepository,
    dialogs: RecordingDialogs,
) -> None:
    type_into(editor, "Llamar al banco")
    repository.failing = True

    assert editor.save() is False

    assert dialogs.kinds() == ["error"]
    assert editor.variable.get() == "Llamar al banco"
    assert editor.edited
    assert service.priority_for_tomorrow() == "Preparar la presentación"

    repository.failing = False  # the save button is not left dead by the failure
    assert editor.save() is True
    assert service.priority_for_tomorrow() == "Llamar al banco"


def test_two_entries_bound_to_the_editor_show_the_same_text(
    tk_root: tk.Tk, editor: PriorityEditor
) -> None:
    first = tk.Entry(tk_root, textvariable=editor.variable)
    second = tk.Entry(tk_root, textvariable=editor.variable)

    first.delete(0, "end")
    first.insert(0, "Escrito en uno")

    assert second.get() == "Escrito en uno"
    assert editor.edited
