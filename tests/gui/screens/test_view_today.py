"""The "Hoy" tab: rows, delete mode, the priority card and what happens when things fail."""

import tkinter as tk
from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.models import PriorityNote
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository
from habit_tracker.ui.theme import palette
from habit_tracker.ui.views.today import CONTENT_WIDTH, ROW_HEIGHT, TodayView

from .conftest import (
    NOW,
    FlakyRepository,
    FormRecorder,
    RecordingDialogs,
    Tree,
    ValuePrompt,
)

EDIT_SEQUENCES = ("<Button-2>", "<Button-3>", "<Control-Button-1>")
ADD, DELETE_MODE = "+ Agregar hábito", "Eliminar hábito…"


@pytest.fixture
def make_view(
    window: tk.Toplevel,
    dialogs: RecordingDialogs,
    forms: FormRecorder,
    value_prompt: ValuePrompt,
) -> Callable[[HabitService], TodayView]:
    """Builds a mapped tab over a service; the dialogs and forms are the doubles."""

    def make(service: HabitService) -> TodayView:
        view = TodayView(window, service, dialogs=dialogs)
        view.pack()
        window.update()
        return view

    return make


@pytest.fixture
def view(make_view: Callable[[HabitService], TodayView], service: HabitService) -> TodayView:
    return make_view(service)


def rows(view: TodayView) -> list[tk.Canvas]:
    return [child for child in view.list_frame.winfo_children() if isinstance(child, tk.Canvas)]


def row_of(view: TodayView, name: str) -> tk.Canvas:
    return next(row for row in rows(view) if name in Tree.texts(row))


def click(widget: tk.Misc, sequence: str = "<Button-1>") -> None:
    widget.update()  # a widget that was just drawn must be mapped to receive events
    widget.event_generate(sequence, x=10, y=10)
    widget.update()


def button_texts(view: TodayView) -> list[str]:
    return [b.text for b in view.buttons_frame.winfo_children() if hasattr(b, "text")]


def trash_buttons(view: TodayView) -> list[tk.Canvas]:
    return list(Tree.trash_buttons(view.list_frame))


def with_priority_today(clock: FixedClock, text: str) -> HabitService:
    snapshot = build_demo_snapshot(NOW.date())
    snapshot.priority = PriorityNote(NOW.date(), text)
    return HabitService(MemoryRepository(snapshot), clock)


