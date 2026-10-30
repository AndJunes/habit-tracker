import tkinter as tk
from collections.abc import Callable, Iterator
from datetime import date

import pytest

from habit_tracker.domain.enums import MeasurementKind
from habit_tracker.domain.frequency import Daily
from habit_tracker.domain.models import Habit, Measurement
from habit_tracker.ui.forms.value_dialog import ValueDialog, ask_value
from habit_tracker.ui.theme import palette
from habit_tracker.ui.theme.tkutil import widget_exists
from habit_tracker.ui.widgets.soft_button import SoftButton

DAY = date(2026, 11, 3)


def measured(measurement: Measurement | None = None) -> Habit:
    return Habit(
        id=1,
        name="Meditar",
        area_id="salud",
        frequency=Daily(),
        start=date(2026, 11, 1),
        measurement=measurement or Measurement(MeasurementKind.DURATION, 30, "minutos"),
    )


def descendants(widget: tk.Misc) -> Iterator[tk.Misc]:
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def value_entry(dialog: ValueDialog) -> tk.Entry:
    return next(w for w in descendants(dialog) if isinstance(w, tk.Entry))


def type_value(dialog: ValueDialog, text: str) -> None:
    entry = value_entry(dialog)
    entry.delete(0, "end")
    entry.insert(0, text)


def press(dialog: ValueDialog, text: str) -> None:
    button = next(w for w in descendants(dialog) if isinstance(w, SoftButton) and w.text == text)
    button.command()


def labels(dialog: ValueDialog) -> list[str]:
    return [str(w.cget("text")) for w in descendants(dialog) if isinstance(w, tk.Label)]


def open_dialog(root: tk.Tk, habit: Habit | None = None) -> ValueDialog:
    dialog = ValueDialog(root, habit or measured(), DAY)
    dialog.withdraw()
    return dialog


class TestValueDialog:
    def test_it_validates_and_delivers_the_number(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)
        assert value_entry(dialog).get() == "30"  # it arrives with the goal typed
        for bad in ("abc", "0", "-3", "", "nan", "inf"):
            type_value(dialog, bad)
            press(dialog, "Registrar")
            assert dialog.result is None
            assert "mayor que cero" in dialog.error_text
            assert dialog.winfo_exists()  # a rejected number does not close the dialog
        type_value(dialog, "7,5")
        press(dialog, "Registrar")
        assert dialog.result == 7.5
        assert not widget_exists(dialog)

    def test_the_goal_is_one_click_away(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)
        press(dialog, "Registrar")
        assert dialog.result == 30

    def test_the_result_is_a_float_even_for_a_whole_number(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)
        type_value(dialog, "12")
        press(dialog, "Registrar")
        assert isinstance(dialog.result, float)

    def test_the_error_is_empty_until_a_number_is_rejected(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)
        assert dialog.error_text == ""

    def test_cancel_closes_without_a_result(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)
        type_value(dialog, "12")
        press(dialog, "Cancelar")
        assert dialog.result is None
        assert not widget_exists(dialog)

    def test_it_shows_the_habit_the_unit_and_the_reference_goals(self, tk_root: tk.Tk) -> None:
        habit = measured(
            Measurement(MeasurementKind.DURATION, 30, "minutos", minimum=10, ideal=45)
        )
        dialog = open_dialog(tk_root, habit)
        shown = labels(dialog)
        assert dialog.title() == "Meditar"
        assert "¿Cuánto hiciste hoy?" in shown
        assert "Meditar" in shown
        assert "minutos" in shown
        assert "meta 30 · mínimo 10 · ideal 45. Cualquier cantidad cuenta." in shown

    def test_only_the_goal_is_listed_when_there_are_no_reference_goals(
        self, tk_root: tk.Tk
    ) -> None:
        dialog = open_dialog(tk_root)
        assert "meta 30. Cualquier cantidad cuenta." in labels(dialog)

    def test_a_decimal_goal_is_shown_as_written_and_a_whole_float_without_a_trailing_zero(
        self, tk_root: tk.Tk
    ) -> None:
        decimal = open_dialog(
            tk_root, measured(Measurement(MeasurementKind.QUANTITY, 2.5, "litros"))
        )
        assert value_entry(decimal).get() == "2.5"
        whole = open_dialog(tk_root, measured(Measurement(MeasurementKind.QUANTITY, 90.0, "min")))
        assert value_entry(whole).get() == "90"

    def test_the_error_is_painted_in_the_warning_color(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)
        type_value(dialog, "x")
        press(dialog, "Registrar")
        error = next(
            w for w in descendants(dialog) if isinstance(w, tk.Label) and w.cget("text")
            and "mayor" in str(w.cget("text"))
        )  # fmt: skip
        assert error.cget("fg") == palette.TRASH_ACTIVE

    def test_a_habit_that_is_not_measured_is_refused(self, tk_root: tk.Tk) -> None:
        plain = Habit(id=1, name="Leer", area_id="salud", frequency=Daily(), start=DAY)
        with pytest.raises(ValueError, match="measured"):
            ValueDialog(tk_root, plain, DAY)

    def test_it_is_not_resizable(self, tk_root: tk.Tk) -> None:
        assert open_dialog(tk_root).resizable() == (False, False)


