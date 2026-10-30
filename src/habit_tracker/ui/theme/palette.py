"""Every color of the interface. Views never write hex values by hand."""

WHITE = "#ffffff"
BLACK = "#000000"

# Surfaces
BACKGROUND = "#efe6ee"  # page background of the dashboard; windows are painted with PAPER
PAPER = "#fffdfb"  # cards and surfaces
BORDER = "#e7dced"  # card border
LILAC = "#a98fd0"  # main accent
LILAC_SOFT = "#efe7f4"  # pale accent: ring track, today's cell

# Text
INK = "#574d63"  # body text
INK_TITLE = "#5b5470"  # serif titles
MUTED = "#9a90b8"  # secondary text
MUTED_LIGHT = "#a99ec0"  # tertiary text and hints
MUTED_DARK = "#7a7090"  # legend text
RING_TEXT = "#7a6f9a"  # number inside the progress ring

WEEKDAY_HEADER = "#b7add0"
ROW_BACKGROUND = "#faf7fc"  # habit row that is not checked

# Calendar
CELL_PAST = "#fdfbfe"
CELL_BORDER = "#f1ecf5"
CELL_FUTURE = "#faf8fc"
NUMBER_PAST = "#8a809e"
NUMBER_FUTURE = "#c3b9d6"
NUMBER_TODAY = "#7a6f9a"

# Tabs
TAB_ACTIVE_BACKGROUND = PAPER
TAB_ACTIVE_TEXT = INK_TITLE
TAB_INACTIVE_BACKGROUND = "#f7f1f8"
TAB_INACTIVE_TEXT = "#a99ec0"

# Soft buttons
BUTTON_LILAC_BACKGROUND = "#f3eef7"
BUTTON_LILAC_TEXT = "#7a6f9a"
BUTTON_PINK_BACKGROUND = "#faf6f4"
BUTTON_PINK_TEXT = "#b58a86"

# Priority card
PEACH_BACKGROUND = "#fdeede"
PEACH_BORDER = "#f6d3b8"
PEACH_LABEL = "#d08a5a"
PEACH_INK = "#7a5365"
PEACH_BUTTON = "#ef9a6e"
PEACH_NOTE = "#c79a7a"  # handwritten note on the card

# Important-date flags
FLAG = "#e07a93"
FLAG_POLE = "#c98aa0"

# Date chips of the dashboard (e.g. "12 JUN")
DATE_CHIP_BACKGROUND = "#fbe9ee"
DATE_CHIP_DAY = "#c25f7e"
DATE_CHIP_MONTH = "#d99ab0"

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
