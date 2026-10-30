"""The "Mi mes" tab: five cards computed from one set of figures."""

import tkinter as tk
from collections.abc import Callable
from datetime import datetime

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.domain.stats import MonthStats
from habit_tracker.service import HabitService
from habit_tracker.ui.views.month import CONTENT_WIDTH, MonthView
from habit_tracker.ui.views.stats_banner import greeting_for_hour, long_date_text

from .conftest import NOW, Tree


@pytest.fixture
def make_view(tk_root: tk.Tk, clock: FixedClock) -> Callable[..., MonthView]:
    def make(service: HabitService, *, clock: FixedClock = clock) -> MonthView:
        view = MonthView(tk_root, service, clock=clock)
        view.pack()
        return view

    return make


@pytest.fixture
def view(make_view: Callable[..., MonthView], service: HabitService) -> MonthView:
    return make_view(service)


def cards(view: MonthView) -> list[tk.Canvas]:
    return [child for child in view.winfo_children() if isinstance(child, tk.Canvas)]


def titles(view: MonthView) -> list[str]:
    return [Tree.texts(card)[0] for card in cards(view)]


@pytest.mark.parametrize(
    ("hour", "greeting"),
    [
        (0, "Buenos días ✿"),
        (11, "Buenos días ✿"),
        (12, "Buenas tardes ✿"),
        (18, "Buenas tardes ✿"),
        (19, "Buenas noches ✿"),
        (23, "Buenas noches ✿"),
    ],
)
def test_the_greeting_changes_at_noon_and_at_seven(hour: int, greeting: str) -> None:
    assert greeting_for_hour(hour) == greeting


def test_the_long_date_names_the_weekday_the_day_and_the_month() -> None:
    assert long_date_text(NOW.date()) == "jueves 29 de octubre"


class TestCards:
    def test_there_are_five_cards_each_as_wide_as_the_content(self, view: MonthView) -> None:
        assert len(cards(view)) == 5
        assert {int(card["width"]) for card in cards(view)} == {CONTENT_WIDTH}

    def test_the_four_chart_cards_have_their_titles_in_order(self, view: MonthView) -> None:
        assert [Tree.texts(card)[0] for card in cards(view)[1:]] == [
            "Tu mes por área",
            "Balance del mes",
            "Ritmo del mes",
            "Constancia del mes",
        ]

    def test_refreshing_replaces_the_cards_instead_of_piling_them_up(
        self, view: MonthView
    ) -> None:
        for _ in range(3):
            view.refresh()

        assert len(cards(view)) == 5

    def test_new_marks_show_up_when_the_tab_is_refreshed(
        self, view: MonthView, service: HabitService
    ) -> None:
        total_before = service.month_stats(2026, 10).total
        quota = next(h for h in service.habits() if h.name.startswith("Entrenar"))

        service.mark(quota.id, True)
        view.refresh()

        assert str(total_before + 1) in Tree.texts(cards(view)[0])


class TestBanner:
    def test_it_shows_the_date_the_greeting_and_the_three_figures(
        self, view: MonthView, service: HabitService
    ) -> None:
        done, due = service.day_progress()
        stats = service.month_stats(2026, 10)

        assert Tree.texts(cards(view)[0]) == [
            "jueves 29 de octubre",
            "Buenos días ✿",
            f"{done}/{due}",
            "hoy",
            str(service.longest_streak()),
            "racha más larga",
            str(stats.total),
            "checks del mes",
        ]

    @pytest.mark.parametrize(
        ("moment", "greeting"),
        [
            (datetime(2026, 10, 29, 8, 0), "Buenos días ✿"),
            (datetime(2026, 10, 29, 15, 0), "Buenas tardes ✿"),
            (datetime(2026, 10, 29, 21, 30), "Buenas noches ✿"),
        ],
    )
    def test_the_greeting_comes_from_the_hour_of_the_clock_it_is_given(
        self,
        make_view: Callable[..., MonthView],
        service: HabitService,
        moment: datetime,
        greeting: str,
    ) -> None:
        view = make_view(service, clock=FixedClock(moment))

        assert Tree.texts(cards(view)[0])[1] == greeting


class TestFigures:
    def test_the_month_figures_are_computed_once_per_refresh(
        self, view: MonthView, service: HabitService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[int, int]] = []
        original = service.month_stats

        def counting(year: int, month: int) -> MonthStats:
            calls.append((year, month))
            return original(year, month)

        monkeypatch.setattr(service, "month_stats", counting)

        view.refresh()

        assert calls == [(2026, 10)]

    def test_the_bars_have_a_row_for_every_area_with_habits(
        self, view: MonthView, service: HabitService
    ) -> None:
        stats = service.month_stats(2026, 10)
        texts = Tree.texts(cards(view)[1])

        for area, percent in stats.percentages:
            assert area.name in texts
            assert f"{percent}%" in texts

    def test_the_donut_shows_the_total_and_its_legend_counts(
        self, view: MonthView, service: HabitService
    ) -> None:
        stats = service.month_stats(2026, 10)
        texts = Tree.texts(cards(view)[2])

        assert str(stats.total) in texts
        assert "checks" in texts
        for area, count in stats.counts_by_area:
            assert area.name in texts
            assert str(count) in texts

    def test_the_pace_card_has_a_number_under_each_elapsed_day(self, view: MonthView) -> None:
        texts = Tree.texts(cards(view)[3])

        assert texts[2:] == [str(day) for day in range(1, 30) if day % 2 == 1]

    def test_the_consistency_map_has_a_row_per_area_with_habits(
        self, view: MonthView, service: HabitService
    ) -> None:
        stats = service.month_stats(2026, 10)
        texts = Tree.texts(cards(view)[4])

        for area in service.areas():
            assert (area.name in texts) == (area.id in stats.matrix)


class TestWithoutHabits:
    def test_the_charts_say_there_is_nothing_to_show_yet(
        self, make_view: Callable[..., MonthView], empty_service: HabitService
    ) -> None:
        view = make_view(empty_service)

        assert "todavía no hay hábitos que mostrar" in Tree.texts(cards(view)[1])
        assert "todavía no hay hábitos que mostrar" in Tree.texts(cards(view)[4])
        # The days that have gone by still get a (short) bar, though no area was done on them.
        assert Tree.texts(cards(view)[3])[2:] == [str(day) for day in range(1, 30) if day % 2]

    def test_the_banner_shows_zeros(
        self, make_view: Callable[..., MonthView], empty_service: HabitService
    ) -> None:
        view = make_view(empty_service)

        banner = Tree.texts(cards(view)[0])

        assert banner[2] == "0/0"
        assert banner[4] == "0"
        assert banner[6] == "0"
