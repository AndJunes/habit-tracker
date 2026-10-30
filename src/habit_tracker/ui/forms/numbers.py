"""Reading and writing the numbers people type into the form."""

import math


def parse_number(text: str) -> int | float | None:
    """``"12"``, ``"12,5"`` or ``"12.5"`` as a number; ``None`` when it is not a finite one.

    Both decimal separators are accepted. A whole number comes back as an ``int``
    so that it is stored and shown without a trailing ``.0``.
    """
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return int(value) if value.is_integer() else value


def format_number(value: float) -> str:
    """``10`` and ``10.0`` become ``"10"``, ``2.5`` stays ``"2.5"``: to fill fields and labels."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
