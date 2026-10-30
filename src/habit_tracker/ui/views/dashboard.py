"""The full-screen dashboard: the big view that appears when the window fills the screen.

A lilac stats bar, a three-column grid (today's habits and priority / the month's calendar and
dates / the month's charts) and, across the whole width, the consistency map.

The page background is BACKGROUND and every card is a canvas in PAPER, the other way round
from the window mode, where the whole window is the card. All the content lives in a page of
fixed width, centered in a canvas that scrolls vertically.

The charts are not drawn here: ``charts`` knows how to paint them at any size.
"""

import calendar
import tkinter as tk
from collections.abc import Callable
from datetime import date
from functools import partial

from ...clock import Clock, SystemClock
from ...domain.models import Habit
from ...domain.stats import MonthStats
from ...service import HabitService
from ..calendar_es import MONTHS, MONTHS_SHORT_UPPER, WEEKDAYS_SHORT
from ..charts import (
    area_bars,
    balance_donut,
    consistency_map,
    donut_legend,
    draw_legend_rows,
    legend_rows,
    month_pace,
)
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
    rounded_rect,
    soft_color_of,
)
from ..theme.fonts import font, measure
from ..theme.tkutil import TkEvent
from ..widgets.scrollbar import SoftScrollbar, bind_mousewheel
from ..widgets.soft_button import SoftButton, TrashButton, TrashState
from . import chart_rows, texts
from .day_cells import DayCellStyle, completed_area_colors, draw_day_cell
from .helpers import (
    EDIT_SEQUENCES,
    clear_children,
    for_habit,
    muted_icon_color,
    new_canvas,
    noop,
    tagged_items,
    truncate_text,
)
from .priority_card import PriorityControlsLayout, add_priority_controls
from .stats_banner import DASHBOARD_BANNER, draw_stats_banner

# The page and the three columns of the grid.
PAGE_WIDTH = 1280
GAP = 18  # between blocks and between cards
COLUMN_A_WIDTH = 388  # today's habits and priority
COLUMN_B_WIDTH = 482  # calendar and dates
COLUMN_C_WIDTH = 372  # the three charts
COLUMN_C_INNER = 332  # what is left of column C inside its 20 px padding

CARD_RADIUS = 22
CARD_PADDING = 20

# The buttons of the "Hoy" card: two side by side inside its useful width.
BUTTON_HEIGHT = 38
_BUTTON_GAP = 12
BUTTON_WIDTH = (COLUMN_A_WIDTH - 2 * CARD_PADDING - _BUTTON_GAP) // 2

# Habit rows of the "Hoy" card: 46 px tall, 8 px apart.
_ROW_HEIGHT = 46
_ROW_STEP = 54
_ROW_RADIUS = 12
_ROWS_TOP = 44
_ROWS_TOP_DELETE_MODE = 64  # delete mode adds a hint line under the title
_ROW_ICON_RADIUS = 15
_ROW_CENTER = _ROW_HEIGHT // 2
_ROW_ICON_X = 35
_NAME_X = 58
_CHECKBOX_SIDE = 26
_CHECKBOX_GAP = 10  # the name is cut this far from the checkbox
_DELETE_ICON_X = 76
_DELETE_TEXT_X = 98
_DELETE_BOX_X = 32
_DELETE_BOX_Y = 12
_DELETE_BOX_SIDE = 22
_TRASH_MARGIN = 24
_EMPTY_TODAY_CARD_HEIGHT = 170
_HABITS_BOTTOM_PADDING = 14
_BUTTONS_BOTTOM_PADDING = 20

_PRIORITY_CARD_HEIGHT = 116
_PRIORITY_CONTROLS = PriorityControlsLayout(
    entry_x=CARD_PADDING,
    entry_y=42,
    entry_width=250,
    entry_height=32,
    button_right=COLUMN_A_WIDTH - CARD_PADDING,
    button_y=42,
    button_height=32,
)

