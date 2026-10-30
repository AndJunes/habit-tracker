"""The full-screen dashboard: the three-column grid, delete mode and the priority card."""

import tkinter as tk
from collections.abc import Callable
from datetime import date

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import Habit
from habit_tracker.domain.stats import MonthStats
from habit_tracker.service import HabitService
from habit_tracker.ui.controllers.priority import PriorityEditor
from habit_tracker.ui.theme.cursors import pointer_cursor
from habit_tracker.ui.views.dashboard import (
    COLUMN_B_WIDTH,
    PAGE_WIDTH,
    DashboardView,
)
from habit_tracker.ui.views.today import TodayView

from .conftest import FlakyRepository, FormRecorder, RecordingDialogs, Tree, ValuePrompt

ADD, DELETE_MODE = "+ Agregar hábito", "Eliminar hábito…"
EDIT_SEQUENCES = ("<Button-2>", "<Button-3>", "<Control-Button-1>")


@pytest.fixture
def make_view(
    window: tk.Toplevel,
    clock: FixedClock,
    dialogs: RecordingDialogs,
    forms: FormRecorder,
    value_prompt: ValuePrompt,
) -> Callable[..., DashboardView]:
    def make(service: HabitService, **options: PriorityEditor) -> DashboardView:
        view = DashboardView(window, service, dialogs=dialogs, clock=clock, **options)
        view.pack(fill="both", expand=True)
        window.update()
        return view

    return make


@pytest.fixture
def view(make_view: Callable[..., DashboardView], service: HabitService) -> DashboardView:
    return make_view(service)


def canvases(widget: tk.Misc) -> list[tk.Canvas]:
    return [item for item in Tree.descendants(widget) if isinstance(item, tk.Canvas)]


def card_titled(view: DashboardView, title: str) -> tk.Canvas:
    """The card whose first text is ``title``."""
    return next(c for c in canvases(view.page) if Tree.texts(c)[:1] == [title])


def today_card(view: DashboardView) -> tk.Canvas:
    return card_titled(view, "Hoy")


def click(widget: tk.Misc, sequence: str = "<Button-1>") -> None:
    widget.update()
    widget.event_generate(sequence, x=10, y=10)
    widget.update()


def click_row(view: DashboardView, habit: Habit, sequence: str = "<Button-1>") -> None:
    """Click in the middle of the habit's row, moving the pointer there first."""
    card = today_card(view)
    card.update()
    x1, y1, x2, y2 = card.bbox(f"h{habit.id}")
    x, y = (x1 + x2) // 2, (y1 + y2) // 2
    card.event_generate("<Motion>", x=x, y=y)
    card.event_generate(sequence, x=x, y=y)
    card.update()


def click_delete_row(view: DashboardView, habit: Habit) -> None:
    card = today_card(view)
    card.update()
    x1, y1, _x2, y2 = card.bbox(f"x{habit.id}")
    x, y = x1 + 40, (y1 + y2) // 2
    card.event_generate("<Motion>", x=x, y=y)
    card.event_generate("<Button-1>", x=x, y=y)
    card.update()


def button_texts(view: DashboardView) -> list[str]:
    return list(Tree.buttons(today_card(view)))


def by_name(service: HabitService, name: str) -> Habit:
    return next(habit for habit in service.habits() if habit.name == name)


