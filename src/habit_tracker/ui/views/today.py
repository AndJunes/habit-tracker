"""The "Hoy" tab: the day's habits, one rounded row each, and tomorrow's priority.

From top to bottom: the date with the progress ring, today's priority (if it was written
last night), the habit rows, the add / delete buttons and the card for tomorrow's single task.

Delete mode happens in this same list: a box on the left and a trash can on the right of every
row, and the buttons turn into Cancel / Delete (n).

The view only draws and asks the controllers to act; the colors come from the theme or from
the areas.
"""

import tkinter as tk
from collections.abc import Callable
from datetime import date
from functools import partial

from ...domain.models import Habit
from ...service import HabitService
from ..calendar_es import MONTHS, WEEKDAYS_LONG
from ..controllers.delete_mode import DeleteMode
from ..controllers.dialogs import Dialogs, TkDialogs
from ..controllers.habit_actions import HabitActions
from ..controllers.priority import PriorityEditor
from ..theme import palette
from ..theme.cursors import pointer_cursor
from ..theme.drawing import (
    area_color_or_default,
    area_icon,
    checkbox,
    ring,
    rounded_rect,
    soft_color_of,
)
from ..theme.fonts import font, measure
from ..widgets.soft_button import SoftButton, TrashButton, TrashState
from . import habit_labels, texts
from .helpers import (
    EDIT_SEQUENCES,
    clear_children,
    for_habit,
    muted_icon_color,
    new_canvas,
    noop,
)
from .priority_card import PriorityControlsLayout, add_priority_controls

# The window is 620 px wide and the useful content 556.
CONTENT_WIDTH = 556
ROW_HEIGHT = 56

_SIDE_MARGIN = 22
_HEADER_HEIGHT = 62
_RING_BOX = 58
_ROW_GAP = 8
_ROW_RADIUS = 14
_ROW_ICON_RADIUS = 17
_ROW_ICON_X = 31
_ROW_CENTER_Y = 28
_NAME_X = 58
_NAME_Y = 20
_SUBTITLE_Y = 38

_CHECKBOX_SIDE = 28
_CHECKBOX_MARGIN = 22  # from the right edge of the row
_CHECKBOX_Y = 14

_PILL_GAP = 10  # between the pill and the checkbox
_PILL_PADDING = 9  # on each side of the text
_PILL_TOP = 18
_PILL_BOTTOM = 38
_PILL_RADIUS = 10

# Delete mode rows are shifted right to make room for the selection box.
_SELECT_BOX_X = 18
_SELECT_BOX_Y = 16
_SELECT_BOX_SIDE = 24
_DELETE_ICON_X = 73
_DELETE_TEXT_X = 100
_TRASH_MARGIN = 20

_BANNER_TEXT_WIDTH = 500
_BANNER_BOTTOM_PADDING = 14

_BUTTON_WIDTH = 272  # two buttons and the gap between them fill the 556 px
_BUTTON_GAP = 12

_PRIORITY_CARD_HEIGHT = 92
_PRIORITY_CONTROLS = PriorityControlsLayout(
    entry_x=20,
    entry_y=40,
    entry_width=410,
    entry_height=32,
    button_right=CONTENT_WIDTH - 20,
    button_y=39,
    button_height=34,
)