# The calendar card: seven columns with 6 px between them fill the card's useful width.
_CALENDAR_GAP = 6
_CALENDAR_CELL_WIDTH = (COLUMN_B_WIDTH - 2 * CARD_PADDING - 6 * _CALENDAR_GAP) / 7
_CALENDAR_CELL_HEIGHT = 62
_CALENDAR_GRID_TOP = 66
_CALENDAR_WEEKDAYS_Y = 52
_CALENDAR_LEGEND_GAP = 22
_CALENDAR_LEGEND_ROW_HEIGHT = 20
_CALENDAR_BOTTOM_PADDING = 18
_CALENDAR_STYLE = DayCellStyle(radius=10, dots_y=44, max_dots=5)

# The dates card: a chip with the day and a title per date.
_DATES_EMPTY_HEIGHT = 96
_DATES_TOP = 44
_DATES_STEP = 46
_DATES_BOTTOM_PADDING = 14
_CHIP_LEFT = 20
_CHIP_RIGHT = 58
_CHIP_TOP = 4
_CHIP_BOTTOM = 42
_DATES_TITLE_X = 70

# Column C.
_BARS_TOP = 48
_BARS_ROW_HEIGHT = 26  # what area_bars takes per row
_BARS_BOTTOM_PADDING = 14
_DONUT_RADIUS = 54
_DONUT_THICKNESS = 16
_DONUT_LEGEND_OFFSET = 128  # from the card's inner left edge to the legend
_DONUT_LEGEND_STEP = 20
_PACE_TOP = 56
_PACE_HEIGHT = 78  # what month_pace takes

# The consistency map across the page.
_MAP_TOP = 52
_MAP_ROW_STEP = 38
_MAP_LABEL_WIDTH = 150
_MAP_GAP = 3
_MAP_ICON_RADIUS = 13  # 26 px squares, like the heatmap of the design
_MAP_LEGEND_HEIGHT = 60
_MAP_EMPTY_HEIGHT = 40
_MAP_BOTTOM_PADDING = 18