class TestRows:
    def test_there_is_a_row_per_habit_with_the_gestures_for_editing(
        self, view: TodayView, service: HabitService
    ) -> None:
        drawn = rows(view)

        assert len(drawn) == len(service.habits())
        for row in drawn:
            for sequence in EDIT_SEQUENCES:
                assert row.bind(sequence), sequence

    def test_a_row_is_as_big_as_the_design_says(self, view: TodayView) -> None:
        row = rows(view)[0]

        assert (int(row["width"]), int(row["height"])) == (CONTENT_WIDTH, ROW_HEIGHT)

    def test_a_click_on_the_row_marks_the_habit_and_paints_it_done(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        name = "Entrenar 3 veces por semana"
        train = next(h for h in service.habits() if h.name == name)
        assert not train.is_done(today)
        before = Tree.texts(row_of(view, name))

        click(row_of(view, name))

        assert service.get_habit(train.id).is_done(today)
        after = Tree.texts(row_of(view, name))
        assert before != after  # the pill counted one more this week

    def test_a_second_click_unmarks_it(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        name = "Entrenar 3 veces por semana"
        train = next(h for h in service.habits() if h.name == name)

        click(row_of(view, name))
        click(row_of(view, name))

        assert not service.get_habit(train.id).is_done(today)

    @pytest.mark.parametrize("sequence", EDIT_SEQUENCES)
    def test_right_click_control_click_and_button_2_open_the_editor(
        self, view: TodayView, service: HabitService, forms: FormRecorder, sequence: str
    ) -> None:
        name = "Bloque de estudio"
        study = next(h for h in service.habits() if h.name == name)

        click(row_of(view, name), sequence)

        (call,) = forms.calls
        assert call.habit is study
        assert call.master is view

    def test_a_row_that_is_not_due_today_is_dimmed_and_cannot_be_marked(
        self, view: TodayView, service: HabitService, forms: FormRecorder, today: date
    ) -> None:
        name = "Viernes de finanzas (1 h)"  # today is a Thursday
        finances = next(h for h in service.habits() if h.name == name)
        row = row_of(view, name)

        assert not row.bind("<Button-1>")
        assert "solo viernes" in Tree.texts(row)
        click(row)
        assert not service.get_habit(finances.id).is_done(today)

        click(row, "<Button-3>")  # but it can still be edited
        assert forms.calls[-1].habit is finances

    def test_the_subtitle_of_a_measured_habit_shows_the_goal(self, view: TodayView) -> None:
        texts = Tree.texts(row_of(view, "Inglés 30 minutos"))

        assert any(text.endswith("(meta 30 minutos)") for text in texts)

    def test_a_failed_write_is_reported_and_the_row_keeps_working(
        self,
        view: TodayView,
        service: HabitService,
        repository: FlakyRepository,
        dialogs: RecordingDialogs,
        today: date,
    ) -> None:
        name = "Entrenar 3 veces por semana"
        train = next(h for h in service.habits() if h.name == name)
        repository.failing = True

        click(row_of(view, name))

        assert dialogs.kinds() == ["error"]
        assert not service.get_habit(train.id).is_done(today)

        repository.failing = False
        click(row_of(view, name))

        assert service.get_habit(train.id).is_done(today)
        assert dialogs.kinds() == ["error"]


class TestHeaderAndBanner:
    def test_it_shows_the_weekday_the_date_and_how_many_habits_are_done(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        done, due = service.day_progress(today)

        texts = Tree.all_texts(view.header_frame)

        assert "jueves" in texts
        assert "Hoy es 29 de octubre" in texts
        assert f"{done}/{due}" in texts

    def test_the_ring_follows_the_progress_after_marking(
        self, view: TodayView, service: HabitService, today: date
    ) -> None:
        before = service.day_progress(today)

        click(row_of(view, "Entrenar 3 veces por semana"))

        after = service.day_progress(today)
        assert after[0] == before[0] + 1
        assert f"{after[0]}/{after[1]}" in Tree.all_texts(view.header_frame)

    def test_the_priority_written_last_night_gets_its_card(
        self, make_view: Callable[[HabitService], TodayView], clock: FixedClock
    ) -> None:
        text = "Terminar el informe y enviarlo antes de las cinco de la tarde, sin distraerme"
        view = make_view(with_priority_today(clock, text))

        texts = Tree.all_texts(view.banner_frame)

        assert texts == ["PRIORIDAD DE HOY · UNA SOLA TAREA", text]

    def test_there_is_no_card_when_the_priority_is_for_another_day(self, view: TodayView) -> None:
        assert Tree.all_texts(view.banner_frame) == []  # the demo's note is for tomorrow

    def test_a_long_priority_makes_the_card_taller(
        self, make_view: Callable[[HabitService], TodayView], clock: FixedClock
    ) -> None:
        short = make_view(with_priority_today(clock, "Corto"))
        short_height = int(short.banner_frame.winfo_children()[0]["height"])
        long = make_view(with_priority_today(clock, "palabra " * 40))

        assert int(long.banner_frame.winfo_children()[0]["height"]) > short_height


class TestEmpty:
    def test_without_habits_it_invites_to_create_the_first_one(
        self, make_view: Callable[[HabitService], TodayView], empty_service: HabitService
    ) -> None:
        view = make_view(empty_service)

        assert "No tienes hábitos todavía.\n¡Agrega el primero!" in Tree.all_texts(view.list_frame)
        assert rows(view) == []
        assert button_texts(view) == [ADD, DELETE_MODE]

    def test_the_delete_button_says_there_is_nothing_to_delete(
        self,
        make_view: Callable[[HabitService], TodayView],
        empty_service: HabitService,
        dialogs: RecordingDialogs,
    ) -> None:
        view = make_view(empty_service)

        click(Tree.buttons(view.buttons_frame)[DELETE_MODE])

        assert not view.delete_mode.active
        assert dialogs.shown == [("info", "Aviso", "No hay hábitos para eliminar.")]


class TestAddButton:
    def test_it_opens_the_form_and_the_list_grows_once_a_habit_is_saved(
        self,
        view: TodayView,
        service: HabitService,
        forms: FormRecorder,
        dialogs: RecordingDialogs,
    ) -> None:
        total = len(rows(view))
        dialogs.answers = [True]  # the demo is at the recommended limit: "yes, another one"

        click(Tree.buttons(view.buttons_frame)[ADD])

        (call,) = forms.calls
        assert call.habit is None
        new = service.add_habit(
            name="Nuevo", area_id="salud", frequency=service.habits()[1].frequency
        )
        forms.save(new)
        assert len(rows(view)) == total + 1


class TestDeleteMode:
    def test_the_buttons_and_trash_cans_follow_the_selection(
        self, view: TodayView, service: HabitService
    ) -> None:
        total = len(service.habits())
        habits = service.habits()
        assert button_texts(view) == [ADD, DELETE_MODE]
        assert trash_buttons(view) == []

        click(Tree.buttons(view.buttons_frame)[DELETE_MODE])
        assert view.delete_mode.active
        assert button_texts(view) == ["Cancelar", "Eliminar"]
        assert len(trash_buttons(view)) == total
        assert all(t.state == "normal" for t in trash_buttons(view))

        view.delete_mode.toggle(habits[0])
        view.delete_mode.toggle(habits[2])
        assert sum(1 for t in trash_buttons(view) if t.state == "active") == 2
        assert button_texts(view) == ["Cancelar", "Eliminar 2 hábitos"]

        view.delete_mode.toggle(habits[2])
        assert button_texts(view) == ["Cancelar", "Eliminar 1 hábito"]

    def test_with_nothing_marked_the_delete_button_is_drawn_but_off(self, view: TodayView) -> None:
        view.delete_mode.enter()

        off = Tree.buttons(view.buttons_frame)["Eliminar"]

        assert not Tree.enabled(off)
        assert Tree.enabled(Tree.buttons(view.buttons_frame)["Cancelar"])

    def test_every_habit_is_listed_also_those_not_due_today(self, view: TodayView) -> None:
        view.delete_mode.enter()

        assert "Viernes de finanzas (1 h)" in Tree.all_texts(view.list_frame)

    def test_clicking_a_row_or_its_trash_can_marks_it(
        self, view: TodayView, service: HabitService
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()

        click(rows(view)[0])
        click(trash_buttons(view)[2])

        assert view.delete_mode.selected == {habits[0].id, habits[2].id}

    def test_an_inactive_trash_can_does_not_respond(self, view: TodayView) -> None:
        view.delete_mode.enter()
        trash = trash_buttons(view)[0]
        trash.set_state("inactive")

        click(trash)

        assert view.delete_mode.selected == frozenset()

    def test_cancelling_deletes_nothing_and_brings_back_the_normal_buttons(
        self, view: TodayView, service: HabitService
    ) -> None:
        total = len(service.habits())
        view.delete_mode.enter()
        view.delete_mode.toggle(service.habits()[0])

        click(Tree.buttons(view.buttons_frame)["Cancelar"])

        assert len(service.habits()) == total
        assert not view.delete_mode.active
        assert button_texts(view) == [ADD, DELETE_MODE]

    def test_confirming_deletes_the_selected_habits_and_leaves_the_mode(
        self, view: TodayView, service: HabitService, dialogs: RecordingDialogs
    ) -> None:
        habits = service.habits()
        total = len(habits)
        view.delete_mode.enter()
        view.delete_mode.toggle(habits[0])
        view.delete_mode.toggle(habits[1])

        click(Tree.buttons(view.buttons_frame)["Eliminar 2 hábitos"])

        assert len(dialogs.asked) == 1
        assert [h.id for h in service.habits()] == [h.id for h in habits[2:]]
        assert len(rows(view)) == total - 2
        assert not view.delete_mode.active

    def test_declining_the_confirmation_leaves_everything_as_it_was(
        self, view: TodayView, service: HabitService, dialogs: RecordingDialogs
    ) -> None:
        total = len(service.habits())
        view.delete_mode.enter()
        view.delete_mode.toggle(service.habits()[0])
        dialogs.answers = [False]

        click(Tree.buttons(view.buttons_frame)["Eliminar 1 hábito"])

        assert len(service.habits()) == total
        assert view.delete_mode.active

    def test_reset_modes_leaves_delete_mode_without_redrawing(self, view: TodayView) -> None:
        view.delete_mode.enter()
        drawn = rows(view)

        view.reset_modes()

        assert not view.delete_mode.active
        assert rows(view) == drawn  # not redrawn: the caller does that


class TestPriorityCard:
    def test_the_saved_priority_is_prefilled(self, view: TodayView) -> None:
        assert view.priority_entry.get() == "Preparar la presentación"

    def test_marking_a_habit_keeps_what_is_being_typed(self, view: TodayView) -> None:
        view.priority_entry.delete(0, "end")
        view.priority_entry.insert(0, "Estudiar para el examen")

        click(row_of(view, "Entrenar 3 veces por semana"))

        assert view.priority_entry.get() == "Estudiar para el examen"

    def test_refreshing_again_and_again_keeps_it_too(self, view: TodayView) -> None:
        view.priority_entry.delete(0, "end")
        view.priority_entry.insert(0, "Estudiar para el examen")

        for _ in range(3):
            view.refresh()

        assert view.priority_entry.get() == "Estudiar para el examen"

    def test_the_save_button_stores_what_was_typed(
        self, view: TodayView, service: HabitService, dialogs: RecordingDialogs
    ) -> None:
        view.priority_entry.delete(0, "end")
        view.priority_entry.insert(0, "Llamar al banco")

        click(Tree.buttons(view)["Guardar"])

        assert service.priority_for_tomorrow() == "Llamar al banco"
        assert dialogs.shown[-1][:2] == ("info", "Lista")

    def test_enter_saves_as_well(self, view: TodayView, service: HabitService) -> None:
        view.priority_entry.delete(0, "end")
        view.priority_entry.insert(0, "Llamar al banco")

        view.priority_entry.focus_force()  # key events go to the widget that has the focus
        view.priority_entry.update()
        view.priority_entry.event_generate("<Return>")

        assert service.priority_for_tomorrow() == "Llamar al banco"

    def test_saving_an_empty_field_asks_for_the_task(
        self, view: TodayView, service: HabitService, dialogs: RecordingDialogs
    ) -> None:
        view.priority_entry.delete(0, "end")

        click(Tree.buttons(view)["Guardar"])

        assert dialogs.shown == [("info", "Aviso", "Escribe primero la tarea de mañana.")]
        assert service.priority_for_tomorrow() == "Preparar la presentación"

    def test_a_failed_save_is_reported_and_the_button_works_again_afterwards(
        self, view: TodayView, service: HabitService, repository: FlakyRepository,
        dialogs: RecordingDialogs,
    ) -> None:  # fmt: skip
        view.priority_entry.delete(0, "end")
        view.priority_entry.insert(0, "Llamar al banco")
        repository.failing = True

        click(Tree.buttons(view)["Guardar"])
        assert dialogs.kinds() == ["error"]
        assert view.priority_entry.get() == "Llamar al banco"

        repository.failing = False
        click(Tree.buttons(view)["Guardar"])
        assert service.priority_for_tomorrow() == "Llamar al banco"

    def test_the_card_has_the_peach_colors(self, view: TodayView) -> None:
        card = next(
            c
            for c in view.winfo_children()
            if isinstance(c, tk.Canvas) and "PRIORIDAD DE MAÑANA · UNA SOLA TAREA" in Tree.texts(c)
        )

        fills = {
            str(card.itemcget(i, "fill")) for i in card.find_all() if card.type(i) == "polygon"
        }

        assert fills == {palette.PEACH_BACKGROUND}
