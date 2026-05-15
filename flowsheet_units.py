"""
FLOWSHEET UNITS — conversión de unidades de flujo másico para la UI.

El modelo guarda mass_flow internamente en **tm/año** (siempre).
Para mostrar valores en la UI, convertimos hacia/desde esta unidad
canónica.

API:
  FLOW_UNITS                       lista de (clave, label) en orden de menú
  to_display(value_tm_yr, unit)    tm/año → unidad de display
  from_display(value, unit)        unidad de display → tm/año
  format_flow(value_tm_yr, unit)   string para UI (ej "11.000 tm/año")

Unidades soportadas (sin requerir peso molecular):

    tm/año    tonelada métrica por año            (1)
    kg/h      kilogramo por hora                  (1000/8760)
    kg/s      kilogramo por segundo               (1000/(8760·3600))
    t/d       tonelada por día                    (1/365)
    lb/h      libra por hora                      (2204.62/8760)

Para soportar kmol/hr o flujo en moles habría que extender Stream
con peso molecular del fluido — out of scope.

OPERACIÓN
  asumimos operación continua 8760 h/año (factor de servicio 100%).
  Si el proyecto define operating_hours_per_year en el flowsheet,
  ese override aplica.  Hoy usamos 8760 fijo.
"""

HOURS_PER_YEAR = 8760.0
SEC_PER_YEAR   = HOURS_PER_YEAR * 3600.0


# Factor de conversión: tm/año × factor = unidad_display
# inverso: unidad_display / factor = tm/año
FLOW_FACTORS = {
    "tm/año":  1.0,
    "kg/h":    1000.0 / HOURS_PER_YEAR,
    "kg/s":    1000.0 / SEC_PER_YEAR,
    "t/d":     1.0 / 365.0,
    "lb/h":    2204.6226 / HOURS_PER_YEAR,
}

# Orden de aparición en menús
FLOW_UNITS_ORDER = ["tm/año", "kg/h", "kg/s", "t/d", "lb/h"]


def to_display(value_tm_yr, unit):
    """tm/año (modelo) → valor en la unidad de display."""
    if unit not in FLOW_FACTORS:
        return value_tm_yr
    return float(value_tm_yr) * FLOW_FACTORS[unit]


def from_display(value, unit):
    """unidad de display → tm/año (modelo)."""
    if unit not in FLOW_FACTORS or FLOW_FACTORS[unit] == 0:
        return float(value)
    return float(value) / FLOW_FACTORS[unit]


def format_flow(value_tm_yr, unit):
    """String formateado para UI.  Usa formato adecuado según la
    magnitud de la unidad."""
    v = to_display(value_tm_yr, unit)
    if unit == "kg/s":
        return f"{v:.3g} {unit}"
    if abs(v) < 1:
        return f"{v:.3g} {unit}"
    if abs(v) < 100:
        return f"{v:.2f} {unit}"
    if abs(v) < 100_000:
        return f"{v:,.0f} {unit}"
    return f"{v:.3e} {unit}"