class DashboardView(tk.Frame):
    """The full-screen dashboard, with a vertical scroll and a page of fixed width.

    Like the other screens it takes the shared ``priority`` editor, so what is typed for
    tomorrow follows the person between the window and full screen.
    """

    def __init__(
        self,
        master: tk.Misc,
        service: HabitService,
        *,
        priority: PriorityEditor | None = None,
        dialogs: Dialogs | None = None,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(master, bg=palette.BACKGROUND)
        self.service = service
        self._clock = clock or SystemClock()
        dialogs = dialogs or TkDialogs()
        self.priority = priority or PriorityEditor(service, self, dialogs=dialogs)
        self.actions = HabitActions(service, self, on_change=self.refresh, dialogs=dialogs)
        self.delete_mode = DeleteMode(
            service, self.actions, on_change=self.refresh, dialogs=dialogs
        )
        self.priority_entry: tk.Entry | None = None  # rebuilt by every refresh

        # The scroll frame: a canvas that fills everything and, inside it, a frame (the
        # page) hung from it. The bar and the wheel move the same view.
        scrollbar = SoftScrollbar(
            self,
            lambda *order: self.scroll_canvas.yview(*order),
            parent_background=palette.BACKGROUND,
        )
        scrollbar.pack(side="right", fill="y")
        self.scroll_canvas = tk.Canvas(
            self,
            bg=palette.BACKGROUND,
            highlightthickness=0,
            yscrollincrement=1,
            yscrollcommand=scrollbar.set,
        )
        self.scroll_canvas.pack(side="left", fill="both", expand=True)

        self.page = tk.Frame(self.scroll_canvas, bg=palette.BACKGROUND)
        # anchor="n" hangs the page from its top center, so moving the window item's x
        # is all it takes to keep it centered.
        self._page_window = self.scroll_canvas.create_window(0, 0, anchor="n", window=self.page)

        self.scroll_canvas.bind("<Configure>", self._on_canvas_resize)
        self.page.bind("<Configure>", lambda _event: self._fit_scroll_region())
        bind_mousewheel(self.scroll_canvas, self.scroll_canvas)
        bind_mousewheel(self.page, self.scroll_canvas)

        self.refresh()

    # ---------- Scroll ----------

    def _on_canvas_resize(self, event: TkEvent) -> None:
        """Center the page again when the canvas changes size."""
        # A canvas narrower than the page is not expected in full screen; if it happens the
        # page is pinned to the left edge instead of being cut off on that side.
        self.scroll_canvas.coords(self._page_window, max(event.width, PAGE_WIDTH) / 2, 0)
        self._fit_scroll_region()

    def _fit_scroll_region(self) -> None:
        """Scroll exactly the height of the content.

        The width is left at 0 on purpose: the page is centered, so its x moves with the
        window, and a scroll region that included that shift would pin the view to the left
        edge of the content and the dashboard would look pushed to one side.
        """
        box = self.scroll_canvas.bbox("all")
        if box:
            self.scroll_canvas.configure(scrollregion=(0, 0, 0, box[3]))

    def _bind_wheel(self, widget: tk.Misc) -> None:
        """Make the wheel and the trackpad scroll even with the pointer over a card."""
        bind_mousewheel(widget, self.scroll_canvas)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    # ---------- Redrawing ----------

    def refresh(self) -> None:
        """Empty the page and build the dashboard again with the current data."""
        clear_children(self.page)
        self.priority.sync()
        today = self.service.today()
        month = self.service.month_stats(today.year, today.month)  # computed once
        self._draw_page_title()
        self._draw_stats_bar(today, month)
        self._draw_grid(today, month)
        self._draw_consistency_card(today, month)
        self._bind_wheel(self.page)

    def reset_modes(self) -> None:
        """Leave delete mode without redrawing (the caller redraws afterwards)."""
        self.delete_mode.reset()

    # ---------- Building blocks ----------

    def _card(
        self,
        parent: tk.Misc,
        width: int,
        height: float,
        *,
        fill: str = palette.PAPER,
        border: str = palette.BORDER,
        last: bool = False,
    ) -> tk.Canvas:
        """The canvas of a card with its rounded background already painted.

        The 1 px margin keeps the border from being clipped at the canvas edges.
        """
        canvas = new_canvas(parent, width, height, palette.BACKGROUND)
        canvas.pack(pady=(0, 0 if last else GAP))
        rounded_rect(canvas, 1, 1, width - 1, height - 1, CARD_RADIUS, fill=fill, outline=border)
        return canvas

    def _card_title(self, canvas: tk.Canvas, text: str) -> None:
        canvas.create_text(
            CARD_PADDING,
            24,
            anchor="w",
            text=text,
            font=font("serif", 16, master=canvas),
            fill=palette.INK_TITLE,
        )

    def _card_note(self, canvas: tk.Canvas, text: str) -> None:
        """The small gray line under the title of the charts' cards."""
        canvas.create_text(
            CARD_PADDING,
            42,
            anchor="w",
            text=text,
            font=font("sans", 9, master=canvas),
            fill=palette.MUTED_LIGHT,
        )

    # ---------- 1. Page title ----------

    def _draw_page_title(self) -> None:
        title = tk.Frame(self.page, bg=palette.BACKGROUND)
        title.pack(pady=(28, GAP))
        tk.Label(
            title,
            text=texts.DASHBOARD_BRAND,
            bg=palette.BACKGROUND,
            fg=palette.LILAC,
            font=font("script", 14, master=self),
        ).pack()
        tk.Label(
            title,
            text=texts.DASHBOARD_TITLE,
            bg=palette.BACKGROUND,
            fg=palette.INK_TITLE,
            font=font("serif", 26, master=self),
        ).pack()

    # ---------- 2. Stats bar: greeting and the three figures ----------

    def _draw_stats_bar(self, today: date, month: MonthStats) -> None:
        canvas = new_canvas(
            self.page, DASHBOARD_BANNER.width, DASHBOARD_BANNER.height, palette.BACKGROUND
        )
        canvas.pack(pady=(0, GAP))
        draw_stats_banner(
            canvas,
            DASHBOARD_BANNER,
            today=today,
            hour=self._clock.now().hour,
            progress=self.service.day_progress(today),
            longest_streak=self.service.longest_streak(),
            month_checks=month.total,
        )

    # ---------- 3. The three-column grid ----------

    def _draw_grid(self, today: date, month: MonthStats) -> None:
        grid = tk.Frame(self.page, bg=palette.BACKGROUND)
        grid.pack(pady=(0, GAP))

        # sticky="n" aligns the columns at the top although they differ in height.
        column_a = tk.Frame(grid, bg=palette.BACKGROUND)
        column_a.grid(row=0, column=0, sticky="n")
        column_b = tk.Frame(grid, bg=palette.BACKGROUND)
        column_b.grid(row=0, column=1, sticky="n", padx=GAP)
        column_c = tk.Frame(grid, bg=palette.BACKGROUND)
        column_c.grid(row=0, column=2, sticky="n")

        self._draw_today_card(column_a, today)
        self._draw_priority_card(column_a)
        self._draw_calendar_card(column_b, today)
        self._draw_dates_card(column_b, today)
        self._draw_bars_card(column_c, month)
        self._draw_balance_card(column_c, month)
        self._draw_pace_card(column_c, month, today)

    # ----- Column A: the day's habits and tomorrow's priority -----

    def _draw_today_card(self, parent: tk.Misc, today: date) -> None:
        habits = self.service.habits()
        if not habits:
            # No habits: the invitation and, right below it, the button to create the first.
            canvas = self._card(parent, COLUMN_A_WIDTH, _EMPTY_TODAY_CARD_HEIGHT)
            self._card_title(canvas, texts.DASHBOARD_TODAY_TITLE)
            canvas.create_text(
                COLUMN_A_WIDTH / 2,
                70,
                text=texts.NO_HABITS_YET,
                font=font("script", 14, master=canvas),
                fill=palette.MUTED,
                justify="center",
            )
            self._add_button(
                canvas,
                CARD_PADDING,
                108,
                texts.ADD_HABIT,
                self.actions.add_habit,
                palette.BUTTON_LILAC_BACKGROUND,
                palette.BUTTON_LILAC_TEXT,
                width=COLUMN_A_WIDTH - 2 * CARD_PADDING,
            )
            return

        delete_mode = self.delete_mode.active
        top = _ROWS_TOP_DELETE_MODE if delete_mode else _ROWS_TOP
        buttons_y = (
            top + len(habits) * _ROW_STEP - (_ROW_STEP - _ROW_HEIGHT) + _HABITS_BOTTOM_PADDING
        )
        canvas = self._card(
            parent, COLUMN_A_WIDTH, buttons_y + BUTTON_HEIGHT + _BUTTONS_BOTTOM_PADDING
        )
        self._card_title(canvas, texts.DASHBOARD_TODAY_TITLE)
        if delete_mode:
            canvas.create_text(
                CARD_PADDING,
                46,
                anchor="w",
                text=texts.DASHBOARD_DELETE_HINT,
                font=font("sans", 9, master=canvas),
                fill=palette.MUTED,
            )
        y = top
        for habit in habits:
            if delete_mode:
                self._draw_delete_row(canvas, habit, y)
            else:
                self._draw_habit_row(canvas, habit, y, today)
            y += _ROW_STEP
        self._draw_today_buttons(canvas, buttons_y)

    def _add_button(
        self,
        canvas: tk.Canvas,
        x: float,
        y: float,
        text: str,
        command: Callable[[], object],
        background: str,
        text_color: str,
        *,
        width: int = BUTTON_WIDTH,
        enabled: bool = True,
    ) -> None:
        """A themed button hung from the card (create_window puts a widget in a canvas)."""
        button = SoftButton(
            canvas,
            text,
            command,
            background,
            text_color,
            width=width,
            height=BUTTON_HEIGHT,
            enabled=enabled,
        )
        canvas.create_window(x, y, anchor="nw", window=button)

    def _draw_today_buttons(self, canvas: tk.Canvas, y: float) -> None:
        """The two buttons at the bottom: add and delete, or cancel and confirm with a count."""
        right_x = CARD_PADDING + BUTTON_WIDTH + _BUTTON_GAP
        lilac = (palette.BUTTON_LILAC_BACKGROUND, palette.BUTTON_LILAC_TEXT)
        if not self.delete_mode.active:
            self._add_button(
                canvas, CARD_PADDING, y, texts.ADD_HABIT, self.actions.add_habit, *lilac
            )
            self._add_button(
                canvas,
                right_x,
                y,
                texts.DELETE_HABIT,
                self.delete_mode.enter,
                palette.BUTTON_PINK_BACKGROUND,
                palette.BUTTON_PINK_TEXT,
            )
            return
        self._add_button(canvas, CARD_PADDING, y, texts.CANCEL, self.delete_mode.cancel, *lilac)
        count = self.delete_mode.count
        if count:
            self._add_button(
                canvas,
                right_x,
                y,
                texts.delete_selected(count),
                self.delete_mode.confirm,
                palette.TRASH_ACTIVE,
                palette.WHITE,
            )
        else:
            # Nothing marked yet: the button is visible but off, with no click.
            self._add_button(
                canvas,
                right_x,
                y,
                texts.DELETE,
                noop,
                palette.ROW_BACKGROUND,
                palette.TRASH_INACTIVE,
                enabled=False,
            )

    def _name_width(self, delete_mode: bool = False) -> float:
        """How wide a habit name may be before it is cut, up to just before the control."""
        if delete_mode:
            return COLUMN_A_WIDTH - 24 - TrashButton.SIDE - 8 - 98
        return COLUMN_A_WIDTH - 20 - _CHECKBOX_SIDE - _CHECKBOX_GAP - _NAME_X

    def _row_background(self, canvas: tk.Canvas, y: float, fill: str) -> None:
        rounded_rect(
            canvas,
            CARD_PADDING,
            y,
            COLUMN_A_WIDTH - CARD_PADDING,
            y + _ROW_HEIGHT,
            _ROW_RADIUS,
            fill=fill,
            outline="",
        )

    def _draw_habit_row(self, canvas: tk.Canvas, habit: Habit, y: float, today: date) -> None:
        """A clickable row per habit (dimmed when it is not due today)."""
        area = self.service.area_of(habit)
        color = area_color_or_default(area)
        name_font = font("sans", 11, "bold", master=canvas)
        name_width = self._name_width()
        center_y = y + _ROW_CENTER

        if not habit.applies_on(today):
            # Not its day: dimmed, with no checkbox and no click.
            self._row_background(canvas, y, palette.ROW_BACKGROUND)
            area_icon(
                canvas, _ROW_ICON_X, center_y, _ROW_ICON_RADIUS, habit.area_id,
                muted_icon_color(color),
            )  # fmt: skip
            canvas.create_text(
                _NAME_X,
                center_y,
                anchor="w",
                text=truncate_text(name_font, habit.name, name_width),
                font=name_font,
                fill=palette.MUTED_LIGHT,
            )
            return

        done = habit.is_done(today)
        # Everything drawn for the row gets the habit's tag so that all of it takes the click.
        tag = f"h{habit.id}"
        with tagged_items(canvas, tag):
            self._row_background(
                canvas, y, soft_color_of(area) if done else palette.ROW_BACKGROUND
            )
            area_icon(canvas, _ROW_ICON_X, center_y, _ROW_ICON_RADIUS, habit.area_id, color)
            canvas.create_text(
                _NAME_X,
                center_y,
                anchor="w",
                text=truncate_text(name_font, habit.name, name_width),
                font=name_font,
                fill=palette.INK,
            )
            checkbox(
                canvas, COLUMN_A_WIDTH - 20 - _CHECKBOX_SIDE, y + 10, _CHECKBOX_SIDE, color, done
            )

        canvas.tag_bind(tag, "<Button-1>", for_habit(self.actions.toggle, habit))
        for sequence in EDIT_SEQUENCES:
            canvas.tag_bind(tag, sequence, for_habit(self.actions.edit_habit, habit))
        self._pointer_over(canvas, tag)

    def _draw_delete_row(self, canvas: tk.Canvas, habit: Habit, y: float) -> None:
        """The row in selection mode: box on the left, trash can on the right, pink if marked.

        Every habit is listed, also those that are not due today: deleting is a decision
        about the habit, not about the day.
        """
        color = area_color_or_default(self.service.area_of(habit))
        selected = self.delete_mode.is_selected(habit)
        background = palette.TRASH_ACTIVE_BACKGROUND if selected else palette.ROW_BACKGROUND
        name_font = font("sans", 11, "bold", master=canvas)
        center_y = y + _ROW_CENTER

        tag = f"x{habit.id}"
        with tagged_items(canvas, tag):
            self._row_background(canvas, y, background)
            checkbox(
                canvas, _DELETE_BOX_X, y + _DELETE_BOX_Y, _DELETE_BOX_SIDE, palette.TRASH_ACTIVE,
                selected,
            )  # fmt: skip
            area_icon(canvas, _DELETE_ICON_X, center_y, _ROW_ICON_RADIUS, habit.area_id, color)
            canvas.create_text(
                _DELETE_TEXT_X,
                center_y,
                anchor="w",
                text=truncate_text(name_font, habit.name, self._name_width(delete_mode=True)),
                font=name_font,
                fill=palette.INK,
            )
        canvas.tag_bind(tag, "<Button-1>", for_habit(self.delete_mode.toggle, habit))
        self._pointer_over(canvas, tag)

        # The trash can is a real button: it mirrors the selection and toggles it too.
        state: TrashState = "active" if selected else "normal"
        trash = TrashButton(
            canvas, partial(self.delete_mode.toggle, habit), state, parent_background=background
        )
        canvas.create_window(COLUMN_A_WIDTH - _TRASH_MARGIN, center_y, anchor="e", window=trash)

    def _pointer_over(self, canvas: tk.Canvas, tag: str) -> None:
        """The pointing hand only over the rows (the rest of the card is not clickable)."""
        pointer = pointer_cursor(canvas)
        canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.configure(cursor=pointer))
        canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.configure(cursor=""))

    def _draw_priority_card(self, parent: tk.Misc) -> None:
        """The peach card with the field for the single task of tomorrow."""
        canvas = self._card(
            parent,
            COLUMN_A_WIDTH,
            _PRIORITY_CARD_HEIGHT,
            fill=palette.PEACH_BACKGROUND,
            border=palette.PEACH_BORDER,
            last=True,
        )
        canvas.create_text(
            CARD_PADDING,
            26,
            anchor="w",
            text=texts.DASHBOARD_PRIORITY_LABEL,
            font=font("sans", 9, "bold", master=canvas),
            fill=palette.PEACH_LABEL,
        )
        self.priority_entry = add_priority_controls(canvas, self.priority, _PRIORITY_CONTROLS)
        canvas.create_text(
            CARD_PADDING,
            94,
            anchor="w",
            text=texts.DASHBOARD_PRIORITY_NOTE,
            font=font("script", 13, master=canvas),
            fill=palette.PEACH_NOTE,
        )

    # ----- Column B: the month's calendar and its important dates -----

    def _draw_calendar_card(self, parent: tk.Misc, today: date) -> None:
        important = {day for day, _ in self.service.important_dates(today.year, today.month)}
        colors = completed_area_colors(self.service, today.year, today.month)
        weeks = calendar.monthcalendar(today.year, today.month)

        grid_height = len(weeks) * _CALENDAR_CELL_HEIGHT + (len(weeks) - 1) * _CALENDAR_GAP
        legend_y = _CALENDAR_GRID_TOP + grid_height + _CALENDAR_LEGEND_GAP
        # The legend takes as many rows as it needs (with eight areas it does not fit in one).
        legend_font = font("sans", 9, "bold", master=parent)
        rows = legend_rows(self.service.areas(), legend_font, COLUMN_B_WIDTH - 2 * CARD_PADDING)
        height = (
            legend_y
            + max(0, len(rows) - 1) * _CALENDAR_LEGEND_ROW_HEIGHT
            + _CALENDAR_BOTTOM_PADDING
        )

        canvas = self._card(parent, COLUMN_B_WIDTH, height)
        self._card_title(canvas, f"{MONTHS[today.month - 1]} {today.year}")
        canvas.create_text(
            COLUMN_B_WIDTH - CARD_PADDING,
            24,
            anchor="e",
            text=texts.DASHBOARD_CALENDAR_NOTE,
            font=font("script", 12, master=canvas),
            fill=palette.LILAC,
        )

        weekday_font = font("sans", 9, "bold", master=canvas)
        for column, name in enumerate(WEEKDAYS_SHORT):
            center_x = (
                CARD_PADDING
                + column * (_CALENDAR_CELL_WIDTH + _CALENDAR_GAP)
                + _CALENDAR_CELL_WIDTH / 2
            )
            canvas.create_text(
                center_x,
                _CALENDAR_WEEKDAYS_Y,
                text=name,
                font=weekday_font,
                fill=palette.WEEKDAY_HEADER,
            )

        for row, week in enumerate(weeks):
            for column, number in enumerate(week):
                if number == 0:
                    continue  # a gap that belongs to another month
                draw_day_cell(
                    canvas,
                    CARD_PADDING + column * (_CALENDAR_CELL_WIDTH + _CALENDAR_GAP),
                    _CALENDAR_GRID_TOP + row * (_CALENDAR_CELL_HEIGHT + _CALENDAR_GAP),
                    _CALENDAR_CELL_WIDTH,
                    _CALENDAR_CELL_HEIGHT,
                    date(today.year, today.month, number),
                    today,
                    _CALENDAR_STYLE,
                    flagged=number in important,
                    area_colors=colors.get(number, []),
                )

        draw_legend_rows(
            canvas, rows, COLUMN_B_WIDTH, legend_y, _CALENDAR_LEGEND_ROW_HEIGHT, legend_font
        )

    def _draw_dates_card(self, parent: tk.Misc, today: date) -> None:
        important = self.service.important_dates(today.year, today.month)
        if not important:
            canvas = self._card(parent, COLUMN_B_WIDTH, _DATES_EMPTY_HEIGHT, last=True)
            self._card_title(canvas, texts.DASHBOARD_DATES_TITLE)
            canvas.create_text(
                COLUMN_B_WIDTH / 2,
                64,
                text=texts.DASHBOARD_NO_DATES,
                font=font("sans", 10, master=canvas),
                fill=palette.MUTED_LIGHT,
            )
            return

        height = _DATES_TOP + len(important) * _DATES_STEP + _DATES_BOTTOM_PADDING
        canvas = self._card(parent, COLUMN_B_WIDTH, height, last=True)
        self._card_title(canvas, texts.DASHBOARD_DATES_TITLE)

        month_text = MONTHS_SHORT_UPPER[today.month - 1]
        title_font = font("sans", 11, "bold", master=canvas)
        y = _DATES_TOP
        for day, title in important:
            # The date chip: the day big and the month small below it.
            rounded_rect(
                canvas, _CHIP_LEFT, y + _CHIP_TOP, _CHIP_RIGHT, y + _CHIP_BOTTOM, 12,
                fill=palette.DATE_CHIP_BACKGROUND, outline="",
            )  # fmt: skip
            chip_center = (_CHIP_LEFT + _CHIP_RIGHT) / 2
            canvas.create_text(
                chip_center,
                y + 17,
                text=str(day),
                font=font("sans", 13, "bold", master=canvas),
                fill=palette.DATE_CHIP_DAY,
            )
            canvas.create_text(
                chip_center,
                y + 31,
                text=month_text,
                font=font("sans", 7, "bold", master=canvas),
                fill=palette.DATE_CHIP_MONTH,
            )
            canvas.create_text(
                _DATES_TITLE_X,
                y + 23,
                anchor="w",
                text=truncate_text(
                    title_font, title, COLUMN_B_WIDTH - CARD_PADDING - _DATES_TITLE_X
                ),
                font=title_font,
                fill=palette.INK_TITLE,
            )
            y += _DATES_STEP

    # ----- Column C: the month's charts -----

    def _draw_bars_card(self, parent: tk.Misc, month: MonthStats) -> None:
        rows = chart_rows.area_bar_rows(month)
        # area_bars is deterministic (26 px per row, and 26 for its message when there is
        # nothing), so the card's height is known before drawing.
        height = _BARS_TOP + _BARS_ROW_HEIGHT * max(len(rows), 1) + _BARS_BOTTOM_PADDING
        canvas = self._card(parent, COLUMN_C_WIDTH, height)
        self._card_title(canvas, texts.MONTH_BY_AREA_TITLE)
        area_bars(canvas, CARD_PADDING, _BARS_TOP, COLUMN_C_INNER, rows)

    def _draw_balance_card(self, parent: tk.Misc, month: MonthStats) -> None:
        legend = chart_rows.donut_legend_rows(month)
        center_x, center_y = CARD_PADDING + _DONUT_RADIUS, 60 + _DONUT_RADIUS
        # The taller of the donut's edge and a long legend decides the bottom.
        height = (
            max(
                center_y + _DONUT_RADIUS + 8,
                center_y + len(legend) * _DONUT_LEGEND_STEP / 2,
            )
            + 18
        )
        canvas = self._card(parent, COLUMN_C_WIDTH, height)
        self._card_title(canvas, texts.MONTH_BALANCE_TITLE)
        self._card_note(canvas, texts.MONTH_BALANCE_NOTE)

        balance_donut(
            canvas, center_x, center_y, _DONUT_RADIUS, _DONUT_THICKNESS,
            chart_rows.donut_segments(month), month.total, number_size=21,
        )  # fmt: skip
        # The legend goes on the right, centered on the donut.
        donut_legend(
            canvas,
            CARD_PADDING + _DONUT_LEGEND_OFFSET,
            center_y - len(legend) * _DONUT_LEGEND_STEP / 2,
            COLUMN_C_INNER - _DONUT_LEGEND_OFFSET,
            legend,
            step=_DONUT_LEGEND_STEP,
        )

    def _draw_pace_card(self, parent: tk.Misc, month: MonthStats, today: date) -> None:
        canvas = self._card(parent, COLUMN_C_WIDTH, _PACE_TOP + _PACE_HEIGHT + 14, last=True)
        self._card_title(canvas, texts.MONTH_PACE_TITLE)
        self._card_note(canvas, texts.MONTH_PACE_NOTE)
        month_pace(
            canvas, CARD_PADDING, _PACE_TOP, COLUMN_C_INNER, month.counts_by_day,
            chart_rows.pace_maximum(month), today.day,
        )  # fmt: skip

    # ---------- 4. The consistency map across the page ----------

    def _draw_consistency_card(self, today: date, month: MonthStats) -> None:
        rows = chart_rows.consistency_rows(self.service.areas(), month)
        days = calendar.monthrange(today.year, today.month)[1]

        # The exact height is known only after the map is drawn, so the canvas starts with
        # an estimate and is adjusted afterwards.
        canvas = new_canvas(
            self.page,
            PAGE_WIDTH,
            _MAP_TOP
            + max(len(rows), 1) * _MAP_ROW_STEP
            + _MAP_LEGEND_HEIGHT
            + _MAP_BOTTOM_PADDING,
            palette.BACKGROUND,
        )
        canvas.pack(pady=(0, 40))

        title_font = font("serif", 16, master=canvas)
        canvas.create_text(
            CARD_PADDING,
            24,
            anchor="w",
            text=texts.MONTH_CONSISTENCY_TITLE,
            font=title_font,
            fill=palette.INK_TITLE,
        )
        canvas.create_text(
            CARD_PADDING + measure(title_font, texts.MONTH_CONSISTENCY_TITLE) + 12,
            25,
            anchor="w",
            text=texts.MONTH_CONSISTENCY_NOTE,
            font=font("script", 13, master=canvas),
            fill=palette.LILAC,
        )

        if rows:
            map_height = consistency_map(
                canvas, CARD_PADDING, _MAP_TOP, PAGE_WIDTH - 2 * CARD_PADDING, rows, days,
                label_width=_MAP_LABEL_WIDTH, row_step=_MAP_ROW_STEP, gap=_MAP_GAP,
                with_legend=True, icon_radius=_MAP_ICON_RADIUS,
            )  # fmt: skip
        else:
            canvas.create_text(
                PAGE_WIDTH / 2,
                _MAP_TOP + 20,
                text=texts.NO_HABITS_TO_SHOW,
                font=font("sans", 10, master=canvas),
                fill=palette.MUTED_LIGHT,
            )
            map_height = _MAP_EMPTY_HEIGHT

        # Now the background can be painted with the real height and sent behind everything.
        height = _MAP_TOP + map_height + _MAP_BOTTOM_PADDING
        canvas.configure(height=height)
        background = rounded_rect(
            canvas, 1, 1, PAGE_WIDTH - 1, height - 1, CARD_RADIUS,
            fill=palette.PAPER, outline=palette.BORDER,
        )  # fmt: skip
        canvas.tag_lower(background)
