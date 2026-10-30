"""The live preview: the habit's row as it will look in a list, and the habit in a sentence."""

import tkinter as tk

from ..theme import palette
from ..theme.drawing import area_color_or_default, area_icon, rounded_rect, soft_color_of
from ..theme.fonts import font
from . import texts
from .form_state import FormState
from .parts import FORM_WIDTH, LABEL_SIZE, prompt

PREVIEW_TOP_GAP = 18
ROW_HEIGHT = 64
ROW_MARGIN = 2
ROW_RADIUS = 14
ICON_CENTER = 32
ICON_RADIUS = 17
TEXT_X = 60
TITLE_Y = 24
DETAIL_Y = 42
SENTENCE_TOP_GAP = 6
UNKNOWN_AREA_ICON = "sun"  # any id that is not an area's gets the sun glyph

_TITLE_SIZE = 12
_DETAIL_SIZE = 9


class PreviewSection:
    """Redraws the preview row and the sentence from the state each time it is asked to."""

    def __init__(self, body: tk.Frame, state: FormState) -> None:
        self._state = state
        prompt(body, texts.PREVIEW_PROMPT, top=PREVIEW_TOP_GAP)
        self._canvas = tk.Canvas(
            body, width=FORM_WIDTH, height=ROW_HEIGHT, bg=palette.PAPER, highlightthickness=0
        )
        self._canvas.pack(anchor="w")
        self._sentence = tk.Label(
            body,
            text="",
            bg=palette.PAPER,
            fg=palette.MUTED_DARK,
            font=font("sans", LABEL_SIZE, master=body),
            wraplength=FORM_WIDTH,
            justify="left",
            name="preview_sentence",
        )
        self._sentence.pack(anchor="w", pady=(SENTENCE_TOP_GAP, 0))

    def refresh(self) -> None:
        row = self._state.preview_row()
        canvas = self._canvas
        canvas.delete("all")
        rounded_rect(
            canvas,
            ROW_MARGIN,
            ROW_MARGIN,
            FORM_WIDTH - ROW_MARGIN,
            ROW_HEIGHT - ROW_MARGIN,
            ROW_RADIUS,
            fill=soft_color_of(row.area),
            outline="",
        )
        area_icon(
            canvas,
            cx=ICON_CENTER,
            cy=ICON_CENTER,
            radius=ICON_RADIUS,
            area_id=row.area.id if row.area else UNKNOWN_AREA_ICON,
            color=area_color_or_default(row.area),
        )
        canvas.create_text(
            TEXT_X,
            TITLE_Y,
            anchor="w",
            text=row.title,
            font=font("sans", _TITLE_SIZE, "bold", master=canvas),
            fill=palette.INK,
        )
        canvas.create_text(
            TEXT_X,
            DETAIL_Y,
            anchor="w",
            text=row.detail,
            font=font("sans", _DETAIL_SIZE, master=canvas),
            fill=palette.MUTED_DARK,
        )
        self._sentence.configure(text=self._state.preview_sentence())
