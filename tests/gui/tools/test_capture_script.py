"""The capture script drives the real app, through its public interface, with hidden windows.

No window is ever shown and nothing is written outside ``tmp_path``. The parts that need Pillow
are skipped, with the reason visible, when it is not installed.
"""

import tkinter as tk
from collections.abc import Callable
from datetime import datetime, timedelta
from types import ModuleType
from typing import Any

import pytest

from habit_tracker.clock import FixedClock
from habit_tracker.demo import build_demo_snapshot
from habit_tracker.domain.enums import Weekday
from habit_tracker.service import HabitService
from habit_tracker.storage.memory import MemoryRepository
from habit_tracker.ui.forms import texts as form_texts
from habit_tracker.ui.forms.choices import (
    DayGroup,
    FrequencyChoice,
    MeasurementChoice,
    TextField,
)
from habit_tracker.ui.forms.form_state import FormState
from habit_tracker.ui.forms.habit_form import HabitFormDialog
from habit_tracker.ui.main_window import Mode, Tab
from habit_tracker.ui.theme.tkutil import widget_exists

LILAC = (200, 180, 230, 255)
WINDOW = (620, 800)  # the main window, in points


def form_state(script: Any) -> FormState:
    """The state of the form the script has open."""
    assert script.dialog is not None
    state: FormState = script.dialog.form_state
    return state


# ================= The walk through the scenes =================