def answer_when_open(root: tk.Tk, action: Callable[[ValueDialog], object]) -> None:
    """Runs ``action`` on the value dialog as soon as it exists, inside ``ask_value``'s wait.

    Whatever happens, the dialog is closed afterwards, so a failing test cannot hang.
    """

    def run() -> None:
        dialogs = [w for w in root.winfo_children() if isinstance(w, ValueDialog)]
        try:
            dialogs[0].attributes("-alpha", 0.0)  # keep the test from flashing a window
            action(dialogs[0])
        finally:
            for dialog in dialogs:
                if widget_exists(dialog):
                    dialog.destroy()

    root.after(0, run)


class TestAskValue:
    def test_it_returns_the_number_the_person_registers(self, tk_root: tk.Tk) -> None:
        def register(dialog: ValueDialog) -> None:
            type_value(dialog, "12")
            press(dialog, "Registrar")

        answer_when_open(tk_root, register)
        assert ask_value(tk_root, measured(), DAY) == 12

    def test_it_returns_the_goal_when_the_person_just_confirms(self, tk_root: tk.Tk) -> None:
        answer_when_open(tk_root, lambda dialog: press(dialog, "Registrar"))
        assert ask_value(tk_root, measured(), DAY) == 30

    def test_it_returns_none_when_the_person_cancels(self, tk_root: tk.Tk) -> None:
        answer_when_open(tk_root, lambda dialog: press(dialog, "Cancelar"))
        assert ask_value(tk_root, measured(), DAY) is None

    def test_it_returns_none_when_the_window_is_closed(self, tk_root: tk.Tk) -> None:
        answer_when_open(tk_root, lambda dialog: dialog.destroy())
        assert ask_value(tk_root, measured(), DAY) is None

    def test_an_invalid_number_keeps_it_open_until_a_valid_one_is_sent(
        self, tk_root: tk.Tk
    ) -> None:
        def retry(dialog: ValueDialog) -> None:
            type_value(dialog, "0")
            press(dialog, "Registrar")
            assert widget_exists(dialog)
            type_value(dialog, "20")
            press(dialog, "Registrar")

        answer_when_open(tk_root, retry)
        assert ask_value(tk_root, measured(), DAY) == 20

    def test_it_refuses_a_habit_that_is_not_measured_before_opening_anything(
        self, tk_root: tk.Tk
    ) -> None:
        plain = Habit(id=1, name="Leer", area_id="salud", frequency=Daily(), start=DAY)
        with pytest.raises(ValueError, match="measured"):
            ask_value(tk_root, plain, DAY)
        assert not [w for w in tk_root.winfo_children() if isinstance(w, ValueDialog)]


class TestKeyboard:
    def test_escape_cancels_like_the_cancel_button(
        self, tk_root: tk.Tk, fake_event: Callable[..., object]
    ) -> None:
        dialog = open_dialog(tk_root)
        assert dialog.bind("<Escape>")
        type_value(dialog, "12")

        handled = dialog._on_escape(fake_event())

        assert handled == "break"
        assert dialog.result is None  # what was typed is not delivered
        assert not widget_exists(dialog)

    def test_cancel_closes_without_a_result(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)

        dialog.cancel()

        assert dialog.result is None
        assert not widget_exists(dialog)

    def test_ask_value_returns_none_when_the_dialog_is_cancelled_with_escape(
        self, tk_root: tk.Tk, fake_event: Callable[..., object]
    ) -> None:
        answer_when_open(tk_root, lambda dialog: dialog._on_escape(fake_event()))

        assert ask_value(tk_root, measured(), DAY) is None

    def test_enter_still_accepts_from_the_field(self, tk_root: tk.Tk) -> None:
        dialog = open_dialog(tk_root)

        assert value_entry(dialog).bind("<Return>")

    def test_tab_goes_from_the_field_to_cancel_and_then_to_register(self, tk_root: tk.Tk) -> None:
        dialog = ValueDialog(tk_root, measured(), DAY)
        dialog.attributes("-alpha", 0.0)
        dialog.update()
        if not dialog.winfo_viewable():
            dialog.destroy()
            pytest.skip("windows cannot be mapped in this environment, so there is no layout")
        buttons = {w.text: w for w in descendants(dialog) if isinstance(w, SoftButton)}

        assert value_entry(dialog).tk_focusNext() is buttons["Cancelar"]
        assert buttons["Cancelar"].tk_focusNext() is buttons["Registrar"]

    def test_the_escape_key_cancels_from_the_field(self, tk_root: tk.Tk) -> None:
        dialog = ValueDialog(tk_root, measured(), DAY)
        dialog.attributes("-alpha", 0.0)
        dialog.update()
        dialog.focus_force()
        dialog.update()
        focused = dialog.focus_get()
        if focused is None:
            dialog.destroy()
            pytest.skip("the window did not get the keyboard focus")

        focused.event_generate("<Escape>")

        assert dialog.result is None
        assert not widget_exists(dialog)