class TestPage:
    def test_it_draws_every_kind_of_habit_and_redraws_without_errors(
        self, view: DashboardView, service: HabitService
    ) -> None:
        view.refresh()
        view.refresh()

        assert Tree.texts(today_card(view))[0] == "Hoy"
        for habit in service.habits():
            assert habit.name in Tree.texts(today_card(view))

    def test_the_page_has_its_title_the_stats_bar_the_grid_and_the_map(
        self, view: DashboardView
    ) -> None:
        names = [child.winfo_class() for child in view.page.winfo_children()]

        assert names == ["Frame", "Canvas", "Frame", "Canvas"]
        assert int(view.page.winfo_children()[1]["width"]) == PAGE_WIDTH
        assert int(view.page.winfo_children()[3]["width"]) == PAGE_WIDTH

    def test_the_stats_bar_shows_the_date_and_the_greeting_of_the_clock(
        self, view: DashboardView
    ) -> None:
        stats_bar = view.page.winfo_children()[1]

        assert Tree.texts(stats_bar)[:2] == ["jueves 29 de octubre", "Buenos días ✿"]

    def test_the_month_figures_are_computed_once_per_refresh(
        self, view: DashboardView, service: HabitService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[int, int]] = []
        original = service.month_stats

        def counting(year: int, month: int) -> MonthStats:
            calls.append((year, month))
            return original(year, month)

        monkeypatch.setattr(service, "month_stats", counting)

        view.refresh()

        assert calls == [(2026, 10)]

    def test_the_chart_cards_have_their_titles(self, view: DashboardView) -> None:
        for title in ("Tu mes por área", "Balance del mes", "Ritmo del mes", "octubre 2026"):
            assert card_titled(view, title)

    def test_the_page_is_centered_in_the_scroll_canvas(self, view: DashboardView) -> None:
        view.update()

        x, y = view.scroll_canvas.coords(view._page_window)

        assert x == max(view.scroll_canvas.winfo_width(), PAGE_WIDTH) / 2
        assert y == 0

    def test_the_scroll_region_is_exactly_as_tall_as_the_content(
        self, view: DashboardView
    ) -> None:
        view.update()

        region = [int(float(v)) for v in str(view.scroll_canvas.cget("scrollregion")).split()]

        assert region[0] == region[2] == 0
        assert region[3] == view.scroll_canvas.bbox("all")[3]


class TestCalendarCard:
    def test_the_legend_of_categories_fits_inside_the_card(self, view: DashboardView) -> None:
        card = card_titled(view, "octubre 2026")
        names = [area.name for area in view.service.areas()]

        assert "Estilo de vida" in Tree.texts(card)
        for item in card.find_all():
            if card.type(item) == "text":
                left, _, right, _ = card.bbox(item)
                assert left >= 0, card.itemcget(item, "text")
                assert right <= COLUMN_B_WIDTH, card.itemcget(item, "text")
        assert all(name in Tree.texts(card) for name in names)

    def test_it_shows_the_weekday_names_and_every_day_of_the_month(
        self, view: DashboardView
    ) -> None:
        texts = Tree.texts(card_titled(view, "octubre 2026"))

        assert "lun" in texts
        assert "dom" in texts
        assert [str(day) for day in range(1, 32)] == [t for t in texts if t.isdigit()]

    def test_no_dates_this_month_says_so(self, view: DashboardView) -> None:
        card = card_titled(view, "Fechas del mes")

        assert "este mes no tiene fechas anotadas" in Tree.texts(card)

    def test_a_date_of_the_month_gets_a_chip_with_the_day_and_the_month(
        self, view: DashboardView, service: HabitService
    ) -> None:
        service.add_important_date(date(2026, 10, 31), "Fiesta de disfraces")

        view.refresh()

        assert Tree.texts(card_titled(view, "Fechas del mes")) == [
            "Fechas del mes",
            "31",
            "OCT",
            "Fiesta de disfraces",
        ]

    def test_a_long_date_title_is_cut_with_an_ellipsis(
        self, view: DashboardView, service: HabitService
    ) -> None:
        service.add_important_date(date(2026, 10, 31), "Una fiesta con un nombre larguísimo " * 4)

        view.refresh()

        title = Tree.texts(card_titled(view, "Fechas del mes"))[-1]
        assert title.endswith("…")