def test_the_script_walks_through_every_scene_and_leaves_each_screen_in_its_state(
    make_script: Callable[..., Any],
    capture_screens: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = make_script()
    window, service = script.window, script.service
    today = service.today()
    sample_dates = {today + timedelta(days=offset) for offset in (3, 10, 17)}
    done_before = 0
    form_dialog = None
    visited: list[str] = []

    def done_today() -> int:
        return sum(1 for habit in service.habits() if habit.is_done(today))

    for _ in range(len(script.scenes)):
        scene = script.advance()
        assert scene is not None
        visited.append(scene.name)
        match scene.name:
            case "hoy":
                assert window.active_tab is Tab.TODAY
                assert window.mode is Mode.WINDOW
                done_before = done_today()
            case "marcado":
                assert done_today() == done_before + 1
            case "formulario":
                state = form_state(script)
                form_dialog = script.dialog
                assert state.text(TextField.NAME) == "Leer 20 minutos"
                assert state.text(TextField.DESCRIPTION) == "Un poquito cada día, sin presión."
                assert state.selected_area is not None
                assert state.selected_area.id == "crecimiento"
                assert state.frequency_choice is FrequencyChoice.TIMES_PER_WEEK
                assert state.days(DayGroup.PREFERRED) == {
                    Weekday.MONDAY,
                    Weekday.WEDNESDAY,
                    Weekday.FRIDAY,
                }
            case "formulario-fechas":
                state = form_state(script)
                assert state.frequency_choice is FrequencyChoice.FIXED_DATES
                assert state.chosen_dates == sample_dates
            case "formulario-final":
                state = form_state(script)
                assert state.frequency_choice is FrequencyChoice.TIMES_PER_WEEK
                assert state.measurement_choice is MeasurementChoice.DURATION
                assert state.text(TextField.GOAL) == "20"
                assert state.has_end
                assert state.typed_date(TextField.END) == today + timedelta(days=60)
                assert state.advanced_visible
                assert state.has_reminder
                assert state.text(TextField.REMINDER_TIME) == "20:00"
                assert state.chosen_dates == sample_dates  # kept while on another frequency
            case "calendario":
                assert script.dialog is None
                assert form_dialog is not None
                assert not widget_exists(form_dialog)
                assert window.active_tab is Tab.CALENDAR
            case "mi-mes":
                assert window.active_tab is Tab.MONTH
            case "eliminar":
                delete_mode = window.today_view.delete_mode
                assert window.active_tab is Tab.TODAY
                assert delete_mode.active
                assert delete_mode.selected == {habit.id for habit in service.habits()[3:5]}
            case "dashboard":
                assert window.mode is Mode.FULLSCREEN
                assert window.dashboard is not None
                assert not window.today_view.delete_mode.active
            case "dashboard-constancia":
                assert window.mode is Mode.FULLSCREEN

    assert visited == list(capture_screens.SCENES)
    assert len(set(visited)) == 10  # each scene has its own file name
    assert list(script.output.iterdir()) == []  # walking the scenes saves nothing
    assert script.advance() is None  # past the last scene it finishes and closes the app
    assert not widget_exists(script.root)
    assert "Saved 0 of 10" in capsys.readouterr().out


def test_the_app_runs_on_the_stopped_clock_and_looks_like_the_regular_one(
    make_script: Callable[..., Any], now: datetime
) -> None:
    script = make_script()
    assert script.service.today() == now.date()
    assert script.root.title() == "Registro de hábitos"  # not the demo title
    assert len(script.service.habits()) == 6  # the demo data


# ================= The form =================


def test_the_pilot_operates_the_form_through_its_widgets_and_the_state_follows(
    capture_screens: ModuleType, private_root: tk.Tk, now: datetime
) -> None:
    service = HabitService(MemoryRepository(build_demo_snapshot(now.date())), FixedClock(now))
    dialog = HabitFormDialog(private_root, service, on_saved=lambda habit: None)
    dialog.withdraw()
    pilot = capture_screens.FormPilot(dialog)

    pilot.type_into(TextField.NAME, "Caminar")
    pilot.press_area("Finanzas")
    pilot.choose(form_texts.MEASUREMENT_OPTIONS, MeasurementChoice.QUANTITY)

    state = dialog.form_state
    assert state.text(TextField.NAME) == "Caminar"
    assert state.selected_area is not None
    assert state.selected_area.id == "finanzas"
    assert state.measurement_choice is MeasurementChoice.QUANTITY
    # The menu shows the choice too, not only the state.
    assert pilot.menu(form_texts.MEASUREMENT_OPTIONS).current() == MeasurementChoice.QUANTITY


def test_the_pilot_names_what_it_cannot_find_in_the_form(
    capture_screens: ModuleType, private_root: tk.Tk, now: datetime
) -> None:
    service = HabitService(MemoryRepository(build_demo_snapshot(now.date())), FixedClock(now))
    dialog = HabitFormDialog(private_root, service, on_saved=lambda habit: None)
    dialog.withdraw()
    pilot = capture_screens.FormPilot(dialog)

    with pytest.raises(capture_screens.CaptureError, match="no button"):
        pilot.press("Un botón que no existe")
    with pytest.raises(capture_screens.CaptureError, match="no area"):
        pilot.press_area("Un área que no existe")
    with pytest.raises(capture_screens.CaptureError, match="no menu"):
        pilot.menu(("Una", "opción"))


def test_the_pilot_finds_the_scrolling_area_of_the_form(
    capture_screens: ModuleType, private_root: tk.Tk, now: datetime
) -> None:
    service = HabitService(MemoryRepository(build_demo_snapshot(now.date())), FixedClock(now))
    dialog = HabitFormDialog(private_root, service, on_saved=lambda habit: None)
    dialog.withdraw()
    pilot = capture_screens.FormPilot(dialog)

    assert isinstance(pilot.scroll_canvas(), tk.Canvas)
    pilot.scroll_to(1.0)
    pilot.scroll_to(0.0)
    pilot.scroll_to_widget(pilot.menu(form_texts.FREQUENCY_OPTIONS))  # must not fail unmapped


# ================= Saving the screenshots =================


def test_the_script_saves_window_captures_and_rejects_full_screen_ones(
    make_script: Callable[..., Any], capsys: pytest.CaptureFixture[str]
) -> None:
    pil_image = pytest.importorskip("PIL.Image")
    script = make_script()
    scene = script.scenes[0]
    screen = (script.root.winfo_screenwidth() * 2, script.root.winfo_screenheight() * 2)
    full_screen, main_window, form = (
        script.captures_dir / name for name in ("a.png", "b.png", "c.png")
    )
    pil_image.new("RGBA", screen, LILAC).save(full_screen)
    pil_image.new("RGBA", (1232, 1650), LILAC).save(main_window)
    pil_image.new("RGBA", (928, 1624), LILAC).save(form)

    assert script.accept(scene, WINDOW, full_screen) is False  # it shows the desktop
    assert "PANTALLA COMPLETA" in capsys.readouterr().out
    assert script.accept(scene, WINDOW, form) is False  # it is the form's window
    assert "928x1624" in capsys.readouterr().out
    assert not (script.output / "hoy.png").exists()

    assert script.accept(scene, WINDOW, main_window) is True

    assert (script.output / "hoy.png").exists()
    assert script.saved == [script.output / "hoy.png"]


def test_without_validation_any_capture_is_accepted(make_script: Callable[..., Any]) -> None:
    pil_image = pytest.importorskip("PIL.Image")
    script = make_script(validate=False)
    screen = (script.root.winfo_screenwidth() * 2, script.root.winfo_screenheight() * 2)
    full_screen = script.captures_dir / "a.png"
    pil_image.new("RGBA", screen, LILAC).save(full_screen)

    assert script.accept(script.scenes[0], WINDOW, full_screen) is True
    assert (script.output / "hoy.png").exists()


def test_a_screenshot_dropped_in_the_folder_is_saved_and_the_script_moves_on(
    make_script: Callable[..., Any],
) -> None:
    pil_image = pytest.importorskip("PIL.Image")
    script = make_script(validate=False)
    first = script.advance()
    assert first is not None
    assert first.name == "hoy"
    script.wait_for_capture(first, script.root, since=0.0)

    pil_image.new("RGBA", (1232, 1650), LILAC).save(
        script.captures_dir / "Captura de pantalla 2026-10-29 a las 10.00.00.png"
    )
    script.poll()  # the file is seen: its size is noted
    assert script.saved == []
    script.poll()  # the size did not change: the file is complete
    assert [path.name for path in script.saved] == ["hoy.png"]
    assert script.index == 1  # on to the next scene


def test_a_file_that_is_not_a_screenshot_is_ignored_by_the_script(
    make_script: Callable[..., Any],
) -> None:
    script = make_script(validate=False)
    first = script.advance()
    assert first is not None
    script.wait_for_capture(first, script.root, since=0.0)

    (script.captures_dir / "notas.png").write_bytes(b"not a screenshot")
    script.poll()
    script.poll()

    assert script.saved == []
    assert script.index == 0  # still waiting for the first scene


def test_an_error_in_a_callback_is_printed_and_ends_the_session(
    make_script: Callable[..., Any],
    capture_screens: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = make_script()
    error = capture_screens.CaptureError("the form has no button 'x'")

    script.report_error(type(error), error, None)

    assert "the form has no button 'x'" in capsys.readouterr().err
    assert not widget_exists(script.root)
