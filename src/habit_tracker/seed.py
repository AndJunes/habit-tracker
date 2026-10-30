"""Data the application starts with on its first run.

Area names are display text and use the language of the interface.
"""

from .domain.models import Area


def default_areas() -> list[Area]:
    """The eight life areas offered before the person has saved anything.

    A new list is returned on every call, so callers may modify it freely.
    """
    return [
        Area("salud", "Salud", "#65a882", "#e3efe8"),
        Area("carrera", "Carrera", "#6488d8", "#e3eaf8"),
        Area("finanzas", "Finanzas", "#e6b84c", "#faf2df"),
        Area("relaciones", "Relaciones", "#e78ba6", "#fbeaef"),
        Area("crecimiento", "Crecimiento", "#a58adb", "#efeaf9"),
        Area("experiencias", "Experiencias", "#e99a65", "#fbede3"),
        Area("proposito", "Propósito", "#56b8b0", "#e1f2f1"),
        Area("estilo_vida", "Estilo de vida", "#8493a8", "#e9ecef"),
    ]
