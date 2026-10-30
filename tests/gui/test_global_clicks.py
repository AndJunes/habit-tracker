"""The window-wide click chain: one dispatcher, many handlers, nobody else's bindings touched."""

import tkinter as tk

import pytest

from habit_tracker.ui.theme.tkutil import TkEvent
from habit_tracker.ui.widgets.global_clicks import GlobalClickDispatcher, click_dispatcher
from habit_tracker.ui.widgets.soft_menu import SoftMenu, menu_manager

SEQUENCE = "<Button-1>"


@pytest.fixture
def target(private_window: tk.Toplevel) -> tk.Canvas:
    """A mapped widget to click on, in a window that has its own interpreter."""
    canvas = tk.Canvas(private_window, width=40, height=40)
    canvas.pack()
    private_window.update()
    return canvas


def click(widget: tk.Misc) -> None:
    widget.event_generate(SEQUENCE, x=2, y=2)


def bind_all_lines(widget: tk.Misc) -> list[str]:
    """One line per script bound to the sequence on the ``all`` tag."""
    return [line for line in widget.bind_all(SEQUENCE).splitlines() if line.strip()]


class TestDispatcher:
    def test_it_is_bound_once_and_shared_by_the_whole_window(
        self, private_window: tk.Toplevel, target: tk.Canvas
    ) -> None:
        dispatcher = click_dispatcher(private_window)
        assert click_dispatcher(target) is dispatcher
        assert isinstance(dispatcher, GlobalClickDispatcher)
        assert len(bind_all_lines(target)) == 1

    def test_each_window_gets_its_own_dispatcher(
        self, private_window: tk.Toplevel, window: tk.Toplevel
    ) -> None:
        assert click_dispatcher(private_window) is not click_dispatcher(window)

    def test_it_reaches_every_registered_handler_on_each_click(self, target: tk.Canvas) -> None:
        dispatcher = click_dispatcher(target)
        seen: list[str] = []
        dispatcher.register("a", lambda event: seen.append(f"a:{event.widget}"))
        dispatcher.register("b", lambda event: seen.append(f"b:{event.widget}"))
        assert len(dispatcher) == 2
        click(target)
        assert seen == [f"a:{target}", f"b:{target}"]

    def test_unregistering_stops_only_that_handler(self, target: tk.Canvas) -> None:
        dispatcher = click_dispatcher(target)
        seen: list[str] = []
        dispatcher.register("a", lambda _event: seen.append("a"))
        dispatcher.register("b", lambda _event: seen.append("b"))
        dispatcher.unregister("a")
        dispatcher.unregister("never registered")  # ignored
        click(target)
        assert seen == ["b"]
        assert len(dispatcher) == 1

    def test_registering_a_key_again_replaces_its_handler(self, target: tk.Canvas) -> None:
        dispatcher = click_dispatcher(target)
        seen: list[str] = []
        dispatcher.register("a", lambda _event: seen.append("old"))
        dispatcher.register("a", lambda _event: seen.append("new"))
        click(target)
        assert seen == ["new"]

    def test_a_handler_may_unregister_itself_while_running(self, target: tk.Canvas) -> None:
        dispatcher = click_dispatcher(target)
        seen: list[str] = []

        def once(_event: TkEvent) -> None:
            seen.append("once")
            dispatcher.unregister("once")

        dispatcher.register("once", once)
        dispatcher.register("always", lambda _event: seen.append("always"))
        click(target)
        click(target)
        assert seen == ["once", "always", "always"]


class TestMenusOnTheChain:
    @pytest.fixture
    def menus(self, private_window: tk.Toplevel) -> tuple[SoftMenu, SoftMenu]:
        first = SoftMenu(private_window, ["a", "b"])
        second = SoftMenu(private_window, ["x", "y"])
        first.pack()
        second.pack()
        private_window.update()
        return first, second

    def test_other_bindings_of_the_event_survive_opening_and_closing_menus(
        self, private_window: tk.Toplevel, target: tk.Canvas, menus: tuple[SoftMenu, SoftMenu]
    ) -> None:
        first, second = menus
        outside: list[str] = []
        private_window.bind_all(SEQUENCE, lambda _event: outside.append("all"), add="+")
        target.bind(SEQUENCE, lambda _event: outside.append("widget"), add="+")
        first.open()  # the dispatcher is installed now, after the foreign binding
        first.close()
        lines_before = bind_all_lines(target)
        assert len(lines_before) == 2  # the foreign binding and the dispatcher

        for _ in range(3):
            first.open()
            second.open()  # closes the first
            second.close()
        first.open()
        first.close()

        assert bind_all_lines(target) == lines_before  # nothing was bound or unbound
        click(target)
        assert outside == ["widget", "all"]  # one call each: nothing duplicated or lost

    def test_opening_a_second_menu_leaves_only_the_second_one_listening(
        self, private_window: tk.Toplevel, menus: tuple[SoftMenu, SoftMenu]
    ) -> None:
        first, second = menus
        dispatcher = click_dispatcher(private_window)
        first.open()
        assert len(dispatcher) == 1
        second.open()
        assert first.popup is None
        assert len(dispatcher) == 1
        assert menu_manager(private_window).open_menu is second
        second.close()
        assert len(dispatcher) == 0
        assert menu_manager(private_window).open_menu is None

    def test_closing_a_menu_keeps_handlers_other_widgets_registered(
        self, private_window: tk.Toplevel, target: tk.Canvas, menus: tuple[SoftMenu, SoftMenu]
    ) -> None:
        first, second = menus
        dispatcher = click_dispatcher(private_window)
        seen: list[str] = []
        dispatcher.register("probe", lambda _event: seen.append("probe"))
        first.open()
        second.open()
        second.close()
        click(target)
        assert seen == ["probe"]
        assert len(dispatcher) == 1

    def test_an_outside_click_closes_the_open_menu_and_leaves_no_handler_behind(
        self, private_window: tk.Toplevel, target: tk.Canvas, menus: tuple[SoftMenu, SoftMenu]
    ) -> None:
        first, _ = menus
        first.open()
        click(target)
        assert first.popup is None
        assert len(click_dispatcher(private_window)) == 0
        click(target)  # a click with nothing open is harmless
        first.open()
        assert first.popup is not None
