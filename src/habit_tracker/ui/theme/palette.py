"""Every color of the interface. Views never write hex values by hand.

Text colors reach a contrast of 4.5 : 1 on the surfaces they are drawn on (WCAG 2.2, success
criterion 1.4.3), which ``tests/unit/ui/test_contrast.py`` checks. Hierarchy between primary and
secondary text comes from size and weight, not from lighter grays.
"""

WHITE = "#ffffff"
BLACK = "#000000"

# Surfaces
BACKGROUND = "#efe6ee"  # page background of the dashboard; windows are painted with PAPER
PAPER = "#fffdfb"  # cards and surfaces
BORDER = "#e7dced"  # card border
LILAC = "#a98fd0"  # main accent
LILAC_SOFT = "#efe7f4"  # pale accent: ring track, today's cell
FOCUS_RING = "#917bb3"  # keyboard focus ring: 3 : 1 on every surface (WCAG 1.4.11)

# Text
INK = "#574d63"  # body text
INK_TITLE = "#5b5470"  # serif titles
SECONDARY_TEXT = "#6d6480"  # the gray of every secondary text
MUTED = SECONDARY_TEXT  # secondary text
MUTED_LIGHT = SECONDARY_TEXT  # hints and tertiary text
MUTED_DARK = SECONDARY_TEXT  # legend text
ACCENT_TEXT = "#6d6389"  # lilac-tinted text: ring number, today, soft lilac buttons
RING_TEXT = ACCENT_TEXT  # number inside the progress ring

WEEKDAY_HEADER = SECONDARY_TEXT
ROW_BACKGROUND = "#faf7fc"  # habit row that is not checked

# Calendar
CELL_PAST = "#fdfbfe"
CELL_BORDER = "#f1ecf5"
CELL_FUTURE = "#faf8fc"
NUMBER_PAST = SECONDARY_TEXT
NUMBER_FUTURE = SECONDARY_TEXT
NUMBER_TODAY = ACCENT_TEXT

# Tabs
TAB_ACTIVE_BACKGROUND = PAPER
TAB_ACTIVE_TEXT = INK_TITLE
TAB_INACTIVE_BACKGROUND = "#f7f1f8"
TAB_INACTIVE_TEXT = SECONDARY_TEXT

# Soft buttons
BUTTON_LILAC_BACKGROUND = "#f3eef7"
BUTTON_LILAC_TEXT = ACCENT_TEXT
BUTTON_PINK_BACKGROUND = "#faf6f4"
BUTTON_PINK_TEXT = "#8a6966"

# Priority card
PEACH_BACKGROUND = "#fdeede"
PEACH_BORDER = "#f6d3b8"
PEACH_LABEL = "#946240"
PEACH_INK = "#7a5365"
PEACH_BUTTON = "#ef9a6e"
PEACH_NOTE = "#856752"  # handwritten note on the card

# Important-date flags
FLAG = "#e07a93"
FLAG_POLE = "#c98aa0"

# Date chips of the dashboard (e.g. "12 JUN")
DATE_CHIP_BACKGROUND = "#fbe9ee"
DATE_CHIP_DAY = "#a5516b"
DATE_CHIP_MONTH = "#875f6d"

# Delete mode: selection box and trash can in each of its states
TRASH_REST = BUTTON_PINK_TEXT  # resting trash can
TRASH_HOVER_BACKGROUND = "#fdf0f2"  # background under the pointer
TRASH_ACTIVE = FLAG  # marked for deletion
TRASH_ACTIVE_BACKGROUND = DATE_CHIP_BACKGROUND  # background of a marked row
TRASH_INACTIVE = "#cfc6d4"  # visible but not responding

# Consistency map
HEAT_NOT_DUE = "#f6f3f8"
HEAT_FUTURE = "#f4eff8"
HEAT_FUTURE_BORDER = "#e2d8ec"

# Month pace bars: past days (today is drawn in LILAC)
PACE_BAR = "#cdbce6"

# Dashboard number accents
ACCENT_STREAK = "#ef9a6e"
ACCENT_TOTAL = "#8cc185"

# Color of an area that is not in the list of areas
NEUTRAL_AREA_COLOR = "#b4aabf"