class TestHabitRows:
    def test_a_click_on_a_row_marks_the_habit(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        train = by_name(service, "Entrenar 3 veces por semana")
        assert not train.is_done(today)

        click_row(view, train)

        assert service.get_habit(train.id).is_done(today)

    @pytest.mark.parametrize("sequence", EDIT_SEQUENCES)
    def test_right_click_control_click_and_button_2_open_the_editor(
        self, view: DashboardView, service: HabitService, forms: FormRecorder, sequence: str
    ) -> None:
        study = by_name(service, "Bloque de estudio")

        click_row(view, study, sequence)

        (call,) = forms.calls
        assert call.habit is study

    def test_the_pointing_hand_shows_only_over_a_row(self, view: DashboardView) -> None:
        card = today_card(view)
        study = by_name(view.service, "Bloque de estudio")
        x1, y1, x2, y2 = card.bbox(f"h{study.id}")

        card.event_generate("<Motion>", x=(x1 + x2) // 2, y=(y1 + y2) // 2)
        card.update()
        over_row = str(card.cget("cursor"))
        card.event_generate("<Motion>", x=5, y=5)
        card.update()

        assert over_row == pointer_cursor(card)
        assert str(card.cget("cursor")) == ""

    def test_a_habit_that_is_not_due_today_is_dimmed_and_has_no_click(
        self, view: DashboardView, service: HabitService, today: date
    ) -> None:
        finances = by_name(service, "Viernes de finanzas (1 h)")  # today is a Thursday
        card = today_card(view)

        assert finances.name in Tree.texts(card)
        assert card.find_withtag(f"h{finances.id}") == ()

    def test_a_failed_write_is_reported_and_the_row_keeps_working(
        self,
        view: DashboardView,
        service: HabitService,
        repository: FlakyRepository,
        dialogs: RecordingDialogs,
        today: date,
    ) -> None:
        train = by_name(service, "Entrenar 3 veces por semana")
        repository.failing = True

        click_row(view, train)
        assert dialogs.kinds() == ["error"]
        assert not train.is_done(today)

        repository.failing = False
        click_row(view, train)
        assert service.get_habit(train.id).is_done(today)

    def test_a_name_too_wide_for_the_card_is_cut(
        self, view: DashboardView, service: HabitService
    ) -> None:
        service.add_habit(
            name="Un hábito con un nombre extremadamente largo para esta tarjeta",
            area_id="salud",
            frequency=service.habits()[1].frequency,
            start=date(2026, 9, 29),
        )

        view.refresh()

        names = Tree.texts(today_card(view))
        assert any(
            name.startswith("Un hábito con un nombre") and name.endswith("…") for name in names
        )


class TestEmpty:
    def test_it_offers_to_create_the_first_habit_and_nothing_to_delete(
        self, make_view: Callable[..., DashboardView], empty_service: HabitService
    ) -> None:
        view = make_view(empty_service)

        buttons = Tree.buttons(today_card(view))

        assert ADD in buttons
        assert DELETE_MODE not in buttons
        assert "No tienes hábitos todavía.\n¡Agrega el primero!" in Tree.texts(today_card(view))


class TestAddButton:
    def test_it_opens_the_form_and_redraws_once_a_habit_is_saved(
        self,
        make_view: Callable[..., DashboardView],
        empty_service: HabitService,
        forms: FormRecorder,
    ) -> None:
        view = make_view(empty_service)

        click(Tree.buttons(today_card(view))[ADD])
        (call,) = forms.calls
        assert call.habit is None
        assert empty_service.habits() == ()

        new = empty_service.add_habit(name="Nuevo", area_id="salud", frequency=Daily())
        forms.save(new)

        assert "Nuevo" in Tree.texts(today_card(view))
        assert {ADD, DELETE_MODE} <= set(Tree.buttons(today_card(view)))

    def test_closing_the_form_without_saving_changes_nothing(
        self,
        make_view: Callable[..., DashboardView],
        empty_service: HabitService,
        forms: FormRecorder,
    ) -> None:
        view = make_view(empty_service)
        before = Tree.texts(today_card(view))

        click(Tree.buttons(today_card(view))[ADD])

        assert Tree.texts(today_card(view)) == before

    def test_it_warns_before_going_past_the_recommended_number_of_habits(
        self,
        make_view: Callable[..., DashboardView],
        empty_service: HabitService,
        forms: FormRecorder,
        dialogs: RecordingDialogs,
    ) -> None:
        for number in range(6):
            empty_service.add_habit(name=f"Hábito {number}", area_id="salud", frequency=Daily())
        view = make_view(empty_service)

        dialogs.answers = [False]  # "no, better not"
        click(Tree.buttons(today_card(view))[ADD])
        assert len(dialogs.asked) == 1
        assert forms.calls == []

        dialogs.answers = [True]  # "yes, I want another"
        click(Tree.buttons(today_card(view))[ADD])
        assert len(forms.calls) == 1


class TestDeleteMode:
    def test_the_card_lists_every_habit_with_a_trash_can_and_a_hint(
        self, view: DashboardView, service: HabitService
    ) -> None:
        assert button_texts(view) == [ADD, DELETE_MODE]
        assert Tree.trash_buttons(today_card(view)) == []

        click(Tree.buttons(today_card(view))[DELETE_MODE])

        card = today_card(view)
        assert view.delete_mode.active
        assert button_texts(view) == ["Cancelar", "Eliminar"]
        assert len(Tree.trash_buttons(card)) == len(service.habits())
        assert "Marca los hábitos a eliminar (se borra su historial)" in Tree.texts(card)
        assert not Tree.enabled(Tree.buttons(card)["Eliminar"])

    def test_selecting_by_row_or_by_trash_can_updates_the_buttons_and_the_trash_cans(
        self, view: DashboardView, service: HabitService
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()

        click_delete_row(view, habits[0])
        click(Tree.trash_buttons(today_card(view))[2])

        assert view.delete_mode.selected == {habits[0].id, habits[2].id}
        assert [t.state for t in Tree.trash_buttons(today_card(view))].count("active") == 2
        buttons = Tree.buttons(today_card(view))
        assert "Eliminar 2 hábitos" in buttons
        assert Tree.enabled(buttons["Eliminar 2 hábitos"])

        view.delete_mode.toggle(habits[2])
        assert "Eliminar 1 hábito" in Tree.buttons(today_card(view))

    def test_cancelling_deletes_nothing(self, view: DashboardView, service: HabitService) -> None:
        total = len(service.habits())
        view.delete_mode.enter()
        view.delete_mode.toggle(service.habits()[0])

        click(Tree.buttons(today_card(view))["Cancelar"])

        assert len(service.habits()) == total
        assert not view.delete_mode.active
        assert ADD in Tree.buttons(today_card(view))

    def test_confirming_deletes_only_what_was_marked_and_leaves_the_mode(
        self, view: DashboardView, service: HabitService, dialogs: RecordingDialogs
    ) -> None:
        habits = service.habits()
        view.delete_mode.enter()
        view.delete_mode.toggle(habits[0])
        view.delete_mode.toggle(habits[1])

        dialogs.answers = [False]  # changes their mind at the confirmation
        click(Tree.buttons(today_card(view))["Eliminar 2 hábitos"])
        assert len(service.habits()) == len(habits)
        assert view.delete_mode.active

        dialogs.answers = [True]
        click(Tree.buttons(today_card(view))["Eliminar 2 hábitos"])

        assert [h.id for h in service.habits()] == [h.id for h in habits[2:]]
        assert not view.delete_mode.active

    def test_leaving_the_mode_forgets_what_was_marked(
        self, view: DashboardView, service: HabitService
    ) -> None:
        view.delete_mode.enter()
        view.delete_mode.toggle(service.habits()[0])

        view.reset_modes()
        view.refresh()

        assert not view.delete_mode.active
        assert view.delete_mode.selected == frozenset()
        assert Tree.trash_buttons(view.page) == []


class TestPriorityCard:
    def entry(self, view: DashboardView) -> tk.Entry:
        assert view.priority_entry is not None
        return view.priority_entry

    def test_the_saved_priority_is_prefilled(self, view: DashboardView) -> None:
        assert self.entry(view).get() == "Preparar la presentación"

    def test_what_is_being_typed_survives_the_page_being_rebuilt_by_marking_a_habit(
        self, view: DashboardView, service: HabitService
    ) -> None:
        self.entry(view).delete(0, "end")
        self.entry(view).insert(0, "Estudiar para el examen")

        click_row(view, by_name(service, "Entrenar 3 veces por semana"))

        assert self.entry(view).get() == "Estudiar para el examen"

    def test_the_save_button_stores_the_text(
        self, view: DashboardView, service: HabitService
    ) -> None:
        self.entry(view).delete(0, "end")
        self.entry(view).insert(0, "Llamar al banco")

        click(Tree.buttons(view.page)["Guardar"])

        assert service.priority_for_tomorrow() == "Llamar al banco"

    def test_the_text_typed_in_the_window_is_still_there_in_full_screen(
        self,
        window: tk.Toplevel,
        make_view: Callable[..., DashboardView],
        service: HabitService,
        dialogs: RecordingDialogs,
    ) -> None:
        shared = PriorityEditor(service, window, dialogs=dialogs)
        today_view = TodayView(window, service, priority=shared, dialogs=dialogs)
        today_view.priority_entry.delete(0, "end")
        today_view.priority_entry.insert(0, "Escrito en la ventana")

        dashboard = make_view(service, priority=shared)

        assert dashboard.priority_entry is not None
        assert dashboard.priority_entry.get() == "Escrito en la ventana"