class TodayView(tk.Frame):
    """The "Hoy" tab.

    ``priority`` is the editor of tomorrow's priority; pass the same one to every screen that
    shows the field so that what is typed follows the person from one to the other.
    """

    def __init__(
        self,
        master: tk.Misc,
        service: HabitService,
        *,
        priority: PriorityEditor | None = None,
        dialogs: Dialogs | None = None,
    ) -> None:
        super().__init__(master, bg=palette.PAPER)
        self.service = service
        dialogs = dialogs or TkDialogs()
        self.priority = priority or PriorityEditor(service, self, dialogs=dialogs)
        self.actions = HabitActions(service, self, on_change=self.refresh, dialogs=dialogs)
        self.delete_mode = DeleteMode(
            service, self.actions, on_change=self.refresh, dialogs=dialogs
        )

        # The sections that depend on the data are frames that refresh() empties and fills
        # again; the priority card is built once because it holds what the person is typing.
        # The header keeps a fixed size so that its children neither stretch nor shrink it.
        self.header_frame = tk.Frame(
            self, bg=palette.PAPER, width=CONTENT_WIDTH, height=_HEADER_HEIGHT
        )
        self.header_frame.pack_propagate(False)
        self.header_frame.pack(padx=_SIDE_MARGIN, pady=(20, 10))
        self.banner_frame = tk.Frame(self, bg=palette.PAPER)
        self.banner_frame.pack(padx=_SIDE_MARGIN)
        self.list_frame = tk.Frame(self, bg=palette.PAPER)
        self.list_frame.pack(padx=_SIDE_MARGIN, pady=(4, 0))
        self.buttons_frame = tk.Frame(self, bg=palette.PAPER)
        self.buttons_frame.pack(padx=_SIDE_MARGIN, pady=(14, 14))
        self.priority_entry = self._build_priority_card()

        self.refresh()

    def refresh(self) -> None:
        """Redraw the whole tab with the current data."""
        today = self.service.today()
        self._draw_header(today)
        self._draw_banner()
        self._draw_list(today)
        self._draw_buttons()
        self.priority.sync()

    def reset_modes(self) -> None:
        """Leave delete mode without redrawing (the caller redraws afterwards)."""
        self.delete_mode.reset()

    # ---------- Header and banner ----------

    def _draw_header(self, today: date) -> None:
        """The weekday, the date in serif and the ring with how many of today's habits are done."""
        clear_children(self.header_frame)
        text_block = tk.Frame(self.header_frame, bg=palette.PAPER)
        text_block.pack(side="left")
        tk.Label(
            text_block,
            text=WEEKDAYS_LONG[today.weekday()],
            bg=palette.PAPER,
            fg=palette.MUTED,
            font=font("sans", 11, "bold", master=self),
        ).pack(anchor="w")
        tk.Label(
            text_block,
            text=texts.today_title(today.day, MONTHS[today.month - 1]),
            bg=palette.PAPER,
            fg=palette.INK_TITLE,
            font=font("serif", 22, master=self),
        ).pack(anchor="w")

        done, due = self.service.day_progress(today)
        canvas = new_canvas(self.header_frame, _RING_BOX, _RING_BOX, palette.PAPER)
        canvas.pack(side="right")
        center = _RING_BOX // 2
        ring(
            canvas, cx=center, cy=center, radius=24, thickness=7, fraction=done / due if due else 0
        )
        canvas.create_text(
            center,
            center,
            text=f"{done}/{due}",
            font=font("sans", 12, "bold", master=canvas),
            fill=palette.RING_TEXT,
        )

    def _draw_banner(self) -> None:
        """The peach card with the priority written last night, if there is one."""
        clear_children(self.banner_frame)
        priority = self.service.priority_for_today()
        if not priority:
            return

        canvas = new_canvas(self.banner_frame, CONTENT_WIDTH, 1, palette.PAPER)
        canvas.pack(pady=(0, 6))
        canvas.create_text(
            20,
            21,
            anchor="w",
            text=texts.PRIORITY_TODAY_LABEL,
            font=font("sans", 9, "bold", master=canvas),
            fill=palette.PEACH_LABEL,
        )
        # The width makes a long text wrap by itself.
        text_item = canvas.create_text(
            20,
            34,
            anchor="nw",
            width=_BANNER_TEXT_WIDTH,
            text=priority,
            font=font("serif", 14, master=canvas),
            fill=palette.PEACH_INK,
        )
        # The card is as tall as the wrapped text, so it is measured before painting behind it.
        height = canvas.bbox(text_item)[3] + _BANNER_BOTTOM_PADDING
        canvas.configure(height=height)
        background = rounded_rect(
            canvas, 2, 2, CONTENT_WIDTH - 2, height - 2, 14,
            fill=palette.PEACH_BACKGROUND, outline=palette.PEACH_BORDER,
        )  # fmt: skip
        canvas.tag_lower(background)

    # ---------- The list ----------

    def _draw_list(self, today: date) -> None:
        """A rounded row per habit, or the invitation to create the first one."""
        clear_children(self.list_frame)
        habits = self.service.habits()
        if not habits:
            tk.Label(
                self.list_frame,
                text=texts.NO_HABITS_YET,
                bg=palette.PAPER,
                fg=palette.MUTED,
                font=font("script", 16, master=self),
                justify="center",
            ).pack(pady=30)
            return

        if self.delete_mode.active:
            tk.Label(
                self.list_frame,
                text=texts.TODAY_DELETE_HINT,
                bg=palette.PAPER,
                fg=palette.MUTED,
                font=font("sans", 10, master=self),
            ).pack(anchor="w", pady=(0, 8))
            for habit in habits:
                self._draw_delete_row(habit)
            return

        for habit in habits:
            self._draw_row(habit, today)

    def _new_row_canvas(self) -> tk.Canvas:
        canvas = new_canvas(self.list_frame, CONTENT_WIDTH, ROW_HEIGHT, palette.PAPER)
        canvas.pack(pady=(0, _ROW_GAP))
        return canvas

    def _draw_row_background(self, canvas: tk.Canvas, fill: str) -> None:
        rounded_rect(
            canvas, 2, 2, CONTENT_WIDTH - 2, ROW_HEIGHT - 2, _ROW_RADIUS, fill=fill, outline=""
        )

    def _draw_row(self, habit: Habit, today: date) -> None:
        """One canvas per habit: rounded background, icon, name, subtitle, pill and checkbox."""
        area = self.service.area_of(habit)
        color = area_color_or_default(area)
        canvas = self._new_row_canvas()

        if not habit.applies_on(today):
            # Not its day (finances on Fridays, say): the row is dimmed, with no checkbox
            # and no click to mark. No guilt, it simply is not its day.
            self._draw_muted_row(canvas, habit, color, today)
            self._bind_edit(canvas, habit)  # editing still works on a dimmed row
            return

        done = habit.is_done(today)
        soft_color = soft_color_of(area)
        self._draw_row_background(canvas, soft_color if done else palette.ROW_BACKGROUND)
        area_icon(canvas, _ROW_ICON_X, _ROW_CENTER_Y, _ROW_ICON_RADIUS, habit.area_id, color)
        canvas.create_text(
            _NAME_X,
            _NAME_Y,
            anchor="w",
            text=habit.name,
            font=font("sans", 12, "bold", master=canvas),
            fill=palette.INK,
        )
        area_name = area.name if area else ""
        canvas.create_text(
            _NAME_X,
            _SUBTITLE_Y,
            anchor="w",
            text=habit_labels.subtitle(habit, area_name, today),
            font=font("sans", 9, master=canvas),
            fill=palette.MUTED_LIGHT,
        )

        checkbox_x = CONTENT_WIDTH - _CHECKBOX_MARGIN - _CHECKBOX_SIDE
        checkbox(canvas, checkbox_x, _CHECKBOX_Y, _CHECKBOX_SIDE, color, done)
        self._draw_pill(canvas, habit, today, checkbox_x, color, soft_color)

        # The whole row is clickable: a click marks or unmarks the habit.
        canvas.configure(cursor=pointer_cursor(canvas))
        canvas.bind("<Button-1>", for_habit(self.actions.toggle, habit))
        self._bind_edit(canvas, habit)

    def _draw_muted_row(self, canvas: tk.Canvas, habit: Habit, color: str, today: date) -> None:
        self._draw_row_background(canvas, palette.ROW_BACKGROUND)
        area_icon(
            canvas, _ROW_ICON_X, _ROW_CENTER_Y, _ROW_ICON_RADIUS, habit.area_id,
            muted_icon_color(color),
        )  # fmt: skip
        canvas.create_text(
            _NAME_X,
            _NAME_Y,
            anchor="w",
            text=habit.name,
            font=font("sans", 12, "bold", master=canvas),
            fill=palette.MUTED_LIGHT,
        )
        canvas.create_text(
            _NAME_X,
            _SUBTITLE_Y,
            anchor="w",
            text=habit_labels.muted_subtitle(self.service, habit, today),
            font=font("sans", 9, master=canvas),
            fill=palette.MUTED_LIGHT,
        )

    def _draw_pill(
        self,
        canvas: tk.Canvas,
        habit: Habit,
        today: date,
        checkbox_x: int,
        color: str,
        soft_color: str,
    ) -> None:
        """The pill next to the checkbox: quota progress, "semanal" or the streak."""
        text = habit_labels.pill_text(self.service, habit, today)
        if not text:
            return
        pill_font = font("sans", 9, "bold", master=canvas)
        right = checkbox_x - _PILL_GAP
        left = right - measure(pill_font, text) - 2 * _PILL_PADDING
        rounded_rect(
            canvas, left, _PILL_TOP, right, _PILL_BOTTOM, _PILL_RADIUS, fill=soft_color, outline=""
        )
        canvas.create_text(
            (left + right) / 2, _ROW_CENTER_Y, text=text, font=pill_font, fill=color
        )

    def _draw_delete_row(self, habit: Habit) -> None:
        """The same row in selection mode: box on the left, trash can on the right.

        Every habit is listed, also those that are not due today: deleting is a decision
        about the habit, not about the day.
        """
        area = self.service.area_of(habit)
        selected = self.delete_mode.is_selected(habit)
        canvas = self._new_row_canvas()

        background = palette.TRASH_ACTIVE_BACKGROUND if selected else palette.ROW_BACKGROUND
        self._draw_row_background(canvas, background)
        checkbox(
            canvas, _SELECT_BOX_X, _SELECT_BOX_Y, _SELECT_BOX_SIDE, palette.TRASH_ACTIVE, selected
        )
        area_icon(
            canvas, _DELETE_ICON_X, _ROW_CENTER_Y, _ROW_ICON_RADIUS, habit.area_id,
            area_color_or_default(area),
        )  # fmt: skip
        canvas.create_text(
            _DELETE_TEXT_X,
            _NAME_Y,
            anchor="w",
            text=habit.name,
            font=font("sans", 12, "bold", master=canvas),
            fill=palette.INK,
        )
        canvas.create_text(
            _DELETE_TEXT_X,
            _SUBTITLE_Y,
            anchor="w",
            text=area.name if area else "",
            font=font("sans", 9, master=canvas),
            fill=palette.MUTED_LIGHT,
        )

        # The trash can is a real button that mirrors the selection.
        state: TrashState = "active" if selected else "normal"
        trash = TrashButton(
            canvas,
            partial(self.delete_mode.toggle, habit),
            state,
            parent_background=background,
        )
        canvas.create_window(
            CONTENT_WIDTH - _TRASH_MARGIN, ROW_HEIGHT / 2, anchor="e", window=trash
        )

        # The whole row selects as well, which is easier to hit than the box.
        canvas.configure(cursor=pointer_cursor(canvas))
        canvas.bind("<Button-1>", for_habit(self.delete_mode.toggle, habit))

    def _bind_edit(self, canvas: tk.Canvas, habit: Habit) -> None:
        for sequence in EDIT_SEQUENCES:
            canvas.bind(sequence, for_habit(self.actions.edit_habit, habit))

    # ---------- Buttons and priority card ----------

    def _draw_buttons(self) -> None:
        """The button bar for the current mode: add / delete, or cancel / confirm."""
        clear_children(self.buttons_frame)
        if not self.delete_mode.active:
            self._add_button(
                texts.ADD_HABIT,
                self.actions.add_habit,
                palette.BUTTON_LILAC_BACKGROUND,
                palette.BUTTON_LILAC_TEXT,
                pad_right=_BUTTON_GAP,
            )
            self._add_button(
                texts.DELETE_HABIT,
                self.delete_mode.enter,
                palette.BUTTON_PINK_BACKGROUND,
                palette.BUTTON_PINK_TEXT,
            )
            return

        self._add_button(
            texts.CANCEL,
            self.delete_mode.cancel,
            palette.BUTTON_LILAC_BACKGROUND,
            palette.BUTTON_LILAC_TEXT,
            pad_right=_BUTTON_GAP,
        )
        count = self.delete_mode.count
        if count:
            self._add_button(
                texts.delete_selected(count),
                self.delete_mode.confirm,
                palette.TRASH_ACTIVE,
                palette.WHITE,
            )
        else:
            # Nothing marked yet: the button is visible but off, so it can't be used by mistake.
            self._add_button(
                texts.DELETE,
                noop,
                palette.ROW_BACKGROUND,
                palette.TRASH_INACTIVE,
                enabled=False,
            )

    def _add_button(
        self,
        text: str,
        command: Callable[[], object],
        background: str,
        text_color: str,
        *,
        pad_right: int = 0,
        enabled: bool = True,
    ) -> None:
        SoftButton(
            self.buttons_frame,
            text,
            command,
            background,
            text_color,
            width=_BUTTON_WIDTH,
            enabled=enabled,
        ).pack(side="left", padx=(0, pad_right))

    def _build_priority_card(self) -> tk.Entry:
        """The peach card with the field for the single task of tomorrow."""
        canvas = new_canvas(self, CONTENT_WIDTH, _PRIORITY_CARD_HEIGHT, palette.PAPER)
        canvas.pack(padx=_SIDE_MARGIN, pady=(0, 22))
        rounded_rect(
            canvas, 2, 2, CONTENT_WIDTH - 2, _PRIORITY_CARD_HEIGHT - 2, 14,
            fill=palette.PEACH_BACKGROUND, outline=palette.PEACH_BORDER,
        )  # fmt: skip
        canvas.create_text(
            20,
            24,
            anchor="w",
            text=texts.PRIORITY_TOMORROW_LABEL,
            font=font("sans", 9, "bold", master=canvas),
            fill=palette.PEACH_LABEL,
        )
        return add_priority_controls(canvas, self.priority, _PRIORITY_CONTROLS)
