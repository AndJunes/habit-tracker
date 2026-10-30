"""Measurement units offered by the form, by life area."""

from collections.abc import Mapping

# Keyed by the area ids that the data stores (see ``seed.default_areas``). Any other unit
# can be typed with CUSTOM_UNIT.
UNITS_BY_AREA: Mapping[str, tuple[str, ...]] = {
    "salud": ("vasos", "litros", "minutos", "horas", "sesiones", "pasos"),
    "carrera": ("minutos", "horas", "páginas", "ejercicios", "tareas", "postulaciones"),
    "finanzas": ("pesos", "operaciones", "días"),
    "relaciones": ("llamadas", "encuentros", "actividades", "minutos"),
    "crecimiento": ("páginas", "minutos", "horas", "sesiones"),
    "experiencias": ("actividades", "lugares", "experiencias"),
    "proposito": ("minutos", "sesiones", "acciones"),
    "estilo_vida": ("tareas", "minutos", "habitaciones", "sesiones"),
}

# For an area that has no list of its own.
GENERIC_UNITS: tuple[str, ...] = ("veces", "unidades")

# A habit measured by duration is always counted in one of these.
DURATION_UNITS: tuple[str, ...] = ("minutos", "horas")

# The last option of the unit menu: the person writes the unit.
CUSTOM_UNIT = "personalizada"
