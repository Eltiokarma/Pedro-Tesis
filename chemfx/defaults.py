"""Defaults de allow_reactions por tipo de equipo (§4.5).

Determina si un bloque del flowsheet permite reacciones por default
al crearse. El usuario puede sobreescribir desde el dialog de
propiedades del bloque.

Filosofia (decision D09 — Filosofia B): toggle por equipo + asistente
proactivo. Reactores y absorbedores nacen con allow_reactions=True
(asumimos que el user los puso ahi para reaccionar). Mezcladores,
flashes, intercambiadores, tanques, bombas y compresores nacen en
False — pero el asistente puede sugerir activarlos si detecta
combinacion reactiva, T/P alta, o τ suficiente.

Equipos no listados → default False (conservador).
"""

ALLOW_REACTIONS_DEFAULTS = {
    # Reactores — SIEMPRE
    "Reactor — autoclave":               True,
    "Reactor — jacketed agitated":       True,
    "Reactor — jacketed non-agit.":      True,
    "Reactor — PFR (tubular)":           True,
    "Reactor — CSTR (agitado)":          True,

    # Columnas reactivas (cuando se etiqueten como tal en el catalogo)
    "Tower (column shell) — reactive":   True,
    "Tower (column shell) — distillation": False,  # asistente puede sugerir

    # Absorbers — si (siempre tienen MDEA o reactivo absorbente)
    "Absorber column":                   True,
    "Stripper column":                   True,

    # Mezcladores — no, pero asistente vigila
    "Mixer — static":                    False,
    "Mixer — dynamic":                   False,

    # Flashes / Vessels — no
    "Vessel — vertical":                 False,
    "Vessel — horizontal":               False,

    # Intercambiadores — no
    "Heat exch. — shell and tube":       False,
    "Heat exch. — floating head":        False,
    "Heat exch. — U-tube":               False,
    "Heat exch. — fixed tube":           False,
    "Heat exch. — flat plate":           False,
    "Heat exch. — multiple pipe":        False,
    "Heat exch. — double pipe":          False,
    "Heat exch. — spiral plate":         False,
    "Heat exch. — air cooler":           False,
    "Heat exch. — kettle reboiler":      False,
    "Heat exch. — plate":                False,

    # Hornos — solo SMR pre-activo (T y diseño para reformar)
    "Fired heater — non-reformer":       False,
    "Fired heater — reformer":           True,
    "Fired heater — reformer SMR":       True,

    # Tanques — no
    "Storage tank — cone roof":          False,
    "Storage tank — floating roof":      False,
    "Storage tank — sphere":             False,

    # Bombas — no
    "Pump — centrifugal":                False,
    "Pump — positive displacement":      False,

    # Compresores — no (asistente vigila T post-compresion)
    "Compressor — centrifugal":          False,
    "Compressor — reciprocating":        False,
    "Compressor — axial":                False,
}


def default_allow_reactions(eq_type: str) -> bool:
    """Devuelve el default de allow_reactions para un tipo de equipo.
    Conservador: si el tipo no esta listado, default False."""
    return ALLOW_REACTIONS_DEFAULTS.get(eq_type, False)
